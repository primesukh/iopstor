"""Browser admin at /admin: server-rendered forms on top of the same validation as the admin API.
Login = Supabase email/password; tokens live in the signed Flask session cookie."""
import difflib
import json
import secrets
from collections import Counter
from datetime import date
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from postgrest import APIError
from supabase_auth.errors import AuthError
from werkzeug.exceptions import HTTPException

from . import db, display_name, seo
from .admin_api import apply_post
from .auth import ROLES, create_auth_user, current_user, delete_auth_user, login, set_password
from .blocks import BLOCKS, EDITOR, LAYOUTS, at_path, blocks_text, render_blocks, validate_blocks, warranty_active
from .throttle import clear as throttle_clear, client_ip, record_failure, retry_after, wait_text
from .storage import delete_media, save_upload

ui = Blueprint("admin_ui", __name__, url_prefix="/admin", template_folder="templates")
SETTING_KEYS = ("site_name", "tagline", "logo_url", "default_og_image", "social_links", "ga_id", "contact_email",
                "contact_phone", "address", "robots_extra", "notify_email")
# Which settings tab each key sits on. Every key is rendered on every load whatever tab is
# showing -- the tabs are CSS -- because the save below blanks any key missing from the form.
SETTING_TABS = (("Site identity", ("site_name", "tagline", "logo_url", "default_og_image")),
                ("Contact details", ("contact_email", "contact_phone", "address", "social_links")),
                ("SEO & analytics", ("ga_id", "robots_extra")),
                ("Payments", ("notify_email",)))   # prices are rupees, always: rupees() in __init__.py
LEAD_STATUSES = ("new", "in_progress", "handled")
SEO_KEYS = ("title", "description", "canonical", "robots", "og_image")


def ui_required(min_role="editor"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("admin_ui.login_page", next=request.path))
            if ROLES.get(user["role"], 0) < ROLES[min_role]:
                abort(403)
            if request.method == "POST" and request.form.get("csrf") != session.get("csrf"):
                abort(400, "form token expired, reload the page and try again")
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return deco


@ui.app_context_processor
def _globals():
    # app_context_processor is app-wide, not blueprint-scoped, so without the second test every public
    # page would mint a CSRF token and answer with Set-Cookie -- which no HTTP cache stores, so the site
    # behind the tunnel could never be cached at Cloudflare's edge. No public template reads any of
    # these globals; /admin/canvas and /admin/preview are admin_ui routes, so the editor keeps its token.
    if not has_request_context() or request.blueprint != ui.name:  # CLI / tests, and every public page
        return {}
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(16)
    user = getattr(g, "user", None)
    # nav_counts, not "counts": the dashboard view passes its own `counts` and a view's context
    # shadows a processor's, which would leave the sidebar's leads pill empty on that one page.
    return {"csrf": session["csrf"], "admin_user": user, "post_types": db.post_types() if user else [],
            "nav_counts": db.admin_counts() if user else {}}


@ui.errorhandler(APIError)
def _pg_error(e):
    return render_template("admin/error.html", message=f"Supabase error: {getattr(e, 'message', e)}"), 502


def _safe_next(default="/admin/"):
    """Only relative, same-origin paths may be used as a post-login redirect (no //host, /\\host, or scheme tricks)."""
    nxt = request.args.get("next", "")
    if not nxt.startswith("/") or nxt.startswith(("//", "/\\")) or "\\" in nxt:
        return default
    parsed = urlparse(nxt)
    return default if parsed.scheme or parsed.netloc else nxt


# ---- auth ------------------------------------------------------------------

@ui.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        # keyed by address, never by the email typed in: an email-keyed lock would let anyone shut a
        # named person out of their own site by guessing their password ten times.
        key = f"ip:{client_ip()}"
        wait = retry_after(key)
        if wait:
            return render_template("admin/login.html", error=wait_text(wait)), 429, {"Retry-After": wait}
        try:
            s = login(request.form.get("email", ""), request.form.get("password", ""))
        except AuthError:
            db.audit_event("login_failed", request.form.get("email", ""))
            if record_failure(key):   # True only on the attempt that closes the door, so a locked
                db.audit_event("login_blocked", request.form.get("email", ""))   # login cannot
            return render_template("admin/login.html", error="Wrong email or password."), 401   # flood
        throttle_clear(key)  # the password was right, so two typos before it cost nothing; whether
        user = db.one(db.table("users").select("*").eq("id", s["user_id"]))         # there is a CMS
        if user is None:                                                            # row is separate
            db.audit_event("login_failed", request.form.get("email", ""))
            return render_template("admin/login.html",
                                   error="This login has no CMS account. Ask an admin to add you under Users."), 403
        session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
        db.audit_event("login", user["email"], user=user)   # g.user is not set yet on this request
        return redirect(_safe_next())
    return render_template("admin/login.html")


def _password_errors(new, confirm=None):
    """What is wrong with a proposed password, as plain sentences. Eight matches the invite form's
    `minlength`; GoTrue's own floor is six, so this is the stricter of the two. `confirm=None` is the
    admin's one-field reset, which has nothing to compare against."""
    if len(new) < 8:
        return ["The new password must be at least 8 characters."]
    if confirm is not None and new != confirm:
        return ["The two new passwords do not match."]
    return []


