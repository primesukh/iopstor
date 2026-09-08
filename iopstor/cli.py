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
    "site_name": "IOPSTOR",
    "tagline": "The Storage Specialist. Meet business needs now and tomorrow with converged infrastructure.",
    "logo_url": "", "default_og_image": "", "social_links": [], "ga_id": "",
    "contact_email": "sales@primeabgb.com", "contact_phone": "+91 98219 09800",
    "address": "Marketed by Prime ABGB Pvt. Ltd.\n106-109, Simlim Square, D. B. Marg,\nGrant Road, Mumbai 400007",
    "robots_extra": "",
}
# One line per top-level service, shown under the group name in the header's services panel and as
# the card blurb on the home page. Written from the client's flyers.
SERVICE_BLURBS = {
    "Storage": "Software-defined NAS, DAS and SAS built on ZFS, with AWS integration for disaster recovery.",
    "Hyper Converged Media": "Proxmox and VMware appliances that put compute, storage and networking in one box.",
    "Cloud": "Private cloud, desktop-as-a-service, VPS and S3 storage, running on hardware you own.",
    "AI": "On-prem AI servers, so your models and your data never leave the building.",
    "Software Based": "SQL Server, Tally and SAP, sized and tuned on IOPStor hardware.",
}
# Why choose our NAS — the ten reasons from the flyer, as the cards on the NAS page.
WHY_NAS = [
    ("Set it and forget it", "Once installed, it just works. No complex setup, no constant checking."),
    ("Built on ZFS", "The file system Fortune 500 companies, universities and data centres trust, for one reason: it never compromises on data safety."),
    ("Never lose a file again", "Automatic error correction, snapshots and self-healing storage mean your files are always there."),
    ("Snapshots: time travel for your data", "Deleted something by accident? Go back to yesterday, last week or last month in a few clicks."),
    ("Rock-solid performance, 24/7", "Backups, streaming, file sharing and remote access at speed, with no hiccups."),
    ("Plug, play and expand", "Add drives any time. No reformatting, no migration."),
    ("Military-grade encryption", "Enterprise-level encryption, optional. Only you hold the keys."),
    ("Fits every need, every user", "A creative professional with massive media files, a business with critical documents, or a home user wanting safe backups."),
    ("Save energy, save costs", "Efficient power usage means lower electricity bills and longer hardware life."),
    ("Supported by real humans", "No bots, no endless tickets. Our support team is real, friendly and ready to help."),
]
# ZFS basic features, from the All-Flash and Hybrid Array flyer.
ZFS_FEATURES = [
    ("Zettabyte File System", "A file system and logical volume manager with features found in no other. Robust, scalable and easy to administer."),
    ("128-bit file system", "Sixteen billion billion times the capacity of a 64-bit file system."),
    ("Read/write cache on RAM, SSD or NVMe", "Frequent reads are served from cache; writes land in cache first, so there is no write latency."),
    ("Snapshots and clones", "Recover deleted or corrupted data, and stay protected against ransomware."),
    ("Hot data movement", "Move older, unused data off the SSD pool and into the archival pool."),
    ("End-to-end data integrity", "Every block is checksummed."),
    ("RaidZ", "No write hole, instant array build, and a drive failure never interrupts work."),
    ("Hardware agnostic", "No lock-in. Replace any component with any vendor's."),
]
TESTIMONIALS = [
    ("I sleep better knowing my family photos and business files are in a ZFS NAS.", "Sarah M.", "Photographer"),
    ("Set it up once. Haven't had to touch it in 2 years.", "Mark D.", "Small Business Owner"),
]
PRODUCTS = [  # title, users, specs — the appliance details from the flyers
    ("IOPStor Classic", "5 - 10 users", {"CPU": "Xeon 4 core", "Memory": "32GB DDR4 2400", "Storage": "480GB Enterprise SSD",
                                         "Network": "10G x 2, 1G x 2", "Appliance workload": "5 - 10 users"}),
    ("IOPStor Edge", "10 - 20 users", {"CPU": "Xeon 6 core", "Memory": "64GB DDR4 2400", "Storage": "960GB Enterprise SSD",
                                       "Network": "10G x 2, 1G x 2", "Appliance workload": "10 - 20 users"}),
]


