import re

from conftest import live, make_token, make_user

pytestmark = live


def test_browser_admin_login_and_create_post(client, seeded, monkeypatch):
    from iopstor import admin_ui

    assert client.get("/admin/").status_code == 302  # anonymous → login page
    user = make_user("admin")
    fake = {"access_token": make_token(user["id"]), "refresh_token": "r", "expires_in": 3600, "user_id": user["id"]}
    monkeypatch.setattr(admin_ui, "login", lambda email, password: fake)

    assert client.post("/admin/login", data={"email": user["email"], "password": "x"}).status_code == 302
    dash = client.get("/admin/")
    assert dash.status_code == 200 and b"Dashboard" in dash.data and user["email"].encode() in dash.data

    form = client.get("/admin/posts/new?type=post")
    assert form.status_code == 200 and b"Block reference" in form.data
    csrf = re.search(r'name="csrf" value="([^"]+)"', form.text).group(1)
    r = client.post("/admin/posts/new?type=post", data={"csrf": csrf, "title": "zz-test UI Post", "status": "published", "excerpt": "From the browser",
                                                        "blocks": '[{"type":"hero","data":{"heading":"Hi from the form"}}]'})
    assert r.status_code == 302 and "/admin/posts/" in r.headers["Location"]
    edit = client.get(r.headers["Location"])
    assert edit.status_code == 200 and b"Hi from the form" in edit.data
    public = client.get("/blog/zz-test-ui-post")
    assert public.status_code == 200 and b"Hi from the form" in public.data

    bad = client.post("/admin/posts/new?type=post", data={"csrf": csrf, "title": "", "blocks": "not json"})
    assert bad.status_code == 400 and b"Not saved" in bad.data and b"blocks" in bad.data
    assert client.post("/admin/posts/new?type=post", data={"title": "zz-test nope"}).status_code == 400  # missing CSRF token

    product_form = client.get("/admin/posts/new?type=product")
    assert b'name="meta_price"' in product_form.data and b'name="meta_sku"' in product_form.data
    for path in ("/admin/posts?type=service", "/admin/media", "/admin/leads", "/admin/settings", "/admin/users"):
        assert client.get(path).status_code == 200, path

    client.get("/admin/logout")
    assert client.get("/admin/").status_code == 302
