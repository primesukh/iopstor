"""flask CLI commands: migrate (apply migrations/*.sql through Supabase), seed, create-admin."""
import pathlib

import click
from flask import current_app
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


# The design's fourteen technology partners, and the logo each one uses.
PARTNERS = [
    ("Micron", "650x180_micronlogo.png"), ("CentOS", "Centos-logo-light.svg_.png"),
    ("HGST", "HGST_logo_2012.png"), ("NVM Express", "NVM_Express_logo.svg_.png"),
    ("OmniOS", "OmniOS_logo.png"), ("Red Hat", "RedHat.svg_.png"),
    ("Samsung", "Samsung_logo-2.jpg"), ("Solaris", "Solaris_OS_logo.svg_.png"),
    ("Toshiba", "Toshiba-Leading-Innovation-Logo.png"), ("Microsoft", "microsoft-80658_960_720.png"),
    ("SanDisk", "sandisk-logo-pan.jpg"), ("Supermicro", "supermicro-logo-1.png"),
    ("VMware", "vmware_cloud_logo.jpg"), ("Western Digital", "western_digital-logo.jpg"),
]
# The mock's hero is assets/introducing-rack.png, alt "IOPStor 24-bay 2U all-flash array" --
# that is Untitled-4.png, the 24-bay array with the wordmark over it. Its rack-96tb.png is
# banner-homepage-96tb.png, the 8-bay 2U; the "96tb" in both filenames settles it. tower.png
# is DSC_0305n.png, the Classic.
HERO_IMAGE = "Untitled-4.png"
RACK_IMAGE = "banner-homepage-96tb.png"
TOWER_IMAGE = "DSC_0305n.png"
ABOUT_IMAGE = "background1.jpg"


def media_id(filename):
    """The id of an imported file, or None when it is not in the library. Every use is conditional:
    the seed has to run on a fresh instance where nothing has been uploaded yet."""
    m = db.one(db.table("media").select("id").eq("filename", filename))
    return m["id"] if m else None


def _clean(blocks):
    """Strip keys whose value is None, so a seed run before `flask import-media` does not leave
    `"image": null` sitting in the saved JSON for an editor to wonder about."""
    for b in blocks:
        b["data"] = {k: v for k, v in b["data"].items() if v is not None}
        for col in b["data"].get("cols") or []:
            _clean(col)
    return blocks


