import requests

from . import config, db, intake

WELCOME = ("Namaste! I am the Chennai Corporation grievance bot. Describe a civic issue (garbage, pothole, drainage, "
           "streetlight, water supply) by text, photo or voice note (Tamil/English) and share your location pin or street name.\n"
           "வணக்கம்! குப்பை, சாலை, வடிகால், தெருவிளக்கு, குடிநீர் பிரச்சனைகளை எழுத்து/படம்/குரல் மூலம் அனுப்பவும்.")
REJECT_MSG = ("Please send a civic complaint (what, and where). Greetings and abusive messages are not registered.\n"
              "குடிமைப் புகார்களை மட்டும் அனுப்பவும் (என்ன, எங்கே).")


def _api(method, **params):
    tok = config.get("TELEGRAM_BOT_TOKEN")
    r = requests.post(f"https://api.telegram.org/bot{tok}/{method}", json=params, timeout=params.get("timeout", 0) + 15)
    r.raise_for_status()
    return r.json()["result"]


def send_message(chat_id, text):
    try:
        return _api("sendMessage", chat_id=chat_id, text=text)
    except Exception as e:
        print("telegram send failed:", e)


def _download(file_id):
    info = _api("getFile", file_id=file_id)
    tok = config.get("TELEGRAM_BOT_TOKEN")
    return requests.get(f"https://api.telegram.org/file/bot{tok}/{info['file_path']}", timeout=30).content


def _handle(msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text") or msg.get("caption")
    if text and text.strip().startswith("/start"):
        return send_message(chat_id, WELCOME)

    if "location" in msg:  # pin: attach to the chat's latest complaint awaiting a location, else a new one
        loc = msg["location"]
        waiting = (db.sb().table("complaints").select("id,ref").eq("chat_id", chat_id).eq("status", "review")
                   .order("created_at", desc=True).limit(1).execute().data)
        if waiting:
            db.sb().table("complaints").update({"lat": loc["latitude"], "lon": loc["longitude"], "status": "new",
                                                "review_reason": None}).eq("id", waiting[0]["id"]).execute()
            return send_message(chat_id, f"Location received for {waiting[0]['ref']}; re-checking.")
        c = intake.create_complaint("telegram", text, lat=loc["latitude"], lon=loc["longitude"], chat_id=chat_id)
        return send_message(chat_id, f"Received. Ref {c['ref']}. Please also describe the problem.")

    media = mime = None
    if "photo" in msg:
        media, mime = _download(msg["photo"][-1]["file_id"]), "image/jpeg"
    elif "voice" in msg:
        media, mime = _download(msg["voice"]["file_id"]), "audio/ogg"
    elif "audio" in msg:
        media, mime = _download(msg["audio"]["file_id"]), msg["audio"].get("mime_type", "audio/mpeg")
    if not text and not media:
        return send_message(chat_id, "Please send text, a photo, a voice note or a location pin.")
    c = intake.create_complaint("telegram", text, media, mime, chat_id=chat_id)
    send_message(chat_id, f"Received. Your reference number is {c['ref']}. We are processing it.\nபுகார் பெறப்பட்டது: {c['ref']}")


def poll_once(timeout=3):
    offset = int(db.get_setting("tg_offset", "0"))
    updates = _api("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
    for u in updates:
        try:
            if "message" in u:
                _handle(u["message"])
        except Exception as e:  # keep going; the offset still advances so one bad update can't wedge the bot
            print("update failed:", e)
        offset = u["update_id"] + 1
    if updates:
        db.set_setting("tg_offset", offset)
    return len(updates)
