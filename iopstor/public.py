"""Public site: catch-all page resolver, SEO endpoints (sitemap/robots/llms/feed), and the read-only JSON API."""
from datetime import date

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request
from markupsafe import escape
from postgrest import APIError
from werkzeug.exceptions import HTTPException

from . import db, seo
from .admin_api import _http_error, _pg_error, page_args
from .blocks import blocks_text, render_blocks
from .payments import GATEWAYS, gateway

pub = Blueprint("public", __name__)
api = Blueprint("public_api", __name__, url_prefix="/api/v1")
api.register_error_handler(HTTPException, _http_error)
api.register_error_handler(APIError, _pg_error)

PUBLIC_SETTINGS = ("site_name", "tagline", "logo_url", "social_links", "contact_email", "contact_phone", "address")


@pub.app_context_processor
def _template_globals():
    return {"site": seo.site(), "menu": db.get_menu, "render_blocks": render_blocks, "year": date.today().year}


def _live_post(pt, slug):
    return db.hydrate(db.one(db.live(db.select_posts()).eq("post_type_id", pt["id"]).eq("slug", slug)))


def crumbs_for(post):
    crumbs = [("Home", "/")]
    if post["path"] == "/":
        return crumbs
    pt = post["post_type"]
    if pt["url_prefix"]:
        crumbs.append((pt["name"], "/" + pt["url_prefix"]))
    return crumbs + db.ancestors(post) + [(post["title"], post["path"])]


def render_post(post):
    crumbs = crumbs_for(post)
    children = db.with_paths(db.rows(db.live(db.select_posts()).eq("parent_id", post["id"]).order("menu_order").order("published_at", desc=True))) if post["post_type"]["hierarchical"] else []
    return render_template("post.html", post=post, children=children, crumbs=crumbs, meta=seo.build_meta(post), jsonld=seo.jsonld(post, crumbs))


def render_archive(q, title, path, crumbs, description=""):
    """q: a live select_posts(count='exact') query, already filtered."""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("menu_order").order("published_at", desc=True), page, 20)
    if page > 1 and not result["items"]:
        abort(404)
    meta = seo.build_meta(title=title, description=description, path=path, robots="index,follow" if page == 1 else "noindex,follow")
    has_next = page * 20 < result["total"]
    return render_template("archive.html", title=title, posts=db.with_paths(result["items"]), page=page, has_next=has_next, crumbs=crumbs,
                           meta=meta, jsonld=seo.jsonld(crumbs=crumbs))


@pub.errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):  # unknown API path caught by the site catch-all
        return jsonify(error="not found"), 404
    crumbs = [("Home", "/"), ("Not found", request.path)]
    return render_template("404.html", meta=seo.build_meta(title="Page not found", path=request.path, robots="noindex,follow"), jsonld=seo.jsonld(crumbs=crumbs)), 404


@pub.get("/", defaults={"path": ""})
@pub.get("/<path:path>")
def resolve(path):
    if path.endswith("/"):
        return redirect("/" + path.rstrip("/"), 301)
    full = "/" + path
    r = db.one(db.table("redirects").select("*").eq("from_path", full))
    if r:
        db.update("redirects", r["id"], {"hits": r["hits"] + 1})
        return redirect(r["to_url"], r["code"])
    page_type = db.post_type(slug="page")
    if not path:
        home = _live_post(page_type, "home") if page_type else None
        if home:
            return render_post(home)
        return render_archive(db.live(db.select_posts(count="exact")), "", "/", [("Home", "/")])  # no home page yet: list everything
    segs = path.split("/")
    pt = db.post_type(url_prefix=segs[0])
    if pt:
        if len(segs) == 1:
            q = db.live(db.select_posts(count="exact")).eq("post_type_id", pt["id"])
            if pt["hierarchical"]:
                q = q.is_("parent_id", "null")
            return render_archive(q, pt["name"], full, [("Home", "/"), (pt["name"], full)])
        post = _live_post(pt, segs[-1])
        if post is not None and post["path"] == full:
            return render_post(post)
        abort(404)
    if len(segs) == 1 and page_type:
        if path == "home":
            return redirect("/", 301)
        post = _live_post(page_type, path)
        if post is not None and post["path"] == full:
            return render_post(post)
    if len(segs) == 2:
        tax = db.one(db.table("taxonomies").select("*").eq("slug", segs[0]))
        term = db.one(db.table("terms").select("*").eq("taxonomy_id", tax["id"]).eq("slug", segs[1])) if tax else None
        if term:
            q = db.live(db.table("posts").select(db.POST_SELECT_BY_TERM, count="exact")).eq("post_terms.term_id", term["id"])
            crumbs = [("Home", "/"), (tax["name"], "/" + tax["slug"]), (term["name"], full)]
            return render_archive(q, term["name"], full, crumbs, term["description"])
    abort(404)


# ---- crawler endpoints -----------------------------------------------------

