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


def sniff(data):
    """The allowed type the bytes say they are, or None. A file's name is often wrong -- a logo saved from
    another site keeps whatever ending it was given -- and for rasters that costs nothing, because a browser
    picks the decoder from the bytes. image/svg+xml is the exception: it is read as a drawing and nothing
    else, so WebP bytes behind an .svg name showed in Firefox and not in Chrome (2026-09-23). SVG is text,
    so it is looked for last, and only in a head with no NUL byte in it."""
    head = data[:4096]
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if b"\0" not in head and b"<svg" in head:
        return "image/svg+xml"
    return None


def save_upload(fs, user_id=None):
    mime = mimetypes.guess_type(fs.filename or "")[0]  # the name decides what may be uploaded...
    if mime not in ALLOWED:
        abort(400, f"file type not allowed; use {', '.join(sorted(ALLOWED.values()))}")
    data = fs.read()
    mime = sniff(data) or mime                          # ...and the bytes decide what it is
    key = f"{datetime.now(timezone.utc):%Y/%m}/{uuid.uuid4().hex}{ALLOWED[mime]}"
    bucket = _bucket()
    bucket.upload(key, data, {"content-type": mime, "upsert": "false"})
    return db.insert("media", {"key": key, "url": public_path(key), "filename": secure_filename(fs.filename or "upload")[:300],
                               "mime": mime, "size": len(data), "uploaded_by": user_id})


def delete_media(media):
    _bucket().remove([media["key"]])
    db.delete("media", media["id"])