@ui.route("/account", methods=["GET", "POST"])
@ui_required()
def account():
    """Change your own password. Every role reaches it, which is why it hangs off the sidebar footer
    rather than the nav: Users and Settings are admin-only, and an editor has to be able to do this.

    The current password is proved by signing in with it, not by trusting the session cookie — a
    session says who logged in once, not who is at the keyboard now. login() already is that check,
    so this calls it instead of copying it.

    The second login() is not optional either: GoTrue can revoke the refresh token minted under the
    old password, and without fresh tokens in the session the user is signed out on the next
    _session_token() refresh — one click after changing their password."""
    errors, wait = [], 0
    if request.method == "POST":
        f = request.form
        # by user id, not address: the session is already proof of which account is guessing
        key = f"user:{g.user['id']}"
        wait = retry_after(key)
        errors = [wait_text(wait)] if wait else _password_errors(f.get("new_password", ""), f.get("confirm", ""))
        if not errors:
            try:
                login(g.user["email"], f.get("current_password", ""))
            except AuthError:
                # the same wrong password the login screen records; this one is on the way to
                # changing it, which makes it more worth knowing about, not less
                db.audit_event("login_failed", g.user["email"])
                if record_failure(key):
                    db.audit_event("login_blocked", g.user["email"])
                errors = ["That is not your current password."]
        if not errors:
            try:
                set_password(g.user, f["new_password"])
                s = login(g.user["email"], f["new_password"])
            except AuthError as e:
                errors = [f"Supabase refused the new password: {getattr(e, 'message', e)}"]
            else:
                throttle_clear(key)
                session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
                # set_password() talks to GoTrue and writes no row of ours, so nothing in db.py can
                # see this: a credential changed and the log would otherwise say nothing. The
                # password itself is never recorded -- only that it was changed, and whose.
                db.audit_event("password_changed", g.user["email"])
                flash("Password changed.")
                return redirect(url_for("admin_ui.account"))
    return render_template("admin/account.html", errors=errors), (429 if wait else 400 if errors else 200)


@ui.get("/logout")
def logout():
    if user := current_user():   # no @ui_required on this route, so g.user was never set
        db.audit_event("logout", user["email"], user=user)
    session.clear()
    return redirect(url_for("admin_ui.login_page"))


# ---- dashboard & posts -----------------------------------------------------

@ui.get("/")
@ui_required()
def dashboard():
    # the sidebar already counted everything for this request; reuse it instead of one
    # exact-count round trip per post type
    counts = db.admin_counts()
    recent_leads = db.rows(db.table("leads").select("*").eq("status", "new").order("created_at", desc=True).limit(5))
    recent_posts = db.rows(db.table("posts").select("id,title,status,updated_at")
                           .neq("status", "trash").order("updated_at", desc=True).limit(5))
    return render_template("admin/dashboard.html", counts=counts, new_leads=counts["_leads"],
                           recent_leads=recent_leads, recent_posts=recent_posts)


@ui.get("/posts")
@ui_required()
def posts():
    q = db.select_posts(count="exact")
    pt = db.post_type(slug=request.args.get("type", "")) if request.args.get("type") else None
    if pt:
        q = q.eq("post_type_id", pt["id"])
    # the trash is somewhere you go, never something that turns up in a list you did not ask for
    status = request.args.get("status")
    q = q.eq("status", status) if status else q.neq("status", "trash")
    if s := request.args.get("q"):
        s = s.replace(",", " ").replace("(", " ").replace(")", " ")
        q = q.or_(f"title.ilike.%{s}%,slug.ilike.%{s}%")
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("updated_at", desc=True), page, 50)
    result["items"] = db.with_paths(result["items"])
    return render_template("admin/posts.html", result=result, current_type=pt, page=page, has_next=page * 50 < result["total"])


def _as_ist(value):
    """<input type="datetime-local"> posts a bare wall clock -- "2026-09-11T14:00" -- and every
    parser downstream reads a missing offset as UTC, so an editor in India typing 2 pm was storing
    7:30 pm. Stamped here rather than in db.parse_dt(), which is the fallback for the JSON API too,
    where no offset should still mean UTC."""
    return f"{value}+05:30" if value and "+" not in value and not value.endswith("Z") else value


def _form_body(pt, existing):
    """Turn the post form into the same body dict the JSON API accepts."""
    f = request.form
    b = {"post_type": pt["slug"], "title": f.get("title", ""), "slug": f.get("slug", ""), "status": f.get("status", "draft"),
         "published_at": _as_ist(f.get("published_at", "")), "excerpt": f.get("excerpt", ""),
         "parent_id": f.get("parent_id") or None, "featured_media_id": f.get("featured_media_id") or None,
         "terms": [int(t) for t in f.getlist("terms")], "seo": {k: f.get(f"seo_{k}", "") for k in SEO_KEYS if f.get(f"seo_{k}")}}
    meta = dict(existing.get("meta") or {}) if existing else {}
    for field in pt.get("field_schema") or []:
        raw = f.get(f"meta_{field['key']}", "")
        if field.get("type") == "kv":
            # A list of {k, v}, not an object: jsonb sorts an object's keys, which would throw away
            # the order the editor dragged the rows into. A row with no label is a row not filled in.
            try:
                rows = json.loads(raw) if raw.strip() else []
            except ValueError:
                rows = []
            meta[field["key"]] = [{"k": str(r.get("k", "")), "v": str(r.get("v", ""))}
                                  for r in rows if isinstance(r, dict) and str(r.get("k", "")).strip()] or None
        elif field.get("type") == "json":
            try:
                meta[field["key"]] = json.loads(raw) if raw.strip() else None
            except ValueError:
                meta[field["key"]] = raw  # apply_post accepts any JSON value; keep the text so the user can fix it
        elif field.get("type") == "number":
            meta[field["key"]] = float(raw) if raw.strip() and raw.replace(".", "", 1).replace("-", "", 1).isdigit() else (raw or None)
        else:
            meta[field["key"]] = raw or None
    b["meta"] = {k: v for k, v in meta.items() if v is not None}
    try:
        b["blocks"] = json.loads(f.get("blocks") or "[]")
    except ValueError as e:
        b["blocks"] = f"invalid JSON: {e}"  # validate_blocks turns a non-list into an error message
    return b


