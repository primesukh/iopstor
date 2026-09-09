import json
import re

from conftest import live

pytestmark = live


def _jsonld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _main(resp):
    """The page body alone. The header's services panel lists every child service on every page,
    so "is this link on the page" has to mean the page, not the chrome."""
    return re.search(r'<main id="main">(.*)</main>', resp.text, re.S).group(1)


def test_hierarchical_service_url_and_breadcrumb(client, seeded):
    r = client.get("/services/storage/nas")
    assert r.status_code == 200
    ld = _jsonld(r.text)
    crumbs = next(n for n in ld if n["@type"] == "BreadcrumbList")
    assert [i["name"] for i in crumbs["itemListElement"]] == ["Home", "Services", "Storage", "NAS"]
    assert crumbs["itemListElement"][-1]["item"] == "http://test/services/storage/nas"
    assert any(n["@type"] == "Service" for n in ld)
    assert client.get("/services/nas").status_code == 404  # child only lives under its parent
    assert "/services/storage/nas" in _main(client.get("/services/storage"))
    archive = client.get("/services")
    assert archive.status_code == 200 and b"Storage" in archive.data
    body = _main(archive)
    # The archive is one row per group, and a child appears in it only as a tile inside its parent's
    # row -- never as a row of its own. That is the design's services archive.
    assert '<h3><a href="/services/storage/nas">' not in body
    assert 'class="chip" href="/services/storage/nas"' in body
    home = client.get("/")
    assert home.status_code == 200 and b'"WebSite"' in home.data and b'<link rel="canonical" href="http://test/">' in home.data
    assert client.get("/home").status_code == 301
    assert b"IOPStor was founded" in client.get("/about-us").data
    assert client.get("/healthz").json == {"ok": True}


def test_redirect_and_trailing_slash(client, admin_headers):
    assert client.post("/api/admin/v1/redirects", headers=admin_headers, json={"from_path": "zz-test-old/", "to_url": "/services"}).status_code == 201
    r = client.get("/zz-test-old")
    assert r.status_code == 301 and r.headers["Location"].endswith("/services")
    r = client.get("/services/")
    assert r.status_code == 301 and r.headers["Location"].endswith("/services")
    assert client.get("/nope").status_code == 404
    assert client.get("/services/storage/nope").status_code == 404


