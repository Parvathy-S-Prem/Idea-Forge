from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from . import db, telegram
from .departments import CATEGORIES, ORANGE_FRACTION


def _now():
    return datetime.now(timezone.utc)


def _flag(cl):
    """(colour, label, sort_key) for a cluster based on its SLA window."""
    due = datetime.fromisoformat(cl["due_at"].replace("Z", "+00:00"))
    created = datetime.fromisoformat(cl["created_at"].replace("Z", "+00:00"))
    left = (due - _now()).total_seconds()
    total = max((due - created).total_seconds(), 1)
    if left < 0:
        return "🔴", f"OVERDUE by {abs(left)/3600:.1f}h", left
    if left / total < 1 - ORANGE_FRACTION:
        return "🟠", f"{left/3600:.1f}h left", left
    return "🟢", f"{left/3600:.1f}h left", left


def _trace(complaint_ids):
    logs = db.sb().table("agent_log").select("*").in_("complaint_id", complaint_ids).order("id").execute().data
    for l in logs:
        st.markdown(f"**{l['step']}. `{l['tool']}`**")
        st.json({"args": l["args"], "result": l["result"]}, expanded=False)


def _send_to_cluster(cl, text):
    members = db.sb().table("complaints").select("id,ref,chat_id").eq("cluster_id", cl["id"]).execute().data
    sent = 0
    for m in members:
        if m["chat_id"]:
            telegram.send_message(m["chat_id"], f"{text}\n\nRef: {m['ref']}")
            sent += 1
    db.sb().table("clusters").update({"status": "replied", "draft_reply": text, "replied_at": _now().isoformat()}) \
        .eq("id", cl["id"]).execute()
    db.sb().table("complaints").update({"status": "replied"}).eq("cluster_id", cl["id"]).execute()
    return sent, len(members)


def _queue():
    cls = db.sb().table("clusters").select("*").eq("status", "open").execute().data
    flagged = sorted(((_flag(c), c) for c in cls), key=lambda x: x[0][2])
    if not flagged:
        st.info("No open clusters yet. Send a complaint via Telegram or the web form.")
    for (icon, label, _), cl in flagged:
        n = f" · x{cl['report_count']} reports" if cl["report_count"] > 1 else ""
        with st.expander(f"{icon} {cl['ref']} · {CATEGORIES[cl['category']]['label']} · {cl['ward']}{n} · {label}"):
            st.write(f"**{cl['summary']}**")
            st.caption(f"{cl['department']} · {cl['zone']} · due {cl['due_at'][:16]}")
            members = db.sb().table("complaints").select("id,ref,raw_text,media_url,media_mime,source") \
                .eq("cluster_id", cl["id"]).execute().data
            for m in members:
                st.caption(f"{m['ref']} ({m['source']}): {m['raw_text'] or '(media only)'}")
                if m["media_url"] and (m["media_mime"] or "").startswith("image"):
                    st.image(m["media_url"], width=240)
                elif m["media_url"]:
                    st.audio(m["media_url"])
            text = st.text_area(f"Draft reply ({cl['reply_language']})", cl["draft_reply"] or "", key=f"d{cl['id']}", height=130)
            if st.button("Approve and send", key=f"s{cl['id']}", type="primary"):
                sent, total = _send_to_cluster(cl, text)
                st.success(f"Sent to {sent} Telegram chat(s); {total - sent} web-form complaint(s) can view it by reference.")
                st.rerun()
            with st.popover("Agent trace"):
                _trace([m["id"] for m in members])


def _review():
    rows = db.sb().table("complaints").select("*").eq("status", "review").order("created_at", desc=True).execute().data
    if not rows:
        st.info("Review queue is empty.")
    for c in rows:
        with st.expander(f"{c['ref']} · {c['review_reason'] or 'needs review'}"):
            st.write(c["raw_text"] or "(media only)")
            if c["media_url"] and (c["media_mime"] or "").startswith("image"):
                st.image(c["media_url"], width=240)
            elif c["media_url"]:
                st.audio(c["media_url"])
            c1, c2, c3 = st.columns([2, 2, 1])
            lat = c1.number_input("Lat", value=float(c["lat"] or 0), format="%.6f", key=f"la{c['id']}")
            lon = c2.number_input("Lon", value=float(c["lon"] or 0), format="%.6f", key=f"lo{c['id']}")
            if c3.button("Re-run agent", key=f"r{c['id']}") and lat and lon:
                db.sb().table("complaints").update({"lat": lat, "lon": lon, "status": "new", "review_reason": None}) \
                    .eq("id", c["id"]).execute()
                st.rerun()
            with st.popover("Agent trace"):
                _trace([c["id"]])


def _map():
    cls = db.sb().table("clusters").select("lat,lon,report_count").execute().data
    df = pd.DataFrame([c for c in cls if c["lat"] is not None])
    if df.empty:
        st.info("Nothing to plot yet.")
    else:
        st.map(df.rename(columns={"lon": "longitude", "lat": "latitude"}), size=60)


@st.fragment(run_every=10)
def render():
    st.title("Grievance Desk Co-pilot")
    cls = db.sb().table("clusters").select("due_at,created_at,status").eq("status", "open").execute().data
    over = sum(1 for c in cls if _flag(c)[2] < 0)
    rev = db.sb().table("complaints").select("id", count="exact").eq("status", "review").execute().count
    busy = db.sb().table("complaints").select("id", count="exact").in_("status", ["new", "processing"]).execute().count
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open clusters", len(cls))
    m2.metric("Overdue", over)
    m3.metric("Needs review", rev)
    m4.metric("Processing", busy)
    t1, t2, t3 = st.tabs(["Queue", "Review", "Map"])
    with t1:
        _queue()
    with t2:
        _review()
    with t3:
        _map()