def _new_term_ids(pt):
    """Chips the form invented, "taxonomy-slug:Name" → term ids, reusing a term of that name if there
    already is one. Called from _save() only: _form_body() is shared with /admin/preview, which must
    never write. The taxonomy check is the trust boundary — the field is client-supplied, and without
    it an editor could file a term into a taxonomy this post type does not even use."""
    allowed = pt.get("taxonomies") or []
    ids = []
    for chip in request.form.getlist("new_terms"):
        tax, _, name = chip.partition(":")
        if tax in allowed and name.strip():
            ids.append(db.ensure_term(tax, name.strip()))
    return [i for i in ids if i]


def _form_context(pt, post, errors=None):
    # Slimmed to what the chip picker needs: the whole list is embedded in the page, so matching a
    # typed name against it costs no round trip (like taken_slugs feeds the web-address warning).
    taxonomies = [{"slug": t["slug"], "name": t["name"],
                   "terms": sorted([{"id": x["id"], "name": x["name"]} for x in t["terms"]], key=lambda x: x["name"].lower())}
                  for t in db.rows(db.table("taxonomies").select("*, terms(*)").order("id")) if t["slug"] in (pt.get("taxonomies") or [])]
    # ponytail: assumes < 2000 posts per type, like db._index(); one select feeds both the parent
    # dropdown and the slug list the form warns against.
    siblings = db.rows(db.table("posts").select("id,title,slug").eq("post_type_id", pt["id"]).order("title").limit(2000))
    media = db.rows(db.table("media").select("id,filename,url,mime,alt").order("id", desc=True).limit(200))
    term_ids = {t["id"] for t in (post or {}).get("terms") or []}
    pk = (post or {}).get("id")   # .get(): a rejected save of a *new* post renders a draft dict with no id
    return dict(pt=pt, post=post, errors=errors or {}, taxonomies=taxonomies,
                parents=[p for p in siblings if p["id"] != pk] if pt["hierarchical"] else [],
                taken_slugs=[s["slug"] for s in siblings if s["id"] != pk],
                media=media, term_ids=term_ids, blocks=BLOCKS, blocks_ui=EDITOR, layouts=list(LAYOUTS.items()), blocks_json=json.dumps((post or {}).get("blocks") or [], indent=2, ensure_ascii=False),
                seo_keys=SEO_KEYS)


def _save(pt, existing):
    b = _form_body(pt, existing)
    # Before apply_post, not after: a rejected save then round-trips the new chips for free, because
    # the draft carries their ids and _form_context() re-reads the taxonomies and finds them.
    b["terms"] += _new_term_ids(pt)
    try:
        changes, term_ids = apply_post(existing, b)
    except HTTPException as e:
        payload = e.response.get_json() if e.response is not None else {"error": e.description}
        errors = payload.get("fields") or {"_": payload.get("error")}
        keep = ("title", "slug", "status", "published_at", "excerpt", "parent_id", "featured_media_id", "meta", "seo")
        draft = {**(existing or {}), "post_type": pt, **{k: b[k] for k in keep}, "terms": [{"id": t} for t in b["terms"]], "blocks_text": request.form.get("blocks", "")}
        return None, render_template("admin/post_form.html", **_form_context(pt, draft, errors))
    if existing:
        if changes:
            db.update("posts", existing["id"], changes)
        pk = existing["id"]
    else:
        changes["author_id"] = g.user["id"]
        pk = db.insert("posts", changes)["id"]
    if term_ids is not None:
        db.set_post_terms(pk, term_ids)
    db.uncache(f"post_index_{pt['id']}")
    return pk, None


@ui.route("/posts/new", methods=["GET", "POST"])
@ui_required()
def new_post():
    pt = db.post_type(slug=request.args.get("type", "page")) or abort(404)
    if request.method == "POST":
        pk, page = _save(pt, None)
        if page:
            return page, 400
        flash("Created.")
        return redirect(url_for("admin_ui.edit_post", pk=pk))
    return render_template("admin/post_form.html", **_form_context(pt, None))


@ui.route("/posts/<int:pk>", methods=["GET", "POST"])
@ui_required()
def edit_post(pk):
    post = db.hydrate(db.get_post(pk)) or abort(404)
    if post["status"] == "trash":
        # the POST half is the load-bearing one: the form has no trash option, so saving a trashed
        # post would quietly bring it back as a draft with nobody having asked for that.
        abort(404)
    pt = post["post_type"]
    if request.method == "POST":
        _, page = _save(pt, post)
        if page:
            return page, 400
        flash("Saved.")
        return redirect(url_for("admin_ui.edit_post", pk=pk))
    return render_template("admin/post_form.html", **_form_context(pt, post))


@ui.post("/posts/<int:pk>/delete")
@ui_required("admin")
def delete_post(pk):
    """To the trash, not out of the database. The button still warns that it cannot be undone,
    because that is the behaviour wanted from whoever clicks it -- the trash is an admin's safety
    net, not a promise made at the confirmation dialog."""
    post = db.get_post(pk) or abort(404)
    db.update("posts", pk, {"status": "trash"}, action="delete")
    flash(f"Deleted “{post['title']}”.")
    return redirect(url_for("admin_ui.posts", type=post["post_type"]["slug"]))


@ui.post("/posts/<int:pk>/restore")
@ui_required("admin")
def restore_post(pk):
    """Back as a draft, never straight onto the site: the page has been gone for a while and
    whoever restores it should be the one who decides it goes live again."""
    post = db.get_post(pk) or abort(404)
    if post["status"] != "trash":
        abort(404)   # only a deleted page is restorable; without this a stale form demotes a live one
    db.update("posts", pk, {"status": "draft"}, action="restore")
    flash(f"Restored {post['title']} as a draft.")
    return redirect(url_for("admin_ui.posts", type=post["post_type"]["slug"], status="trash"))


