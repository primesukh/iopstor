"""Browser admin at /admin: server-rendered forms on top of the same validation as the admin API.
Login = Supabase email/password; tokens live in the signed Flask session cookie."""
import json
import secrets
from datetime import date
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from postgrest import APIError
from supabase_auth.errors import AuthError
from werkzeug.exceptions import HTTPException

from . import db, seo
from .admin_api import apply_post
from .auth import ROLES, create_auth_user, current_user, delete_auth_user, login, set_password
from .blocks import BLOCKS, EDITOR, LAYOUTS, at_path, render_blocks, warranty_active
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
    if not has_request_context():  # CLI / tests rendering blocks outside a request
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
        try:
            s = login(request.form.get("email", ""), request.form.get("password", ""))
        except AuthError:
            return render_template("admin/login.html", error="Wrong email or password."), 401
        if db.one(db.table("users").select("id").eq("id", s["user_id"])) is None:
            return render_template("admin/login.html",
                                   error="This login has no CMS account. Ask an admin to add you under Users."), 403
        session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
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
    errors = []
    if request.method == "POST":
        f = request.form
        errors = _password_errors(f.get("new_password", ""), f.get("confirm", ""))
        if not errors:
            try:
                login(g.user["email"], f.get("current_password", ""))
            except AuthError:
                errors = ["That is not your current password."]
        if not errors:
            try:
                set_password(g.user, f["new_password"])
                s = login(g.user["email"], f["new_password"])
            except AuthError as e:
                errors = [f"Supabase refused the new password: {getattr(e, 'message', e)}"]
            else:
                session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
                flash("Password changed.")
                return redirect(url_for("admin_ui.account"))
    return render_template("admin/account.html", errors=errors), (400 if errors else 200)


@ui.get("/logout")
def logout():
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
    recent_posts = db.rows(db.table("posts").select("id,title,status,updated_at").order("updated_at", desc=True).limit(5))
    return render_template("admin/dashboard.html", counts=counts, new_leads=counts["_leads"],
                           recent_leads=recent_leads, recent_posts=recent_posts)


@ui.get("/posts")
@ui_required()
def posts():
    q = db.select_posts(count="exact")
    pt = db.post_type(slug=request.args.get("type", "")) if request.args.get("type") else None
    if pt:
        q = q.eq("post_type_id", pt["id"])
    if s := request.args.get("status"):
        q = q.eq("status", s)
    if s := request.args.get("q"):
        s = s.replace(",", " ").replace("(", " ").replace(")", " ")
        q = q.or_(f"title.ilike.%{s}%,slug.ilike.%{s}%")
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = db.paginate(q.order("updated_at", desc=True), page, 50)
    result["items"] = db.with_paths(result["items"])
    return render_template("admin/posts.html", result=result, current_type=pt, page=page, has_next=page * 50 < result["total"])


def _form_body(pt, existing):
    """Turn the post form into the same body dict the JSON API accepts."""
    f = request.form
    b = {"post_type": pt["slug"], "title": f.get("title", ""), "slug": f.get("slug", ""), "status": f.get("status", "draft"),
         "published_at": f.get("published_at", ""), "excerpt": f.get("excerpt", ""),
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
    post = db.get_post(pk) or abort(404)
    db.table("posts").delete().eq("id", pk).execute()
    flash(f"Deleted “{post['title']}”.")
    return redirect(url_for("admin_ui.posts", type=post["post_type"]["slug"]))


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
    db.table("warranties").delete().eq("id", pk).execute()
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
