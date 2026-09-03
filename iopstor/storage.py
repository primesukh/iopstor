"""Media uploads → Supabase Storage bucket (public). Rows in the media table."""
import mimetypes
import uuid
from datetime import datetime, timezone

from flask import abort, current_app
from werkzeug.utils import secure_filename

from . import db

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg", "application/pdf": ".pdf"}


def _bucket():
    return db.sb().storage.from_(current_app.config["MEDIA_BUCKET"])


def save_upload(fs, user_id=None):
    mime = mimetypes.guess_type(fs.filename or "")[0]  # by extension; staff-only uploads, no magic-byte sniffing
    if mime not in ALLOWED:
        abort(400, f"file type not allowed; use {', '.join(sorted(ALLOWED.values()))}")
    data = fs.read()
    key = f"{datetime.now(timezone.utc):%Y/%m}/{uuid.uuid4().hex}{ALLOWED[mime]}"
    bucket = _bucket()
    bucket.upload(key, data, {"content-type": mime, "upsert": "false"})
    return db.insert("media", {"key": key, "url": bucket.get_public_url(key), "filename": secure_filename(fs.filename or "upload")[:300],
                               "mime": mime, "size": len(data), "uploaded_by": user_id})


def delete_media(media):
    _bucket().remove([media["key"]])
    db.table("media").delete().eq("id", media["id"]).execute()
