"""Admin REST API at /api/admin/v1 for the future admin UI. Bearer JWT from Supabase Auth; roles editor < admin."""
from flask import Blueprint, abort, g, jsonify, make_response, request
from postgrest import APIError
from supabase_auth.errors import AuthApiError, AuthError
from werkzeug.exceptions import HTTPException

from . import db
from .auth import ROLES, create_auth_user, delete_auth_user, login, logout, refresh, require_role
from .blocks import BLOCKS, validate_blocks
from .storage import delete_media, save_upload

bp = Blueprint("admin_api", __name__, url_prefix="/api/admin/v1")


# ---- helpers ---------------------------------------------------------------

def fail(msg, code=400, **fields):
    abort(make_response(jsonify(error=msg, **({"fields": fields} if fields else {})), code))


@bp.errorhandler(HTTPException)
def _http_error(e):
    if e.response is not None:  # raised via fail()
        return e.response
    return jsonify(error=e.description), e.code


@bp.errorhandler(APIError)
def _pg_error(e):
    code = getattr(e, "code", "") or ""
    return jsonify(error=f"database: {getattr(e, 'message', e)}"), 409 if code == "23505" else 502


@bp.errorhandler(AuthError)
def _auth_error(e):
    return jsonify(error=f"supabase auth: {getattr(e, 'message', e)}"), 502


def body():
    b = request.get_json(silent=True)
    if not isinstance(b, dict):
        fail("JSON object body required")
    return b


def page_args():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = min(max(request.args.get("per_page", 20, type=int) or 20, 1), 100)
    return page, per_page


def paginated(q, transform=lambda x: x):
    page, per_page = page_args()
    return jsonify(db.paginate(q, page, per_page, transform))


def get_or_404(name, pk, select="*"):
    return db.one(db.table(name).select(select).eq("id", pk)) or abort(404)


def pick(b, fields):
    return {f: b[f] for f in fields if f in b}


def parse_dt(value):
    if value in (None, ""):
        return None
    try:
        return db.parse_dt(value).isoformat()
    except (TypeError, ValueError):
        fail("validation failed", published_at="use ISO 8601")


# ---- auth ------------------------------------------------------------------

@bp.post("/auth/login")
def auth_login():
    b = body()
    try:
        s = login(b.get("email", ""), b.get("password", ""))
    except AuthApiError:
        fail("invalid email or password", 401)
    user = db.one(db.table("users").select("*").eq("id", s["user_id"]))
    if user is None:
        fail("no CMS account for this login; ask an admin to add you", 403)
    return jsonify(access_token=s["access_token"], refresh_token=s["refresh_token"], expires_in=s["expires_in"], user=user)


@bp.post("/auth/refresh")
def auth_refresh():
    try:
        s = refresh(body().get("refresh_token", ""))
    except AuthError:
        fail("invalid refresh token", 401)
    return jsonify(access_token=s["access_token"], refresh_token=s["refresh_token"], expires_in=s["expires_in"])


@bp.post("/auth/logout")
def auth_logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            logout(auth[7:])
        except AuthError:
            pass
    return "", 204


@bp.get("/auth/me")
@require_role("editor")
def me():
    return jsonify(g.user)


# ---- post types ------------------------------------------------------------

PT_FIELDS = ("name", "hierarchical", "field_schema", "taxonomies", "jsonld_type", "in_sitemap")


def _post_type_or_404(slug):
    return db.post_type(slug=slug) or abort(404)


@bp.get("/post-types")
@require_role("editor")
def list_post_types():
    return jsonify(db.post_types())


@bp.post("/post-types")
@require_role("admin")
def create_post_type():
    b = body()
    if not b.get("name"):
        fail("validation failed", name="required")
    slug = db.slugify(b.get("slug") or b["name"])
    if db.post_type(slug=slug):
        fail("slug already exists", 409, slug=slug)
    row = {"slug": slug, "name": b["name"], "url_prefix": (b["url_prefix"] if b.get("url_prefix") is not None else slug).strip("/"), **pick(b, PT_FIELDS)}
    pt = db.insert("post_types", row)
    db.uncache("post_types")
    return jsonify(pt), 201


@bp.get("/post-types/<slug>")
@require_role("editor")
def get_post_type(slug):
    return jsonify(_post_type_or_404(slug))


@bp.patch("/post-types/<slug>")
@require_role("admin")
def update_post_type(slug):
    pt = _post_type_or_404(slug)
    b = body()
    changes = pick(b, PT_FIELDS)
    if "url_prefix" in b:
        changes["url_prefix"] = (b["url_prefix"] or "").strip("/")
    db.uncache("post_types")
    return jsonify(db.update("post_types", pt["id"], changes) if changes else pt)