def _indexable(post):
    return not (post.get("seo") or {}).get("robots", "").startswith("noindex")


def _live_term_ids():
    q = db.table("post_terms").select("term_id, posts!inner(status, published_at)").eq("posts.status", "published").lte("posts.published_at", db.now_iso())
    return {r["term_id"] for r in db.rows(q)}


@pub.get("/sitemap.xml")
def sitemap():
    base = seo.site()["url"]
    urls = {base + "/": None}
    types = [t for t in db.post_types() if t["in_sitemap"]]
    for t in types:
        if t["url_prefix"]:
            urls[f"{base}/{t['url_prefix']}"] = None
    posts = db.rows(db.live(db.select_posts()).in_("post_type_id", [t["id"] for t in types]).order("id").limit(5000))  # ponytail: single sitemap, <5000 urls
    for p in db.with_paths(posts):
        if _indexable(p):
            urls[base + p["path"]] = p["updated_at"]
    live_terms = _live_term_ids()
    for term in db.rows(db.table("terms").select("slug, id, taxonomy:taxonomies(slug)")):
        if term["id"] in live_terms:
            urls[f"{base}/{term['taxonomy']['slug']}/{term['slug']}"] = None
    body = "".join(f"<url><loc>{escape(u)}</loc>{f'<lastmod>{m[:10]}</lastmod>' if m else ''}</url>" for u, m in urls.items())
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', mimetype="application/xml")


@pub.get("/robots.txt")
def robots():
    s = seo.site()
    lines = ["User-agent: *", "Allow: /", "Disallow: /admin", "Disallow: /api/admin", s["robots_extra"], f"Sitemap: {s['url']}/sitemap.xml"]
    return Response("\n".join(l for l in lines if l) + "\n", mimetype="text/plain")


def _sections():
    """[(post type, [live posts])] for llms.txt, in post type order."""
    out = []
    for t in db.post_types():
        if not t["in_sitemap"]:
            continue
        posts = db.with_paths(db.rows(db.live(db.select_posts()).eq("post_type_id", t["id"]).order("menu_order").order("published_at", desc=True).limit(1000)))
        posts = [p for p in posts if _indexable(p)]
        if posts:
            out.append((t, posts))
    return out


@pub.get("/llms.txt")
def llms():
    s = seo.site()
    lines = [f"# {s['name']}", f"> {s['tagline']}" if s["tagline"] else "", ""]
    if s["email"] or s["phone"]:
        lines += [f"Contact: {' · '.join(x for x in (s['email'], s['phone']) if x)}", ""]
    for t, posts in _sections():
        lines.append(f"## {t['name']}")
        lines += [f"- [{p['title']}]({s['url']}{p['path']}){': ' + p['excerpt'] if p['excerpt'] else ''}" for p in posts]
        lines.append("")
    lines += ["## Machine-readable", f"- Full text: {s['url']}/llms-full.txt", f"- JSON API: {s['url']}/api/v1/posts", f"- Sitemap: {s['url']}/sitemap.xml"]
    return Response("\n".join(lines) + "\n", mimetype="text/plain; charset=utf-8")


@pub.get("/llms-full.txt")
def llms_full():
    s = seo.site()
    parts = [f"# {s['name']}\n{s['tagline']}\n"]
    for t, posts in _sections():
        for p in posts:
            parts.append(f"## {p['title']}\nType: {t['name']}\nURL: {s['url']}{p['path']}\n\n{p['excerpt']}\n\n{blocks_text(p['blocks'] or [])}\n")
    return Response("\n---\n\n".join(parts), mimetype="text/plain; charset=utf-8")


@pub.get("/feed.xml")
def feed():
    s = seo.site()
    blog = db.post_type(slug="post")
    posts = db.with_paths(db.rows(db.live(db.select_posts()).eq("post_type_id", blog["id"]).order("published_at", desc=True).limit(20))) if blog else []
    items = "".join(
        f"<item><title>{escape(p['title'])}</title><link>{s['url']}{p['path']}</link><guid>{s['url']}{p['path']}</guid>"
        f"<pubDate>{db.parse_dt(p['published_at']).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate><description>{escape(p['excerpt'])}</description></item>"
        for p in posts)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(s["name"])} blog</title><link>{s["url"]}/blog</link>'
           f'<description>{escape(s["tagline"])}</description>{items}</channel></rss>')
    return Response(xml, mimetype="application/rss+xml")


# ---- public JSON API -------------------------------------------------------

def public_post(post):
    d = dict(post)
    d.pop("author_id", None)
    d["url"] = seo.site()["url"] + post["path"]
    d["text"] = blocks_text(post.get("blocks") or [])
    return d


@api.get("/post-types")
def api_post_types():
    return jsonify([{"slug": t["slug"], "name": t["name"], "url_prefix": t["url_prefix"], "hierarchical": t["hierarchical"]} for t in db.post_types()])


