"""Environment → Flask config. Plain module, loaded with app.config.from_object. Everything lives in Supabase."""
import ipaddress
import os

# No defaults on purpose: both are in create_app()'s REQUIRED, so a deploy that forgets one refuses to
# boot instead of signing sessions with a key printed in this repo, or publishing localhost canonicals.
SECRET_KEY = os.environ.get("SECRET_KEY", "")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")

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

# The networks whose forwarding headers throttle.client_ip() believes: cloudflared on the compose
# bridge, and whatever fronts the LAN port. Parsed here rather than per request, so a typo refuses to
# boot the way a missing SECRET_KEY does instead of failing quietly on every login. `or`, not a get()
# default: compose passes ${TRUSTED_PROXIES:-}, and an empty string has to mean unset -- read as
# "trust nothing" it would drop CF-Connecting-IP and put every tunnel visitor in cloudflared's bucket.
TRUSTED_PROXIES = tuple(ipaddress.ip_network(c.strip()) for c in (
    os.environ.get("TRUSTED_PROXIES") or "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,::1/128,fc00::/7"
).split(",") if c.strip())
# The networks allowed to reach /admin and /api/admin/v1 at all, so an editor's session only works from
# the office. Empty means no restriction, which is what development and any deploy that has not set it
# want. Compared against the address client_ip() resolves, NOT against remote_addr -- behind Traefik
# every request would otherwise look like Traefik and either all pass or all fail.
ADMIN_NETWORKS = tuple(ipaddress.ip_network(c.strip())
                       for c in os.environ.get("ADMIN_NETWORKS", "").split(",") if c.strip())
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = SITE_URL.startswith("https://")
