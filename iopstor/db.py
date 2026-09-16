"""All data access: Supabase PostgREST over Kong with the service-role key (bypasses RLS).
No direct Postgres connection anywhere. Rows are plain dicts."""
import os
import random
import re
import string
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from flask import current_app, g, has_app_context, has_request_context
from postgrest import APIError
from supabase import ClientOptions, create_client

from .throttle import client_ip

POST_SELECT = "*, post_type:post_types(*), featured_media:media(*), terms(*, taxonomy:taxonomies(*))"
POST_SELECT_BY_TERM = POST_SELECT + ", post_terms!inner(term_id)"  # + .eq("post_terms.term_id", id)


# The library waits two minutes on a PostgREST call by default, while gunicorn kills a worker at
# thirty seconds -- so a Supabase that is merely slow parked eight threads per worker until the
# worker was killed mid-request, turning a slow database into a dead site. Fifteen seconds is far
# longer than any query here (the widest is the sitemap's 5000 rows) and safely inside gunicorn's
# timeout, so overload now fails fast enough to shed load instead of swallowing the pool.
# ponytail: a constant, not an env key -- it would have to join docker-compose's x-app-env and the
# test that walks it, and nobody has needed to tune it. STRESS_DB is a constant for the same reason.
PGRST_TIMEOUT = 15


def _client(key):
    cfg = current_app.config
    return create_client(cfg["SUPABASE_URL"], key, ClientOptions(
        auto_refresh_token=False, persist_session=False, postgrest_client_timeout=PGRST_TIMEOUT))


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


def _audit(action, name="", row_id="", changes=None, label="", user=None, system=False, ip=None):
    """One row in audit_log. Silent outside a request context, which is exactly how `flask seed` and
    `flask import-media` stay out of the log -- they write content, reproducibly and with no actor.

    `ip` is passed in for the same reason `user` is: a finished editing session (flush_sessions())
    is written inside whatever request happened to notice it had gone stale, which is usually another
    editor's. Taking either from the current request would record the wrong person.

    `system=True` is the one exception, for `flask create-admin`: creating a credential that can sign
    in and change anything is not content, and a log that cannot say where an admin account came from
    has a hole in the place it exists to cover. It has to skip client_ip() as well as the guard --
    that reads `request`, and off a request it would raise straight into the except below and write
    nothing at all, which is the silent gap this is closing.

    # ponytail: a failed audit write is swallowed, so the log can have a gap the log cannot report.
    # The alternative is worse: the content write has already succeeded by here, so raising would
    # show the editor an error for a save that did happen, and would stop the app running at all
    # against a database where 0008 has not been applied yet. Watch the warnings instead.
    """
    if not has_request_context() and not system:
        return
    # The live tests run against the real Supabase, and audit_log is append-only by trigger -- so
    # every suite run would leave rows in the client's Activity screen that the cleanup fixture is
    # not allowed to remove. throttle._off() sits out of TESTING for the same shape of reason.
    if current_app.config.get("TESTING"):
        return
    try:
        u = user or (getattr(g, "user", None) if has_request_context() else None) or {}
        table("audit_log").insert({"user_id": u.get("id"), "user_email": u.get("email") or "",
                                   "ip": ip if ip is not None else (client_ip() if has_request_context() else "command line"),
                                   "action": action, "table_name": name,
                                   "row_id": str(row_id), "label": label,
                                   "changes": changes or {}}).execute()
    except Exception as e:   # noqa: BLE001 - see the ceiling above; nothing here may break a save
        current_app.logger.warning("audit %s %s/%s not recorded: %s", action, name, row_id, e)


def audit_event(action, label="", user=None, system=False, name="", row_id="", changes=None):
    """For the things that are not a row write at all -- signing in, signing out, getting the
    password wrong, being locked out, throwing away unpublished edits. `user` is passed in because
    g.user is not set yet at the moment of a login; `name`/`row_id` because an act that changed no
    row of ours can still be ABOUT one, and without them the Activity screen cannot name the page
    (_post_context() looks the post up by row_id)."""
    _audit(action, name=name, row_id=row_id, changes=changes, label=label, user=user, system=system)


