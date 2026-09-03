"""Offline tests run always. Integration tests (marked `live`) run against the Supabase in .env and skip otherwise.
Everything they create is prefixed zz-test and removed by the `cleanup` fixture."""
import os
import time
import uuid

import jwt
import pytest

from iopstor import create_app

LIVE = all(os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET"))
live = pytest.mark.skipif(not LIVE, reason="needs SUPABASE_* in .env (pipenv loads it)")
SECRET = os.environ.get("SUPABASE_JWT_SECRET") or "test-secret-" + "x" * 32
FAKE_KEY = jwt.encode({"role": "anon"}, "y" * 32, algorithm="HS256")


@pytest.fixture
def app():
    cfg = {"TESTING": True, "SITE_URL": "http://test"}
    if not LIVE:
        cfg.update(SUPABASE_URL="http://supabase.invalid", SUPABASE_ANON_KEY=FAKE_KEY, SUPABASE_SERVICE_ROLE_KEY=FAKE_KEY, SUPABASE_JWT_SECRET=SECRET)
    app = create_app(cfg)
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def make_token(sub, secret=SECRET, **claims):
    payload = {"sub": str(sub), "aud": "authenticated", "role": "authenticated", "exp": int(time.time()) + 3600, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def make_user(role="admin"):
    from iopstor import db
    return db.insert("users", {"id": str(uuid.uuid4()), "email": f"zz-test-{role}-{uuid.uuid4().hex[:6]}@zz-test.local", "role": role})


@pytest.fixture
def cleanup(app):
    yield
    from iopstor import db
    ids = [r["id"] for r in db.rows(db.table("posts").select("id").like("slug", "zz-test%"))]
    if ids:
        db.table("payments").delete().in_("post_id", ids).execute()
        db.table("leads").delete().in_("post_id", ids).execute()
        db.table("posts").delete().in_("id", ids).execute()
    db.table("leads").delete().like("email", "%@zz-test.local").execute()
    db.table("redirects").delete().like("from_path", "/zz-test%").execute()
    db.table("menus").delete().like("slug", "zz-test%").execute()
    db.table("terms").delete().like("slug", "zz-test%").execute()
    db.table("users").delete().like("email", "%@zz-test.local").execute()


@pytest.fixture
def seeded(app, cleanup):
    from iopstor.cli import run_seed
    run_seed()


@pytest.fixture
def admin_headers(seeded):
    return {"Authorization": f"Bearer {make_token(make_user('admin')['id'])}"}


@pytest.fixture
def editor_headers(seeded):
    return {"Authorization": f"Bearer {make_token(make_user('editor')['id'])}"}