@api.get("/posts")
def api_posts():
    if term_slug := request.args.get("term"):
        term = db.one(db.table("terms").select("id").eq("slug", term_slug)) or abort(404)
        q = db.table("posts").select(db.POST_SELECT_BY_TERM, count="exact").eq("post_terms.term_id", term["id"])
    else:
        q = db.select_posts(count="exact")
    q = db.live(q)
    if t := request.args.get("type"):
        pt = db.post_type(slug=t) or abort(404)
        q = q.eq("post_type_id", pt["id"])
    page, per_page = page_args()
    result = db.paginate(q.order("published_at", desc=True), page, per_page)
    result["items"] = [public_post(p) for p in db.with_paths(result["items"])]
    return jsonify(result)


@api.get("/posts/<type_slug>/<slug>")
def api_post(type_slug, slug):
    pt = db.post_type(slug=type_slug) or abort(404)
    return jsonify(public_post(_live_post(pt, slug) or abort(404)))


@api.get("/taxonomies/<slug>/terms")
def api_terms(slug):
    t = db.one(db.table("taxonomies").select("*").eq("slug", slug)) or abort(404)
    terms = db.rows(db.table("terms").select("*").eq("taxonomy_id", t["id"]).order("name"))
    return jsonify([{"slug": x["slug"], "name": x["name"], "description": x["description"], "url": f"/{t['slug']}/{x['slug']}"} for x in terms])


@api.get("/menus/<slug>")
def api_menu(slug):
    return jsonify(db.get_menu(slug))


@api.get("/settings")
def api_settings():
    s = db.settings()
    return jsonify({k: s.get(k) for k in PUBLIC_SETTINGS})


def _form_redirect(b):
    """Plain HTML form posts go back to the page they came from with ?sent=1 (JSON clients get JSON)."""
    if request.is_json:
        return None
    back = str(b.get("back") or "/")
    if not back.startswith("/") or back.startswith(("//", "/\\")):
        back = "/"
    return redirect(back + ("&" if "?" in back else "?") + "sent=1", 303)


@api.post("/leads")
def api_create_lead():
    b = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    b = b if isinstance(b, dict) else {}
    if b.get("website"):  # ponytail: honeypot only; add rate limiting if spam gets through
        return _form_redirect(b) or (jsonify(ok=True), 201)
    name, email = str(b.get("name") or "").strip(), str(b.get("email") or "").strip()
    if not name or "@" not in email:
        abort(400, "name and email required")
    post_id = int(b["post_id"]) if str(b.get("post_id") or "").isdigit() else None
    if post_id and db.one(db.table("posts").select("id").eq("id", post_id)) is None:
        post_id = None
    known = {"name", "email", "phone", "company", "message", "kind", "post_id", "website", "back"}
    lead = db.insert("leads", {
        "kind": b.get("kind") if b.get("kind") in ("contact", "quote", "career") else "contact", "name": name[:200], "email": email[:300],
        "phone": str(b.get("phone") or "")[:50], "company": str(b.get("company") or "")[:200], "message": str(b.get("message") or ""),
        "post_id": post_id, "data": {k: v for k, v in b.items() if k not in known}})
    return _form_redirect(b) or (jsonify(ok=True, id=lead["id"]), 201)


@api.post("/payments/checkout")
def api_checkout():
    b = request.get_json(silent=True) or {}
    product_type = db.post_type(slug="product") or abort(404, "product not found")
    product = db.one(db.live(db.table("posts").select("*")).eq("post_type_id", product_type["id"]).eq("id", int(b.get("product_id") or 0)))
    if product is None:
        abort(404, "product not found")
    meta = product.get("meta") or {}
    if meta.get("price") in (None, ""):
        abort(400, "product has no price")
    email = str(b.get("email") or "").strip()
    if "@" not in email:
        abort(400, "email required")
    lead = db.insert("leads", {"kind": "quote", "name": str(b.get("name") or email)[:200], "email": email[:300], "post_id": product["id"], "data": {"source": "checkout"}})
    payment = db.insert("payments", {"provider": gateway().name, "post_id": product["id"], "lead_id": lead["id"], "amount": meta["price"],
                                     "currency": str(meta.get("currency") or "INR")[:3]})
    result = gateway().create_checkout(payment)
    return jsonify({"payment_id": payment["id"], "status": payment["status"], **result}), 201


@api.post("/payments/webhook/<provider>")
def api_webhook(provider):
    gw = GATEWAYS.get(provider) or abort(404)
    payment = gw.handle_webhook(request)
    return jsonify(payment_id=payment["id"], status=payment["status"])


@api.get("/payments/dummy/<int:pk>")
def api_dummy_page(pk):
    p = db.one(db.table("payments").select("*").eq("id", pk)) or abort(404)
    return jsonify(payment_id=p["id"], status=p["status"], amount=p["amount"], currency=p["currency"],
                   note="Placeholder gateway. POST {payment_id, status: paid|failed} to /api/v1/payments/webhook/dummy")
