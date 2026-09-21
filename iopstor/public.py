"""Public site: catch-all page resolver, SEO endpoints (sitemap/robots/llms/feed), and the read-only JSON API."""
import json
import textwrap
import threading
import time
from collections import OrderedDict
from datetime import date
from email.utils import format_datetime
from io import BytesIO
from pathlib import PurePosixPath

from flask import Blueprint, Response, abort, g, jsonify, redirect, render_template, request, send_file
from markupsafe import escape
from postgrest import APIError
from storage3.exceptions import StorageApiError
from werkzeug.exceptions import HTTPException

from . import db, seo, storage
from .admin_api import _http_error, _pg_error, page_args
from .blocks import ARTICLE_TYPES, OWN_HEAD_BLOCKS, blocks_md, blocks_text, details_at, owns_head, render_blocks
from .payments import GATEWAYS, gateway
from .seo import md_url

pub = Blueprint("public", __name__)
api = Blueprint("public_api", __name__, url_prefix="/api/v1")
api.register_error_handler(HTTPException, _http_error)
api.register_error_handler(APIError, _pg_error)

PUBLIC_SETTINGS = ("site_name", "tagline", "logo_url", "social_links", "contact_email", "contact_phone", "address")


# ---- the page cache ---------------------------------------------------------
# The public site renders identical bytes for every visitor: measured, one home page cost 29
# PostgREST round trips and 219 ms, i.e. 4.6 renders a second per thread, and ten thousand people
# browsing at once needs a few hundred views a second. Even with every query answered from memory
# the render alone is ~28 ms, so the answer cannot be a faster render -- it has to be no render.
#
# Two layers do that. This one holds the finished page in the worker process, so a repeat view is a
# dict lookup. The Cache-Control header set below hands the same job to Cloudflare, which is what
# takes the traffic off the box altogether; this layer still matters because the Dokploy/Traefik LAN
# ingress does not go through Cloudflare, and a cold edge would otherwise arrive here all at once.
#
# Freshness is not on a timer. db.bump_epoch() touches one file on /dev/shm on every write and a
# stale entry is dropped the moment its stamp is older, so the origin is never behind -- only the
# edge is, for its s-maxage. The TTL below is just a backstop.
# ponytail: a dict per worker, so thirty workers each render a cold page once rather than once
# between them. A shared cache would fix that and would also be another service to run on a box
# that is already short of cores.

PAGE_TTL = 30       # seconds; backstop only, the epoch is what actually invalidates
PAGE_MAX = 512      # entries; campaign ?utm_* junk must not grow this without bound
EDGE_TTL = 60       # seconds a shared cache may serve a page for -- agreed with the client
FEED_MAX = 40       # items in /feed.xml
_page_cache = OrderedDict()     # key -> (expires, epoch, body, content_type)
_refreshing = set()             # keys some thread is already re-rendering
_refresh_lock = threading.Lock()


def _cache_key():
    """The page resolver only. /media/<key> is on this same blueprint and serves files up to
    MAX_CONTENT_LENGTH (20 MB), so this is an allow-list on purpose, not a list of exclusions."""
    if request.endpoint != "public.resolve" or request.method not in ("GET", "HEAD"):
        return None
    if "sn" in request.args:                                # warranty_check answers per serial
        return None
    if request.path.rstrip("/").endswith("/checkout"):      # a form, and it is noindex anyway
        return None
    return request.full_path            # path + query, so ?page=2 is its own entry


@pub.before_request
def _page_cache_read():
    g.page_key = key = _cache_key()
    hit = _page_cache.get(key) if key else None
    if hit is None:
        return None
    expires, epoch, body, ctype = hit
    if expires > time.time() and epoch >= db.content_epoch():
        g.page_cached = True
        return Response(body, content_type=ctype)
    # Stale. One caller re-renders and the rest keep reading the old copy until it does, so a
    # lapsed entry on a busy page cannot become 240 simultaneous renders of the same page.
    with _refresh_lock:
        if key in _refreshing:
            g.page_cached = True
            return Response(body, content_type=ctype)
        _refreshing.add(key)
        g.page_refreshing = True
    return None


