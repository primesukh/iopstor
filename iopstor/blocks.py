"""Block registry. Adding a block = one entry in BLOCKS + templates/blocks/<type>.html."""
import re

from flask import render_template
from markupsafe import Markup

BLOCKS = {  # type: (required fields, optional fields)
    "hero": (["heading"], ["subheading", "image", "cta_label", "cta_url"]),
    "rich_text": (["html"], []),  # ponytail: raw HTML from trusted staff; add nh3 sanitising if untrusted authors appear
    "image": (["media_id"], ["alt", "caption"]),
    "gallery": (["images"], []),  # images: [{media_id, alt}]
    "cards": (["items"], ["heading"]),  # items: [{title, text, icon, url}]
    "cta": (["heading", "button_label", "button_url"], ["text"]),
    "faq": (["items"], ["heading"]),  # items: [{q, a}] → also emits FAQPage JSON-LD
    "stats": (["items"], []),  # items: [{value, label}]
    "testimonial": (["quote", "author"], ["role", "company"]),
    "embed_html": (["html"], []),
    "post_list": (["post_type"], ["heading", "term", "limit", "top_level"]),  # queried at render time; top_level=true → parents only
    "spec_table": (["rows"], ["heading"]),  # rows: [{k, v}]
    "contact_form": (["kind"], ["heading"]),  # kind: contact | quote | career → POST /api/v1/leads
}
# Admin editor metadata: how each field is edited in /admin (iopstor/static/admin.js).
# Field shapes that used to live in the comments above are data here so the editor has one source of truth.
EDITOR = {
    # widget per field key; "<block>.<field>" overrides the bare key. Default: text.
    "widgets": {"html": "richtext", "embed_html.html": "code", "text": "textarea", "a": "textarea", "subheading": "textarea",
                "caption": "textarea", "quote": "textarea", "image": "media", "media_id": "media",
                "url": "url", "cta_url": "url", "button_url": "url", "limit": "number",
                "top_level": "checkbox", "post_type": "post_type", "kind": "kind"},
    # repeater fields (items/images/rows) -> the subfields of one row
    "items": {"cards": ["title", "text", "icon", "url"], "faq": ["q", "a"], "stats": ["value", "label"],
              "spec_table": ["k", "v"], "gallery": ["media_id", "alt"]},
    # friendlier labels; anything missing is the key with underscores as spaces
    "labels": {"q": "Question", "a": "Answer", "k": "Label", "v": "Value", "html": "Content", "kind": "Form type",
               "cta_url": "Button link", "cta_label": "Button text", "top_level": "Top-level only",
               "media_id": "Image", "image": "Image", "post_type": "Content type", "term": "Term slug"},
    "kinds": ["contact", "quote", "career"],
}
REPEATERS = ("items", "images", "rows")

_NON_TEXT_KEYS = {"url", "cta_url", "button_url", "icon", "image", "media_id", "post_type", "term", "limit", "kind", "top_level"}
# JSONB does not keep key order, so text extraction walks fields in this reading order (unknown keys follow, alphabetically)
_TEXT_ORDER = ("heading", "subheading", "title", "q", "a", "text", "html", "quote", "author", "role", "company", "value", "label", "k", "v",
               "caption", "alt", "cta_label", "button_label", "items", "images", "rows")
_RANK = {k: i for i, k in enumerate(_TEXT_ORDER)}


def validate_blocks(blocks):
    if not isinstance(blocks, list):
        return ["blocks must be a list"]
    errors = []
    for i, b in enumerate(blocks):
        if not isinstance(b, dict) or not isinstance(b.get("data"), dict):
            errors.append(f"blocks[{i}]: must be an object with 'type' and 'data'")
            continue
        spec = BLOCKS.get(b.get("type"))
        if spec is None:
            errors.append(f"blocks[{i}]: unknown type {b.get('type')!r}")
            continue
        for field in spec[0]:
            if b["data"].get(field) in (None, "", []):
                errors.append(f"blocks[{i}].{field} required")
    return errors


def render_blocks(blocks):
    out = []
    for b in blocks:
        extra = {}
        if b["type"] == "post_list":
            extra["posts"] = _post_list(b["data"])
        out.append(render_template(f"blocks/{b['type']}.html", data=b["data"], **extra))
    return Markup("".join(out))


def blocks_text(blocks):
    """Plain text of all block content — for llms-full.txt and admin search."""
    out = []

    def walk(v, key=None):
        if isinstance(v, str) and key not in _NON_TEXT_KEYS:
            out.append(re.sub(r"<[^>]+>", " ", v))
        elif isinstance(v, dict):
            for k in sorted(v, key=lambda k: (_RANK.get(k, len(_RANK)), k)):
                walk(v[k], k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)

    for b in blocks:
        walk(b.get("data", {}))
    return " ".join(" ".join(out).split())


def _post_list(data):
    from . import db

    pt = db.post_type(slug=data["post_type"])
    if pt is None:
        return []
    if data.get("term"):
        term = db.one(db.table("terms").select("id").eq("slug", data["term"]))
        if term is None:
            return []
        q = db.table("posts").select(db.POST_SELECT_BY_TERM).eq("post_terms.term_id", term["id"])
    else:
        q = db.select_posts()
    q = db.live(q).eq("post_type_id", pt["id"])
    if data.get("top_level"):
        q = q.is_("parent_id", "null")
    q = q.order("menu_order").order("published_at", desc=True).limit(int(data.get("limit") or 10))
    return db.with_paths(db.rows(q))
