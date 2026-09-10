"""Public site: catch-all page resolver, SEO endpoints (sitemap/robots/llms/feed), and the read-only JSON API."""
import json
from datetime import date
from io import BytesIO
from pathlib import PurePosixPath

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, send_file
from markupsafe import escape
from postgrest import APIError
from storage3.exceptions import StorageApiError
from werkzeug.exceptions import HTTPException

from . import db, seo, storage
from .admin_api import _http_error, _pg_error, page_args
from .blocks import blocks_md, blocks_text, render_blocks
from .payments import GATEWAYS, gateway
from .seo import md_url

pub = Blueprint("public", __name__)
api = Blueprint("public_api", __name__, url_prefix="/api/v1")
api.register_error_handler(HTTPException, _http_error)
api.register_error_handler(APIError, _pg_error)

PUBLIC_SETTINGS = ("site_name", "tagline", "logo_url", "social_links", "contact_email", "contact_phone", "address")


def _service_nav():
    """The Services menu: the archive URL, and the live top-level services with their children.
    Drives the header's mega panel and the footer's Services column. None when there are none.
    menu('header') carries labels and URLs only, and the panel needs each group's excerpt.
    # ponytail: services is the only menu that gets a mega panel, which is what the design asks
    # for. Give post_types a flag if a second one ever wants one."""
    pt = db.post_type(slug="service")
    if pt is None:
        return None
    groups = db.tree("service")
    return {"url": "/" + pt["url_prefix"], "groups": groups} if groups else None


@pub.app_context_processor
def _template_globals():
    # service_nav stays a callable, not a value: this processor is app-wide, and an /admin page has
    # no use for a posts query.
    return {"site": seo.site(), "menu": db.get_menu, "render_blocks": render_blocks,
            "year": date.today().year, "service_nav": _service_nav}


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


def _kids(parent_id):
    return db.with_paths(db.rows(db.live(db.select_posts()).eq("parent_id", parent_id)
                                 .order("menu_order").order("published_at", desc=True)))


# ---- Markdown twins --------------------------------------------------------
# Every page also answers at its own path with ".md" on the end, so an AI crawler reads the
# content instead of the theme. resolve() strips the suffix and resolves as usual; these build the
# document. Discovery is the <link rel="alternate"> in base.html (from seo.build_meta()) and the
# links in /llms.txt.

def _wants_md():
    """This request asked for the Markdown twin. Read off the URL every time rather than stashed in
    g on the way past: g lives on the app context, which a CLI or a test client holds open across
    several requests, and a stale flag there would serve Markdown to a browser."""
    return request.path.endswith(".md")


def _md(text):
    return Response(text, mimetype="text/markdown")


def _front(**kv):
    """YAML front matter. json.dumps() doubles as a YAML double-quoted scalar, so a title with a
    colon or a quote in it cannot break the block."""
    return "---\n" + "".join(f"{k}: {json.dumps(str(v))}\n" for k, v in kv.items() if v not in (None, "")) + "---\n"


def _md_doc(front, parts):
    return _md(front + "\n" + "\n\n".join(x for x in parts if x and str(x).strip()) + "\n")


def _md_list(posts):
    """Live posts as one Markdown list, each line pointing at its own .md twin."""
    return "\n".join(f"- [{p['title']}]({md_url(p['path'])})" + (f": {p['excerpt']}" if p.get("excerpt") else "")
                     for p in posts if p.get("path"))


def _md_page(title, path, parts):
    """An index — a type archive or a term archive — as Markdown."""
    return _md_doc(_front(title=title, url=seo.site()["url"] + path, type="Index"), [f"# {title}"] + parts)


def _md_fields(pt, meta):
    """The type's own fields (post_types.field_schema), split by shape the way post.html splits
    them: short ones a bullet list, long ones their own section, kv/json ones a table."""
    from . import rupees                 # module scope in __init__.py, imported here to dodge the cycle
    from .blocks import _media

    tiles, out = [], []
    for f in pt.get("field_schema") or []:
        v = meta.get(f.get("key"))
        if v in (None, "", [], {}):
            continue
        if f.get("type") == "media":       # the id is not the content: the file's address is
            v = _media(v)[0]
        elif f.get("key") == "price":
            v = rupees(v)
        if v in (None, ""):
            continue
        if f.get("type") == "textarea":
            out += [f"## {f['label']}", str(v)]
        elif f.get("type") in ("kv", "json"):
            rows = list(v.items()) if isinstance(v, dict) else [(r.get("k"), r.get("v")) for r in v if isinstance(r, dict)] if isinstance(v, list) else []
            if rows:
                out.append(f"## {f['label']}\n\n| Label | Value |\n| --- | --- |\n"
                           + "\n".join(f"| {k} | {x} |" for k, x in rows))
        else:
            tiles.append(f"- **{f['label']}:** {v}")
    return (["\n".join(tiles)] if tiles else []) + out