def insert(name, row):
    created = table(name).insert(row).execute().data[0]
    _audit("create", name, created.get("id", ""), _diff({}, created), _label(created))
    bump_epoch()
    return created


def update(name, pk, changes, action="update", if_unchanged=None):
    """`action` is a label for the log, not a different write: moving a post to the trash is an
    UPDATE, but the audit screen has to say "delete" or reading it means decoding a status pair.

    `if_unchanged` is the row's `updated_at` as the caller last saw it, and it goes into the
    UPDATE's own filter -- never into a comparison here. Postgres then decides, atomically, whether
    this writer still has the row it thinks it has; ~30 gunicorn workers share no memory, so a
    read-then-compare in Python would be the race it is meant to catch. No rows back means somebody
    else saved first, and `None` is already what a vanished row returns, so nothing downstream has
    to learn a new shape -- a conflict also writes no audit row for free, because `_audit` already
    sits behind `if after:`. The moddatetime trigger keeps `updated_at` current (0001), which is
    what makes it a version token nobody has to maintain.

    Callers that deliberately do NOT pass it, so nobody "fixes" them later: the JSON API's
    PATCH /posts/<id> and `flask seed --reset-content` are machine callers with no screen to warn,
    and **`/admin/audit/<pk>/restore` is an intentional overwrite of whatever is there now** -- that
    is the whole point of the button. The column is `updated_at` on purpose and not a parameter:
    it is the only version token that exists today, and a second one can add the argument when it
    has a second caller."""
    before = _before(name, pk)
    q = table(name).update(changes).eq("id", pk)
    if if_unchanged:
        q = q.eq("updated_at", if_unchanged)
    data = q.execute().data
    after = data[0] if data else None
    if after:
        _audit(action, name, pk, _diff(before, after), _label(after) or _label(before))
        bump_epoch()
    return after


def delete(name, pk):
    """The delete every caller should use: the filter is not optional here, and the row is written
    to the audit log on its way out -- after it is gone, nothing else knows what row 12 was."""
    row = _before(name, pk)
    table(name).delete().eq("id", pk).execute()
    _audit("delete", name, pk, _diff(row, {}), _label(row))
    bump_epoch()
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


# The first segment of a URL belongs to the app, not to content: /admin is the CMS, /api its two APIs,
# /media the file proxy, /static and /healthz Flask's own. Flask matches a blueprint's static prefix
# before public.py's catch-all, so a page that claims one of these is not merely wrong in the sitemap --
# it can never load at all, which is how a page slugged "admin" used to save cleanly and then 404 for
# ever with nothing to say why. Two readers: reserved() refuses it on save, and _indexable() keeps
# anything that slipped in before out of every crawler-facing output.
RESERVED_SEGMENTS = frozenset({"admin", "api", "media", "static", "healthz"})


def reserved(value):
    """Is this word, or the first segment of this path, one of the app's own?

    Takes a bare slug ("admin"), a url_prefix ("api/v1") or a built path ("/admin/thing"), because the
    three callers hold it in those three shapes and normalising here beats remembering at each."""
    first = str(value or "").strip("/").split("/")[0].strip().lower()
    return first in RESERVED_SEGMENTS


def _cached(key, loader):
    if not hasattr(g, key):
        setattr(g, key, loader())
        g._cache_keys = getattr(g, "_cache_keys", set()) | {key}
    return getattr(g, key)


def uncache(*keys):
    for k in keys:
        g.pop(k, None)


# ---- the cross-request cache ---------------------------------------------
# _cached() above dies with the request, which is why every page used to pay a round trip for
# post_types, settings and one per picture. This one lives in the worker process, so it also has to
# answer "has anything changed since?" -- and the ~30 workers share no memory. They do share
# /dev/shm (throttle.py's trick), so one empty file's mtime is the whole invalidation protocol:
# every write touches it, every reader stats it. A stat on tmpfs is microseconds against a render
# that measured 219 ms, so it is cheaper to ask every time than to be stale.
# The drafts and editing-session writes deliberately do NOT bump it: they are autosaves, they change
# no public page, and bumping on each would empty the cache every few seconds while somebody types.