@bp.delete("/post-types/<slug>")
@require_role("admin")
def delete_post_type(slug):
    pt = _post_type_or_404(slug)
    if db.one(db.table("posts").select("id").eq("post_type_id", pt["id"])):
        fail("post type still has posts", 409)
    db.table("post_types").delete().eq("id", pt["id"]).execute()
    db.uncache("post_types")
    return "", 204


# ---- posts -----------------------------------------------------------------

def apply_post(existing, b):
    """Validate a create/PATCH body → (changes, term_ids | None). existing is None on create."""
    create = existing is None
    changes, errors = {}, {}
    if create or "post_type" in b:
        pt = db.post_type(slug=str(b.get("post_type", "")))
        if pt is None:
            errors["post_type"] = "unknown post type"
        else:
            changes["post_type_id"] = pt["id"]
    type_id = changes.get("post_type_id") or (existing["post_type_id"] if existing else None)
    if create or "title" in b:
        title = str(b.get("title") or "").strip()
        if not title:
            errors["title"] = "required"
        else:
            changes["title"] = title[:300]
    if "blocks" in b:
        errs = validate_blocks(b["blocks"])
        if errs:
            errors["blocks"] = errs
        else:
            changes["blocks"] = b["blocks"]
    for f in ("meta", "seo"):
        if f in b:
            if not isinstance(b[f], dict):
                errors[f] = "must be an object"
            else:
                changes[f] = b[f]
    if "status" in b:
        if b["status"] not in ("draft", "published"):
            errors["status"] = "draft or published"
        else:
            changes["status"] = b["status"]
    if "published_at" in b:
        changes["published_at"] = parse_dt(b["published_at"])
    if "excerpt" in b:
        changes["excerpt"] = b["excerpt"] or ""
    if "menu_order" in b:
        changes["menu_order"] = int(b["menu_order"] or 0)
    if "featured_media_id" in b:
        if b["featured_media_id"] and db.get_media(int(b["featured_media_id"])) is None:
            errors["featured_media_id"] = "unknown media"
        else:
            changes["featured_media_id"] = int(b["featured_media_id"]) if b["featured_media_id"] else None
    if "parent_id" in b:
        if b["parent_id"]:
            parent = db.one(db.table("posts").select("id,post_type_id").eq("id", int(b["parent_id"])))
            if parent is None or parent["post_type_id"] != type_id or (existing and parent["id"] == existing["id"]):
                errors["parent_id"] = "parent must be an existing post of the same type"
            else:
                changes["parent_id"] = parent["id"]
        else:
            changes["parent_id"] = None
    term_ids = None
    if "terms" in b:
        term_ids = sorted({int(i) for i in (b["terms"] or [])})
        found = db.rows(db.table("terms").select("id").in_("id", term_ids)) if term_ids else []
        if len(found) != len(term_ids):
            errors["terms"] = "unknown term id"
    if errors:
        fail("validation failed", **errors)
    exclude = existing["id"] if existing else None
    if b.get("slug"):
        wanted = db.slugify(b["slug"])
        if db.unique_slug(type_id, wanted, exclude) != wanted:
            fail("slug already in use", 409, slug=wanted)
        changes["slug"] = wanted
    elif create:
        changes["slug"] = db.unique_slug(type_id, db.slugify(changes["title"]))
    status = changes.get("status", existing["status"] if existing else "draft")
    published_at = changes["published_at"] if "published_at" in changes else (existing["published_at"] if existing else None)
    if status == "published" and not published_at:
        changes["published_at"] = db.now_iso()
    return changes, term_ids


@bp.get("/posts")
@require_role("editor")
def list_posts():
    q = db.select_posts(count="exact")
    if t := request.args.get("type"):
        pt = db.post_type(slug=t) or abort(404)
        q = q.eq("post_type_id", pt["id"])
    if s := request.args.get("status"):
        q = q.eq("status", s)
    if term := request.args.get("term", type=int):
        q = db.table("posts").select(db.POST_SELECT_BY_TERM, count="exact").eq("post_terms.term_id", term)
        if t:
            q = q.eq("post_type_id", pt["id"])
    if s := request.args.get("q"):
        s = s.replace(",", " ").replace("(", " ").replace(")", " ")  # ponytail: PostgREST or= syntax delimiters
        q = q.or_(f"title.ilike.%{s}%,slug.ilike.%{s}%")
    if "parent_id" in request.args:
        pid = request.args.get("parent_id", type=int)
        q = q.eq("parent_id", pid) if pid else q.is_("parent_id", "null")
    page, per_page = page_args()
    result = db.paginate(q.order("updated_at", desc=True), page, per_page)
    result["items"] = db.with_paths(result["items"])
    return jsonify(result)