@ui.post("/canvas")
@ui_required()
def canvas():
    """The visual editor's iframe. Renders the blocks the browser currently holds — unsaved ones
    included — through the same render_blocks() the public site uses, with edit markers on.
    With ?p=PATH it returns just that one block, so an edit swaps one <section> instead of reloading.
    PATH is a data-b path ("3", or "3.1.0" for a block inside a column), and the fragment comes back
    already carrying it, so the browser does not have to renumber what it just dropped in."""
    try:
        blocks = json.loads(request.form.get("blocks") or "[]")
    except ValueError:
        blocks = []
    if not isinstance(blocks, list):
        blocks = []
    path = request.form.get("p")
    if path is not None:
        one = at_path(blocks, path)
        return render_blocks([one], edit=True, path=path) if one else ""
    return render_template("admin/canvas.html", body=render_blocks(blocks, edit=True),
                           title=request.form.get("title", ""), excerpt=request.form.get("excerpt", ""),
                           has_hero=bool(blocks) and isinstance(blocks[0], dict) and blocks[0].get("type") == "hero")


def _preview_post(pt, b, existing):
    """The edit form as it stands right now, shaped like a hydrated post row so post.html can render it.

    Deliberately carries no "id": nothing on the preview path needs one, and an unsaved post has none.
    published_at stays the form's STRING — apply_post() turns it into a datetime, and post.html slices
    it (`published_at[:10]`) while seo.jsonld() hands it to |tojson."""
    blocks = b["blocks"] if isinstance(b["blocks"], list) else []   # _form_body parks an error string here
    terms = db.rows(db.table("terms").select("*, taxonomy:taxonomies(*)").in_("id", b["terms"])) if b["terms"] else []
    post = {**(existing or {}), "post_type": pt, "post_type_id": pt["id"],
            "title": b["title"] or "Untitled", "slug": b["slug"] or (existing or {}).get("slug") or "preview",
            "excerpt": b["excerpt"], "blocks": blocks, "meta": b["meta"], "seo": b["seo"], "status": b["status"],
            "published_at": b["published_at"] or "",
            "parent_id": int(b["parent_id"]) if b["parent_id"] else None,
            "featured_media": db.get_media(b["featured_media_id"]) if b["featured_media_id"] else None,
            "terms": terms}
    post.pop("id", None)
    return db.hydrate(post)


@ui.post("/preview")
@ui_required()
def preview():
    """The page exactly as a visitor gets it — real header, nav, breadcrumbs, footer and SEO — built
    from the form as it stands, so a draft or an unsaved edit can be checked before saving. The public
    route cannot do this: db.live() gates every lookup on status='published' with no bypass.
    ?part=card returns just the search/social card from the same data."""
    from .public import crumbs_for  # local import: keeps admin_ui out of public.py's import graph

    pt = db.post_type(slug=request.args.get("type", "page")) or abort(404)
    pk = request.args.get("pk", type=int)
    existing = db.get_post(pk) if pk else None
    post = _preview_post(pt, _form_body(pt, existing), existing)
    crumbs = crumbs_for(post)
    meta = {**seo.build_meta(post), "robots": "noindex,nofollow"}  # a preview must never be indexable
    if request.args.get("part") == "card":
        return render_template("admin/seo_card.html", meta=meta, site=seo.site())
    children = (db.with_paths(db.rows(db.live(db.select_posts()).eq("parent_id", pk).order("menu_order").order("published_at", desc=True)))
                if pk and pt["hierarchical"] else [])
    try:
        return render_template("post.html", post=post, children=children, crumbs=crumbs, meta=meta,
                               jsonld=seo.jsonld(post, crumbs), preview=True)
    except Exception as e:
        # render_blocks(edit=False) re-raises by design. On the public site that is honest; here it
        # would blank the pane mid-edit, so say which section is not finished instead.
        return render_template("admin/canvas.html", title=post["title"], excerpt="", has_hero=False,
                               body=Markup('<div class="wrap"><p class="iop-err">This page cannot be shown yet — '
                                           f'{escape(e)}</p></div>'))


# ---- media, leads, settings, users ----------------------------------------

def _upload(fs, alt=""):
    """Store one upload and return the media row. Raises HTTPException(400) on a rejected file type."""
    m = save_upload(fs, g.user["id"])
    if alt:
        m = db.update("media", m["id"], {"alt": alt[:300]}) or m
    return m


@ui.route("/media", methods=["GET", "POST"])
@ui_required()
def media():
    if request.method == "POST":
        fs = request.files.get("file")
        if not fs or not fs.filename:
            flash("Choose a file first.")
        else:
            try:
                m = _upload(fs, request.form.get("alt", ""))
            except HTTPException as e:
                flash(e.description)
            else:
                flash(f"Uploaded {m['filename']} (id {m['id']}).")
        return redirect(url_for("admin_ui.media"))
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(db.table("media").select("*", count="exact").order("id", desc=True), page, 60)
    return render_template("admin/media.html", result=result, page=page, has_next=page * 60 < result["total"])


@ui.post("/media/<int:pk>/alt")
@ui_required()
def media_alt(pk):
    """Alt text used to be settable only at upload time, so a picture uploaded without it could
    never be described. The media panel's Save button posts here."""
    db.one(db.table("media").select("id").eq("id", pk)) or abort(404)
    db.update("media", pk, {"alt": (request.form.get("alt") or "")[:300]})
    flash("Alt text saved.")
    return redirect(url_for("admin_ui.media", **{k: v for k, v in request.args.items()}))


@ui.post("/media/<int:pk>/delete")
@ui_required()
def media_delete(pk):
    m = db.one(db.table("media").select("*").eq("id", pk)) or abort(404)
    delete_media(m)
    flash("Deleted.")
    return redirect(url_for("admin_ui.media"))


