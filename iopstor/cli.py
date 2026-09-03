"""flask CLI commands: migrate (apply migrations/*.sql through Supabase), seed, create-admin."""
import pathlib

import click
from flask.cli import with_appcontext
from postgrest import APIError

from . import db
from .db import slugify

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"


@click.command("migrate")
@with_appcontext
def migrate():
    """Apply unapplied migrations/*.sql (in name order) via the apply_migration() RPC created by 0000_bootstrap.sql."""
    sb = db.sb()
    try:
        applied = {r["filename"] for r in sb.table("schema_migrations").select("filename").execute().data}
    except APIError:
        raise click.ClickException("schema_migrations not found: run migrations/0000_bootstrap.sql once in Supabase Studio's SQL editor first")
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name.startswith("0000_") or path.name in applied:
            continue
        try:
            ok = sb.rpc("apply_migration", {"name": path.name, "sql": path.read_text()}).execute().data
        except APIError as e:
            raise click.ClickException(f"{path.name}: {getattr(e, 'message', e)}")
        click.echo(f"applied {path.name}" if ok else f"skipped {path.name} (already applied)")
    click.echo("migrations up to date")


# ---- seed ------------------------------------------------------------------

POST_TYPES = [  # slug, name, url_prefix, hierarchical, jsonld_type, taxonomies, field_schema
    ("page", "Pages", "", False, None, [], []),
    ("post", "Blog", "blog", False, "BlogPosting", ["category", "tag"], []),
    ("service", "Services", "services", True, "Service", [], [
        {"key": "icon", "label": "Icon", "type": "text", "required": False},
        {"key": "summary", "label": "One-line summary", "type": "text", "required": False}]),
    ("case_study", "Case Studies", "case-studies", False, "Article", ["industry", "solution"], [
        {"key": "client", "label": "Client", "type": "text", "required": True},
        {"key": "challenge", "label": "Challenge", "type": "textarea", "required": False},
        {"key": "solution_text", "label": "Solution", "type": "textarea", "required": False},
        {"key": "results", "label": "Results", "type": "textarea", "required": False}]),
    ("event", "Events", "events", False, "Event", [], [
        {"key": "start_date", "label": "Start date", "type": "date", "required": True},
        {"key": "end_date", "label": "End date", "type": "date", "required": False},
        {"key": "location", "label": "Location", "type": "text", "required": False}]),
    ("partner", "Technology Partners", "partners", False, "Organization", [], [
        {"key": "logo_media_id", "label": "Logo", "type": "media", "required": False},
        {"key": "website", "label": "Website", "type": "url", "required": False}]),
    ("datasheet", "Datasheets", "datasheets", False, None, [], [
        {"key": "file_media_id", "label": "PDF", "type": "media", "required": True},
        {"key": "product_family", "label": "Product family", "type": "text", "required": False}]),
    ("product", "Products", "products", False, "Product", ["category"], [
        {"key": "price", "label": "Price", "type": "number", "required": False},
        {"key": "currency", "label": "Currency", "type": "text", "required": False},
        {"key": "sku", "label": "SKU", "type": "text", "required": False},
        {"key": "specs", "label": "Specifications", "type": "json", "required": False},
        {"key": "datasheet_media_id", "label": "Datasheet PDF", "type": "media", "required": False}]),
]
TAXONOMIES = {
    "industry": ("Industry", ["Finance", "Education", "Post Production", "Services", "Distribution", "Travel", "Logistics"]),
    "solution": ("Solution", ["Virtualization", "Big Data", "Media", "Private Cloud", "HCI"]),
    "category": ("Category", []),
    "tag": ("Tag", []),
}
SERVICES = {
    "Storage": ["NAS", "DAS", "SAS", "AWS Integration (DR)"],
    "Hyper Converged Media": ["Proxmox", "VMware"],
    "Cloud": ["Desktop as a Service", "Storage as a Service", "VPS", "Linux Containers", "Serverless", "S3 Bucket Solutions",
              "Disaster Recovery as a Service (DRaaS)"],
    "AI": ["On-prem AI Servers"],
    "Software Based": ["SQL Server", "Tally", "SAP"],
}
CASE_STUDIES = [  # client, industry, solution
    ("LKS", "Finance", "Virtualization"), ("SCM", "Education", "Big Data"), ("FM", "Post Production", "Media"),
    ("DCSL", "Services", "Private Cloud"), ("SSC", "Distribution", "Private Cloud"), ("ATPL", "Travel", "HCI"),
    ("KLPL", "Logistics", "Private Cloud"),
]
EVENTS = [("Broadcast 2018", "2018-01-01"), ("Seagate Collaboration December 2018", "2018-12-01")]
ABOUT = (
    "IOPStor specializes in software defined storage and solves the productivity problems SMBs and large enterprises face every day.\n\n"
    "With our unique convergence of hardware, software, and storage expertise, we bring you IOPStor flash and all-flash storage arrays, "
    "offering enterprise reliability and performance at a value unheard of in storage.\n\n"
    "Unify your business-critical applications with an IOPStor storage array that fits the performance and capacity requirements of your "
    "application. IOPStor unifies block and file storage, grows to nearly 5PB in a rack, is available in hybrid and all-flash configurations, "
    "and uses the block storage file system to guarantee data stays pristine and safe.\n\n"
    "With storage needs growing and an opportunity to serve an under-served market for customized storage, IOPStor was founded by "
    "Gulbirr Bhatia (Prime ABGB) and Noshir Dalal, who have a cumulative experience of more than 50 years in the IT space."
)
SETTINGS = {
    "site_name": "IOPSTOR", "tagline": "Software defined storage, cloud and HCI for SMBs and enterprises", "logo_url": "",
    "default_og_image": "", "social_links": [], "ga_id": "", "contact_email": "", "contact_phone": "", "address": "", "robots_extra": "",
}


