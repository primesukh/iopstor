import uuid

from conftest import live, make_token, make_user

pytestmark = live
POSTS = "/api/admin/v1/posts"


def test_jwt_missing_invalid_wrong_role(client, editor_headers, admin_headers):
    assert client.get(POSTS, headers={"Authorization": f"Bearer {make_token(uuid.uuid4())}"}).status_code == 401  # valid JWT, no CMS user
    assert client.get(POSTS, headers={"Authorization": f"Bearer {make_token(uuid.uuid4(), secret='wrong-' + 'y' * 32)}"}).status_code == 401
    assert client.get(POSTS, headers=editor_headers).status_code == 200
    assert client.get("/api/admin/v1/settings", headers=editor_headers).status_code == 403
    assert client.get("/api/admin/v1/settings", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/v1/auth/me", headers=admin_headers).json["role"] == "admin"


def test_login_flow_with_mocked_gotrue(client, cleanup, monkeypatch):
    from supabase_auth.errors import AuthApiError

    from iopstor import admin_api

    user = make_user("admin")
    session = {"access_token": "t", "refresh_token": "r", "expires_in": 3600, "user_id": user["id"]}
    monkeypatch.setattr(admin_api, "login", lambda email, password: session)
    r = client.post("/api/admin/v1/auth/login", json={"email": user["email"], "password": "x"})
    assert r.status_code == 200 and r.json["user"]["role"] == "admin" and r.json["access_token"] == "t"

    session["user_id"] = str(uuid.uuid4())  # GoTrue user without a CMS row
    assert client.post("/api/admin/v1/auth/login", json={"email": "who@x.y", "password": "x"}).status_code == 403

    def boom(email, password):
        raise AuthApiError("Invalid login credentials", 400, "invalid_grant")
    monkeypatch.setattr(admin_api, "login", boom)
    assert client.post("/api/admin/v1/auth/login", json={"email": "a@b.c", "password": "bad"}).status_code == 401
    assert client.post("/api/admin/v1/auth/login", data="not json").status_code == 400


def test_real_login_rejects_bad_password(client, cleanup):
    r = client.post("/api/admin/v1/auth/login", json={"email": "nobody@zz-test.local", "password": "definitely-wrong"})
    assert r.status_code == 401 and r.json["error"]