# ponytail: _proc_cache grows one key per media id ever read by this worker and is never trimmed.
# It is bounded by the media table (a few hundred small dicts), so a ceiling costs more than it
# saves; give it PAGE_MAX's treatment in public.py if the library ever gets large.
CACHE_TTL = 30          # seconds; the ceiling on staleness if a bump is ever missed
EPOCH_FILE = "/dev/shm/iopstor-content-epoch"
_proc_cache = {}        # key -> (expires, epoch, value)


def content_epoch():
    try:
        return os.stat(EPOCH_FILE).st_mtime
    except OSError:     # first boot, or no /dev/shm: everyone reads 0.0 and the TTL carries it
        return 0.0


def bump_epoch():
    """Invalidate every worker's cache. Called from the three write helpers, so a new write path is
    covered without anybody remembering -- the same reason the audit log lives in them.

    It also drops _cached()'s memos for the rest of THIS request. Those are per-request and usually
    die before anything can read them stale, but a writer routinely reads the old row first --
    set_menu() calls get_menu() for the audit diff -- and that read caches the value it is about to
    make wrong. Doing it here rather than at each write site is the same argument as the audit log:
    one place every write already goes through, so the next one is covered without being asked."""
    try:
        with open(EPOCH_FILE, "w"):
            pass
    except OSError:
        pass
    if has_app_context():
        uncache(*getattr(g, "_cache_keys", ()), "_cache_keys")


def _proc_cached(key, loader, ttl=None):
    """Cache across requests inside this worker. The epoch is read BEFORE the loader runs, so a
    write landing mid-load stores the older stamp and the next reader reloads -- wrong in the safe
    direction."""
    now, epoch = time.time(), content_epoch()
    hit = _proc_cache.get(key)
    if hit and hit[0] > now and hit[1] >= epoch:
        return hit[2]
    value = loader()
    _proc_cache[key] = (now + (CACHE_TTL if ttl is None else ttl), epoch, value)
    return value


# ---- post types & settings -------------------------------------------------

def post_types():
    return _cached("post_types", lambda: _proc_cached(
        "post_types", lambda: rows(table("post_types").select("*").order("id"))))


def post_type(**match):
    """post_type(slug="post") / post_type(id=3) / post_type(url_prefix="blog")"""
    return next((t for t in post_types() if all(t.get(k) == v for k, v in match.items())), None)


def settings():
    return _cached("settings", lambda: _proc_cached(
        "settings", lambda: {r["key"]: r["value"] for r in rows(table("settings").select("*"))}))


def set_settings(values):
    if values:  # PostgREST rejects an empty bulk upsert
        before = settings()
        table("settings").upsert([{"key": k, "value": v} for k, v in values.items()]).execute()
        # one entry per key, not one for the whole form: the Settings screen posts all eleven keys
        # every time, and "which setting did they change" is the question the log is asked.
        for k, v in values.items():
            if before.get(k) != v:
                _audit("update", "settings", k, {"value": [before.get(k), v]}, k)
        bump_epoch()   # upsert(), not update(): the helper's bump never runs here
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
    bump_epoch()   # a term archive's contents just changed; neither write went through the helpers
    uncache("post_index_")


# ---- the working draft, and who changed what --------------------------------
"""posts.blocks is the PUBLISHED content and nothing here touches it. The editor saves itself into
post_drafts every second or two; Publish is what copies a draft across through the ordinary audited
update() and then clears it. See migrations/0010 for why these are tables and not columns."""

# PGRST205 is what actually comes back, not Postgres's own 42P01: PostgREST answers from its schema
# cache and never reaches the table, so it reports "could not find the table in the schema cache".
# Measured against the dev Supabase before this file was applied. 42P01 is kept for the paths that do
# reach Postgres (a function, a view), so the check does not depend on which layer refuses first.
NO_SUCH_TABLE = ("PGRST205", "42P01")


