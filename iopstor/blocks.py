"""Block registry. Adding a block = one entry in BLOCKS + templates/blocks/<type>.html."""
import re
from copy import deepcopy

from flask import render_template
from markupsafe import Markup, escape

BLOCKS = {  # type: (required fields, optional fields)
    "hero": (["heading"], ["subheading", "image", "cta_label", "cta_url"]),
    "rich_text": (["html"], []),  # ponytail: raw HTML from trusted staff; add nh3 sanitising if untrusted authors appear
    "image": (["media_id"], ["alt", "caption"]),
    "gallery": (["images"], []),  # images: [{media_id, alt}]
    "cards": (["items"], ["heading"]),  # items: [{title, text, icon, url}]
    # the only block that holds other blocks: cols is a list of columns, each an ordered [{type, data}].
    # One level deep only — validate_blocks() rejects a columns or a hero inside a column.
    "columns": (["cols"], ["heading", "widths"]),  # widths: "50/25/25", blank = equal
    "cta": (["heading", "button_label", "button_url"], ["text"]),
    "faq": (["items"], ["heading"]),  # items: [{q, a}] → also emits FAQPage JSON-LD
    "stats": (["items"], []),  # items: [{value, label}]
    "testimonial": (["quote", "author"], ["role", "company"]),
    "embed_html": (["html"], []),
    "post_list": (["post_type"], ["heading", "term", "limit", "top_level"]),  # queried at render time; top_level=true → parents only
    "spec_table": (["rows"], ["heading"]),  # rows: [{k, v}]
    "contact_form": (["kind"], ["heading"]),  # kind: contact | quote | career → POST /api/v1/leads
    # file_media_id, not media_id: EDITOR["labels"] is keyed by bare field name and media_id already reads "Image".
    # ponytail: the viewer is a fixed height in site.css; add a "height" field if editors ask for one.
    "pdf": (["file_media_id"], ["heading"]),
}
# Admin editor metadata: how each field is edited in /admin (iopstor/static/admin.js).
# Field shapes that used to live in the comments above are data here so the editor has one source of truth.
EDITOR = {
    # widget per field key; "<block>.<field>" overrides the bare key. Default: text.
    "widgets": {"html": "richtext", "embed_html.html": "code", "text": "textarea", "a": "textarea", "subheading": "textarea",
                "caption": "textarea", "quote": "textarea", "image": "media", "media_id": "media", "file_media_id": "pdf",
                "url": "url", "cta_url": "url", "button_url": "url", "limit": "number",
                "top_level": "checkbox", "post_type": "post_type", "kind": "kind"},
    # repeater fields (items/images/rows/cols) -> the subfields of one row; [] = rows are not field rows
    "items": {"cards": ["title", "text", "icon", "url"], "faq": ["q", "a"], "stats": ["value", "label"],
              "spec_table": ["k", "v"], "gallery": ["media_id", "alt"],
              "columns": []},  # a column is a list of blocks, not a row of fields: the panel only adds/moves/removes it
    # friendlier labels; anything missing is the key with underscores as spaces
    "labels": {"q": "Question", "a": "Answer", "k": "Label", "v": "Value", "html": "Content", "kind": "Form type",
               "cols": "Columns", "widths": "Column widths, e.g. 50/25/25",
               "cta_url": "Button link", "cta_label": "Button text", "top_level": "Top-level only",
               "media_id": "Image", "image": "Image", "file_media_id": "PDF file", "post_type": "Content type",
               "term": "Term slug"},
    "kinds": ["contact", "quote", "career"],
    # order the section picker offers them in, commonest first (Jinja's tojson sorts dict keys,
    # so BLOCKS' own order does not survive the trip to the browser)
    "order": ["hero", "rich_text", "cards", "columns", "cta", "faq", "stats", "testimonial", "spec_table",
              "image", "gallery", "pdf", "post_list", "contact_form", "embed_html"],
    # the visual inserter: icon, plain-English name, one line on what the visitor sees
    "names": {
        "hero": ("\U0001F3D4", "Hero", "The big opening band: headline, one line of text, one button."),
        "rich_text": ("\u00B6", "Rich text", "Words, headings and lists \u2014 type into it like a Word document."),
        "cards": ("\u25A4", "Cards", "A row of boxes, each with a title, a line of text and an optional link."),
        "columns": ("\u25A5", "Columns", "Two or more columns side by side, each holding its own sections."),
        "cta": ("\U0001F4E3", "Call to action", "A coloured band that asks the visitor to do one thing."),
        "faq": ("\u2753", "Questions & answers", "Questions that open to reveal the answer. Google shows these too."),
        "stats": ("\U0001F4CA", "Numbers", "A row of big figures with a label under each one."),
        "testimonial": ("\U0001F4AC", "Customer quote", "Something a customer said, with their name and company."),
        "spec_table": ("\U0001F4CB", "Specification table", "A two-column table of labels and values."),
        "image": ("\U0001F5BC", "Picture", "One picture across the page, with an optional caption."),
        "gallery": ("\U0001F5C2", "Picture grid", "Several pictures laid out in a grid."),
        "post_list": ("\U0001F4D1", "Automatic list", "Lists pages of a type you choose, and keeps itself up to date."),
        "contact_form": ("\u2709", "Contact form", "A form visitors fill in. Replies arrive under Leads."),
        "pdf": ("\U0001F4C4", "PDF", "A PDF shown on the page in the reader's own PDF viewer."),
        "embed_html": ("</>", "Embedded code", "Paste code from YouTube, a map or another service."),
    },
    # starting content for a freshly inserted block, so a new section is visible and clickable.
    # Anything with placeholder copy also passes validate_blocks(), so the page saves straight away.
    "seed": {
        "hero": {"heading": "A headline that says what you do", "subheading": "One or two lines explaining it in plain English.",
                 "cta_label": "Talk to us", "cta_url": "/contact-us"},
        "rich_text": {"html": "<p>Write your text here.</p>"},
        "cards": {"heading": "What we do", "items": [{"title": "First thing", "text": "A sentence about it.", "icon": "", "url": ""},
                                                     {"title": "Second thing", "text": "A sentence about it.", "icon": "", "url": ""},
                                                     {"title": "Third thing", "text": "A sentence about it.", "icon": "", "url": ""}]},
        "columns": {"cols": [[{"type": "rich_text", "data": {"html": "<p>The left column.</p>"}}],
                             [{"type": "rich_text", "data": {"html": "<p>The right column.</p>"}}]]},
        "cta": {"heading": "Ready to talk?", "text": "Tell us what you need and we will come back to you.",
                "button_label": "Contact us", "button_url": "/contact-us"},
        "faq": {"heading": "Questions", "items": [{"q": "Your question here?", "a": "<p>And the answer here.</p>"}]},
        "stats": {"items": [{"value": "99.999%", "label": "uptime"}, {"value": "5 PB", "label": "per rack"},
                            {"value": "24\u00D77", "label": "support"}]},
        "testimonial": {"quote": "What a customer said about working with you.", "author": "Their name",
                        "role": "Job title", "company": "Company"},
        "spec_table": {"heading": "Specifications", "rows": [{"k": "Capacity", "v": "Up to 5 PB"}, {"k": "Interface", "v": "NFS, SMB, S3"}]},
        "contact_form": {"kind": "contact", "heading": "Get in touch"},
        "post_list": {"post_type": "post", "heading": "Latest"},
        "embed_html": {"html": "<!-- paste the embed code from YouTube, Google Maps, etc. here -->"},
        "image": {"caption": ""},      # media_id must be chosen: no placeholder can stand in for a picture
        "pdf": {"heading": ""},        # same for the file: an empty viewer is worse than an empty section
        "gallery": {"images": []},
    },
}
REPEATERS = ("items", "images", "rows", "cols")
# Starting points offered on a new post, as block types expanded through EDITOR["seed"].
# Only types whose seed passes validate_blocks() belong here (so: no picture blocks).
LAYOUTS = {
    "Product page": ["hero", "stats", "spec_table", "faq", "cta"],
    "Service page": ["hero", "rich_text", "cards", "testimonial", "cta"],
    "Landing page": ["hero", "cards", "stats", "contact_form"],
}


