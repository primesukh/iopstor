import re
from datetime import timedelta

from conftest import live

from iopstor import db

pytestmark = live
POSTS = "/api/admin/v1/posts"


def test_post_create_publish_visible(client, editor_headers):
    r = client.post(POSTS, headers=editor_headers, json={"post_type": "post", "title": "zz-test Hello World", "blocks": [{"type": "rich_text", "data": {"html": "<p>hi there</p>"}}]})
    assert r.status_code == 201, r.json
    assert r.json["slug"] == "zz-test-hello-world" and r.json["status"] == "draft" and r.json["path"] == "/blog/zz-test-hello-world" and r.json["post_type"]["slug"] == "post"
    assert client.get("/blog/zz-test-hello-world").status_code == 404

    r2 = client.patch(f"{POSTS}/{r.json['id']}", headers=editor_headers, json={"status": "published"})
    assert r2.status_code == 200 and r2.json["published_at"]
    page = client.get("/blog/zz-test-hello-world")
    assert page.status_code == 200 and b"<p>hi there</p>" in page.data and b'"BlogPosting"' in page.data
    assert b'<link rel="canonical" href="http://test/blog/zz-test-hello-world">' in page.data

    # a second page of the same name is never blocked: it takes the title's address plus three random letters
    dup = client.post(POSTS, headers=editor_headers, json={"post_type": "post", "title": "zz-test Hello World"})
    assert dup.status_code == 201 and re.fullmatch(r"zz-test-hello-world-[a-z]{3}", dup.json["slug"]), dup.json
    taken = client.post(POSTS, headers=editor_headers, json={"post_type": "post", "title": "zz-test x", "slug": "zz-test-hello-world"})
    assert taken.status_code == 201 and re.fullmatch(r"zz-test-hello-world-[a-z]{3}", taken.json["slug"]), taken.json
    # renaming an existing post onto a taken address is deliberate, so it is refused rather than guessed at
    clash = client.patch(f"{POSTS}/{dup.json['id']}", headers=editor_headers, json={"slug": "zz-test-hello-world"})
    assert clash.status_code == 409 and "already in use" in clash.json["fields"]["slug"]
    bad = client.post(POSTS, headers=editor_headers, json={"post_type": "nope", "blocks": [{"type": "zzz", "data": {}}]})
    assert bad.status_code == 400 and set(bad.json["fields"]) == {"post_type", "title", "blocks"}
    assert client.delete(f"{POSTS}/{r.json['id']}", headers=editor_headers).status_code == 403  # editors cannot delete


def test_scheduled_post_hidden(client, editor_headers):
    future = (db.utcnow() + timedelta(days=1)).isoformat()
    r = client.post(POSTS, headers=editor_headers, json={"post_type": "post", "title": "zz-test Soon", "status": "published", "published_at": future})
    assert r.status_code == 201
    assert client.get("/blog/zz-test-soon").status_code == 404
    assert any(p["slug"] == "zz-test-soon" for p in client.get(f"{POSTS}?type=post&q=zz-test", headers=editor_headers).json["items"])
    assert not any(p["slug"] == "zz-test-soon" for p in client.get("/api/v1/posts?type=post&per_page=100").json["items"])


def test_terms_settings_menus(client, admin_headers):
    t = client.post("/api/admin/v1/taxonomies/tag/terms", headers=admin_headers, json={"name": "zz-test All Flash"})
    assert t.status_code == 201 and t.json["slug"] == "zz-test-all-flash"
    p = client.post(POSTS, headers=admin_headers, json={"post_type": "post", "title": "zz-test Tagged", "status": "published", "terms": [t.json["id"]]})
    assert p.status_code == 201 and [x["slug"] for x in p.json["terms"]] == ["zz-test-all-flash"]
    assert b"zz-test Tagged" in client.get("/tag/zz-test-all-flash").data
    assert client.get("/api/v1/posts?term=zz-test-all-flash").json["total"] == 1

    before = client.get("/api/admin/v1/settings", headers=admin_headers).json.get("site_name")
    try:
        assert client.put("/api/admin/v1/settings", headers=admin_headers, json={"site_name": "IOPSTOR Test"}).json["site_name"] == "IOPSTOR Test"
        assert b"<title>zz-test Tagged | IOPSTOR Test</title>" in client.get("/blog/zz-test-tagged").data
    finally:
        client.put("/api/admin/v1/settings", headers=admin_headers, json={"site_name": before})
    m = client.put("/api/admin/v1/menus/zz-test-menu", headers=admin_headers, json={"items": [{"label": "Only", "url": "/x"}]})
    assert m.status_code == 200, m.json
    assert client.get("/api/v1/menus/zz-test-menu").json == [{"label": "Only", "url": "/x"}]
