import streamlit as st

from . import db, intake


def render():
    st.header("Report a civic issue")
    with st.form("submit", clear_on_submit=True):
        text = st.text_area("Describe the problem (English / தமிழ் / Tanglish)")
        address = st.text_input("Street / area / landmark in Chennai")
        photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"])
        audio = st.file_uploader("Voice note (optional)", type=["ogg", "mp3", "wav", "m4a"])
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude (optional)", value=0.0, format="%.6f")
        lon = c2.number_input("Longitude (optional)", value=0.0, format="%.6f")
        ok = st.form_submit_button("Submit")
    if ok:
        body = "\n".join(x for x in [text, f"Address: {address}" if address else ""] if x)
        media = mime = None
        f = photo or audio
        if f:
            media, mime = f.getvalue(), f.type
        if not body and not media:
            st.warning("Please add a description, photo or voice note.")
        else:
            c = intake.create_complaint("web", body or None, media, mime,
                                        lat=lat if lat else None, lon=lon if lon else None)
            st.success(f"Received. Your reference number is **{c['ref']}**. Use it below to track the reply.")

    st.subheader("Track a complaint")
    ref = st.text_input("Reference number (e.g. GC-AB12CD)").strip().upper()
    if ref:
        rows = db.sb().table("complaints").select("*").eq("ref", ref).execute().data
        if not rows:
            st.error("Not found.")
        else:
            c = rows[0]
            st.write(f"Status: **{c['status']}**" + (f" · {c['department']} · {c['ward']}" if c.get("department") else ""))
            if c.get("cluster_id"):
                cl = db.sb().table("clusters").select("status,draft_reply").eq("id", c["cluster_id"]).execute().data[0]
                if cl["status"] == "replied":
                    st.info(cl["draft_reply"])
