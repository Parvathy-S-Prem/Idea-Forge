import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default=None):
    """Env var first, then Streamlit secrets (for Streamlit Cloud)."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


GEMINI_MODEL = get("GEMINI_MODEL", "gemini-2.5-flash")
