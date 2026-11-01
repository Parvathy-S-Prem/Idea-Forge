"""Shared complaint creation for Telegram and the web form."""
import secrets
import string
import uuid

from . import db

_ALPHA = string.ascii_uppercase + string.digits


def new_ref():
    return "GC-" + "".join(secrets.choice(_ALPHA) for _ in range(6))


def upload_media(data: bytes, mime: str) -> str | None:
    ext = {"image/jpeg": "jpg", "image/png": "png", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav",
           "audio/x-wav": "wav", "audio/mp4": "m4a"}.get(mime, "bin")
    path = f"{uuid.uuid4().hex}.{ext}"
    try:
        db.sb().storage.from_("media").upload(path, data, {"content-type": mime})
        return db.sb().storage.from_("media").get_public_url(path)
    except Exception as e:
        print("media upload failed:", e)
        return None


def create_complaint(source, text=None, media=None, mime=None, lat=None, lon=None, chat_id=None) -> dict:
    """Saves the raw complaint immediately (status=new); the worker picks it up for the agent."""
    url = upload_media(media, mime) if media else None
    row = {"ref": new_ref(), "source": source, "chat_id": chat_id, "raw_text": text, "media_url": url,
           "media_mime": mime if url else None, "lat": lat, "lon": lon, "status": "new"}
    return db.sb().table("complaints").insert(row).execute().data[0]
