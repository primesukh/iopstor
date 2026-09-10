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
THROTTLE_DB = os.environ.get("THROTTLE_DB", "/dev/shm/iopstor-throttle.db")  # tmpfs: every worker shares it, gone on redeploy
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "10"))  # failed password checks per key per window
LOGIN_WINDOW = int(os.environ.get("LOGIN_WINDOW", "900"))  # seconds; tune both while under attack, no code change
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = SITE_URL.startswith("https://")