def home_blocks(media=lambda name: None):
    """The home page, in the order the design lays it out. A function rather than a constant so it
    can carry media ids, which only exist once someone has run `flask import-media`; the default
    lookup returns None, which is both the fresh-instance case and what test_offline validates."""
    return _clean([
        {"type": "hero", "data": {"eyebrow": "The Storage Specialist",
                                  "image": media(HERO_IMAGE),
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
        {"type": "post_list", "data": {"tone": "grey", "post_type": "service", "top_level": True, "limit": 6, "eyebrow": "What we do",
                                       "heading": "Storage, virtualisation and cloud, delivered as one stack",
                                       "link_label": "All services", "link_url": "/services"}},
        {"type": "columns", "data": {"cols": [
            [{"type": "image", "data": {"media_id": media(RACK_IMAGE), "alt": "IOPStor 2U rackmount"}}]
            if media(RACK_IMAGE) else [],
            [{"type": "rich_text", "data": {"html":
                '<p class="eyebrow">Built on ZFS</p>'
                '<h2 class="section-title">The file system trusted by Fortune 500 companies, '
                'universities and data centres</h2>'
                '<p class="lead">ZFS never compromises on data safety. Every IOPStor appliance '
                'inherits it: end-to-end checksums, self-healing pools, and snapshots that recover '
                'deleted or corrupt data and protect against ransomware.</p>'
                '<ul class="dash">'
                '<li>Unlimited snapshots and clones: go back to yesterday, last week or last month</li>'
                '<li>RAID-Z: instantaneous build, no write hole, multiple-disk failure tolerance</li>'
                '<li>RAM / SSD / NVMe read-write cache, compression and de-duplication</li>'
                '<li>Hardware agnostic: replace any component from any vendor</li>'
                '</ul>'
                '<p><a class="btn dark" href="/services/storage/nas">All ZFS features</a></p>'}}]]}},
        {"type": "post_list", "data": {"tone": "grey", "post_type": "product", "limit": 6, "eyebrow": "Appliances",
                                       "heading": "Sized from 5 users upward",
                                       "link_label": "All appliances", "link_url": "/products"}},
        {"type": "post_list", "data": {"tone": "dark", "post_type": "case_study", "limit": 4, "eyebrow": "Case studies",
                                       "heading": "Proven across finance, education, media and logistics",
                                       "link_label": "All case studies", "link_url": "/case-studies"}},
        {"type": "columns", "data": {"cols": [
            [{"type": "testimonial", "data": {"quote": TESTIMONIALS[0][0], "author": TESTIMONIALS[0][1], "role": TESTIMONIALS[0][2]}}],
            [{"type": "testimonial", "data": {"quote": TESTIMONIALS[1][0], "author": TESTIMONIALS[1][1], "role": TESTIMONIALS[1][2]}}]]}},
        {"type": "post_list", "data": {"post_type": "partner", "limit": 24, "eyebrow": "Technology partners"}},
        {"type": "cta", "data": {"heading": "Don't just store data. Protect it.",
                                 "text": "Tell us the workload and the user count. We come back with a configuration and a one-time price, "
                                         "with no hidden or repetitive costs.",
                                 "button_label": "Request a quote", "button_url": "/contact-us"}}])


def _get_or_create(name, keys, defaults=None):
    q = db.table(name).select("*")
    for k, v in keys.items():
        q = q.eq(k, v)
    return db.one(q) or db.insert(name, {**keys, **(defaults or {})})


RESET = False  # set by `flask seed --reset-content`: overwrite blocks/excerpt/meta of the seed-defined posts


def _post(pt, title, *, slug=None, parent=None, blocks=None, meta=None, terms=(), excerpt="", menu_order=0, featured=None):
    """Get-or-create a published post; never overwrites existing content unless RESET."""
    slug = slug or slugify(title)
    blocks = blocks if blocks is not None else [{"type": "hero", "data": {"heading": title}}]
    post = db.one(db.table("posts").select("id").eq("post_type_id", pt["id"]).eq("slug", slug))
    if post is not None and RESET:
        changes = {"blocks": blocks, "excerpt": excerpt, "meta": meta or {}, "menu_order": menu_order}
        if featured:
            changes["featured_media_id"] = featured
        db.update("posts", post["id"], changes)
    if post is None:
        post = db.insert("posts", {
            "post_type_id": pt["id"], "slug": slug, "title": title, "parent_id": parent["id"] if parent else None, "excerpt": excerpt,
            "blocks": blocks, "meta": meta or {}, "featured_media_id": featured,
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
              featured=media_id(TOWER_IMAGE if "Classic" in title else RACK_IMAGE),
              excerpt=f"Appliance workload {users}. Zero touch setup and management through a web GUI, and one source for support.",
              blocks=[{"type": "hero", "data": {"heading": title, "eyebrow": "Appliance",
                                                "subheading": f"Sized for {users}. Xeon, enterprise SSD and 10G networking, on ZFS.",
                                                "cta_label": "Request a quote", "cta_url": "/contact-us"}}])
    for i, (name, logo) in enumerate(PARTNERS):
        _post(types["partner"], name, menu_order=i, meta={"logo_media_id": media_id(logo)},
              excerpt=f"{name} hardware and software, supported in every IOPStor build.",
              blocks=[{"type": "rich_text", "data": {"html": f"<p>IOPStor builds and supports {name} technology.</p>"}}])
    page = types["page"]
    # The home page, in the order the design lays it out.
    _post(page, "Home", slug="home", excerpt=SETTINGS["tagline"], blocks=home_blocks(media_id))
    _post(page, "About Us", excerpt="Customised storage for a market nobody else was serving.", blocks=[
        {"type": "hero", "data": {"dark": True, "eyebrow": "About us", "image": media_id(ABOUT_IMAGE),
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
    logo = db.one(db.table("media").select("url").eq("filename", "iopstor_logo-png1.png"))
    if logo:
        SETTINGS["logo_url"] = logo["url"]
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


@click.command("import-media")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--dry-run", is_flag=True, help="List what would be uploaded, without uploading anything.")
@with_appcontext
def import_media(directory, dry_run):
    """Upload every image/PDF under DIRECTORY into the Supabase media bucket and the media table.

    The same key scheme and public URL as /admin/media, so an imported file is indistinguishable
    from one an editor uploaded. Idempotent on filename: re-running skips what is already there,
    which is what makes it safe to point at a folder you have added one file to.
    Alt text is derived from the filename ("rack-96tb.png" -> "rack 96tb"); edit it under Media.
    """
    import mimetypes
    import uuid
    from datetime import datetime, timezone

    from .storage import ALLOWED

    have = {m["filename"] for m in db.rows(db.table("media").select("filename").limit(5000))}
    bucket = db.sb().storage.from_(current_app.config["MEDIA_BUCKET"])
    added = skipped = 0
    for path in sorted(pathlib.Path(directory).rglob("*")):
        if not path.is_file():
            continue
        mime = mimetypes.guess_type(path.name)[0]
        if mime not in ALLOWED:
            continue
        if path.name in have:
            click.echo(f"  skip  {path.name}")
            skipped += 1
            continue
        if dry_run:
            click.echo(f"  would upload {path.name} ({mime})")
            added += 1
            continue
        data = path.read_bytes()
        key = f"{datetime.now(timezone.utc):%Y/%m}/{uuid.uuid4().hex}{ALLOWED[mime]}"
        bucket.upload(key, data, {"content-type": mime, "upsert": "false"})
        row = db.insert("media", {"key": key, "url": bucket.get_public_url(key), "filename": path.name[:300],
                                  "mime": mime, "size": len(data), "alt": alt_from_name(path.name)})
        click.echo(f"  #{row['id']:<5} {path.name}")
        have.add(path.name)
        added += 1
    click.echo(f"{'would add' if dry_run else 'added'} {added}, skipped {skipped}")


def alt_from_name(filename):
    """A first draft of the alt text, so nothing lands with an empty one. Editors fix it under Media."""
    stem = pathlib.Path(filename).stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split())[:300]


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
    for cmd in (migrate, seed, import_media, create_admin):
        app.cli.add_command(cmd)
