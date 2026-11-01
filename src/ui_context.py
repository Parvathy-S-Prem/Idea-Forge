import pandas as pd
import requests
import streamlit as st

from . import config


def render():
    st.header("Government grievance context - Tamil Nadu (data.gov.in, CPGRAMS)")
    key, rid = config.get("DATA_GOV_API_KEY"), config.get("DATA_GOV_RESOURCE_ID")
    if not key or not rid:
        st.warning("Set DATA_GOV_API_KEY and DATA_GOV_RESOURCE_ID (the CPGRAMS state-wise resource id from data.gov.in).")
        return
    try:
        r = requests.get(f"https://api.data.gov.in/resource/{rid}",
                         params={"api-key": key, "format": "json", "limit": 500}, timeout=20)
        r.raise_for_status()
        df = pd.DataFrame(r.json().get("records", []))
    except Exception as e:
        st.error(f"data.gov.in unavailable: {e}")
        return
    state_col = next((c for c in df.columns if "state" in c.lower()), None)
    if state_col:
        tn = df[df[state_col].astype(str).str.contains("tamil", case=False)]
        df = tn if not tn.empty else df
    st.dataframe(df, use_container_width=True)
    st.caption("Source: data.gov.in CPGRAMS state-wise dataset (live API).")