@pub.after_request
def _public_cache_headers(resp):
    """Store the render, and tell shared caches they may serve it. max-age=0 keeps the visitor's own
    browser revalidating -- they get a fresh page on every click -- while s-maxage lets Cloudflare
    answer from the edge, which is the whole point. stale-while-revalidate means the edge refreshes
    in the background instead of making somebody wait for it."""
    key = getattr(g, "page_key", None)
    if key and not getattr(g, "page_cached", False):
        storable = (resp.status_code == 200 and not resp.headers.get("Set-Cookie")
                    and not resp.direct_passthrough)
        with _refresh_lock:     # the whole store, so a concurrent trim cannot evict what we reinsert
            if storable:
                _page_cache.pop(key, None)      # reinsert rather than move_to_end: another thread's
                _page_cache[key] = (time.time() + PAGE_TTL, db.content_epoch(),
                                    resp.get_data(), resp.content_type)   # trim may have evicted it
                while len(_page_cache) > PAGE_MAX:
                    _page_cache.popitem(last=False)
            elif resp.status_code < 500:
                # A definitive non-200 -- the page was trashed, unpublished, or is now a redirect.
                # Without this the old 200 stays and every CONCURRENT request keeps being served the
                # page that no longer exists, which is exactly the traffic shape this cache is for.
                # 5xx is left alone on purpose: a pool-exhausted database should go on serving the
                # last good copy rather than replacing a working site with an error.
                _page_cache.pop(key, None)
    if request.method in ("GET", "HEAD") and resp.status_code == 200 and not resp.headers.get("Set-Cookie") \
            and "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = f"public, max-age=0, s-maxage={EDGE_TTL}, stale-while-revalidate=300"
    return resp


@pub.teardown_request
def _page_cache_release(exc=None):
    """In teardown, not after_request: an unhandled exception skips after_request, and a key left in
    the set would pin that page's stale copy until the worker restarts."""
    if getattr(g, "page_refreshing", False):
        _refreshing.discard(g.page_key)


# The glyph beside each service in the header panel, keyed by slug. These are the design's own
# seventeen item icons and five group icons (`assets/icons.js` in the client's design project,
# 2026-09-21), and the ids match the <symbol>s in base.html's sprite. This is presentation, not
# content: a service whose slug is not here -- a new one, or a renamed one -- gets `dot` and the
# menu still reads correctly, and an editor overrides any of them by typing one of these names
# into the service's **Icon** box.
# ponytail: a slug map rather than 22 rows of content. Set meta.icon on every service and delete it.
SERVICE_ICONS = {
    "storage": "g-storage", "hyper-converged-media": "g-hcm", "cloud": "g-cloud",
    "ai": "g-ai", "software-based": "g-soft",
    "nas": "nas", "das": "das", "sas": "sas", "aws-integration-dr": "aws",
    "proxmox": "proxmox", "vmware": "vmware",
    "desktop-as-a-service": "daas", "storage-as-a-service": "staas", "vps": "vps",
    "linux-containers": "lxc", "serverless": "serverless", "s3-bucket-solutions": "s3",
    "disaster-recovery-as-a-service-draas": "draas", "on-prem-ai-servers": "ai",
    "sql-server": "sql", "tally": "tally", "sap": "sap",
}
ICON_IDS = frozenset(SERVICE_ICONS.values()) | {"dot"}


def service_icon(post):
    """Which <symbol> one service points at. The editor's Icon box wins when it names one we ship,
    otherwise the design's own choice for that slug, otherwise a neutral dot. Whitelisted either
    way, because the value lands in a `use href="#svc-..."` attribute -- the same rule
    section_class() follows for anything an editor types that reaches markup."""
    want = ((post.get("meta") or {}).get("icon") or "").strip().lower()
    return want if want in ICON_IDS else SERVICE_ICONS.get(post.get("slug"), "dot")


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
    # the icon is attached here rather than worked out in Jinja, so the whitelist is one function.
    # db.tree() is memoised per request and shared with the archive and post_list; adding a key it
    # does not read is safe, and doing it twice writes the same value.
    for g in groups:
        g["icon"] = service_icon(g)
        for c in g["children"]:
            c["icon"] = service_icon(c)
    return {"url": "/" + pt["url_prefix"], "groups": groups} if groups else None