@bp.post("/posts")
@require_role("editor")
def create_post():
    changes, term_ids = apply_post(None, body())
    changes["author_id"] = g.user["id"]
    row = db.insert("posts", changes)
    if term_ids:
        db.set_post_terms(row["id"], term_ids)
    return jsonify(db.hydrate(db.get_post(row["id"]))), 201


@bp.get("/posts/<int:pk>")
@require_role("editor")
def get_post(pk):
    return jsonify(db.hydrate(db.get_post(pk) or abort(404)))


@bp.patch("/posts/<int:pk>")
@require_role("editor")
def update_post(pk):
    post = db.get_post(pk) or abort(404)
    changes, term_ids = apply_post(post, body())
    if changes:
        db.update("posts", pk, changes)
    if term_ids is not None:
        db.set_post_terms(pk, term_ids)
    db.uncache(f"post_index_{post['post_type_id']}")
    return jsonify(db.hydrate(db.get_post(pk)))


@bp.delete("/posts/<int:pk>")
@require_role("admin")
def delete_post(pk):
    get_or_404("posts", pk, "id")
    db.table("posts").delete().eq("id", pk).execute()
    return "", 204


# ---- taxonomies & terms ----------------------------------------------------

def _taxonomy(slug):
    return db.one(db.table("taxonomies").select("*").eq("slug", slug)) or abort(404)


def _terms_of(tax_id):
    return db.rows(db.table("terms").select("*").eq("taxonomy_id", tax_id).order("name"))


@bp.get("/taxonomies")
@require_role("editor")
def list_taxonomies():
    return jsonify(db.rows(db.table("taxonomies").select("*, terms(*)").order("id")))


@bp.post("/taxonomies")
@require_role("admin")
def create_taxonomy():
    b = body()
    if not b.get("name"):
        fail("validation failed", name="required")
    slug = db.slugify(b.get("slug") or b["name"])
    if db.one(db.table("taxonomies").select("id").eq("slug", slug)):
        fail("slug already exists", 409, slug=slug)
    return jsonify(db.insert("taxonomies", {"slug": slug, "name": b["name"]})), 201


@bp.patch("/taxonomies/<slug>")
@require_role("admin")
def update_taxonomy(slug):
    t = _taxonomy(slug)
    changes = pick(body(), ("name",))
    return jsonify(db.update("taxonomies", t["id"], changes) if changes else t)


@bp.delete("/taxonomies/<slug>")
@require_role("admin")
def delete_taxonomy(slug):
    t = _taxonomy(slug)
    db.table("taxonomies").delete().eq("id", t["id"]).execute()  # terms + post_terms cascade in Postgres
    return "", 204


@bp.get("/taxonomies/<slug>/terms")
@require_role("editor")
def list_terms(slug):
    return jsonify(_terms_of(_taxonomy(slug)["id"]))


@bp.post("/taxonomies/<slug>/terms")
@require_role("editor")
def create_term(slug):
    t = _taxonomy(slug)
    b = body()
    if not b.get("name"):
        fail("validation failed", name="required")
    term_slug = db.slugify(b.get("slug") or b["name"])
    if db.one(db.table("terms").select("id").eq("taxonomy_id", t["id"]).eq("slug", term_slug)):
        fail("term slug already exists", 409, slug=term_slug)
    return jsonify(db.insert("terms", {"taxonomy_id": t["id"], "slug": term_slug, "name": b["name"], "description": b.get("description") or ""})), 201


@bp.patch("/terms/<int:pk>")
@require_role("editor")
def update_term(pk):
    term = get_or_404("terms", pk)
    changes = pick(body(), ("name", "description"))
    return jsonify(db.update("terms", pk, changes) if changes else term)


@bp.delete("/terms/<int:pk>")
@require_role("editor")
def delete_term(pk):
    get_or_404("terms", pk, "id")
    db.table("terms").delete().eq("id", pk).execute()
    return "", 204


# ---- media -----------------------------------------------------------------

@bp.get("/media")
@require_role("editor")
def list_media():
    return paginated(db.table("media").select("*", count="exact").order("created_at", desc=True))


@bp.post("/media")
@require_role("editor")
def upload_media():
    fs = request.files.get("file") or fail("validation failed", file="multipart field 'file' required")
    media = save_upload(fs, g.user["id"])
    if request.form.get("alt"):
        media = db.update("media", media["id"], {"alt": request.form["alt"][:300]})
    return jsonify(media), 201


@bp.patch("/media/<int:pk>")
@require_role("editor")
def update_media(pk):
    media = get_or_404("media", pk)
    changes = pick(body(), ("alt",))
    return jsonify(db.update("media", pk, changes) if changes else media)


@bp.delete("/media/<int:pk>")
@require_role("editor")
def remove_media(pk):
    delete_media(get_or_404("media", pk))
    return "", 204


# ---- leads -----------------------------------------------------------------