def _get_or_create(name, keys, defaults=None):
    q = db.table(name).select("*")
    for k, v in keys.items():
        q = q.eq(k, v)
    return db.one(q) or db.insert(name, {**keys, **(defaults or {})})


RESET = False  # set by `flask seed --reset-content`: overwrite blocks/excerpt/meta of the seed-defined posts


def _post(pt, title, *, slug=None, parent=None, blocks=None, meta=None, terms=(), excerpt="", menu_order=0):
    """Get-or-create a published post; never overwrites existing content unless RESET."""
    slug = slug or slugify(title)
    blocks = blocks if blocks is not None else [{"type": "hero", "data": {"heading": title}}]
    post = db.one(db.table("posts").select("id").eq("post_type_id", pt["id"]).eq("slug", slug))
    if post is not None and RESET:
        db.update("posts", post["id"], {"blocks": blocks, "excerpt": excerpt, "meta": meta or {}, "menu_order": menu_order})
    if post is None:
        post = db.insert("posts", {
            "post_type_id": pt["id"], "slug": slug, "title": title, "parent_id": parent["id"] if parent else None, "excerpt": excerpt,
            "blocks": blocks, "meta": meta or {},
            "status": "published", "published_at": db.now_iso(), "menu_order": menu_order})
        if terms:
            db.set_post_terms(post["id"], [t["id"] for t in terms])
    return post