@ui.post("/media/upload")
@ui_required()
def media_upload():
    """Inline uploader used by the post form (admin.js); same storage path as the media page."""
    fs = request.files.get("file")
    if not fs or not fs.filename:
        return jsonify({"error": "Choose a file first."}), 400
    try:
        m = _upload(fs, request.form.get("alt", ""))
    except HTTPException as e:  # save_upload rejects unsupported types
        return jsonify({"error": e.description}), e.code
    return jsonify({k: m.get(k) for k in ("id", "url", "filename", "mime", "alt")}), 201


@ui.get("/leads")
@ui_required()
def leads():
    q = db.table("leads").select("*, post:posts(title)", count="exact")
    if s := request.args.get("status"):
        q = q.eq("status", s)
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("id", desc=True), page, 50)
    return render_template("admin/leads.html", result=result, page=page, has_next=page * 50 < result["total"])


@ui.post("/leads/<int:pk>/status")
@ui_required()
def lead_status(pk):
    # a whitelist, not a toggle: the design has three tabs, and leads.status is a plain varchar
    # so anything posted would otherwise be stored verbatim.
    want = request.form.get("status")
    db.update("leads", pk, {"status": want if want in LEAD_STATUSES else "new"})
    return redirect(url_for("admin_ui.leads", **{k: v for k, v in request.args.items()}))


@ui.route("/warranty", methods=["GET", "POST"])
@ui_required()
def warranty():
    """The warranty register: list, search, add and edit on one page (?edit=<id> loads a record into
    the form). The public Warranty check section reads the same table by serial number.

    A save that works redirects (post-redirect-get, so a refresh cannot save twice); a save that is
    refused falls through to the same render with what was typed still in the form, the way the post
    form re-renders instead of redirecting. Losing a filled-in record to a typo is not a validation
    message, it is a re-typing exercise.

    A refusal is `(field, message)`, not a flash: the message belongs on the field it is about, so
    admin.js hands it to the browser's own validation bubble (setCustomValidity, as initSlug already
    does for a taken web address). Only a success flashes, at the top, where a confirmation belongs."""
    editing, refused = None, None
    if request.method == "POST":
        f = request.form
        row = {k: f.get(k, "").strip()[:limit] for k, limit in
               (("serial", 100), ("customer_name", 200), ("email", 300), ("expiry_date", 10), ("purchase_date", 10))}
        row["remarks"] = f.get("remarks", "").strip()
        row["amc"] = f.get("amc") == "yes"
        row["remarks_public"] = bool(f.get("remarks_public"))
        row["purchase_date"] = row["purchase_date"] or None  # optional: an empty string is not a date
        pk = f.get("id", "")
        dupe = db.one(db.table("warranties").select("id").eq("serial_key", row["serial"].upper())) if row["serial"] else None
        if not (row["serial"] and row["customer_name"] and row["expiry_date"]):
            refused = ("serial", "Serial number, customer name and warranty expiry are required.")
        elif dupe and str(dupe["id"]) != pk:
            # the one the browser cannot check for itself: it would need every serial on file
            refused = ("serial", f"Serial number {row['serial']} already has a record.")
        elif row["purchase_date"] and row["expiry_date"] < row["purchase_date"]:
            # the friendly half of warranties_expiry_after_purchase (0004); ISO dates compare as dates.
            # No purchase date means no comparison to make: any expiry is allowed.
            refused = ("expiry_date", f"Warranty expiry cannot be before the purchase date ({row['purchase_date']}).")
        else:
            if pk.isdigit():
                db.update("warranties", int(pk), row)
                flash(f"Saved {row['serial']}.")
            else:
                db.insert("warranties", row)
                flash(f"Added {row['serial']}.")
            return redirect(url_for("admin_ui.warranty", q=request.args.get("q"), page=request.args.get("page")))
        # refused: hand the submitted values back to the form. The id decides add-vs-edit in the
        # template, so a rejected new record does not come back wearing an Edit heading.
        editing = {**row, "id": pk} if pk.isdigit() else row
    q = db.table("warranties").select("*", count="exact")
    if s := request.args.get("q"):
        s = s.replace(",", " ").replace("(", " ").replace(")", " ")  # PostgREST's or_ is comma/paren-delimited
        q = q.or_(f"serial.ilike.%{s}%,customer_name.ilike.%{s}%,email.ilike.%{s}%")
    # In warranty / Expired is the same comparison the public page and warranty_active() make:
    # expiry_date against today. Nothing is stored, so the tabs cannot drift from the badge.
    today = date.today().isoformat()
    if request.args.get("state") == "in":
        q = q.gte("expiry_date", today)
    elif request.args.get("state") == "out":
        q = q.lt("expiry_date", today)
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("id", desc=True), page, 50)
    edit_id = request.args.get("edit", type=int)
    if editing is None and edit_id:
        editing = db.one(db.table("warranties").select("*").eq("id", edit_id))
    return render_template("admin/warranty.html", result=result, page=page, has_next=page * 50 < result["total"],
                           editing=editing, refused=refused, today=date.today().isoformat(),
                           active=warranty_active), (400 if refused else 200)


@ui.post("/warranty/<int:pk>/delete")
@ui_required("admin")
def warranty_delete(pk):
    db.delete("warranties", pk)
    flash("Warranty record removed.")
    return redirect(url_for("admin_ui.warranty", q=request.args.get("q"), page=request.args.get("page")))


def menu_items(labels, urls, levels):
    """Flat form rows -> the nested [{label, url, children}] shape db.get_menu() returns.
    A row marked level 1 joins the item above it; one at level 1 with nothing above it is promoted
    rather than dropped, and a row with no label is skipped so an emptied row deletes itself."""
    items = []
    for label, url, level in zip(labels, urls, levels):
        label, url = label.strip()[:100], url.strip()[:500]
        if not label:
            continue
        if level == "1" and items:
            items[-1].setdefault("children", []).append({"label": label, "url": url})
        else:
            items.append({"label": label, "url": url})
    return items


