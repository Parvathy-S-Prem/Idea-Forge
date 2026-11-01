import threading

import streamlit as st

st.set_page_config(page_title="Grievance Desk Co-pilot", page_icon="📋", layout="wide")

from src import config, worker  # noqa: E402
from src import ui_context, ui_desk, ui_submit  # noqa: E402


@st.cache_resource
def start_worker():
    t = threading.Thread(target=worker.run_forever, daemon=True, name="gdc-worker")
    t.start()
    return t


start_worker()  # Telegram polling + agent runs, once per server process

page = st.sidebar.radio("Page", ["Officer desk", "Submit / track (citizen)", "Government context"])
st.sidebar.caption("Telegram bot and this form feed the same desk.")

if page == "Submit / track (citizen)":
    ui_submit.render()
elif page == "Government context":
    ui_context.render()
else:
    if not st.session_state.get("auth"):
        pw = st.text_input("Officer password", type="password")
        if pw and pw == config.get("DESK_PASSWORD"):
            st.session_state["auth"] = True
            st.rerun()
        elif pw:
            st.error("Wrong password")
    else:
        ui_desk.render()
