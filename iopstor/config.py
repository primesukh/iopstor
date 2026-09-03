"""Environment → Flask config. Plain module, loaded with app.config.from_object. Everything lives in Supabase."""
import os

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")  # Kong gateway; http:// is fine on the LAN dev box
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "media")
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "dummy")
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # uploads; Flask returns 413 above this
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = SITE_URL.startswith("https://")
