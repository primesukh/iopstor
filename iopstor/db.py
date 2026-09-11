"""All data access: Supabase PostgREST over Kong with the service-role key (bypasses RLS).
No direct Postgres connection anywhere. Rows are plain dicts."""
import random
import re
import string
import unicodedata
from datetime import datetime, timedelta, timezone

from flask import current_app, g, has_request_context
from supabase import ClientOptions, create_client

from .throttle import client_ip

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


# ---- the audit log -------------------------------------------------------
# Every write in the app already funnels through insert()/update()/delete(), so the recording lives
# in them rather than at the thirty-odd call sites: a write path added later is logged without
# anybody remembering to log it. An after_request hook was the other candidate and it sees the
# response but not the row, so it could never answer "what was it before".

NOT_A_CHANGE = ("created_at", "updated_at",   # the moddatetime trigger moves one of these on every write
                "serial_key")                 # GENERATED ALWAYS: it moves with serial, and cannot be written back
# order matters: media has both filename and key, users both name and email, terms both name and slug
LABELS = ("title", "name", "filename", "email", "serial", "from_path", "slug", "key")


def _diff(before, after):
    """{field: [was, now]} for the fields that actually moved. One format for create (was=None),
    update and delete (now=None), which is what lets one template render all three and one Restore
    reverse any of them."""
    return {k: [before.get(k), after.get(k)] for k in set(before) | set(after)
            if k not in NOT_A_CHANGE and before.get(k) != after.get(k)}


def _label(row):
    """What to call this row on the audit screen. One tuple rather than a per-table map: every table
    here names itself with one of these columns, and the first match wins."""
    return next((str(row[k]) for k in LABELS if row.get(k)), "")


def _before(name, pk):
    """The row as it stands, for the diff. Skipped off a request, where nothing will be logged."""
    return (one(table(name).select("*").eq("id", pk)) or {}) if has_request_context() else {}


def _audit(action, name="", row_id="", changes=None, label="", user=None):
    """One row in audit_log. Silent outside a request context, which is exactly how `flask seed` and
    `flask import-media` stay out of the log.

    # ponytail: a failed audit write is swallowed, so the log can have a gap the log cannot report.
    # The alternative is worse: the content write has already succeeded by here, so raising would
    # show the editor an error for a save that did happen, and would stop the app running at all
    # against a database where 0008 has not been applied yet. Watch the warnings instead.
    """
    if not has_request_context():
        return
    try:
        u = user or getattr(g, "user", None) or {}
        table("audit_log").insert({"user_id": u.get("id"), "user_email": u.get("email") or "",
                                   "ip": client_ip(), "action": action, "table_name": name,
                                   "row_id": str(row_id), "label": label,
                                   "changes": changes or {}}).execute()
    except Exception as e:   # noqa: BLE001 - see the ceiling above; nothing here may break a save
        current_app.logger.warning("audit %s %s/%s not recorded: %s", action, name, row_id, e)


def audit_event(action, label="", user=None):
    """For the things that are not a row write at all -- signing in, signing out, getting the
    password wrong. `user` is passed in because g.user is not set yet at the moment of a login."""
    _audit(action, label=label, user=user)


def insert(name, row):
    created = table(name).insert(row).execute().data[0]
    _audit("create", name, created.get("id", ""), _diff({}, created), _label(created))
    return created


def update(name, pk, changes, action="update"):
    """`action` is a label for the log, not a different write: moving a post to the trash is an
    UPDATE, but the audit screen has to say "delete" or reading it means decoding a status pair."""
    before = _before(name, pk)
    data = table(name).update(changes).eq("id", pk).execute().data
    after = data[0] if data else None
    if after:
        _audit(action, name, pk, _diff(before, after), _label(after) or _label(before))
    return after


def delete(name, pk):
    """The delete every caller should use: the filter is not optional here, and the row is written
    to the audit log on its way out -- after it is gone, nothing else knows what row 12 was."""
    row = _before(name, pk)
    table(name).delete().eq("id", pk).execute()
    _audit("delete", name, pk, _diff(row, {}), _label(row))
    return row


def utcnow():
    return datetime.now(timezone.utc)


def now_iso():
    return utcnow().isoformat()


def parse_dt(value):
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# A fixed offset, not zoneinfo("Asia/Kolkata"): India has never observed daylight saving, so +05:30
# is exactly right for every date there will ever be -- and it does not need tzdata, which the slim
# container image does not ship.
IST = timezone(timedelta(hours=5, minutes=30))


def ist(value):
    """A stored UTC timestamp as the clock the editor was actually looking at. 24-hour, because an
    audit log is read for precision and an unlabelled am/pm is the wrong place to save four
    characters."""
    return f"{parse_dt(value).astimezone(IST):%d %b %Y, %H:%M} IST" if value else "\u2014"


