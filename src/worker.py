"""Background loop: poll Telegram, run the agent on new complaints. Run standalone with `python -m src.worker`
or let app.py start it in a thread."""
import time
from datetime import datetime, timedelta, timezone

from . import agent, db, telegram


def process_pending(limit=3):
    sb = db.sb()
    # recover rows stuck in 'processing' (crashed worker)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    sb.table("complaints").update({"status": "new"}).eq("status", "processing").lt("claimed_at", cutoff).execute()
    rows = sb.table("complaints").select("*").eq("status", "new").order("created_at").limit(limit).execute().data
    for c in rows:
        claimed = sb.table("complaints").update({"status": "processing", "claimed_at": datetime.now(timezone.utc).isoformat()}).eq("id", c["id"]).eq("status", "new").execute().data
        if not claimed:
            continue
        agent.process_complaint(c)
        after = sb.table("complaints").select("status,ref,chat_id,review_reason").eq("id", c["id"]).execute().data[0]
        if after["chat_id"]:
            if after["status"] == "rejected":
                telegram.send_message(after["chat_id"], telegram.REJECT_MSG)
            elif after["status"] == "review":
                telegram.send_message(after["chat_id"], f"{after['ref']}: we need a clearer location. Please share your "
                                      "location pin or the full street/area name. (இருப்பிடத்தைப் பகிரவும்)")


def run_forever():
    while True:
        try:
            telegram.poll_once(timeout=3)
        except Exception as e:
            print("poll error:", e)
            time.sleep(3)
        try:
            process_pending()
        except Exception as e:
            print("process error:", e)
            time.sleep(3)
        time.sleep(1)


if __name__ == "__main__":
    run_forever()