def _md_post(post, children):
    """One post as a Markdown document. The h1 comes from the hero when the page starts with one,
    exactly as post.html does it, so the twin has the same single h1 as the page it mirrors."""
    pt, blocks = post["post_type"], post.get("blocks") or []
    parts = [] if blocks and blocks[0].get("type") == "hero" else [f"# {post['title']}", post.get("excerpt") or ""]
    parts += _md_fields(pt, post.get("meta") or {}) + [blocks_md(blocks)]
    if children:
        parts += ["## Related pages", _md_list(children)]
    return _md_doc(_front(title=post["title"], url=seo.site()["url"] + post["path"], type=pt["name"],
                          published=(post.get("published_at") or "")[:10], updated=(post.get("updated_at") or "")[:10],
                          description=post.get("excerpt") or ""), parts)


def render_post(post):
    crumbs = crumbs_for(post)
    children, siblings = [], False
    if post["post_type"]["hierarchical"]:
        children = _kids(post["id"])
        # A leaf shows the rest of its group instead, which is what the design ends a service on:
        # "Other Storage services". Same query, same list, one page up.
        if not children and post["parent_id"]:
            children = [c for c in _kids(post["parent_id"]) if c["id"] != post["id"]]
            siblings = bool(children)
    if _wants_md():
        if not _indexable(post):
            abort(404)      # the one test that keeps a page out of sitemap.xml and llms.txt keeps
        return _md_post(post, children)     # it out of the Markdown too
    return render_template("post.html", post=post, children=children, siblings=siblings, crumbs=crumbs,
                           meta=seo.build_meta(post), jsonld=seo.jsonld(post, crumbs))


def _filters(pt):
    """The chip row on a type archive: the terms of its first taxonomy, as name + archive URL.
    # ponytail: the first taxonomy only. Case studies have two (industry, solution) and the design
    # filters on industry. Add a second row here if anyone wants to filter on both at once."""
    slugs = (pt or {}).get("taxonomies") or []
    tax = db.one(db.table("taxonomies").select("*").eq("slug", slugs[0])) if slugs else None
    if tax is None:
        return []
    terms = db.rows(db.table("terms").select("slug,name").eq("taxonomy_id", tax["id"]).order("name"))
    return [{"name": t["name"], "url": f"/{tax['slug']}/{t['slug']}"} for t in terms]


def render_archive(q, title, path, crumbs, description="", pt=None):
    """q: a live select_posts(count='exact') query, already filtered."""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("menu_order").order("published_at", desc=True), page, 20)
    if page > 1 and not result["items"]:
        abort(404)
    meta = seo.build_meta(title=title, description=description, path=path, robots="index,follow" if page == 1 else "noindex,follow")
    has_next = page * 20 < result["total"]
    # description was built into meta but never reached the template, so archive.html's lead
    # paragraph could not render and every term archive's prose was invisible.
    posts = db.with_paths(result["items"])
    if _wants_md():
        nxt = f"- [Next page]({md_url(path)}?page={page + 1})" if has_next else ""
        return _md_page(title or seo.site()["name"], path, [description, _md_list(posts), nxt])
    # The services archive is a row per group with its children as tiles beside it, the same shape
    # the home page's list uses. db.tree() is memoised per request by the header's panel, so this is
    # the lookup that has already happened.
    if pt and pt["hierarchical"]:
        kids = {t["id"]: t["children"] for t in db.tree(pt["slug"])}
        for p in posts:
            p["children"] = kids.get(p["id"], [])
    return render_template("archive.html", title=title, posts=posts, page=page, has_next=has_next, crumbs=crumbs,
                           description=description, pt=pt, filters=_filters(pt),
                           meta=meta, jsonld=seo.jsonld(crumbs=crumbs))


@pub.errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):  # unknown API path caught by the site catch-all
        return jsonify(error="not found"), 404
    if _wants_md():
        return _md("# Page not found\n"), 404
    crumbs = [("Home", "/"), ("Not found", request.path)]
    return render_template("404.html", meta=seo.build_meta(title="Page not found", path=request.path, robots="noindex,follow"), jsonld=seo.jsonld(crumbs=crumbs)), 404