@ui.route("/menus", methods=["GET", "POST"])
@ui_required("admin")
def menus():
    """Flat rows plus a level select, which is how the nested [{label, url, children}] shape
    db.get_menu() returns is built back up. One level only -- that is all base.html renders.
    The level is a <select>, not a checkbox: an unchecked box posts nothing, so getlist() would
    come back short and every row after the first unticked one would shift up a place."""
    slug = "footer" if request.args.get("slug") == "footer" else "header"
    if request.method == "POST":
        db.set_menu(slug, menu_items(request.form.getlist("label"), request.form.getlist("url"),
                                     request.form.getlist("level")))
        flash(f"{slug.title()} menu saved.")
        return redirect(url_for("admin_ui.menus", slug=slug))
    # flatten for the form: a parent, then each of its children marked one level in
    flat = []
    for i in db.get_menu(slug):
        flat.append({"label": i.get("label", ""), "url": i.get("url", ""), "level": 0})
        for c in i.get("children") or []:
            flat.append({"label": c.get("label", ""), "url": c.get("url", ""), "level": 1})
    return render_template("admin/menus.html", slug=slug, rows=flat)


@ui.route("/settings", methods=["GET", "POST"])
@ui_required("admin")
def settings():
    if request.method == "POST":
        values = {k: request.form.get(k, "") for k in SETTING_KEYS}
        try:
            values["social_links"] = [l.strip() for l in values["social_links"].splitlines() if l.strip()]
        except AttributeError:
            values["social_links"] = []
        db.set_settings(values)
        flash("Settings saved.")
        return redirect(url_for("admin_ui.settings"))
    s = db.settings()
    s = {**s, "social_links": "\n".join(s.get("social_links") or [])}
    from .payments import gateway
    return render_template("admin/settings.html", s=s, keys=SETTING_KEYS, tabs=SETTING_TABS,
                           provider=gateway().name)


@ui.route("/users", methods=["GET", "POST"])
@ui_required("admin")
def users():
    if request.method == "POST":
        f = request.form
        if not f.get("email") or not f.get("password"):
            flash("Email and password are required.")
        elif db.one(db.table("users").select("id").eq("email", f["email"])):
            flash("That email already has an account.")
        else:
            try:
                create_auth_user(f["email"], f["password"], f.get("role") if f.get("role") in ROLES else "editor", f.get("name", ""))
                flash(f"Added {f['email']}.")
            except AuthError as e:
                flash(f"Supabase refused: {getattr(e, 'message', e)}")
        return redirect(url_for("admin_ui.users"))
    return render_template("admin/users.html", users=db.rows(db.table("users").select("*").order("email")))


@ui.post("/users/<uuid:pk>/password")
@ui_required("admin")
def user_password(pk):
    """Hand a locked-out user a new password. Your own row is refused on purpose: /admin/account is
    the way you change yours, and it asks for the current one — a self-reset here would walk around
    that check for the one account whose session is already open."""
    user = db.one(db.table("users").select("*").eq("id", str(pk))) or abort(404)
    errors = _password_errors(request.form.get("password", ""))
    if user["id"] == g.user["id"]:
        flash("Use the Password screen to change your own.")
    elif errors:
        flash(errors[0])
    else:
        try:
            set_password(user, request.form["password"])
            db.audit_event("password_reset", user["email"])   # whose, never what
            flash(f"New password set for {user['email']}. Tell them, and ask them to change it.")
        except AuthError as e:
            flash(f"Supabase refused: {getattr(e, 'message', e)}")
    return redirect(url_for("admin_ui.users"))


@ui.post("/users/<uuid:pk>/delete")
@ui_required("admin")
def user_delete(pk):
    user = db.one(db.table("users").select("*").eq("id", str(pk))) or abort(404)
    if user["id"] == g.user["id"]:
        flash("You cannot delete yourself.")
    else:
        delete_auth_user(user)
        flash(f"Removed {user['email']}.")
    return redirect(url_for("admin_ui.users"))


# ---- activity log ----------------------------------------------------------

# ---- saying what happened, in words an editor uses ------------------------
# The screen's whole job is that somebody who has never seen the database can read a row aloud. So
# every column name, table name and JSON blob is translated here before it reaches the template, and
# the template does no thinking. These are pure functions on purpose -- they sit above the routes,
# import nothing from them, and the offline tests call them directly.

# {kind} is the thing, {name} is what it is called. A missing action falls through to the last line.
VERB = {"create": "added the {kind} {name}", "update": "edited the {kind} {name}",
        "delete": "deleted the {kind} {name}", "restore": "put the {kind} {name} back",
        "login": "signed in", "logout": "signed out",
        "login_failed": "tried to sign in as {name} and got the password wrong",
        "login_blocked": "was locked out after too many wrong passwords (as {name})",
        "password_changed": "changed their own password",
        "password_reset": "set a new password for {name}",
        "create_admin": "created the administrator account {name}"}

# table -> the noun an editor would use for one of them. `posts` is absent on purpose: it is eight
# different things (pages, blog posts, services, ...) and is answered per row by _post_context().
KIND = {"media": "picture or file", "leads": "enquiry", "warranties": "warranty record",
        "users": "person", "terms": "category or tag", "settings": "setting", "menus": "menu",
        "redirects": "redirect", "post_types": "content type", "taxonomies": "grouping",
        "payments": "payment", "audit_log": "activity entry"}

# post_types.name is plural ("Pages", "Case Studies") because it titles a list; a sentence wants one
# of them. Anything added later falls back to that plural name, the way base.html's ICON map falls
# back to i-dot -- a new content type reads slightly oddly rather than not at all.
POST_KIND = {"page": "page", "post": "blog post", "service": "service", "case_study": "case study",
             "event": "event", "partner": "technology partner", "datasheet": "datasheet",
             "product": "product"}

