"""Meta tags and JSON-LD. Everything a crawler sees in <head> is built here and rendered by base.html. Posts are dicts with 'path'."""
from urllib.parse import urlsplit

from flask import current_app

from . import db

# Which networks get a glyph in the footer sprite (base.html). Keyed by the registrable host, so
# in.linkedin.com and m.youtube.com match too; twitter.com and x.com are the same bird.
SOCIAL = {"linkedin.com": ("LinkedIn", "linkedin"), "x.com": ("X", "x"), "twitter.com": ("X", "x"),
          "youtube.com": ("YouTube", "youtube"), "instagram.com": ("Instagram", "instagram"),
          "facebook.com": ("Facebook", "facebook")}


def _social(url):
    """A profile URL from Settings as {url, name, icon}. A network that is not in SOCIAL keeps its
    hostname and no icon, so one an editor pastes later still renders as a link rather than vanishing."""
    host = (urlsplit(url).netloc or url.split("/")[0]).lower()      # tolerate a schemeless paste
    key = next((k for k in SOCIAL if host == k or host.endswith("." + k)), None)
    name, icon = SOCIAL[key] if key else (host.removeprefix("www."), "")
    return {"url": url, "name": name or url, "icon": icon}


def site():
    s = db.settings()
    return {
        "name": s.get("site_name") or "IOPSTOR", "tagline": s.get("tagline") or "", "url": current_app.config["SITE_URL"],
        "logo": s.get("logo_url") or "", "og_image": s.get("default_og_image") or "", "social": [_social(u) for u in s.get("social_links") or []],
        "ga_id": s.get("ga_id") or "", "email": s.get("contact_email") or "", "phone": s.get("contact_phone") or "",
        "address": s.get("address") or "", "robots_extra": s.get("robots_extra") or "",
    }


def _abs(url, base):
    return url if not url or url.startswith("http") else base + url


def md_url(path):
    """The Markdown twin of a site path: /services/nas -> /services/nas.md, / -> /index.md.
    Every page has one, served by public.resolve(); this is the one place that spells the rule."""
    return "/index.md" if path in ("", "/") else path.rstrip("/") + ".md"


def _image(post):
    return (post.get("featured_media") or {}).get("url", "")


def build_meta(post=None, *, title=None, description="", path="/", robots="index,follow"):
    s = site()
    seo = (post.get("seo") or {}) if post else {}
    if post:
        path = post["path"] or path      # a type with no pages: keep the caller's default
        page_title = f"{post['title']} | {s['name']}"
    else:
        page_title = f"{title} | {s['name']}" if title else (f"{s['name']} — {s['tagline']}" if s["tagline"] else s["name"])
    image = seo.get("og_image") or (_image(post) if post else "") or s["og_image"]
    robots = seo.get("robots") or robots
    return {
        "title": seo.get("title") or page_title,
        "description": seo.get("description") or (post["excerpt"] if post else description) or s["tagline"],
        "canonical": seo.get("canonical") or s["url"] + path,
        "robots": robots,
        # <link rel="alternate" type="text/markdown"> in base.html. A noindex page has no
        # scrapeable twin to advertise.
        "markdown": "" if robots.startswith("noindex") else s["url"] + md_url(path),
        "image": _abs(image, s["url"]),
        "type": "article" if post and post["post_type"]["slug"] == "post" else "website",
        "site_name": s["name"],
    }


def jsonld(post=None, crumbs=()):
    """List of schema.org nodes for the page. crumbs = [(name, path), ...] starting at Home."""
    s = site()
    org = {"@type": "Organization", "name": s["name"], "url": s["url"] + "/"}
    if s["logo"]:
        org["logo"] = _abs(s["logo"], s["url"])
    if s["social"]:
        org["sameAs"] = [x["url"] for x in s["social"]]
    out = []
    if len(crumbs) <= 1:  # home
        out.append({"@context": "https://schema.org", **org})
        out.append({"@context": "https://schema.org", "@type": "WebSite", "name": s["name"], "url": s["url"] + "/"})
    else:
        out.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": s["url"] + path} for i, (name, path) in enumerate(crumbs)]})
    if post is None or not post["path"]:
        return out          # no page, no canonical URL to describe: crumbs only
    url = s["url"] + post["path"]
    m = post.get("meta") or {}
    t = post["post_type"].get("jsonld_type")
    if t:
        node = {"@context": "https://schema.org", "@type": t, "name": post["title"], "url": url, "description": post.get("excerpt") or ""}
        if _image(post):
            node["image"] = _abs(_image(post), s["url"])
        if t in ("BlogPosting", "Article", "NewsArticle"):
            node.update(headline=post["title"], datePublished=post.get("published_at"), dateModified=post.get("updated_at"), author=org, publisher=org,
                        mainEntityOfPage=url)
        elif t == "Product":
            if m.get("sku"):
                node["sku"] = m["sku"]
            node["brand"] = {"@type": "Brand", "name": s["name"]}
            if m.get("price") not in (None, ""):
                node["offers"] = {"@type": "Offer", "price": m["price"], "priceCurrency": "INR", "url": url,
                                  "availability": "https://schema.org/InStock"}
        elif t == "Service":
            node.update(provider=org, serviceType=post["title"])
        elif t == "Event":
            node.update(startDate=m.get("start_date"), endDate=m.get("end_date"), organizer=org,
                        location={"@type": "Place", "name": m.get("location") or s["name"]})
        out.append(node)
    faqs = [q for b in (post.get("blocks") or []) if b.get("type") == "faq" for q in b["data"].get("items", [])]
    if faqs:
        out.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f.get("q", ""), "acceptedAnswer": {"@type": "Answer", "text": f.get("a", "")}} for f in faqs]})
    return out