@pub.get("/", defaults={"path": ""})
@pub.get("/<path:path>")
def resolve(path):
    if path.endswith("/"):
        return redirect("/" + path.rstrip("/"), 301)
    # The Markdown twin is the same page, resolved the same way: strip the suffix and every branch
    # below — pages, posts, both kinds of archive, redirects, 404 — comes along.
    # ponytail: "index" is a reserved slug (the home page's twin), like "checkout" further down.
    if path.endswith(".md"):
        path = "" if path == "index.md" else path[:-3]
    full = "/" + path
    r = db.one(db.table("redirects").select("*").eq("from_path", full))
    if r:
        # ponytail: read-then-write loses hits under parallel visits, and nothing reads the column yet.
        # A bump_redirect(id) SQL function called via .rpc() makes it exact if it is ever reported on.
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
            return render_archive(q, pt["name"], full, [("Home", "/"), (pt["name"], full)], pt=pt)
        # Checkout is a page, not a modal: the public site ships no JavaScript. Handled here rather
        # than as its own rule, which would have to out-rank the catch-all.
        # ponytail: "checkout" is a reserved last segment, so a product slugged "checkout" would be
        # unreachable. Nothing is.
        if segs[-1] == "checkout" and len(segs) > 1:
            if _wants_md():
                abort(404)          # a form is not content: noindex in HTML, absent in Markdown
            product = _live_post(pt, segs[-2])
            if product is None or product["path"] != full.rsplit("/", 1)[0] or (product["meta"] or {}).get("price") in (None, ""):
                abort(404)
            return render_template("checkout.html", post=product, crumbs=crumbs_for(product) + [("Checkout", full)],
                                   meta=seo.build_meta(title=f"Checkout — {product['title']}", path=full, robots="noindex,nofollow"),
                                   jsonld=[])
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
    # No URL, nothing to point a crawler at. This one test gates both the sitemap and llms.txt.
    return bool(post.get("path")) and not (post.get("seo") or {}).get("robots", "").startswith("noindex")


def _live_term_ids():
    q = db.table("post_terms").select("term_id, posts!inner(status, published_at)").eq("posts.status", "published").lte("posts.published_at", db.now_iso())
    return {r["term_id"] for r in db.rows(q)}


@pub.get("/media/<path:key>")
def media_file(key):
    """Every picture and PDF on the site comes through here. Supabase sits on the LAN and only this app
    is exposed, so the browser asks Flask and Flask asks Storage with the service-role key it already
    holds. The key is a uuid under YYYY/MM, so the bytes behind a URL never change: cache for a year and
    answer a repeat view with a 304. ?download=<name> is what media_download() appends — Storage used to
    turn that into a Content-Disposition, now we do.
    # ponytail: no server-side cache, so a cold client costs one Storage round trip per file. The
    # immutable year covers repeat views; put a CDN or a disk cache in front if that stops being enough."""
    mime = storage.EXT.get(PurePosixPath(key).suffix.lower())
    if not mime or ".." in key:
        abort(404)
    try:
        data = storage.fetch(key)
    except StorageApiError:  # the API answered and said no; a gateway that is down still raises a 500
        abort(404)
    # the name the file saves under. A newline would split the header; werkzeug quotes everything else,
    # and the name has to survive intact — "flash array.pdf" is what the editor uploaded.
    name = "".join(c for c in request.args.get("download", "") if c not in "\r\n")[:300]
    r = send_file(BytesIO(data), mimetype=mime, etag=key, conditional=True, max_age=31536000,
                  as_attachment=bool(name), download_name=name or None)
    r.cache_control.immutable = True
    if mime == "image/svg+xml":
        # An SVG is a document that can carry <script>, and this origin holds the admin session cookie —
        # a Storage URL was cross-origin and could not. Visited directly it now runs sandboxed, in an
        # opaque origin with scripts off; used as <img src> nothing changes, images never execute anyway.
        # Scoped to SVG on purpose: an empty sandbox on a PDF can stop the browser's own viewer.
        r.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return r


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
        # The .md twin, not the page: llms.txt is read by machines, and this saves them a hop
        # through the theme's HTML. The canonical URL is inside each twin's front matter.
        lines += [f"- [{p['title']}]({s['url']}{md_url(p['path'])}){': ' + p['excerpt'] if p['excerpt'] else ''}" for p in posts]
        lines.append("")
    lines += ["## Machine-readable", "- Any page as Markdown: add .md to its URL (the home page is /index.md)",
              f"- Full text: {s['url']}/llms-full.txt", f"- JSON API: {s['url']}/api/v1/posts", f"- Sitemap: {s['url']}/sitemap.xml"]
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@pub.get("/llms-full.txt")
def llms_full():
    s = seo.site()
    parts = [f"# {s['name']}\n{s['tagline']}\n"]
    for t, posts in _sections():
        for p in posts:
            parts.append(f"## {p['title']}\nType: {t['name']}\nURL: {s['url']}{p['path']}\n\n{p['excerpt']}\n\n{blocks_md(p['blocks'] or [], h1=False)}\n")
    return Response("\n---\n\n".join(parts), mimetype="text/plain")


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
    d["url"] = (seo.site()["url"] + post["path"]) if post["path"] else None
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
    b = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    b = b or {}
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
                                     "currency": "INR"})
    result = gateway().create_checkout(payment)
    if not request.is_json:  # a browser posting the checkout page's form follows the gateway
        return redirect(result.get("redirect_url") or "/", 303)
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
