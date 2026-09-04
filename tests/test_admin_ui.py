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
    # the visual editor's mount points and the metadata it is driven by
    for hook in (b'id="canvas"', b'id="doc-toolbar"', b'id="block-settings"', b'id="content-tabs"', b'"layouts"', b'"seed"', b'"names"'):
        assert hook in form.data, hook
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

    # inline uploader used by the post form's media pickers: JSON in, JSON out, CSRF enforced
    from io import BytesIO
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    up = client.post("/admin/media/upload", data={"csrf": csrf, "alt": "zz-test dot", "file": (BytesIO(png), "zz-test-inline.png")},
                     content_type="multipart/form-data")
    assert up.status_code == 201 and up.json["url"] and up.json["alt"] == "zz-test dot"
    client.post(f"/admin/media/{up.json['id']}/delete", data={"csrf": csrf})
    assert client.post("/admin/media/upload", data={"csrf": csrf}, content_type="multipart/form-data").status_code == 400
    assert client.post("/admin/media/upload", data={"csrf": csrf, "file": (BytesIO(b"x"), "zz.exe")},
                       content_type="multipart/form-data").status_code == 400

    # the visual editor's iframe: the real render_blocks() output, with edit markers on
    blocks = '[{"type":"hero","data":{"heading":"zz canvas"}},{"type":"cta","data":{"heading":"h","button_label":"b","button_url":"/x"}}]'
    page = client.post("/admin/canvas", data={"csrf": csrf, "blocks": blocks, "title": "zz-test"})
    assert page.status_code == 200 and b'data-b="0"' in page.data and b'data-b="1"' in page.data
    assert b'data-f="heading"' in page.data and b"canvas.css" in page.data
    one = client.post("/admin/canvas", data={"csrf": csrf, "blocks": blocks, "i": "1"})
    assert one.status_code == 200 and b"<html" not in one.data and b'data-b="0"' in one.data  # bare fragment
    assert client.post("/admin/canvas", data={"csrf": csrf, "blocks": "not json"}).status_code == 200  # never 500s
    assert client.post("/admin/canvas", data={"blocks": "[]"}).status_code == 400  # CSRF still enforced

    # a document-shaped post: one rich_text block, the way the editor saves plain writing
    doc = ('[{"type":"rich_text","data":{"html":"<h2>What it does</h2><p>Stores <strong>things</strong>.</p>'
           '<ul><li>NFS</li></ul><table><tbody><tr><th>Capacity</th><td>5 PB</td></tr></tbody></table>"}}]')
    r = client.post("/admin/posts/new?type=post", data={"csrf": csrf, "title": "zz-test Document", "status": "published",
                                                        "excerpt": "A standfirst", "blocks": doc})
    assert r.status_code == 302
    page = client.get("/blog/zz-test-document")
    assert page.status_code == 200
    body = page.data
    assert b"<h2>What it does</h2>" in body and b"<li>NFS</li>" in body and b"<th>Capacity</th>" in body
    assert body.count(b"<h1") == 1  # the page title is the only h1; prose starts at h2
    assert b'class="lead"' in body  # no hero, so post.html gives it a document header

    # live preview: the real public shell, built from the form, for a post that is not published
    fields = {"csrf": csrf, "title": "zz-test Preview", "slug": "zz-test-preview", "status": "draft",
              "excerpt": "How it looks to a visitor", "blocks": doc}
    pv = client.post("/admin/preview?type=post", data=fields)
    assert pv.status_code == 200
    shown = pv.data
    assert b'class="site-header"' in shown and b'class="site-footer"' in shown and b"breadcrumb" in shown
    assert b"data-f=" not in shown and b"data-b=" not in shown      # no editing chrome
    assert b"googletagmanager" not in shown                        # a preview must not touch analytics
    assert b'name="robots" content="noindex,nofollow"' in shown
    assert b"<h2>What it does</h2>" in shown                        # unsaved blocks render
    assert client.get("/blog/zz-test-preview").status_code == 404   # ...while the public URL still 404s

    card = client.post("/admin/preview?type=post&part=card", data=fields)
    assert card.status_code == 200 and b"zz-test Preview" in card.data and b"How it looks to a visitor" in card.data
    assert client.post("/admin/preview?type=post", data={"title": "x"}).status_code == 400  # CSRF enforced

    # post.html slices published_at as a string; apply_post() stores a datetime. The preview must
    # keep the form's string or this render raises TypeError.
    dated = client.post("/admin/preview?type=post", data={**fields, "status": "published", "published_at": "2026-09-04T10:30"})
    assert dated.status_code == 200 and b"2026-09-04" in dated.data

    product_form = client.get("/admin/posts/new?type=product")
    assert b'name="meta_price"' in product_form.data and b'name="meta_sku"' in product_form.data
    for path in ("/admin/posts?type=service", "/admin/media", "/admin/leads", "/admin/settings", "/admin/users"):
        assert client.get(path).status_code == 200, path

    client.get("/admin/logout")
    assert client.get("/admin/").status_code == 302