@pub.app_context_processor
def _template_globals():
    # service_nav stays a callable, not a value: this processor is app-wide, and an /admin page has
    # no use for a posts query.
    return {"site": seo.site(), "menu": db.get_menu, "render_blocks": render_blocks,
            "details_at": details_at, "owns_head": owns_head, "article_types": ARTICLE_TYPES,
            "own_head_blocks": OWN_HEAD_BLOCKS,
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
    """Live posts as one Markdown list, each line pointing at its own .md twin.

    _indexable(), not just `path`: this renders an archive's twin AND the "Related pages" list inside a
    post's twin, both of which a crawler reads, so a noindex page linked from here would be handed the
    very address it asked to be left out of. The HTML page keeps listing it -- _kids() is untouched --
    because noindex means do not index, not do not link."""
    return "\n".join(f"- [{p['title']}]({md_url(p['path'])})" + (f": {p['excerpt']}" if p.get("excerpt") else "")
                     for p in posts if _indexable(p))


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
    """One post as a Markdown document, with exactly one top-level `#` however the page is built.

    Two separate questions, and conflating them is the trap. `owns_head()` decides whether the HTML
    page draws its own title, and is passed on to blocks_md() so a hero that is not the page's
    heading writes `###` instead of `#` -- a hero further down used to open a second `#` under this
    one on every type. Whether THIS function writes the title is the narrower question of whether a
    hero is about to, and only a `hero` ever does: blocks_md() gives a `columns` block `##`. So a
    columns-led page keeps its `#` here even though its HTML has no `<h1>` at all -- that is a real
    defect in the page, and making the twin match it would only lose the heading twice."""
    pt, blocks = post["post_type"], post.get("blocks") or []
    own_head = owns_head(pt["slug"], blocks)
    hero_owns_h1 = not own_head and bool(blocks) and blocks[0].get("type") == "hero"
    parts = [] if hero_owns_h1 else [f"# {post['title']}", post.get("excerpt") or ""]
    parts += _md_fields(pt, post.get("meta") or {}) + [blocks_md(blocks, h1=not own_head)]
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


def _archive_type(tax, posts):
    """Which post type a TERM archive is an archive of. A term archive is the only one that does not
    arrive knowing, and everything downstream keys off it: the head's band, the pl-<type> card rules
    and the chip row (`_filters`) all read `pt`, and the breadcrumb needs a real archive to point at.

    The posts are the truth and are free -- POST_SELECT_BY_TERM embeds each post's own post_type --
    so a `category` holding products is a Products archive and one holding blog posts is a Blog
    archive, which is the only taxonomy where the declaration is ambiguous (post AND product both
    claim it). An EMPTY term has nothing to ask, so it falls back to whichever type declares the
    taxonomy; and a taxonomy nothing declares gets None, which drops the crumb rather than pointing
    it somewhere untrue.
    # ponytail: a genuinely MIXED term styles as the type it has more of -- pl-<type> is on the
    # container and the whole .pl-* group is ancestor-scoped. No content can reach it today.
    """
    seen = [p["post_type"] for p in (posts or []) if p.get("post_type")]
    slugs = {t["slug"] for t in seen}
    if len(slugs) == 1:
        return seen[0]
    if seen:
        top = max(slugs, key=lambda sl: sum(1 for t in seen if t["slug"] == sl))
        return next(t for t in seen if t["slug"] == top)
    return next((t for t in db.post_types() if tax and tax["slug"] in (t.get("taxonomies") or [])), None)


def render_archive(q, title, path, crumbs, description="", pt=None, tax=None):
    """q: a live select_posts(count='exact') query, already filtered.

    `tax` marks this as a term archive: `pt` is then worked out from the posts below rather than
    handed in, and the middle crumb is built here for the same reason -- the answer needs the page
    of posts, which does not exist until paginate() has run."""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("menu_order").order("published_at", desc=True), page, 20)
    if page > 1 and not result["items"]:
        abort(404)
    meta = seo.build_meta(title=title, description=description, path=path, robots="index,follow" if page == 1 else "noindex,follow")
    has_next = page * 20 < result["total"]
    # description was built into meta but never reached the template, so archive.html's lead
    # paragraph could not render and every term archive's prose was invisible.
    posts = db.with_paths(result["items"])
    if tax is not None:
        pt = _archive_type(tax, posts)
        # Home / Case Studies / Finance. It used to be Home / Industry / Finance, and "/industry"
        # is served by nothing -- a 404 in the breadcrumb and, through seo.jsonld(), in the
        # BreadcrumbList handed to Google (design.md, known since 2026-09-15). jsonld() iterates
        # this same list, so there is nothing to change in seo.py.
        mid = [(pt["name"], "/" + pt["url_prefix"])] if pt and pt.get("url_prefix") else []
        crumbs = [crumbs[0]] + mid + [crumbs[-1]]
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
    # ponytail: "index" is taken by routing order (the home page's twin), like "checkout" further
    # down. Neither is in db.RESERVED_SEGMENTS, which is about segments the app owns outright.
    if path.endswith(".md"):
        path = "" if path == "index.md" else path[:-3]
    full = "/" + path
    r = db.redirect_for(full)
    if r:
        # ponytail: the hit counter is now approximate in a second way -- `hits` comes from the
        # per-worker cache, so within one cache generation every visit writes back the same number.
        # It was already lossy under parallel visits, and nothing reads the column. A bump_redirect(id)
        # SQL function called via .rpc() makes it exact if it is ever reported on.
        # Not db.update(): this fires on an anonymous page view, and a hit counter is not a step
        # anybody took, so an audit entry per visit would bury the log it was meant to fill.
        db.table("redirects").update({"hits": r["hits"] + 1}).eq("id", r["id"]).execute()
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
        # Checkout is a page, not a modal: site.js drives the sliding row and nothing else. Handled here rather
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
            # the middle crumb is render_archive's to build: it needs the posts to know the type
            crumbs = [("Home", "/"), (term["name"], full)]
            return render_archive(q, term["name"], full, crumbs, term["description"], tax=tax)
    abort(404)


