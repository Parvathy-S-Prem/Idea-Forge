"""Agent tools: locate, find_similar, route, submit_decision. Each returns a JSON-able dict."""
from dataclasses import dataclass, field

import requests

from . import db, llm, wards
from .departments import CATEGORIES

NOMINATIM = "https://nominatim.openstreetmap.org/search"
SIM_THRESHOLD = 0.72


@dataclass
class RunContext:
    complaint: dict
    lat: float | None = None
    lon: float | None = None
    ward: str | None = None
    zone: str | None = None
    precision: str | None = None
    located: bool = False
    similar_called: bool = False
    candidates: dict = field(default_factory=dict)  # complaint_id -> candidate row
    embedding: list | None = None
    routed: str | None = None
    decision: dict | None = None


def locate(ctx: RunContext, query: str = "", lat: float | None = None, lon: float | None = None) -> dict:
    precision = "pin"
    if lat is None or lon is None:
        if ctx.complaint.get("lat") is not None and not query.strip():
            lat, lon = ctx.complaint["lat"], ctx.complaint["lon"]
        elif query.strip():
            try:
                r = requests.get(
                    NOMINATIM,
                    params={
                        "q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in",
                        "viewbox": "80.05,13.30,80.36,12.80",  # bias (not bound) towards Chennai
                    },
                    headers={"User-Agent": "GrievanceDeskCopilot/1.0 (hackathon prototype)"},
                    timeout=10,
                )
                res = r.json()
            except Exception as e:
                return {"found": False, "error": f"geocoder unavailable: {e}"}
            if not res:
                return {"found": False, "error": "no geocoding match for that query"}
            lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
            precision = "street" if int(res[0].get("place_rank", 0)) >= 26 else "area_only"
            matched = res[0].get("display_name")
        else:
            return {"found": False, "error": "no coordinates and no query - location unknown"}
    else:
        matched = "shared pin"
    if not wards.in_bbox(lat, lon):
        return {"found": True, "in_gcc": False, "lat": lat, "lon": lon, "note": "outside Chennai city bounds"}
    try:
        hit = wards.lookup(lat, lon)
    except Exception as e:
        return {"found": False, "error": str(e)}
    if hit is None:
        return {"found": True, "in_gcc": False, "lat": lat, "lon": lon, "note": "inside bbox but outside GCC ward polygons"}
    ctx.lat, ctx.lon, ctx.ward, ctx.zone, ctx.precision, ctx.located = lat, lon, hit["ward"], hit["zone"], precision, True
    return {"found": True, "in_gcc": True, "lat": lat, "lon": lon, "ward": hit["ward"], "zone": hit["zone"],
            "precision": precision, "matched": matched if precision != "pin" else "shared pin"}


def find_similar(ctx: RunContext, summary: str) -> dict:
    if not ctx.located:
        return {"error": "call locate first and get a ward; duplicates are only checked within a ward"}
    ctx.embedding = llm.embed(summary)
    rows = db.sb().rpc(
        "match_complaints",
        {"query_embedding": ctx.embedding, "p_ward": ctx.ward, "match_threshold": SIM_THRESHOLD, "match_count": 5},
    ).execute().data or []
    ctx.similar_called = True
    ctx.candidates = {r["id"]: r for r in rows}
    return {"ward": ctx.ward, "candidates": [
        {"id": r["id"], "ref": r["ref"], "summary": r["summary"], "category": r["category"],
         "similarity": round(r["similarity"], 3)} for r in rows]}


def route(ctx: RunContext, category: str) -> dict:
    c = CATEGORIES.get(category)
    if not c:
        return {"error": f"unknown category '{category}'", "valid": list(CATEGORIES)}
    ctx.routed = category
    return {"category": category, "department": c["department"], "sla_hours": c["sla_hours"], "body": c["body"]}


def submit_decision(ctx: RunContext, **d) -> dict:
    errs = []
    status = d.get("status")
    if status not in ("registered", "review", "rejected"):
        errs.append("status must be registered | review | rejected")
    if status in ("review", "rejected") and not d.get("reason"):
        errs.append("reason is required for review/rejected")
    if status == "registered":
        cat = d.get("category")
        if cat not in CATEGORIES:
            errs.append(f"category must be one of {list(CATEGORIES)}")
        elif ctx.routed != cat:
            errs.append(f"call route('{cat}') before registering with that category")
        if not ctx.located or not ctx.ward:
            errs.append("cannot register without a verified GCC ward from locate; use status=review")
        elif d.get("ward") != ctx.ward:
            errs.append(f"ward must equal the locate result '{ctx.ward}'")
        if not ctx.similar_called:
            errs.append("call find_similar before registering")
        dup = d.get("duplicate_of")
        if dup and dup not in ctx.candidates:
            errs.append("duplicate_of must be an id returned by find_similar in this run (do not invent ids)")
        if dup and dup in ctx.candidates and ctx.candidates[dup].get("category") != cat:
            errs.append("duplicate_of has a different category; it is not the same issue")
        if not d.get("summary"):
            errs.append("summary (English, one sentence) is required")
        if d.get("reply_language") not in ("ta", "en"):
            errs.append("reply_language must be 'ta' or 'en'")
        try:
            if float(d.get("confidence", 0)) < 0.5:
                errs.append("confidence below 0.5: use status=review instead of guessing")
        except (TypeError, ValueError):
            errs.append("confidence must be a number 0-1")
    if errs:
        return {"ok": False, "errors": errs}
    ctx.decision = d
    return {"ok": True}


TOOLS = {"locate": locate, "find_similar": find_similar, "route": route, "submit_decision": submit_decision}

DECLARATIONS = [
    {"name": "locate",
     "description": "Resolve the complaint location to coordinates, then to a GCC ward and zone. Pass a specific street/area/landmark "
                    "query, or lat/lon if given. Returns in_gcc, ward, zone and precision (pin|street|area_only).",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING", "description": "address or landmark with area, e.g. 'Anna Nagar 2nd Avenue, Chennai'"},
         "lat": {"type": "NUMBER"}, "lon": {"type": "NUMBER"}}}},
    {"name": "find_similar",
     "description": "Find open complaints in the same ward that may be the same issue. Needs a successful locate first.",
     "parameters": {"type": "OBJECT", "properties": {"summary": {"type": "STRING"}}, "required": ["summary"]}},
    {"name": "route",
     "description": "Map a category to its owning department and SLA hours.",
     "parameters": {"type": "OBJECT", "properties": {
         "category": {"type": "STRING", "enum": list(CATEGORIES)}}, "required": ["category"]}},
    {"name": "submit_decision",
     "description": "Final step. Validated; if rejected with errors, fix and call again.",
     "parameters": {"type": "OBJECT", "properties": {
         "status": {"type": "STRING", "enum": ["registered", "review", "rejected"]},
         "category": {"type": "STRING", "enum": list(CATEGORIES)},
         "summary": {"type": "STRING", "description": "one-sentence English summary"},
         "transcript": {"type": "STRING", "description": "verbatim transcription if a voice note"},
         "ward": {"type": "STRING"},
         "duplicate_of": {"type": "STRING", "description": "id from find_similar if same issue, else omit"},
         "reply_language": {"type": "STRING", "enum": ["ta", "en"]},
         "confidence": {"type": "NUMBER"},
         "reason": {"type": "STRING", "description": "why review/rejected"}},
         "required": ["status"]}},
]