def layout(name):
    """Expand a LAYOUTS entry into real blocks. Unknown name -> a blank page."""
    return [{"type": t, "data": deepcopy(EDITOR["seed"].get(t) or {})} for t in LAYOUTS.get(name, [])]

_NON_TEXT_KEYS = {"url", "cta_url", "button_url", "icon", "image", "media_id", "file_media_id", "post_type", "term", "limit", "kind", "top_level", "type", "widths"}
# JSONB does not keep key order, so text extraction walks fields in this reading order (unknown keys follow, alphabetically)
_TEXT_ORDER = ("heading", "subheading", "title", "q", "a", "text", "html", "quote", "author", "role", "company", "value", "label", "k", "v",
               "caption", "alt", "cta_label", "button_label", "items", "images", "rows", "cols")
_RANK = {k: i for i, k in enumerate(_TEXT_ORDER)}


# A column holds sections, but not another grid (one level is enough to lay a page out, and nesting
# grids is how an Elementor page becomes unmaintainable) and not a hero, which is a full-bleed band
# owning the page's only <h1>.
NEVER_NESTED = ("columns", "hero")


def validate_blocks(blocks, where="blocks", nested=False):
    if not isinstance(blocks, list):
        return [f"{where} must be a list"]
    errors = []
    for i, b in enumerate(blocks):
        at = f"{where}[{i}]"
        if not isinstance(b, dict) or not isinstance(b.get("data"), dict):
            errors.append(f"{at}: must be an object with 'type' and 'data'")
            continue
        spec = BLOCKS.get(b.get("type"))
        if spec is None:
            errors.append(f"{at}: unknown type {b.get('type')!r}")
            continue
        if nested and b["type"] in NEVER_NESTED:
            errors.append(f"{at}: a {b['type']} section cannot go inside a column")
            continue
        for field in spec[0]:
            if b["data"].get(field) in (None, "", []):
                errors.append(f"{at}.{field} required")
        if b["type"] == "columns":
            cols = b["data"].get("cols")
            if isinstance(cols, list):
                for c, col in enumerate(cols):
                    errors += validate_blocks(col, f"{at}.cols[{c}]", nested=True)
            elif cols not in (None, "", []):        # missing or empty already said "cols required"
                errors.append(f"{at}.cols must be a list of columns")
    return errors