# ---- crawler endpoints -----------------------------------------------------

def _noindex(seo_field):
    """Does this SEO robots value say noindex? `robots` is a free-text box whose own hint reads
    "e.g. noindex,follow", so an editor writes `NOINDEX` or `nofollow,noindex` as readily as the
    expected spelling -- and a plain startswith() let both of those render a noindex page that stayed
    in the sitemap, which is the failure the field exists to prevent."""
    return "noindex" in {t.strip() for t in str(seo_field or "").lower().split(",")}


def _indexable(post):
    """The one gate. Everything a crawler can read comes through here: sitemap.xml, llms.txt,
    llms-full.txt, the feed, every .md twin and the lists inside them.

    Three questions, and the third is the one that is easy to miss. A path we do not own is worse than
    no path: /admin and /api belong to the app, so a page an editor slugged "admin" cannot load at all,
    and publishing its address tells every crawler where the CMS lives. reserved() refuses new ones at
    save time; this keeps any that predate that rule out of everything a crawler reads."""
    path = post.get("path")
    return bool(path) and not db.reserved(path) and not _noindex((post.get("seo") or {}).get("robots"))


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
        if t["url_prefix"] and not db.reserved(t["url_prefix"]):
            urls[f"{base}/{t['url_prefix']}"] = None
    posts = db.rows(db.live(db.select_posts()).in_("post_type_id", [t["id"] for t in types]).order("id").limit(5000))  # ponytail: single sitemap, <5000 urls
    for p in db.with_paths(posts):
        if _indexable(p):
            urls[base + p["path"]] = p["updated_at"]
    live_terms = _live_term_ids()
    # The archive prefixes above and the term archives here are the two URL sources that are not posts,
    # so _indexable() never sees them and each needs the reserved test itself.
    for term in db.rows(db.table("terms").select("slug, id, taxonomy:taxonomies(slug)")):
        if term["id"] in live_terms and not db.reserved(term["taxonomy"]["slug"]):
            urls[f"{base}/{term['taxonomy']['slug']}/{term['slug']}"] = None
    body = "".join(f"<url><loc>{escape(u)}</loc>{f'<lastmod>{m[:10]}</lastmod>' if m else ''}</url>" for u, m in urls.items())
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', mimetype="application/xml")


