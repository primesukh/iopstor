"""All data access: Supabase PostgREST over Kong with the service-role key (bypasses RLS).
No direct Postgres connection anywhere. Rows are plain dicts."""
import random
import re
import string
import unicodedata
from datetime import datetime, timezone

from flask import current_app, g
from supabase import ClientOptions, create_client

POST_SELECT = "*, post_type:post_types(*), featured_media:media(*), terms(*, taxonomy:taxonomies(*))"
POST_SELECT_BY_TERM = POST_SELECT + ", post_terms!inner(term_id)"  # + .eq("post_terms.term_id", id)


def _client(key):
    cfg = current_app.config
    return create_client(cfg["SUPABASE_URL"], key, ClientOptions(auto_refresh_token=False, persist_session=False))


def sb():
    """Service-role client, one per app. Never call auth.sign_in_* on it (that would swap its storage bearer)."""
    ext = current_app.extensions
    if "supabase" not in ext:
        ext["supabase"] = _client(current_app.config["SUPABASE_SERVICE_ROLE_KEY"])
    return ext["supabase"]


def anon():
    """Fresh anon client for password sign-in / refresh only."""
    return _client(current_app.config["SUPABASE_ANON_KEY"])


def table(name):
    return sb().table(name)


def rows(q):
    return q.execute().data


def one(q):
    data = q.limit(1).execute().data
    return data[0] if data else None


def insert(name, row):
    return table(name).insert(row).execute().data[0]


def update(name, pk, changes):
    data = table(name).update(changes).eq("id", pk).execute().data
    return data[0] if data else None


def utcnow():
    return datetime.now(timezone.utc)


def now_iso():
    return utcnow().isoformat()


def parse_dt(value):
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def slugify(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _cached(key, loader):
    if not hasattr(g, key):
        setattr(g, key, loader())
    return getattr(g, key)


def uncache(*keys):
    for k in keys:
        g.pop(k, None)


# ---- post types & settings -------------------------------------------------

def post_types():
    return _cached("post_types", lambda: rows(table("post_types").select("*").order("id")))


def post_type(**match):
    """post_type(slug="post") / post_type(id=3) / post_type(url_prefix="blog")"""
    return next((t for t in post_types() if all(t.get(k) == v for k, v in match.items())), None)


def settings():
    return _cached("settings", lambda: {r["key"]: r["value"] for r in rows(table("settings").select("*"))})


def set_settings(values):
    if values:  # PostgREST rejects an empty bulk upsert
        table("settings").upsert([{"key": k, "value": v} for k, v in values.items()]).execute()
    uncache("settings")


# ---- posts ---------------------------------------------------------------

def live(q):
    """Public visibility filter: published and not scheduled for later."""
    return q.eq("status", "published").lte("published_at", now_iso())


def select_posts(count=None):
    return table("posts").select(POST_SELECT, count=count)


def get_post(pk):
    return one(select_posts().eq("id", pk))


def is_live(post):
    return post["status"] == "published" and bool(post["published_at"]) and parse_dt(post["published_at"]) <= utcnow()


def _index(type_id):
    """id → {slug, parent_id, title} for one hierarchical post type (all statuses, so draft parents still route)."""
    def load():  # ponytail: assumes < 2000 posts per hierarchical type; paginate here if that ever breaks
        return {r["id"]: r for r in rows(table("posts").select("id,slug,parent_id,title").eq("post_type_id", type_id).limit(2000))}
    return _cached(f"post_index_{type_id}", load)


def _chain(post):
    if not post["post_type"]["hierarchical"] or not post["parent_id"]:
        return []
    index, chain, pid = _index(post["post_type_id"]), [], post["parent_id"]
    while pid and pid in index and len(chain) < 10:
        chain.append(index[pid])
        pid = index[pid]["parent_id"]
    return chain[::-1]


def ancestors(post):
    """[(title, path), ...] from the root ancestor down to the parent."""
    prefix = post["post_type"]["url_prefix"]
    parts, out = ([prefix] if prefix else []), []
    for r in _chain(post):
        parts.append(r["slug"])
        out.append((r["title"], "/" + "/".join(parts)))
    return out


def with_paths(posts):
    for p in posts:
        pt = p["post_type"]
        if not pt["url_prefix"] and p["parent_id"] is None and p["slug"] == "home":
            p["path"] = "/"  # the page with slug "home" is the site root
        else:
            parts = ([pt["url_prefix"]] if pt["url_prefix"] else []) + [r["slug"] for r in _chain(p)] + [p["slug"]]
            p["path"] = "/" + "/".join(parts)
    return posts


def hydrate(post):
    return with_paths([post])[0] if post else None


def unique_slug(post_type_id, base, exclude_id=None):
    """base if it is free, else base-xyz. Three random letters rather than -2: a second "Testing" is a
    different page, not the second part of one, and the suffix does not leak how many there are."""
    taken = {r["slug"] for r in rows(table("posts").select("id,slug").eq("post_type_id", post_type_id).like("slug", f"{base}%")) if r["id"] != exclude_id}
    slug = base
    while slug in taken:   # ponytail: 17576 combinations, so the retry is the collision handler, not a hot path
        slug = f"{base}-{''.join(random.choices(string.ascii_lowercase, k=3))}"
    return slug


def ensure_term(tax_slug, name):
    """Id of the term called `name` in this taxonomy, creating the row the first time. Matched on the
    slug, like every other name here, so "All-Flash" and "all flash" are the same term rather than
    two. None if the taxonomy does not exist."""
    tax = one(table("taxonomies").select("id").eq("slug", tax_slug))
    if tax is None:
        return None
    slug = slugify(name)
    row = one(table("terms").select("id").eq("taxonomy_id", tax["id"]).eq("slug", slug))
    return (row or insert("terms", {"taxonomy_id": tax["id"], "slug": slug, "name": name[:200]}))["id"]


def set_post_terms(post_id, term_ids):
    table("post_terms").delete().eq("post_id", post_id).execute()
    if term_ids:
        table("post_terms").insert([{"post_id": post_id, "term_id": t} for t in term_ids]).execute()
    uncache("post_index_")


def paginate(q, page, per_page, transform=lambda x: x):
    """q must be a select(..., count='exact'). Returns the API list envelope."""
    res = q.range((page - 1) * per_page, page * per_page - 1).execute()
    return {"items": [transform(r) for r in res.data], "total": res.count or 0, "page": page, "per_page": per_page}


def get_media(pk):
    # per-request memo: the visual editor calls media_url()/media_alt() once per image per block swap
    return _cached(f"media_{pk}", lambda: one(table("media").select("*").eq("id", pk))) if pk else None


def get_menu(slug):
    m = one(table("menus").select("*").eq("slug", slug))
    return m["items"] if m else []