# The home page, in the order the design lays it out. A module constant so test_offline can run
# validate_blocks() over it without a database -- a bad array here would only surface at insert.
HOME = [
    {"type": "hero", "data": {"eyebrow": "The Storage Specialist",
                              "heading": "Your data. Safer. Smarter. Forever.",
                              "subheading": "Software-defined NAS, hyper-converged appliances and private cloud, all built on ZFS. "
                                            "Meet business needs now and tomorrow with converged infrastructure.",
                              "cta_label": "Talk to an engineer", "cta_url": "/contact-us",
                              "cta2_label": "See the appliances", "cta2_url": "/products"}},
    {"type": "stats", "data": {"items": [
        {"value": "300+", "label": "satisfied customers across the country"},
        {"value": "25+ yrs", "label": "of productivity and innovative solutions"},
        {"value": "3 yr", "label": "hardware warranty, unlimited support in year one"},
        {"value": "Zero", "label": "hidden or repetitive licence costs"}]}},
    {"type": "post_list", "data": {"post_type": "service", "top_level": True, "limit": 6, "eyebrow": "What we do",
                                   "heading": "Storage, virtualisation and cloud, delivered as one stack",
                                   "link_label": "All services", "link_url": "/services"}},
    # ponytail: two text columns because the client's rack photo is not in Media yet. Drop an
    # image section into the left column once it is uploaded; that is what the design shows.
    {"type": "columns", "data": {"cols": [
        [{"type": "rich_text", "data": {"html":
            "<h2>The file system trusted by Fortune 500 companies, universities and data centres</h2>"
            "<p>ZFS is a file system and logical volume manager that changes how storage is administered. "
            "Every block is checksummed, every snapshot is instant, and a failed drive never costs you a day's work.</p>"
            "<p><a href=\"/services/storage/nas\">All ZFS features &rarr;</a></p>"}}],
        [{"type": "rich_text", "data": {"html": "<ul>" + "".join(
            f"<li><strong>{t}</strong> — {d}</li>" for t, d in ZFS_FEATURES[:5]) + "</ul>"}}]]}},
    {"type": "post_list", "data": {"post_type": "product", "limit": 6, "eyebrow": "Appliances",
                                   "heading": "Sized from 5 users upward",
                                   "link_label": "All appliances", "link_url": "/products"}},
    {"type": "post_list", "data": {"post_type": "case_study", "limit": 4, "eyebrow": "Case studies",
                                   "heading": "Proven across finance, education, media and logistics",
                                   "link_label": "All case studies", "link_url": "/case-studies"}},
    {"type": "columns", "data": {"cols": [
        [{"type": "testimonial", "data": {"quote": TESTIMONIALS[0][0], "author": TESTIMONIALS[0][1], "role": TESTIMONIALS[0][2]}}],
        [{"type": "testimonial", "data": {"quote": TESTIMONIALS[1][0], "author": TESTIMONIALS[1][1], "role": TESTIMONIALS[1][2]}}]]}},
    {"type": "post_list", "data": {"post_type": "partner", "limit": 24, "eyebrow": "Technology partners"}},
    {"type": "cta", "data": {"heading": "Don't just store data. Protect it.",
                             "text": "Tell us the workload and the user count. We come back with a configuration and a one-time price, "
                                     "with no hidden or repetitive costs.",
                             "button_label": "Request a quote", "button_url": "/contact-us"}}]


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
        parent = _post(types["service"], group, menu_order=i, excerpt=SERVICE_BLURBS.get(group, ""),
                       blocks=[{"type": "hero", "data": {"heading": group, "subheading": f"{group} solutions from IOPSTOR: {', '.join(children)}.",
                                                          "cta_label": "Talk to an engineer", "cta_url": "/contact-us"}}])
        for j, child in enumerate(children):
            why = [{"type": "cards", "data": {"heading": "Why choose our NAS?", "items": [
                {"title": t, "text": d, "icon": f"{n + 1:02d}", "url": ""} for n, (t, d) in enumerate(WHY_NAS)]}},
                {"type": "cards", "data": {"heading": "ZFS, feature by feature", "items": [
                    {"title": t, "text": d, "icon": "", "url": ""} for t, d in ZFS_FEATURES]}}] if child == "NAS" else []
            _post(types["service"], child, parent=parent, menu_order=j, excerpt=f"{child} solutions, sized for your workload.",
                  blocks=[{"type": "hero", "data": {"heading": child, "eyebrow": group, "subheading": f"Enterprise-grade {child} from IOPSTOR.", "cta_label": "Request a quote", "cta_url": "/contact-us"}}]
                         + why
                         + [{"type": "cta", "data": {"heading": f"Need {child} for your business?", "text": "Tell us about your workload and we will size a solution.", "button_label": "Contact us", "button_url": "/contact-us"}}])
    for i, (client, industry, solution) in enumerate(CASE_STUDIES):
        _post(types["case_study"], f"{client} — {industry} ({solution})", slug=slugify(client), menu_order=i,
              meta={"client": client}, terms=[terms[("industry", industry)], terms[("solution", solution)]])
    for title, start in EVENTS:
        _post(types["event"], title, meta={"start_date": start})
    for i, (title, users, specs) in enumerate(PRODUCTS):
        _post(types["product"], title, menu_order=i, meta={"specs": specs},
              excerpt=f"Appliance workload {users}. Zero touch setup and management through a web GUI, and one source for support.",
              blocks=[{"type": "hero", "data": {"heading": title, "eyebrow": "Appliance",
                                                "subheading": f"Sized for {users}. Xeon, enterprise SSD and 10G networking, on ZFS.",
                                                "cta_label": "Request a quote", "cta_url": "/contact-us"}}])
    page = types["page"]
    # The home page, in the order the design lays it out.
    _post(page, "Home", slug="home", excerpt=SETTINGS["tagline"], blocks=HOME)
    _post(page, "About Us", excerpt="Customised storage for a market nobody else was serving.", blocks=[
        {"type": "hero", "data": {"dark": True, "eyebrow": "About us",
                                  "heading": "Customised storage for a market nobody else was serving",
                                  "subheading": "IOPStor was built by people who had spent decades watching SMBs pay enterprise prices for "
                                                "storage that still did not fit them."}},
        {"type": "rich_text", "data": {"html": "".join(f"<p>{p}</p>" for p in ABOUT.split("\n\n"))}}])
    _post(page, "Warranty Check", slug="warranty-check", excerpt="Check what cover your appliance still has.", blocks=[
        {"type": "hero", "data": {"dark": True, "eyebrow": "Support", "heading": "Check your warranty",
                                  "subheading": "Every IOPStor appliance ships with a three-year hardware warranty, and unlimited telephone "
                                                "and web support in the first year. Type your serial number to see where yours stands."}},
        {"type": "warranty_check", "data": {"heading": ""}}])
    _post(page, "Careers", blocks=[{"type": "hero", "data": {"heading": "Careers"}}, {"type": "contact_form", "data": {"kind": "career", "heading": "Send us your CV"}}])
    _post(page, "Contact Us", blocks=[{"type": "hero", "data": {"heading": "Contact Us"}}, {"type": "contact_form", "data": {"kind": "contact"}}])
    _post(page, "Technology Partners", blocks=[{"type": "hero", "data": {"heading": "Technology Partners"}}, {"type": "post_list", "data": {"post_type": "partner", "limit": 50}}])
    existing = db.settings()
    # fill a key that is missing OR blank -- every key exists from the first seed as "", so
    # "not already there" would mean the contact details could never land. A value someone has
    # actually set is never overwritten.
    db.set_settings({k: v for k, v in SETTINGS.items() if not existing.get(k)})
    services_menu = [{"label": g, "url": f"/services/{slugify(g)}"} for g in SERVICES]
    _get_or_create("menus", {"slug": "header"}, {"name": "Header", "items": [
        {"label": "Services", "url": "/services", "children": services_menu},
        {"label": "Products", "url": "/products"},
        {"label": "Case Studies", "url": "/case-studies"}, {"label": "Blog", "url": "/blog"},
        {"label": "Company", "url": "/about-us", "children": [
            {"label": "About Us", "url": "/about-us"}, {"label": "Technology Partners", "url": "/technology-partners"},
            {"label": "Events", "url": "/events"}, {"label": "Datasheets", "url": "/datasheets"},
            {"label": "Careers", "url": "/careers"}]}]})
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