@pub.get("/robots.txt")
def robots():
    s = seo.site()
    # No Disallow naming the admin. It protected nothing -- /admin answers 404 to anything outside
    # ADMIN_NETWORKS, so there is no page for a crawler to index -- while robots.txt is world-readable
    # and the first file a scanner fetches, which made those two lines the only public statement that
    # this site has an admin at all (user, 2026-09-15). robots_extra still appends whatever the client
    # wants by hand.
    lines = ["User-agent: *", "Allow: /", s["robots_extra"], f"Sitemap: {s['url']}/sitemap.xml"]
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


def _summary(post, limit=400):
    """The sentence a feed reader shows under the headline: what the editor wrote for search engines,
    then the excerpt, then the beginning of the page, then the type's own long fields.

    Deliberately not build_meta()'s chain, which ends at the site tagline. That is right for one page
    in <head> and wrong here -- it would give forty items the same sentence. Ending at the content
    instead is what stops the empty <description/> an excerpt-less post used to ship.

    The last step exists because a case study keeps its prose in meta, not in blocks: its challenge
    and its results ARE the post, and blocks_text() of it is "". `textarea` is the same test
    _md_fields() uses to decide a field is long enough to be a section of its own -- a `text` field
    like Client is a label, and "LKS" is not a summary of anything.

    Still empty is a real answer: a post with no excerpt, no body and no fields has nothing to say,
    and inventing a sentence for it would be worse than the blank a reader already handles."""
    fields = post["post_type"].get("field_schema") or []
    meta = post.get("meta") or {}
    text = ((post.get("seo") or {}).get("description") or post.get("excerpt")
            or blocks_text(post.get("blocks") or [])
            or " ".join(str(meta.get(f["key"]) or "") for f in fields if f.get("type") == "textarea"))
    return textwrap.shorten(text, limit, placeholder=" …") if text.strip() else ""


def _feed_item(post, s):
    """One <item>. post_type, featured_media and terms are already embedded by db.POST_SELECT, so a
    richer item costs no extra query."""
    media = post.get("featured_media") or {}
    parts = [f"<title>{escape(post['title'])}</title>",
             f"<link>{s['url']}{post['path']}</link>",
             # isPermaLink is the default, but saying it lets a reader treat the URL as the identity
             # rather than guessing. The path never changes, so the item is stable across rebuilds.
             f'<guid isPermaLink="true">{s["url"]}{post["path"]}</guid>',
             f"<pubDate>{format_datetime(db.parse_dt(post['published_at']))}</pubDate>",
             # The organisation, not a person: author names are not in POST_SELECT and embedding them
             # would touch every query on the site. jsonld() credits the same way (author=org).
             f"<dc:creator>{escape(s['name'])}</dc:creator>",
             f"<description>{escape(_summary(post))}</description>",
             f"<category>{escape(post['post_type']['name'])}</category>"]
    parts += [f'<category domain="{escape(t["taxonomy"]["slug"])}">{escape(t["name"])}</category>'
              for t in post.get("terms") or [] if t.get("taxonomy")]
    if media.get("url") and media.get("mime"):
        # length is required by the RSS spec and readers do read it; media.size is the byte count
        # storage.save_upload() recorded.
        parts.append(f'<enclosure url="{escape(seo._abs(media["url"], s["url"]))}" type="{escape(media["mime"])}"'
                     f' length="{int(media.get("size") or 0)}"/>')
    return "<item>" + "".join(parts) + "</item>"


