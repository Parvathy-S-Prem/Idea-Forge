"""Tool-using triage agent: Gemini function-calling loop + persistence of the validated decision."""
from datetime import datetime, timedelta, timezone

import requests
from google.genai import types

from . import db, llm
from .departments import CATEGORIES
from .tools import DECLARATIONS, TOOLS, RunContext

MAX_STEPS = 10

SYSTEM = f"""You are the triage agent for a Greater Chennai Corporation (GCC) ward grievance cell.
You process ONE citizen complaint (text, photo, voice note and/or shared location; English, Tamil or Tanglish).
Work with tools; do not guess.

Procedure:
1. Understand the complaint (transcribe voice, read the photo). If it is a greeting, spam, abuse or not a civic issue,
   call submit_decision(status=rejected, reason=...) immediately.
2. Call locate. Use the shared pin if given (lat/lon), else a specific street/area/landmark query from the complaint.
   - Vague places ("near the temple", "our street") with no usable area, a photo with no location, a geocode with
     precision 'area_only', or in_gcc=false (e.g. Bengaluru) -> submit_decision(status=review, reason=...). NEVER guess a location.
3. Call find_similar with a one-sentence English summary. If a candidate is clearly the same issue at the same spot,
   set duplicate_of to its id. Different issues or different spots are NOT duplicates.
4. Decide the category and call route. Water supply failures and sewage belong to CMWSSB, not GCC.
   Categories: {', '.join(CATEGORIES)}.
5. Call submit_decision(status=registered, category, summary, ward (exactly as returned by locate), duplicate_of?,
   reply_language ('ta' if the citizen wrote/spoke Tamil or Tanglish, else 'en'), confidence 0-1, transcript if voice).
If submit_decision returns errors, fix them and call it again. Low confidence -> status=review."""

_DECL = types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in DECLARATIONS])
_CFG = types.GenerateContentConfig(
    system_instruction=SYSTEM,
    tools=[_DECL],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    temperature=0.1,
)


def _media_part(c):
    if not c.get("media_url"):
        return None
    try:
        data = requests.get(c["media_url"], timeout=20).content
        return types.Part.from_bytes(data=data, mime_type=c.get("media_mime") or "image/jpeg")
    except Exception:
        return None


def _initial_parts(c):
    desc = [f"Complaint ref {c['ref']} via {c['source']}.", f"Text: {c.get('raw_text') or '(none)'}"]
    if c.get("lat") is not None:
        desc.append(f"Shared location pin: lat={c['lat']}, lon={c['lon']}")
    else:
        desc.append("No shared location pin.")
    parts = [types.Part.from_text(text="\n".join(desc))]
    m = _media_part(c)
    if m:
        parts.append(m)
    return parts


def run_agent(c: dict) -> RunContext:
    ctx = RunContext(complaint=c)
    contents = [types.Content(role="user", parts=_initial_parts(c))]
    for step in range(1, MAX_STEPS + 1):
        resp = llm.generate(contents, _CFG)
        if not resp.candidates or not resp.candidates[0].content:
            break
        cand = resp.candidates[0].content
        contents.append(cand)
        calls = [p.function_call for p in (cand.parts or []) if p.function_call]
        if not calls:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="You must finish by calling submit_decision.")]))
            continue
        out = []
        for fc in calls:
            args = dict(fc.args or {})
            fn = TOOLS.get(fc.name)
            try:
                result = fn(ctx, **args) if fn else {"error": f"unknown tool {fc.name}"}
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            db.log_step(c["id"], step, fc.name, args, result)
            out.append(types.Part.from_function_response(name=fc.name, response=result))
        contents.append(types.Content(role="user", parts=out))
        if ctx.decision:
            break
    return ctx


def _apply(c, ctx):
    d = ctx.decision
    now = datetime.now(timezone.utc)
    upd = {"processed_at": now.isoformat(), "status": d["status"], "transcript": d.get("transcript"),
           "confidence": d.get("confidence")}
    sb = db.sb()
    if d["status"] != "registered":
        upd["review_reason"] = d.get("reason")
        if d["status"] == "review" and ctx.lat is not None:
            upd.update(lat=ctx.lat, lon=ctx.lon)
        sb.table("complaints").update(upd).eq("id", c["id"]).execute()
        return
    cat = CATEGORIES[d["category"]]
    upd.update(category=d["category"], department=cat["department"], sla_hours=cat["sla_hours"], ward=ctx.ward,
               zone=ctx.zone, summary=d["summary"], reply_language=d["reply_language"], lat=ctx.lat, lon=ctx.lon,
               embedding=ctx.embedding)
    dup = d.get("duplicate_of")
    if dup:
        cl_id = ctx.candidates[dup]["cluster_id"]
        cl = sb.table("clusters").select("report_count").eq("id", cl_id).execute().data[0]
        sb.table("clusters").update({"report_count": cl["report_count"] + 1}).eq("id", cl_id).execute()
    else:
        created = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
        draft = ""
        try:
            draft = llm.draft_reply(c["ref"], d["summary"], cat["department"], cat["sla_hours"], d["reply_language"])
        except Exception as e:
            draft = f"[draft failed: {e}] Please write the reply manually."
        cl_id = sb.table("clusters").insert({
            "ref": c["ref"], "ward": ctx.ward, "zone": ctx.zone, "category": d["category"],
            "department": cat["department"], "summary": d["summary"], "lat": ctx.lat, "lon": ctx.lon,
            "due_at": (created + timedelta(hours=cat["sla_hours"])).isoformat(),
            "draft_reply": draft, "reply_language": d["reply_language"],
        }).execute().data[0]["id"]
    upd["cluster_id"] = cl_id
    sb.table("complaints").update(upd).eq("id", c["id"]).execute()


def process_complaint(c: dict):
    """Never raises: any failure parks the complaint in the review queue instead of losing it."""
    try:
        ctx = run_agent(c)
        if not ctx.decision:
            ctx.decision = {"status": "review", "reason": "Agent did not produce a valid decision - needs human triage"}
        _apply(c, ctx)
    except Exception as e:
        db.log_step(c["id"], 99, "error", {}, {"error": f"{type(e).__name__}: {e}"})
        db.sb().table("complaints").update({"status": "review", "review_reason": f"Processing error: {e}"[:300]}) \
            .eq("id", c["id"]).execute()