def run_seed():
    types = {}
    for slug, name, prefix, hier, ld, taxes, schema in POST_TYPES:
        types[slug] = _get_or_create("post_types", {"slug": slug}, dict(name=name, url_prefix=prefix, hierarchical=hier, jsonld_type=ld, taxonomies=taxes, field_schema=schema))
    db.uncache("post_types")
    terms = {}
    for slug, (name, names) in TAXONOMIES.items():
        tax = _get_or_create("taxonomies", {"slug": slug}, {"name": name})
        for n in names:
            terms[(slug, n)] = _get_or_create("terms", {"taxonomy_id": tax["id"], "slug": slugify(n)}, {"name": n})
    for i, (group, children) in enumerate(SERVICES.items()):
        parent = _post(types["service"], group, menu_order=i, excerpt=f"{', '.join(children[:3])}{' and more' if len(children) > 3 else ''}.",
                       blocks=[{"type": "hero", "data": {"heading": group, "subheading": f"{group} solutions from IOPSTOR: {', '.join(children)}.",
                                                          "cta_label": "Talk to an engineer", "cta_url": "/contact-us"}}])
        for j, child in enumerate(children):
            _post(types["service"], child, parent=parent, menu_order=j, excerpt=f"{child} solutions, sized for your workload.",
                  blocks=[{"type": "hero", "data": {"heading": child, "subheading": f"Enterprise-grade {child} from IOPSTOR.", "cta_label": "Request a quote", "cta_url": "/contact-us"}},
                          {"type": "cta", "data": {"heading": f"Need {child} for your business?", "text": "Tell us about your workload and we will size a solution.", "button_label": "Contact us", "button_url": "/contact-us"}}])
    for i, (client, industry, solution) in enumerate(CASE_STUDIES):
        _post(types["case_study"], f"{client} — {industry} ({solution})", slug=slugify(client), menu_order=i,
              meta={"client": client}, terms=[terms[("industry", industry)], terms[("solution", solution)]])
    for title, start in EVENTS:
        _post(types["event"], title, meta={"start_date": start})
    page = types["page"]
    _post(page, "Home", slug="home", excerpt=SETTINGS["tagline"], blocks=[
        {"type": "hero", "data": {"heading": "Software defined storage, built for your workload",
                                  "subheading": "Flash and all-flash storage arrays, private cloud, hyper-converged infrastructure and on-prem AI servers with enterprise reliability at a value unheard of in storage.",
                                  "cta_label": "Talk to us", "cta_url": "/contact-us"}},
        {"type": "post_list", "data": {"post_type": "service", "top_level": True, "limit": 6, "heading": "What we do"}},
        {"type": "stats", "data": {"items": [{"value": "5 PB", "label": "in a single rack"}, {"value": "50+", "label": "years of combined IT experience"},
                                             {"value": "Block + file", "label": "unified storage"}, {"value": "Hybrid / all-flash", "label": "configurations"}]}},
        {"type": "post_list", "data": {"post_type": "case_study", "limit": 3, "heading": "Case studies"}},
        {"type": "cta", "data": {"heading": "Need customised storage?", "text": "Our engineers size every solution to your performance and capacity needs.",
                                 "button_label": "Request a quote", "button_url": "/contact-us"}}])
    _post(page, "About Us", blocks=[{"type": "hero", "data": {"heading": "About IOPStor"}},
                                    {"type": "rich_text", "data": {"html": "".join(f"<p>{p}</p>" for p in ABOUT.split("\n\n"))}}])
    _post(page, "Careers", blocks=[{"type": "hero", "data": {"heading": "Careers"}}, {"type": "contact_form", "data": {"kind": "career", "heading": "Send us your CV"}}])
    _post(page, "Contact Us", blocks=[{"type": "hero", "data": {"heading": "Contact Us"}}, {"type": "contact_form", "data": {"kind": "contact"}}])
    _post(page, "Technology Partners", blocks=[{"type": "hero", "data": {"heading": "Technology Partners"}}, {"type": "post_list", "data": {"post_type": "partner", "limit": 50}}])
    existing = db.settings()
    db.set_settings({k: v for k, v in SETTINGS.items() if k not in existing})
    services_menu = [{"label": g, "url": f"/services/{slugify(g)}"} for g in SERVICES]
    _get_or_create("menus", {"slug": "header"}, {"name": "Header", "items": [
        {"label": "Services", "url": "/services", "children": services_menu},
        {"label": "Case Studies", "url": "/case-studies"}, {"label": "Blog", "url": "/blog"},
        {"label": "Technology Partners", "url": "/technology-partners"},
        {"label": "Company", "url": "/about-us", "children": [{"label": "About Us", "url": "/about-us"}, {"label": "Events", "url": "/events"},
                                                              {"label": "Careers", "url": "/careers"}, {"label": "Contact Us", "url": "/contact-us"}]},
        {"label": "Datasheets", "url": "/datasheets"}, {"label": "Products", "url": "/products"}]})
    _get_or_create("menus", {"slug": "footer"}, {"name": "Footer", "items": [{"label": "About Us", "url": "/about-us"}, {"label": "Contact Us", "url": "/contact-us"},
                                                                          {"label": "Careers", "url": "/careers"}, {"label": "Blog", "url": "/blog"}]})
    db.uncache("post_types", "settings")


@click.command("seed")
@click.option("--reset-content", is_flag=True, help="Also overwrite blocks/excerpt/meta of the seed-defined posts with the seed version.")
@with_appcontext
def seed(reset_content):
    """Create post types, taxonomies, the site-map pages, settings and menus (idempotent, never overwrites unless --reset-content)."""
    global RESET
    RESET = reset_content
    run_seed()
    RESET = False
    n = db.table("posts").select("id", count="exact").limit(1).execute().count
    click.echo(f"seeded: {n} posts, {len(db.post_types())} post types")


@click.command("create-admin")
@click.argument("email")
@click.argument("password")
@with_appcontext
def create_admin(email, password):
    """Create a Supabase Auth user + CMS admin row."""
    from supabase_auth.errors import AuthError

    from .auth import create_auth_user

    if db.one(db.table("users").select("id").eq("email", email)):
        raise click.ClickException(f"{email} already exists")
    try:
        user = create_auth_user(email, password, role="admin")
    except AuthError as e:
        raise click.ClickException(f"supabase auth: {getattr(e, 'message', e)}")
    click.echo(f"admin created: {user['email']} ({user['id']})")


def register(app):
    for cmd in (migrate, seed, create_admin):
        app.cli.add_command(cmd)
