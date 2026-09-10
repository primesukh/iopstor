"""Media uploads → Supabase Storage bucket. Rows in the media table, bytes served back by public.media_file():
Supabase is reachable only on the LAN, so a browser can never fetch an object itself."""
import mimetypes
import uuid
from datetime import datetime, timezone

from flask import abort, current_app
from werkzeug.utils import secure_filename

from . import db

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg", "application/pdf": ".pdf"}
EXT = {v: k for k, v in ALLOWED.items()}  # ".jpg" → "image/jpeg"; also the whitelist of servable keys


def _bucket():
    return db.sb().storage.from_(current_app.config["MEDIA_BUCKET"])


def public_path(key):
    """The address this site serves a bucket object at, and what goes in media.url. Never
    bucket.get_public_url(): that points at the Supabase gateway, which only this app can reach."""
    return f"/media/{key}"


def fetch(key):
    # ponytail: the whole file lands in memory (MAX_CONTENT_LENGTH caps an upload at 20 MB).
    # Stream it through httpx if PDFs ever get big enough to matter.
    return _bucket().download(key)


def save_upload(fs, user_id=None):
    mime = mimetypes.guess_type(fs.filename or "")[0]  # by extension; staff-only uploads, no magic-byte sniffing
    if mime not in ALLOWED:
        abort(400, f"file type not allowed; use {', '.join(sorted(ALLOWED.values()))}")
    data = fs.read()
    key = f"{datetime.now(timezone.utc):%Y/%m}/{uuid.uuid4().hex}{ALLOWED[mime]}"
    bucket = _bucket()
    bucket.upload(key, data, {"content-type": mime, "upsert": "false"})
    return db.insert("media", {"key": key, "url": public_path(key), "filename": secure_filename(fs.filename or "upload")[:300],
                               "mime": mime, "size": len(data), "uploaded_by": user_id})


def delete_media(media):
    _bucket().remove([media["key"]])
    db.table("media").delete().eq("id", media["id"]).execute()
