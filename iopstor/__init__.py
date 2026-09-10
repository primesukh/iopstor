import re
from urllib.parse import quote

from flask import Flask
from flask.json.provider import DefaultJSONProvider

from . import config

REQUIRED = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET")


class JSONProvider(DefaultJSONProvider):
    sort_keys = False  # keep block/meta field order as authored


def rupees(n):
    """A price the way an Indian customer reads one: the last three digits, then twos.
    `{:,}` groups in threes all the way up, which would print 12,50,000 as 1,250,000. Anything
    that is not a number comes back untouched, so a price typed as "on request" still prints.
    Module scope, not a create_app() closure: public.py prints prices into Markdown too."""
    try:
        paise = round(float(n))
    except (TypeError, ValueError):
        return str(n or "")
    digits = str(abs(paise))
    if len(digits) > 3:
        digits = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", digits[:-3]) + "," + digits[-3:]
    return ("-" if paise < 0 else "") + "\u20b9 " + digits


def display_name(user):
    """The name to show for a CMS user: their own if they set one, otherwise the email's local part
    made readable \u2014 sukhpreet.saluja@\u2026 reads as "Sukhpreet Saluja". users.name defaults to '' and
    `flask create-admin` never fills it, so without the fallback the sidebar would say nothing."""
    return (user.get("name") or "").strip() or \
        user["email"].split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ").title()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(config)
    app.config.from_mapping(test_config or {})
    app.json = JSONProvider(app)
    missing = [k for k in REQUIRED if not app.config.get(k)]
    if missing:
        raise RuntimeError(f"{', '.join(missing)} not set. IOPSTOR runs entirely on Supabase; fill .env (see .env.example)")

    from . import db
    from .admin_api import bp as admin_api
    from .admin_ui import ui as admin_ui
    from .blocks import count_up, section_class
    from .cli import register as register_cli
    from .public import api as public_api, pub as public_site

    def media_download(i):
        # public.media_file() turns ?download into Content-Disposition: attachment; the value names the
        # saved file, so the reader gets "datasheet.pdf" and not the uuid the bucket key is made of.
        m = db.get_media(int(i)) if i else None
        return f"{m['url']}?download={quote(m.get('filename') or '')}" if m else ""

    app.jinja_env.globals.update(
        rupees=rupees,
        display_name=display_name,   # the admin sidebar's user block and the Users table say the same name
        count_up=count_up,        # stats.html splits a figure into the part a CSS counter can roll to
        section_class=section_class,   # and whitelists one figure's own effect the same way a section's is
        media_url=lambda i: (db.get_media(int(i)) or {}).get("url", "") if i else "",
        media_alt=lambda i: (db.get_media(int(i)) or {}).get("alt", "") if i else "",
        media_download=media_download,
    )
    app.register_blueprint(admin_api)
    app.register_blueprint(admin_ui)
    app.register_blueprint(public_api)
    app.register_blueprint(public_site)
    register_cli(app)

    @app.errorhandler(404)
    def _not_found(e):  # unmatched routes outside blueprints (e.g. /static/missing.css)
        from .public import _not_found as site_404
        return site_404(e)

    @app.get("/healthz")
    def healthz():
        db.table("post_types").select("id").limit(1).execute()
        return {"ok": True}

    return app