@bp.get("/leads")
@require_role("editor")
def list_leads():
    q = db.table("leads").select("*", count="exact")
    if s := request.args.get("status"):
        q = q.eq("status", s)
    if k := request.args.get("kind"):
        q = q.eq("kind", k)
    return paginated(q.order("id", desc=True))


@bp.get("/leads/<int:pk>")
@require_role("editor")
def get_lead(pk):
    return jsonify(get_or_404("leads", pk))


@bp.patch("/leads/<int:pk>")
@require_role("editor")
def update_lead(pk):
    lead = get_or_404("leads", pk)
    b = body()
    if b.get("status") not in (None, "new", "handled"):
        fail("validation failed", status="new or handled")
    changes = pick(b, ("status",))
    return jsonify(db.update("leads", pk, changes) if changes else lead)


@bp.delete("/leads/<int:pk>")
@require_role("editor")
def delete_lead(pk):
    get_or_404("leads", pk, "id")
    db.table("leads").delete().eq("id", pk).execute()
    return "", 204


# ---- settings, menus, redirects -------------------------------------------

@bp.get("/settings")
@require_role("admin")
def get_settings():
    return jsonify(db.settings())


@bp.put("/settings")
@require_role("admin")
def put_settings():
    db.set_settings(body())
    return jsonify(db.settings())


@bp.get("/menus")
@require_role("editor")
def list_menus():
    return jsonify(db.rows(db.table("menus").select("*").order("id")))


@bp.put("/menus/<slug>")
@require_role("admin")
def put_menu(slug):
    b = body()
    if not isinstance(b.get("items", []), list):
        fail("validation failed", items="must be a list")
    slug = db.slugify(slug)
    row = {"slug": slug, "name": b.get("name") or slug, **pick(b, ("items",))}
    existing = db.one(db.table("menus").select("*").eq("slug", slug))
    if existing:
        row = {**existing, **{k: v for k, v in row.items() if k in b or k == "slug"}}
    return jsonify(db.table("menus").upsert(row, on_conflict="slug").execute().data[0])


@bp.get("/redirects")
@require_role("admin")
def list_redirects():
    return jsonify(db.rows(db.table("redirects").select("*").order("id")))


@bp.post("/redirects")
@require_role("admin")
def create_redirect():
    b = body()
    from_path = "/" + str(b.get("from_path") or "").strip("/")
    if from_path == "/" or not b.get("to_url"):
        fail("validation failed", from_path="required, not '/'", to_url="required")
    if db.one(db.table("redirects").select("id").eq("from_path", from_path)):
        fail("redirect already exists", 409, from_path=from_path)
    return jsonify(db.insert("redirects", {"from_path": from_path, "to_url": b["to_url"], "code": 302 if b.get("code") == 302 else 301})), 201


@bp.delete("/redirects/<int:pk>")
@require_role("admin")
def delete_redirect(pk):
    get_or_404("redirects", pk, "id")
    db.table("redirects").delete().eq("id", pk).execute()
    return "", 204


# ---- users, blocks, payments -----------------------------------------------

@bp.get("/users")
@require_role("admin")
def list_users():
    return jsonify(db.rows(db.table("users").select("*").order("email")))


@bp.post("/users")
@require_role("admin")
def create_user():
    b = body()
    if not b.get("email") or not b.get("password"):
        fail("validation failed", email="required", password="required")
    if b.get("role", "editor") not in ROLES:
        fail("validation failed", role="editor or admin")
    if db.one(db.table("users").select("id").eq("email", b["email"])):
        fail("user already exists", 409)
    try:
        user = create_auth_user(b["email"], b["password"], b.get("role", "editor"), b.get("name", ""))
    except AuthApiError as e:
        fail(f"could not create login: {getattr(e, 'message', e)}", 400)
    return jsonify(user), 201


@bp.patch("/users/<uuid:pk>")
@require_role("admin")
def update_user(pk):
    user = get_or_404("users", str(pk))
    b = body()
    if "role" in b and b["role"] not in ROLES:
        fail("validation failed", role="editor or admin")
    changes = pick(b, ("role", "name"))
    return jsonify(db.update("users", str(pk), changes) if changes else user)


@bp.delete("/users/<uuid:pk>")
@require_role("admin")
def delete_user(pk):
    user = get_or_404("users", str(pk))
    if user["id"] == g.user["id"]:
        fail("cannot delete yourself", 409)
    delete_auth_user(user)
    return "", 204


@bp.get("/blocks")
@require_role("editor")
def list_blocks():
    return jsonify({t: {"required": r, "optional": o} for t, (r, o) in BLOCKS.items()})


@bp.get("/payments")
@require_role("editor")
def list_payments():
    return paginated(db.table("payments").select("*", count="exact").order("id", desc=True))