def _tolerate_0010(fn, default=None):
    """0010 may not be applied yet, and the app has to run against a database where it is not --
    /migration step 8. Without a draft table the editor loads posts.blocks and no session is ever
    opened, which is exactly how the editor behaved before this feature existed. Anything other than
    a missing table still raises: a permission error or a broken query is a real fault, and
    swallowing it here would turn "autosave is off" into an invisible bug."""
    try:
        return fn()
    except APIError as e:
        if (getattr(e, "code", "") or "") not in NO_SUCH_TABLE:
            raise
        return default


def get_draft(post_id):
    return _tolerate_0010(lambda: one(table("post_drafts").select("*").eq("post_id", post_id)))


def save_draft(post_id, blocks, state, user):
    """The autosave. **Deliberately not audited**, and one of only two writes in this module that are
    not -- see touch_session() for the other half of the deal.

    audit_log has no retention job and _diff() stores the whole blocks array on both sides of every
    write, so routing an autosave through update() would add a full copy of the page every couple of
    seconds, per editor, for ever. The per-person record is not lost, it is deferred: touch_session()
    accumulates what each editor changed and flush_sessions() writes ONE row per person per sitting.
    Publish and Discard are audited normally.

    Returns True when the draft was stored and **False when 0010 is not applied yet**, and the caller
    is expected to pass that on. Tolerating the missing table is right -- the editor has to run before
    the migration -- but doing it silently told every editor "Saved just now" over work that was going
    nowhere, which is precisely the invisible bug _tolerate_0010's own docstring refuses to create."""
    def store():
        table("post_drafts").upsert(
            {"post_id": post_id, "blocks": blocks, "state": state,
             "updated_by": (user or {}).get("id"), "updated_by_email": (user or {}).get("email") or ""},
            on_conflict="post_id").execute()
        return True
    return _tolerate_0010(store, default=False)


def clear_draft(post_id):
    """Publish, Discard and Restore all end here. Every caller that writes posts.blocks must, or the
    editor reopens the draft and the write looks as though it never happened."""
    return _tolerate_0010(lambda: table("post_drafts").delete().eq("post_id", post_id).execute())


def open_sessions(post_id):
    return _tolerate_0010(lambda: rows(table("post_sessions").select("*").eq("post_id", post_id)), []) or []


def _merge_changes(old, new):
    """One person, one sitting, more than one visit to the page. Keep the EARLIEST `was` for each
    section and the LATEST `now`, matched by the section's own name.

    A sitting ends after fifteen minutes with no activity -- the rule the client asked for -- and not
    when somebody reloads or wanders off to another screen and comes back. But each visit starts with
    a fresh baseline, so without merging here the second visit's `was` would replace the first's and
    the entry would cover only whatever they did after returning. Sections with no name cannot be
    matched, so the later visit simply stands on its own."""
    if not old or "blocks" not in (old or {}) or "blocks" not in (new or {}):
        return new
    was_old, now_old = old["blocks"]
    was_new, now_new = new["blocks"]

    def name(b):
        return ((b or {}).get("data") or {}).get("_id")

    def first_win(*lists):
        seen, out = set(), []
        for bs in lists:
            for b in bs or []:
                if name(b) and name(b) not in seen:
                    seen.add(name(b))
                    out.append(b)
        return out

    if not all(name(b) for bs in (was_old, now_old, was_new, now_new) for b in bs or []):
        return new
    return {**new, "blocks": [first_win(was_old, was_new),     # as they first found each section
                              first_win(now_new, now_old)]}    # as they have left it


def touch_session(post_id, user, changes, ip=""):
    """What THIS editor has changed since they opened the page, kept until their session is closed.
    Not audited for the same reason save_draft() is not; flush_sessions() is where it becomes a log
    entry. `changes` is already {field: [was, now]} -- the shape audit_log.changes uses -- so the
    Activity screen renders it with no new code. Merged into whatever this person's open session
    already holds, so one sitting is one entry however many times they reloaded."""
    def go():
        prev = one(table("post_sessions").select("changes")
                   .eq("post_id", post_id).eq("user_id", user["id"]))
        table("post_sessions").upsert(
            {"post_id": post_id, "user_id": user["id"], "user_email": user.get("email") or "",
             "ip": ip, "changes": _merge_changes((prev or {}).get("changes"), changes)},
            on_conflict="post_id,user_id").execute()
        return True
    return _tolerate_0010(go, default=False)


