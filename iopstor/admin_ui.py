"""Browser admin at /admin: server-rendered forms on top of the same validation as the admin API.
Login = Supabase email/password; tokens live in the signed Flask session cookie."""
import json
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from postgrest import APIError
from supabase_auth.errors import AuthError
from werkzeug.exceptions import HTTPException

from . import db
from .admin_api import apply_post
from .auth import ROLES, create_auth_user, current_user, delete_auth_user, login
from .blocks import BLOCKS, EDITOR, LAYOUTS, render_blocks
from .storage import delete_media, save_upload

ui = Blueprint("admin_ui", __name__, url_prefix="/admin", template_folder="templates")
SETTING_KEYS = ("site_name", "tagline", "logo_url", "default_og_image", "social_links", "ga_id", "contact_email", "contact_phone", "address", "robots_extra")
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
    return {"csrf": session["csrf"], "admin_user": getattr(g, "user", None), "post_types": db.post_types() if getattr(g, "user", None) else []}


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
            flash("Wrong email or password.")
            return render_template("admin/login.html"), 401
        if db.one(db.table("users").select("id").eq("id", s["user_id"])) is None:
            flash("This login has no CMS account. Ask an admin to add you under Users.")
            return render_template("admin/login.html"), 403
        session["access_token"], session["refresh_token"] = s["access_token"], s["refresh_token"]
        return redirect(_safe_next())
    return render_template("admin/login.html")


@ui.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin_ui.login_page"))


# ---- dashboard & posts -----------------------------------------------------

@ui.get("/")
@ui_required()
def dashboard():
    counts = {t["slug"]: db.table("posts").select("id", count="exact").eq("post_type_id", t["id"]).limit(1).execute().count for t in db.post_types()}
    new_leads = db.table("leads").select("id", count="exact").eq("status", "new").limit(1).execute().count
    return render_template("admin/dashboard.html", counts=counts, new_leads=new_leads)


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
         "published_at": f.get("published_at", ""), "excerpt": f.get("excerpt", ""), "menu_order": f.get("menu_order") or 0,
         "parent_id": f.get("parent_id") or None, "featured_media_id": f.get("featured_media_id") or None,
         "terms": [int(t) for t in f.getlist("terms")], "seo": {k: f.get(f"seo_{k}", "") for k in SEO_KEYS if f.get(f"seo_{k}")}}
    meta = dict(existing.get("meta") or {}) if existing else {}
    for field in pt.get("field_schema") or []:
        raw = f.get(f"meta_{field['key']}", "")
        if field.get("type") == "json":
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


def _form_context(pt, post, errors=None):
    taxonomies = [t for t in db.rows(db.table("taxonomies").select("*, terms(*)").order("id")) if t["slug"] in (pt.get("taxonomies") or [])]
    parents = db.rows(db.table("posts").select("id,title,slug").eq("post_type_id", pt["id"]).order("title")) if pt["hierarchical"] else []
    media = db.rows(db.table("media").select("id,filename,url,mime,alt").order("id", desc=True).limit(200))
    term_ids = {t["id"] for t in (post or {}).get("terms") or []}
    return dict(pt=pt, post=post, errors=errors or {}, taxonomies=taxonomies, parents=[p for p in parents if not post or p["id"] != post["id"]],
                media=media, term_ids=term_ids, blocks=BLOCKS, blocks_ui=EDITOR, layouts=list(LAYOUTS.items()), blocks_json=json.dumps((post or {}).get("blocks") or [], indent=2, ensure_ascii=False),
                seo_keys=SEO_KEYS)


def _save(pt, existing):
    b = _form_body(pt, existing)
    try:
        changes, term_ids = apply_post(existing, b)
    except HTTPException as e:
        payload = e.response.get_json() if e.response is not None else {"error": e.description}
        errors = payload.get("fields") or {"_": payload.get("error")}
        keep = ("title", "slug", "status", "published_at", "excerpt", "menu_order", "parent_id", "featured_media_id", "meta", "seo")
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
    With ?i=N it returns just that one block, so an edit swaps one <section> instead of reloading."""
    try:
        blocks = json.loads(request.form.get("blocks") or "[]")
    except ValueError:
        blocks = []
    if not isinstance(blocks, list):
        blocks = []
    i = request.form.get("i", type=int)
    if i is not None:
        return render_blocks(blocks[i:i + 1], edit=True) if 0 <= i < len(blocks) else ""
    return render_template("admin/canvas.html", body=render_blocks(blocks, edit=True),
                           title=request.form.get("title", ""), excerpt=request.form.get("excerpt", ""),
                           has_hero=bool(blocks) and isinstance(blocks[0], dict) and blocks[0].get("type") == "hero")


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
    db.update("leads", pk, {"status": "handled" if request.form.get("status") == "handled" else "new"})
    return redirect(url_for("admin_ui.leads", **{k: v for k, v in request.args.items()}))


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
    return render_template("admin/settings.html", s=s, keys=SETTING_KEYS)


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