def test_sitemap_feed_llms_and_public_api(client, editor_headers):
    ok = client.post("/api/admin/v1/posts", headers=editor_headers, json={"post_type": "post", "title": "zz-test Public Post", "status": "published", "excerpt": "An excerpt",
                                                                          "blocks": [{"type": "faq", "data": {"items": [{"q": "Why?", "a": "Because."}]}}]})
    assert ok.status_code == 201, ok.json
    client.post("/api/admin/v1/posts", headers=editor_headers, json={"post_type": "post", "title": "zz-test Secret Draft"})
    for path in ("/sitemap.xml", "/feed.xml", "/llms.txt", "/llms-full.txt", "/robots.txt", "/index.md"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert b"zz-test-secret-draft" not in r.data and b"Secret Draft" not in r.data, path
    assert b"<loc>http://test/blog/zz-test-public-post</loc>" in client.get("/sitemap.xml").data
    assert b"<loc>http://test/industry/finance</loc>" in client.get("/sitemap.xml").data
    assert b"http://test/blog/zz-test-public-post" in client.get("/feed.xml").data
    full = client.get("/llms-full.txt").data
    assert b"## zz-test Public Post" in full and b"Because." in full
    assert b"Sitemap: http://test/sitemap.xml" in client.get("/robots.txt").data
    # every page also answers as Markdown, and llms.txt points at those twins
    assert b"http://test/blog/zz-test-public-post.md" in client.get("/llms.txt").data
    md = client.get("/blog/zz-test-public-post.md")
    assert md.status_code == 200 and md.mimetype == "text/markdown"
    assert b"# zz-test Public Post" in md.data and b"### Why?" in md.data and b"Because." in md.data
    assert b'url: "http://test/blog/zz-test-public-post"' in md.data      # front matter names the canonical page
    assert client.get("/blog.md").status_code == 200                     # archives have twins too
    assert client.get("/industry/finance.md").status_code == 200         # so do term archives
    assert client.get("/blog/zz-test-secret-draft.md").status_code == 404
    assert b'type="text/markdown" href="http://test/blog/zz-test-public-post.md"' in client.get("/blog/zz-test-public-post").data
    assert b'"FAQPage"' in client.get("/blog/zz-test-public-post").data
    api = client.get("/api/v1/posts/post/zz-test-public-post")
    assert api.status_code == 200 and api.json["title"] == "zz-test Public Post" and api.json["text"] == "Why? Because." and "author_id" not in api.json
    assert client.get("/api/v1/posts/post/zz-test-secret-draft").status_code == 404
    assert client.get("/api/v1/posts?type=case_study&term=private-cloud").json["total"] == 3
    assert client.get("/api/v1/settings").json["site_name"]


def test_lead_submission(client, editor_headers):
    r = client.post("/api/v1/leads", json={"name": "A", "email": "a@zz-test.local", "kind": "quote", "message": "hi", "budget": "10L"})
    assert r.status_code == 201 and r.json["id"]
    form = client.post("/api/v1/leads", data={"name": "Form", "email": "f@zz-test.local", "kind": "contact", "back": "/contact-us"})
    assert form.status_code == 303 and form.headers["Location"].endswith("/contact-us?sent=1")  # HTML form posts go back to the page
    assert client.post("/api/v1/leads", data={"name": "Evil", "email": "e@zz-test.local", "back": "//evil.com"}).headers["Location"].endswith("/?sent=1")
    assert client.post("/api/v1/leads", json={"name": "Bot", "email": "b@zz-test.local", "website": "spam"}).status_code == 201  # honeypot, dropped
    assert client.post("/api/v1/leads", json={"name": "", "email": "bad"}).status_code == 400
    leads = client.get("/api/admin/v1/leads?per_page=100", headers=editor_headers).json["items"]
    mine = {l["email"]: l for l in leads if l["email"].endswith("@zz-test.local")}
    assert set(mine) == {"a@zz-test.local", "f@zz-test.local", "e@zz-test.local"} and mine["a@zz-test.local"]["data"] == {"budget": "10L"}


def test_upload_checkout_seed(client, editor_headers):
    import io

    bad = client.post("/api/admin/v1/media", headers=editor_headers, data={"file": (io.BytesIO(b"MZ"), "zz-test.exe")})
    assert bad.status_code == 400 and "not allowed" in bad.json["error"]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    ok = client.post("/api/admin/v1/media", headers=editor_headers, data={"file": (io.BytesIO(png), "zz-test-logo.png"), "alt": "Logo"})
    assert ok.status_code == 201, ok.json
    assert "/storage/v1/object/public/" in ok.json["url"] and ok.json["alt"] == "Logo" and ok.json["size"] == len(png)
    assert client.delete(f"/api/admin/v1/media/{ok.json['id']}", headers=editor_headers).status_code == 204

    prod = client.post("/api/admin/v1/posts", headers=editor_headers, json={"post_type": "product", "title": "zz-test Flash 24", "status": "published",
                                                                            "meta": {"price": 199999, "currency": "INR", "sku": "IOF-24"}})
    assert prod.status_code == 201, prod.json
    page = client.get("/products/zz-test-flash-24").data
    assert b'"sku": "IOF-24"' in page
    # the price is the ask, not a spec: it rides on the Buy button, not in a card of its own
    assert "Buy &middot; \u20b9 1,99,999".encode() in page
    assert b"<dt>Price</dt>" not in page and b"<dt>SKU</dt>" in page
    r = client.post("/api/v1/payments/checkout", json={"product_id": prod.json["id"], "email": "buyer@zz-test.local", "name": "Buyer"})
    assert r.status_code == 201, r.json
    pid = r.json["payment_id"]
    assert r.json["redirect_url"] == f"/api/v1/payments/dummy/{pid}"
    assert client.get(r.json["redirect_url"]).json["status"] == "created"
    assert client.post("/api/v1/payments/webhook/dummy", json={"payment_id": pid, "status": "paid"}).status_code == 200
    assert client.get(f"/api/v1/payments/dummy/{pid}").json["status"] == "paid"
    assert client.post("/api/v1/payments/webhook/dummy", json={"payment_id": pid, "status": "nope"}).status_code == 400
    assert any(p["id"] == pid for p in client.get("/api/admin/v1/payments", headers=editor_headers).json["items"])


def test_seed_idempotent(app, seeded):
    from iopstor import db
    from iopstor.cli import run_seed

    def counts():
        return tuple(db.table(t).select("id", count="exact").limit(1).execute().count for t in ("posts", "post_types", "terms", "menus"))
    first = counts()
    run_seed()
    assert counts() == first and first[1] == 8 and first[0] >= 30