# column -> the label the editor already sees for it elsewhere in the admin
FIELD = {"blocks": "The writing on the page", "title": "Title", "slug": "Web address",
         "status": "Status", "published_at": "Publish date", "excerpt": "Summary",
         "featured_media_id": "Main picture", "parent_id": "Filed under", "menu_order": "Order",
         "meta": "Details", "seo": "Search engine settings", "terms": "Categories and tags",
         "author_id": "Author", "alt": "Description", "filename": "File name", "mime": "File type",
         "size": "File size", "key": "Stored as", "url": "Address", "uploaded_by": "Uploaded by",
         "role": "Permission level", "items": "Menu items", "value": "Value", "kind": "Form type",
         "message": "Message", "data": "Answers from the form", "post_id": "About",
         "serial": "Serial number", "customer_name": "Customer", "purchase_date": "Purchase date",
         "expiry_date": "Expiry date", "amc": "Annual maintenance contract", "remarks": "Remarks",
         "remarks_public": "Show the remarks to the customer", "from_path": "Old address",
         "to_url": "Goes to", "code": "Redirect type", "hits": "Times followed",
         "url_prefix": "Address starts with", "field_schema": "Its own fields",
         "has_pages": "Gets pages of its own", "in_sitemap": "Offered to search engines"}

STATUS = {"draft": "Draft", "published": "Published", "trash": "Deleted"}
DIFF_MAX = 2000   # ponytail: word-diffing two novels on a 50-row page is real CPU; past this, plain text


def _label_of(key):
    """A column name as a person would say it. The fallback is the transform settings.html already
    uses, so the two screens never disagree about what a key is called."""
    return FIELD.get(key) or str(key).replace("_", " ").capitalize()


def _block_name(t):
    """The plain-English name of a section type, from the same table the section picker uses."""
    return (EDITOR["names"].get(t) or ("", str(t), ""))[1]


def _word_diff(before, after):
    """The two texts, each marked up with what left and what arrived. Word-level, not character-
    level: a word is the unit somebody writing a page thinks in, and a character diff of "Better" ->
    "Getting Better." marks up the inside of words for no reader's benefit."""
    a, b = before.split(), after.split()
    was, now = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        old, new = escape(" ".join(a[i1:i2])), escape(" ".join(b[j1:j2]))
        if tag == "equal":
            was.append(old)
            now.append(new)
            continue
        if i2 > i1:
            was.append(Markup("<del>%s</del>") % old)
        if j2 > j1:
            now.append(Markup("<ins>%s</ins>") % new)
    return Markup(" ").join(was), Markup(" ").join(now)


def _structural(was, now):
    """What changed when the words did not. blocks_text() deliberately drops every picture, link and
    setting (_NON_TEXT_KEYS), so swapping an image leaves two versions reading identically -- and
    "nothing changed" would be a lie about a save that certainly did something."""
    a, b = [x.get("type") for x in was], [x.get("type") for x in now]
    gained = Counter(b) - Counter(a)
    lost = Counter(a) - Counter(b)
    if gained or lost:
        said = []
        if gained:
            said.append("Added " + ", ".join(_block_name(t) for t in gained.elements()))
        if lost:
            said.append("Removed " + ", ".join(_block_name(t) for t in lost.elements()))
        return "; ".join(said) + "."
    if a != b:
        return "Moved the sections around."
    moved = [_block_name(t) for i, t in enumerate(b) if i < len(was) and was[i] != now[i]]
    if moved:
        return f"Changed a picture, link or setting in the {', '.join(moved)} section."
    return "Nothing an editor would see."


def _blocks_change(was, now):
    """(what it said, what it says, a sentence about it) for a page's content."""
    was, now = was or [], now or []
    t_was, t_now = blocks_text(was), blocks_text(now)
    if t_was == t_now:
        return escape(t_was), escape(t_now), _structural(was, now)
    if len(t_was.split()) > DIFF_MAX or len(t_now.split()) > DIFF_MAX:
        return escape(t_was), escape(t_now), "A long page \u2014 the change is somewhere in here."
    a, b = _word_diff(t_was, t_now)
    return a, b, ""


def _value(key, v, labels=None):
    """One stored value, as something readable. Falls through to JSON only when nothing better
    exists -- which, after this, is a shape nobody has met yet rather than the normal case."""
    if v is None or v == "" or v == [] or v == {}:
        return Markup('<span class="muted">nothing</span>')
    if key == "status":
        return escape(STATUS.get(v, v))
    if isinstance(v, bool):
        return escape("Yes" if v else "No")
    if key.endswith(("_at", "_date")) and isinstance(v, str):
        try:
            return escape(db.ist(v))
        except ValueError:
            pass                      # not a date after all; fall through and print it
    if key.endswith("_media_id") or key == "featured_media_id":
        return escape((db.get_media(v) or {}).get("filename") or f"picture {v}")
    if key == "terms" and isinstance(v, list):
        return escape(", ".join(_term_names(v)) or "none")
    if key == "items" and isinstance(v, list):
        return escape(", ".join(str(i.get("label") or "") for i in v if isinstance(i, dict)) or "none")
    if isinstance(v, dict):
        # meta/seo/data: one line per key, named by the content type's own field labels where we
        # know them (post_types.field_schema -- "Client", "Start date", "SKU")
        labels = labels or {}
        return Markup("<br>").join(Markup("<b>%s:</b> %s") % (labels.get(k) or _label_of(k), _value(k, x, labels))
                                   for k, x in sorted(v.items()))
    if isinstance(v, list):
        return escape(", ".join(str(x) for x in v))
    return escape(v)


def _term_names(ids):
    """Ids to names in one query, memoised for the page. Ids can outlive their terms -- deleting a
    taxonomy cascades its terms away -- so an unresolved one keeps its number rather than vanishing."""
    if not ids:
        return []
    found = db._cached(f"audit_terms_{','.join(map(str, sorted(ids)))}",
                       lambda: {r["id"]: r["name"] for r in db.rows(db.table("terms").select("id,name").in_("id", ids))})
    return [found.get(i, f"#{i}") for i in ids]