def ist_input(value):
    """The same instant in the shape <input type="datetime-local"> wants. The pair with _as_ist()
    in admin_ui: the box shows IST and reads back IST, so a stored time round-trips unchanged."""
    return f"{parse_dt(value).astimezone(IST):%Y-%m-%dT%H:%M}" if value else ""


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
        before = settings()
        table("settings").upsert([{"key": k, "value": v} for k, v in values.items()]).execute()
        # one entry per key, not one for the whole form: the Settings screen posts all eleven keys
        # every time, and "which setting did they change" is the question the log is asked.
        for k, v in values.items():
            if before.get(k) != v:
                _audit("update", "settings", k, {"value": [before.get(k), v]}, k)
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
        # A type with has_pages=false has no URLs at all, and that one fact does the whole job:
        # resolve() matches a detail page by `post["path"] == full`, which None can never satisfy, so
        # it 404s without a rule of its own; _indexable() keeps it out of the sitemap and llms.txt;
        # and _card.html renders the card without a link. .get() so the app still runs against a
        # database where migration 0005 has not been applied yet.
        if not pt.get("has_pages", True):
            p["path"] = None
        elif not pt["url_prefix"] and p["parent_id"] is None and p["slug"] == "home":
            p["path"] = "/"  # the page with slug "home" is the site root
        else:
            parts = ([pt["url_prefix"]] if pt["url_prefix"] else []) + [r["slug"] for r in _chain(p)] + [p["slug"]]
            p["path"] = "/" + "/".join(parts)
    return posts


def hydrate(post):
    return with_paths([post])[0] if post else None


def tree(type_slug):
    """Top-level live posts of one type, each with p["children"] (live, ordered, with paths).
    One query, not two: the whole type comes back and the parent/child split happens here, which is
    also why a draft parent's children drop out — they are grouped under an id that is not a top.
    The header mega panel, the services archive and post_list(top_level) all want this same shape."""
    def load():
        pt = post_type(slug=type_slug)
        if pt is None:
            return []
        posts = with_paths(rows(live(select_posts()).eq("post_type_id", pt["id"])
                                .order("menu_order").order("published_at", desc=True)))
        kids = {}
        for p in posts:
            if p["parent_id"] is not None:
                kids.setdefault(p["parent_id"], []).append(p)
        tops = [p for p in posts if p["parent_id"] is None]
        for t in tops:
            t["children"] = kids.get(t["id"], [])
        return tops
    return _cached(f"tree_{type_slug}", load)


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
    # logged against the post, not as two writes to the join table: the editor ticked a category,
    # they did not delete four rows and insert five.
    before = ([r["term_id"] for r in rows(table("post_terms").select("term_id").eq("post_id", post_id))]
              if has_request_context() else [])
    table("post_terms").delete().eq("post_id", post_id).execute()
    if term_ids:
        table("post_terms").insert([{"post_id": post_id, "term_id": t} for t in term_ids]).execute()
    if sorted(before) != sorted(term_ids):
        # the title costs one more read, but only on a save that actually changed the categories,
        # and without it the entry reads "12 in posts" and names nothing
        _audit("update", "posts", post_id, {"terms": [before, list(term_ids)]},
               _label(one(table("posts").select("title").eq("id", post_id)) or {}))
    uncache("post_index_")


def paginate(q, page, per_page, transform=lambda x: x):
    """q must be a select(..., count='exact'). Returns the API list envelope."""
    res = q.range((page - 1) * per_page, page * per_page - 1).execute()
    return {"items": [transform(r) for r in res.data], "total": res.count or 0, "page": page, "per_page": per_page}


def get_media(pk):
    # per-request memo: the visual editor calls media_url()/media_alt() once per image per block swap
    return _cached(f"media_{pk}", lambda: one(table("media").select("*").eq("id", pk))) if pk else None


def admin_counts():
    """{post-type slug: n} for the admin sidebar, plus "_leads" = new leads. One query over posts,
    counted in Python: PostgREST has no GROUP BY, and one exact-count call per type would be eight
    round trips on every admin page.
    # ponytail: reads every post's type id per admin page. Swap for a counts view past a few thousand."""
    def load():
        seen = {}
        for r in rows(table("posts").select("post_type_id").neq("status", "trash").limit(5000)):
            seen[r["post_type_id"]] = seen.get(r["post_type_id"], 0) + 1
        out = {pt["slug"]: seen.get(pt["id"], 0) for pt in post_types()}
        out["_leads"] = table("leads").select("id", count="exact").eq("status", "new").limit(1).execute().count or 0
        return out
    return _cached("admin_counts", load)


def get_menu(slug):
    m = one(table("menus").select("*").eq("slug", slug))
    return m["items"] if m else []


def set_menu(slug, items):
    """The write side of get_menu(), so /admin/menus keeps every query in this module."""
    before = get_menu(slug)
    table("menus").upsert({"slug": slug, "name": slug.title(), "items": items}, on_conflict="slug").execute()
    if before != items:
        _audit("update", "menus", slug, {"items": [before, items]}, slug)