def col_widths(data):
    """"50/25/25" -> "50fr 25fr 25fr", for the --cols custom property. Anything that is not exactly
    one positive number per column -> "" (equal columns). Strict, because it lands in a style
    attribute: only digits and one dot per part ever get through."""
    parts = str(data.get("widths") or "").replace(" ", "").split("/")
    if len(parts) != len(data.get("cols") or []) or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        return ""
    nums = [float(p) for p in parts]
    return " ".join(f"{n:g}fr" for n in nums) if all(n > 0 for n in nums) else ""


def at_path(blocks, path):
    """Resolve a data-b path to one block, or None. "3" is a top-level block, "3.1.0" is block 3's
    column 1, first block — parts alternate block index / column index, so the count is always odd."""
    parts = str(path).split(".")
    if len(parts) % 2 == 0 or not all(p.isdigit() for p in parts):
        return None
    block = None
    try:
        while parts:
            block = blocks[int(parts.pop(0))]
            if parts:
                blocks = block["data"]["cols"][int(parts.pop(0))]
    except (IndexError, KeyError, TypeError):
        return None
    return block if isinstance(block, dict) else None


def _no_fe(*_a, **_k):
    return ""


def _fe(path):
    """Edit markers for blocks/<type>.html, handed in by render_blocks(edit=True) and only then —
    the public site is passed _no_fe, so data-* attributes cannot leak into it.
      fe()                -> the block root          data-b="2"   (or "2.1.0" inside a column)
      fe("heading")       -> a text field            data-f="heading" data-ph="Heading"
      fe("items", 0)      -> one repeater row        data-r="items" data-i="0"
      fe("html", rich=1)  -> value is innerHTML      ... data-rich="1"
      fe("html", ph="…")  -> override the empty-state placeholder
    Write it tight against the tag (<h1{{ fe('heading') }}>) so the public render is plain <h1>."""

    def fe(field=None, row=None, rich=False, ph=None):
        if field is None:
            return Markup(f' data-b="{path}"')
        if row is not None:
            return Markup(f' data-r="{escape(field)}" data-i="{int(row)}"')
        ph = ph or EDITOR["labels"].get(field) or field.replace("_", " ").capitalize()
        out = f' data-f="{escape(field)}" data-ph="{escape(ph)}"'
        return Markup(out + ' data-rich="1"' if rich else out)

    return fe


def render_blocks(blocks, edit=False, path="0"):
    """`path` is the data-b path of the FIRST block; its siblings increment the last part. The page
    itself starts at "0"; column 1 of block 2 renders with path "2.1.0"."""
    head, _, first = path.rpartition(".")
    out = []
    for i, b in enumerate(blocks):
        p = f"{head}.{int(first) + i}" if head else str(int(first) + i)
        try:
            extra = {}
            if b["type"] == "post_list":
                extra = {"posts": _post_list(b["data"])}
            elif b["type"] == "columns":
                # the one block that renders other blocks: each column is its own list, one level down
                cols = b["data"].get("cols") or []
                extra = {"col": lambda n, p=p, cols=cols: render_blocks(cols[n], edit, f"{p}.{n}.0"),
                         "widths": col_widths(b["data"])}
            out.append(render_template(f"blocks/{b['type']}.html", data=b["data"], edit=edit,
                                       fe=_fe(p) if edit else _no_fe, **extra))
        except Exception as e:
            if not edit:
                raise  # a public page that cannot render should fail loudly, not hide it
            out.append(Markup(f'<section class="section" data-b="{p}"><div class="wrap">'
                              f'<p class="iop-err">This section is not finished yet \u2014 {escape(e)}</p></div></section>'))
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