def _post_context(entries):
    """{row id: (what to call it, {meta key: its label})} for every post named on this page of the
    log -- one query, not one per row. A post row always survives (deleting one only trashes it), so
    this resolves for history as well as for today."""
    ids = [e["row_id"] for e in entries if e["table_name"] == "posts" and str(e["row_id"]).isdigit()]
    if not ids:
        return {}
    out = {}
    for r in db.rows(db.table("posts").select("id, post_type:post_types(slug,name,field_schema)").in_("id", ids)):
        pt = r.get("post_type") or {}
        kind = POST_KIND.get(pt.get("slug")) or pt.get("name") or "page or post"
        out[str(r["id"])] = (kind, {f.get("key"): f.get("label") for f in (pt.get("field_schema") or [])})
    return out


def _sentence(entry, posts):
    """The row, as a sentence. Never blank: an unknown action still reads as itself."""
    action, table = entry["action"], entry["table_name"]
    name = entry["label"] or entry["row_id"] or ""
    if table == "settings":
        name = _label_of(name)
    kind = posts.get(str(entry["row_id"]), ("page or post", {}))[0] if table == "posts" \
        else KIND.get(table) or (table or "").replace("_", " ")
    tmpl = VERB.get(action) or (action.replace("_", " ") + " the {kind} {name}")
    return Markup(tmpl).format(kind=kind, name=Markup("<b>%s</b>") % escape(name) if name else "")


def _present(entry, posts, people):
    """Everything the template needs, worked out here so the template does none of it."""
    person = people.get(entry["user_id"]) or ({"email": entry["user_email"]} if entry["user_email"] else None)
    labels = posts.get(str(entry["row_id"]), ("", {}))[1]
    fields = []
    for k, pair in sorted((entry["changes"] or {}).items()):
        if k == "blocks":
            was, now, note = _blocks_change(pair[0], pair[1])
        else:
            was, now, note = _value(k, pair[0], labels), _value(k, pair[1], labels), ""
        fields.append({"label": _label_of(k), "was": was, "now": now, "note": note})
    return {**entry, "can_restore": _restorable(entry), "fields": fields,
            "who": display_name(person) if person else "the website",
            "sentence": _sentence(entry, posts)}


AUDIT_ACTIONS = ("create", "update", "delete", "restore", "login", "logout", "login_failed",
                 "login_blocked", "password_changed", "password_reset", "create_admin")


def _restorable(entry):
    """What can be put back. An update can, always -- the "was" half of every changed field is
    stored. A deleted post can, because deleting a post only moves it to the trash. Every other
    delete is real, and re-creating the row would be a lie: the user's Supabase login is gone, the
    media file has left the bucket, the taxonomy's terms cascaded away. The entry still shows what
    the row held, which is what makes it evidence."""
    return entry["action"] == "update" or (entry["action"] == "delete" and entry["table_name"] == "posts")


@ui.get("/audit")
@ui_required("admin")
def audit():
    """Everything anybody did, newest first. Ordered by id rather than by `at` so the primary key
    does the sorting -- the two agree, ids being handed out in time order, and that is one index
    this table then does not need."""
    q = db.table("audit_log").select("*", count="exact")
    for arg, col in (("user", "user_id"), ("table", "table_name"), ("action", "action")):
        if (v := request.args.get(arg)) and v != "-":
            q = q.eq(col, v)
    if request.args.get("user") == "-":
        q = q.is_("user_id", "null")       # the website itself: a form sent by somebody not signed in
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("id", desc=True), page, 50)
    people = db.rows(db.table("users").select("id,email,name").order("email"))
    posts = _post_context(result["items"])
    by_id = {p["id"]: p for p in people}
    result["items"] = [_present(r, posts, by_id) for r in result["items"]]
    return render_template("admin/audit.html", result=result, page=page, people=people,
                           actions=AUDIT_ACTIONS, kinds=sorted(KIND.items()),
                           has_next=page * 50 < result["total"])


@ui.post("/audit/<int:pk>/restore")
@ui_required("admin")
def audit_restore(pk):
    """Write the "was" half of an entry back. One stored format, three writers: db.update() reaches
    anything keyed by id, and settings and menus are keyed by their own column, so they need the
    helper that knows that. The restore is an ordinary write, so it is itself logged."""
    entry = db.one(db.table("audit_log").select("*").eq("id", pk)) or abort(404)
    if not _restorable(entry):
        abort(400, "there is nothing on this entry to go back to")
    old = {k: pair[0] for k, pair in (entry["changes"] or {}).items()}
    name, row_id = entry["table_name"], entry["row_id"]
    # it was valid when it was saved; a block type can have been renamed or dropped since
    errors = validate_blocks(old["blocks"] or []) if "blocks" in old else []
    if name == "settings" and old.get("value") is None:
        # settings.value is NOT NULL, so "it did not exist before" cannot be restored by writing it
        errors = ["this setting had no value before that change"]
    if errors:
        flash(f"Cannot restore: {errors[0]}")
    else:
        if name == "posts" and "terms" in old:
            # set_post_terms() logs against the post, so the entry says table "posts" but the one
            # field in it is not a posts column: writing it back through db.update() would 400.
            db.set_post_terms(int(row_id), old["terms"] or [])
        elif name == "settings":
            db.set_settings({row_id: old.get("value")})
        elif name == "menus":
            db.set_menu(row_id, old.get("items") or [])
        else:
            db.update(name, row_id, old, action="restore")
        flash(f"Put {entry['label'] or name} back the way it was.")
    return redirect(url_for("admin_ui.audit", **{k: v for k, v in request.args.items()}))