@pub.get("/feed.xml")
def feed():
    """The site's news, not the blog's. Which types count is a row -- post_types.in_feed, beside
    in_sitemap -- because a content type is a row here and "is this news" is a property of one. The
    default while the column does not exist yet is the blog alone, which is what this used to do."""
    s = seo.site()
    types = [t for t in db.post_types() if t.get("in_feed", t["slug"] == "post")]
    posts = []
    if types:
        # Fetch past the cap and cut after filtering: _indexable() used to run on an already-truncated
        # 20, so one noindex post quietly shortened the feed.
        # ponytail: over-fetch 2x rather than loop. FEED_MAX noindex posts in a row would still come
        # up short; page the query if that ever happens.
        q = db.live(db.select_posts()).in_("post_type_id", [t["id"] for t in types]).order("published_at", desc=True).limit(FEED_MAX * 2)
        posts = [p for p in db.with_paths(db.rows(q)) if _indexable(p)][:FEED_MAX]   # the feed is a crawler surface like any other
    built = max([db.parse_dt(p["updated_at"]) for p in posts], default=db.utcnow())
    image = (f"<image><url>{escape(seo._abs(s['logo'], s['url']))}</url><title>{escape(s['name'])}</title>"
             f"<link>{s['url']}/</link></image>") if s["logo"] else ""
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<channel><title>{escape(s["name"])}</title><link>{s["url"]}/</link>'
           f'<description>{escape(s["tagline"])}</description><language>en</language>'
           f"<lastBuildDate>{format_datetime(built)}</lastBuildDate>"
           f'<atom:link href="{s["url"]}/feed.xml" rel="self" type="application/rss+xml"/>'
           f'{image}{"".join(_feed_item(p, s) for p in posts)}</channel></rss>')
    # application/xml, not application/rss+xml, so a browser renders it instead of downloading it.
    # No browser has had a feed viewer since Firefox 64 dropped its own, and a type none of them
    # renders is treated as a file to save -- clicking "RSS" in the footer downloaded feed.xml.
    # sitemap.xml has always answered application/xml for the same reason and has never been
    # reported. Feed readers are unaffected: they parse the body, and the type they discover the
    # feed BY is the <link rel="alternate" type="application/rss+xml"> in base.html, unchanged.
    # ponytail: no XSLT stylesheet to make it a designed page -- Chrome removes XSLT on 2026-11-17
    # and Firefox and WebKit have said they will follow, so it would break inside two months. The
    # human-readable version of this list is the /blog archive, which already exists.
    return Response(xml, mimetype="application/xml")


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
    # ponytail: a honeypot is the whole bot defence. When spam gets through, the rate limit belongs at
    # Cloudflare -- a WAF rule on this path -- rather than here: the edge sees the real client IP,
    # while client_ip() sees only what TRUSTED_PROXIES tells it to believe, and getting that wrong
    # would cap the contact form for every visitor at once (the ADMIN_NETWORKS failure again).
    if b.get("website"):
        return _form_redirect(b) or (jsonify(ok=True), 201)
    name, email = str(b.get("name") or "").strip(), str(b.get("email") or "").strip()
    if not name or "@" not in email:
        abort(400, "name and email required")
    post_id = int(b["post_id"]) if str(b.get("post_id") or "").isdigit() else None
    if post_id and db.one(db.table("posts").select("id").eq("id", post_id)) is None:
        post_id = None
    known = {"name", "email", "phone", "company", "message", "kind", "post_id", "website", "back"}
    # Every stored field is capped, including the ones nobody named: db.insert() writes the whole row
    # a second time into audit_log, which is append-only by trigger with no retention job, so an
    # uncapped body is stored twice and neither copy can be deleted. MAX_CONTENT_LENGTH is 20 MB
    # because an upload needs it, which is not a bound a public form should inherit. `known` is
    # filtered out before the 20 are counted, so the fields the endpoint reads by name never spend
    # that budget -- the site's own forms add two keys to `data` (interest, users), well inside it.
    extra = {k: str(v)[:200] for k, v in b.items() if k not in known}
    lead = db.insert("leads", {
        "kind": b.get("kind") if b.get("kind") in ("contact", "quote", "career") else "contact", "name": name[:200], "email": email[:300],
        "phone": str(b.get("phone") or "")[:50], "company": str(b.get("company") or "")[:200], "message": str(b.get("message") or "")[:5000],
        "post_id": post_id, "data": dict(list(extra.items())[:20])})
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