def flush_sessions(post_id, idle_minutes=15, user_id=None):
    """Close finished editing sessions on this page, one audit row each, attributed to the editor who
    made them rather than to whoever is making this request.

    There is no scheduler here -- no cron, and thirty stateless gunicorn workers -- so stale sessions
    are closed opportunistically by whoever next touches the page: an autosave, a publish, or just
    opening the editor. That backstop is what makes the browser's own idle timer and its
    beforeunload beacon optimisations rather than load-bearing; a crashed tab still gets its record.

    # ponytail: a session on a page nobody ever reopens stays pending. The row is still there and a
    # sweep command can close it later; a scheduler is not worth it for a page nobody is reading.
    """
    q = table("post_sessions").select("*").eq("post_id", post_id)
    q = q.eq("user_id", user_id) if user_id else q.lt("updated_at", (utcnow() - timedelta(minutes=idle_minutes)).isoformat())
    done = _tolerate_0010(lambda: rows(q), []) or []
    if not done:
        return 0
    label = _label(one(table("posts").select("title").eq("id", post_id)) or {})
    for sess in done:
        if sess.get("changes"):   # opened the page, changed nothing: nothing to say
            _audit("edit", "posts", post_id, sess["changes"], label,
                   user={"id": sess["user_id"], "email": sess["user_email"]}, ip=sess.get("ip") or "")
    table("post_sessions").delete().eq("post_id", post_id).in_("user_id", [s["user_id"] for s in done]).execute()
    return len(done)


def paginate(q, page, per_page, transform=lambda x: x):
    """q must be a select(..., count='exact'). Returns the API list envelope."""
    res = q.range((page - 1) * per_page, page * per_page - 1).execute()
    return {"items": [transform(r) for r in res.data], "total": res.count or 0, "page": page, "per_page": per_page}


def get_media(pk):
    """# ponytail: one row per picture, cached per process. The N+1 was the single biggest cost on the
    public site -- a page with seventeen pictures made seventeen sequential round trips, fourteen of
    them the partner logos in _card.html. Batching the ids per page would fix the home page; caching
    the row fixes every page, the admin included, for less code."""
    if not pk:
        return None
    return _cached(f"media_{pk}", lambda: _proc_cached(
        f"media_{pk}", lambda: one(table("media").select("*").eq("id", pk))))


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


def redirect_for(path):
    """The whole redirects table as {from_path: row}, cached per worker. It was one round trip on
    every request of every page -- a tiny table that almost always misses. A redirect added or
    removed goes through insert()/delete(), which bump the epoch, so this drops on the next read."""
    found = _proc_cached("redirects", lambda: {r["from_path"]: r for r in rows(table("redirects").select("*"))})
    return found.get(path)


def get_menu(slug):
    """base.html calls this twice on every page (header, footer) and it had no cache of any kind --
    not even the per-request one -- so it was two round trips on every view of every page."""
    def load():
        m = one(table("menus").select("*").eq("slug", slug))
        return m["items"] if m else []
    return _cached(f"menu_{slug}", lambda: _proc_cached(f"menu_{slug}", load))


def set_menu(slug, items, name=None):
    """The write side of get_menu(), so /admin/menus keeps every query in this module. `name` is for
    the JSON API, which lets a caller title a menu; the browser screen has no field for it."""
    before = get_menu(slug)
    table("menus").upsert({"slug": slug, "name": name or slug.title(), "items": items}, on_conflict="slug").execute()
    bump_epoch()   # upsert(), not update(): the helper's bump never runs here
    if before != items:
        _audit("update", "menus", slug, {"items": [before, items]}, slug)
