from functools import lru_cache

from supabase import create_client

from . import config


@lru_cache(maxsize=1)
def sb():
    return create_client(config.get("SUPABASE_URL"), config.get("SUPABASE_SERVICE_KEY"))


def log_step(complaint_id, step, tool, args, result):
    try:
        sb().table("agent_log").insert(
            {"complaint_id": complaint_id, "step": step, "tool": tool, "args": args, "result": result}
        ).execute()
    except Exception as e:  # logging must never break processing
        print("log_step failed:", e)


def get_setting(key, default=None):
    r = sb().table("settings").select("value").eq("key", key).execute().data
    return r[0]["value"] if r else default


def set_setting(key, value):
    sb().table("settings").upsert({"key": key, "value": str(value)}).execute()
