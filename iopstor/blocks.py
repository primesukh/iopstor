"""Block registry. Adding a block = one entry in BLOCKS + templates/blocks/<type>.html."""
import re
from copy import deepcopy
from datetime import date
from html import unescape

from flask import render_template
from markupsafe import Markup, escape

from .seo import md_url

BLOCKS = {  # type: (required fields, optional fields)
    # dark: the full-bleed variant, where "image" becomes the faded backdrop rather than the art
    # beside the words. A checkbox, not a free-text "tone": nothing typed reaches a class name.
    # image is the single picture; images (>= 2) turns it into the rotator that takes turns on its
    # own, in CSS. Both are kept: images wins when it has two or more rows, so nothing already
    # published changes shape.
    "hero": (["heading"], ["eyebrow", "subheading", "image", "images", "cta_label", "cta_url",
                           "cta2_label", "cta2_url", "dark"]),
    "rich_text": (["html"], ["fx"]),  # ponytail: raw HTML from trusted staff; add nh3 sanitising if untrusted authors appear
    "image": (["media_id"], ["alt", "caption"]),
    "gallery": (["images"], []),  # images: [{media_id, alt}]
    "cards": (["items"], ["heading"]),  # items: [{title, text, icon, url}]
    # the only block that holds other blocks: cols is a list of columns, each an ordered [{type, data}].
    # One level deep only — validate_blocks() rejects a columns or a hero inside a column.
    "columns": (["cols"], ["heading", "widths"]),  # widths: "50/25/25", blank = equal
    "cta": (["heading", "button_label", "button_url"], ["text"]),
    "faq": (["items"], ["heading"]),  # items: [{q, a}] → also emits FAQPage JSON-LD
    "stats": (["items"], ["count_up", "fx"]),  # items: [{value, label, fx, count_up}] — a figure can override the section
    "testimonial": (["quote", "author"], ["role", "company", "dark"]),
    "embed_html": (["html"], []),
    # link_label/link_url are the "All services →" link in the section header.
    "post_list": (["post_type"], ["heading", "eyebrow", "term", "limit", "top_level",
                                  "link_label", "link_url"]),  # queried at render time; top_level=true → parents only
    "spec_table": (["rows"], ["heading"]),  # rows: [{k, v}]
    "contact_form": (["kind"], ["heading"]),  # kind: contact | quote | career → POST /api/v1/leads
    # file_media_id, not media_id: EDITOR["labels"] is keyed by bare field name and media_id already reads "Image".
    # ponytail: the viewer is a fixed height in site.css; add a "height" field if editors ask for one.
    "pdf": (["file_media_id"], ["heading"]),
    # nothing required: the section is a serial-number box, and the answer is looked up at render time.
    # Explanatory copy goes in a rich_text section above it, like any other words on the page.
    "warranty_check": ([], ["heading"]),
    # The two sections that are not content. Nothing required: a gap is a gap and a line is a line.
    # height is a whitelist (HEIGHTS -> sp-*), not a number, because it lands in a class attribute;
    # a divider takes nothing of its own -- the universal width/align_box keys already shorten it
    # and move it, through --w and .alb-*.
    "spacer": ([], ["height"]),
    "divider": ([], []),
}
# Admin editor metadata: how each field is edited in /admin (iopstor/static/admin.js).
# Field shapes that used to live in the comments above are data here so the editor has one source of truth.
EDITOR = {
    # widget per field key; "<block>.<field>" overrides the bare key. Default: text.
    "widgets": {"html": "richtext", "embed_html.html": "code", "text": "textarea", "a": "textarea", "subheading": "textarea",
                "caption": "textarea", "quote": "textarea", "image": "media", "media_id": "media", "file_media_id": "pdf",
                "url": "url", "cta_url": "url", "button_url": "url", "limit": "number",
                "top_level": "checkbox", "post_type": "post_type", "kind": "kind",
                "cta2_url": "url", "link_url": "url", "dark": "checkbox",
                "count_up": "checkbox", "fx": "choice", "height": "choice"},
    # repeater fields (items/images/rows/cols) -> the subfields of one row; [] = rows are not field rows
    "items": {"cards": ["title", "text", "icon", "url"], "faq": ["q", "a"], "stats": ["value", "label", "fx", "count_up"],
              "spec_table": ["k", "v"], "gallery": ["media_id", "alt"], "hero": ["media_id", "alt"],
              "columns": []},  # a column is a list of blocks, not a row of fields: the panel only adds/moves/removes it
    # friendlier labels; anything missing is the key with underscores as spaces
    "labels": {"q": "Question", "a": "Answer", "k": "Label", "v": "Value", "html": "Content", "kind": "Form type",
               "cols": "Columns", "widths": "Column widths, e.g. 50/25/25",
               "cta_url": "Button link", "cta_label": "Button text", "top_level": "Top-level only",
               "media_id": "Image", "image": "Image", "images": "Pictures that take turns", "file_media_id": "PDF file", "post_type": "Content type",
               "term": "Term slug", "eyebrow": "Small label above the heading",
               "cta2_label": "Second button text", "cta2_url": "Second button link",
               "link_label": "Header link text", "link_url": "Header link",
               "dark": "Dark background",
               "count_up": "Count up from zero", "fx": "Effect"},
    "kinds": ["contact", "quote", "career"],
    # options for the "choice" widget, keyed by field: [value, label] pairs, so the empty one can
    # say what it means. blocks.py FX is the whitelist these values are checked against.
    "choices": {"fx": [["", "None"],
                       ["rise", "Fades in as the page loads"],
                       ["gradient", "Gradient across the big text"],
                       ["sweep", "Highlighter sweep behind the headings"]],
                "height": [["small", "Small"], ["medium", "Medium"], ["large", "Large"], ["huge", "Extra large"]]},
    # order the section picker offers them in, commonest first (Jinja's tojson sorts dict keys,
    # so BLOCKS' own order does not survive the trip to the browser)
    "order": ["hero", "rich_text", "cards", "columns", "spacer", "divider", "cta", "faq", "stats",
              "testimonial", "spec_table", "image", "gallery", "pdf", "post_list", "contact_form",
              "warranty_check", "embed_html"],
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
        "warranty_check": ("\U0001F6E1", "Warranty check", "A box where a customer types their serial number and sees their warranty."),
        "pdf": ("\U0001F4C4", "PDF", "A PDF shown on the page in the reader's own PDF viewer."),
        "embed_html": ("</>", "Embedded code", "Paste code from YouTube, a map or another service."),
        "spacer": ("\u2195", "Spacer", "A blank gap between two sections, in one of four heights."),
        "divider": ("\u2500", "Divider", "A thin line straight across the page."),
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
        "warranty_check": {"heading": "Check your warranty"},
        "post_list": {"post_type": "post", "heading": "Latest"},
        "embed_html": {"html": "<!-- paste the embed code from YouTube, Google Maps, etc. here -->"},
        "image": {"caption": ""},      # media_id must be chosen: no placeholder can stand in for a picture
        "pdf": {"heading": ""},        # same for the file: an empty viewer is worse than an empty section
        "gallery": {"images": []},
        "spacer": {"height": "medium"},
        "divider": {},               # a line has nothing to fill in
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

_NON_TEXT_KEYS = {"url", "cta_url", "cta2_url", "button_url", "link_url", "icon", "image", "media_id", "file_media_id",
                  "post_type", "term", "limit", "kind", "top_level", "dark", "type", "widths", "align", "align_box", "width",
                  "tone", "fx", "count_up", "height"}
# JSONB does not keep key order, so text extraction walks fields in this reading order (unknown keys follow, alphabetically)
_TEXT_ORDER = ("eyebrow", "heading", "subheading", "title", "q", "a", "text", "html", "quote", "author", "role", "company",
               "value", "label", "k", "v", "caption", "alt", "cta_label", "cta2_label", "button_label", "link_label",
               "items", "images", "rows", "cols")
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


_COUNT = re.compile(r"(?<![\d,.])(\d+)(?![\d,])")


def count_up(value):
    """Find the one whole number in a figure that a CSS counter can roll up to, and split the words
    off either side of it so only the number moves: "300+" -> (300, "", "300", "+"),
    "Up to 5 PB" -> (5, "Up to ", "5", " PB"). None when there is nothing to count, and stats.html
    leaves the figure as plain text. The number reaches a style attribute as an int, so nothing
    typed can get in — the same guarantee section_style() makes about --w.
    ponytail: the first whole number wins, and only whole ones. CSS counters are integers, so
    "99.999%" rolls 0->99 and holds ".999%"; a grouped "1,200" is refused by the two lookarounds
    rather than counting to a figure that spells itself differently from the one on the page."""
    m = _COUNT.search(str(value or ""))
    if not m or int(m.group(1)) <= 0:
        return None
    v = str(value)
    return int(m.group(1)), v[:m.start()], m.group(1), v[m.end():]


TONES = ("grey", "dark", "blue")   # the bands a section can sit on; absent = the page's own white
ALIGNS = ("left", "center", "right")
WIDTHS = {"wide": "w-wide", "full": "w-full"}   # "width" also takes a number of pixels; see section_style()
FX = ("rise", "gradient", "sweep")   # the motion an editor can put on a section; counting figures up is its own checkbox
HEIGHTS = ("small", "medium", "large", "huge")   # how tall a spacer is; the CSS holds the pixels
MAX_W = 4000


def section_class(data):
    """The layout classes for one section, from six optional keys — absent means the theme's own
    layout. "align" lines up what is inside it, "align_box" moves the box, "tone" is the band it sits
    on (the design alternates white and grey down a page for rhythm), "width" is either a named
    step (wide / full) or a number of pixels, which section_style() carries instead, and "fx" is
    the motion in site.css's effects group, and "height" is how tall a spacer stands. A whitelist,
    not a passthrough: the result goes straight into a class attribute, the same reason col_widths()
    is strict — which is also why stats.html calls this for one figure's own effect rather than
    building the class itself.
    Returns "" or " al-center", " al-center alb-right w-full fx-rise", …"""
    out = [p + data[k] for k, p in (("align", "al-"), ("align_box", "alb-")) if data.get(k) in ALIGNS]
    out += ["t-" + data["tone"]] if data.get("tone") in TONES else []
    out += [WIDTHS[str(data.get("width"))]] if str(data.get("width")) in WIDTHS else []
    out += ["fx-" + data["fx"]] if data.get("fx") in FX else []
    out += ["sp-" + data["height"]] if data.get("height") in HEIGHTS else []
    return (" " + " ".join(out)) if out else ""


def section_style(data):
    """An exact content width as the --w custom property, which is what every max-width in the theme
    falls back from. Digits only, 1..MAX_W: this one lands in a style attribute, so nothing that is
    not a plain number gets in. A named width returns "" — it is a class instead."""
    w = str(data.get("width") or "").strip()
    return Markup(f' style="--w:{w}px"') if w.isdigit() and 0 < int(w) <= MAX_W else ""


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
                # pt_slug comes from the DB lookup, never from b["data"], so the class it becomes in
                # the template cannot be anything an editor typed.
                posts, pt_slug = _post_list(b["data"])
                extra = {"posts": posts, "pt_slug": pt_slug}
            elif b["type"] == "warranty_check":
                extra = {"found": None if edit else _warranty()}  # the admin canvas gets the bare form, never a lookup
            elif b["type"] == "columns":
                # the one block that renders other blocks: each column is its own list, one level down
                cols = b["data"].get("cols") or []
                extra = {"col": lambda n, p=p, cols=cols: render_blocks(cols[n], edit, f"{p}.{n}.0"),
                         "widths": col_widths(b["data"])}
            out.append(render_template(f"blocks/{b['type']}.html", data=b["data"], edit=edit,
                                       cls=section_class(b["data"]), sty=section_style(b["data"]),
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


MD_SKIP = ("embed_html", "spacer")   # an iframe is a video or a map, and a gap is a gap: nothing to write down


def _html_md(html):
    """The admin's rich text (a contenteditable) as Markdown. h1 is demoted to ## because the page
    title owns the only #.
    # ponytail: regex, not a parser — a nested list or a pasted table comes out flat, and a bold
    # word inside a blockquote loses its stars. Swap for markdownify if editors start pasting
    # complicated HTML."""
    if not html:
        return ""
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", str(html))
    s = re.sub(r"(?is)<blockquote[^>]*>(.*?)</blockquote>",
               lambda m: "\n\n> " + " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split()) + "\n\n", s)
    s = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>",
               lambda m: f"\n\n{'#' * max(2, int(m.group(1)))} {' '.join(m.group(2).split())}\n\n", s)
    s = re.sub(r"""(?is)<a[^>]*?href=["']([^"']*)["'][^>]*>(.*?)</a>""", r"[\2](\1)", s)
    s = re.sub(r"(?is)<(strong|b)\b[^>]*>(.*?)</\1>", r"**\2**", s)
    s = re.sub(r"(?is)<(em|i)\b[^>]*>(.*?)</\1>", r"*\2*", s)
    s = re.sub(r"(?is)<code\b[^>]*>(.*?)</code>", r"`\1`", s)
    s = re.sub(r"(?is)<li[^>]*>(.*?)</li>", lambda m: "\n- " + " ".join(m.group(1).split()), s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|ul|ol|table|tr)>", "\n\n", s)
    s = unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _md_link(label, url):
    return f"[{label}]({url})" if label and url else ""


def _media(media_id):
    """(url, alt) for a media id, or ("", "") — the same row media_url()/media_alt() read."""
    from . import db

    m = (db.get_media(int(media_id)) if str(media_id or "").isdigit() else None) or {}
    return m.get("url") or "", m.get("alt") or ""


def _md_img(media_id, alt=""):
    url, media_alt = _media(media_id)
    return f"![{alt or media_alt}]({url})" if url else ""


def blocks_md(blocks, h1=True):
    """Markdown of all block content — the body of every page's .md twin and of llms-full.txt.
    h1=False when the caller already opened a heading above this content (llms-full.txt puts every
    page under a ## of its own), so the hero's heading does not out-rank its own container.
    blocks_text() flattens the same content to one line for admin search; this keeps the shape a
    reader (human or machine) needs: headings, lists, tables, links.
    # ponytail: a new entry in BLOCKS needs a branch here too, or its words never reach the .md.
    # test_blocks_md_covers_every_block() fails until it has one."""
    out = []
    for b in blocks:
        t, d = b.get("type"), b.get("data") or {}
        head = f"## {d['heading']}" if d.get("heading") else ""
        if t == "hero":
            out += [d.get("eyebrow") or "", f"{'#' if h1 else '###'} {d.get('heading', '')}", d.get("subheading") or "",
                    _md_link(d.get("cta_label"), d.get("cta_url")), _md_link(d.get("cta2_label"), d.get("cta2_url"))]
        elif t == "rich_text":
            out.append(_html_md(d.get("html")))
        elif t == "image":
            out += [_md_img(d.get("media_id"), d.get("alt")), f"*{d['caption']}*" if d.get("caption") else ""]
        elif t == "gallery":
            out.append("\n\n".join(x for x in (_md_img(i.get("media_id"), i.get("alt")) for i in d.get("images") or []) if x))
        elif t == "cards":
            out.append(head)
            for i in d.get("items") or []:
                out += [f"### {i.get('title', '')}", i.get("text") or "", _md_link(i.get("title"), i.get("url"))]
        elif t == "columns":
            out += [head] + [blocks_md(c, h1) for c in d.get("cols") or [] if isinstance(c, list)]
        elif t == "cta":
            out += [head, d.get("text") or "", _md_link(d.get("button_label"), d.get("button_url"))]
        elif t == "faq":
            out.append(head)
            for i in d.get("items") or []:
                out += [f"### {i.get('q', '')}", _html_md(i.get("a"))]
        elif t == "stats":
            out.append("\n".join(f"- **{i.get('value', '')}** — {i.get('label', '')}" for i in d.get("items") or []))
        elif t == "testimonial":
            who = ", ".join(x for x in (d.get("author"), d.get("role"), d.get("company")) if x)
            out.append(f"> {d.get('quote', '')}" + (f"\n>\n> — {who}" if who else ""))
        elif t == "spec_table":
            rows = [r for r in d.get("rows") or [] if isinstance(r, dict)]
            table = "\n".join(f"| {r.get('k', '')} | {r.get('v', '')} |" for r in rows)
            out += [head, f"| Label | Value |\n| --- | --- |\n{table}" if rows else ""]
        elif t == "post_list":
            out.append(head)
            out.append("\n".join(f"- [{p['title']}]({md_url(p['path'])})" + (f": {p['excerpt']}" if p.get("excerpt") else "")
                                 for p in _post_list(d)[0] if p.get("path")))
        elif t == "pdf":
            out += [head, _md_link("Download the PDF", _media(d.get("file_media_id"))[0])]
        elif t == "contact_form":
            out += [head, "*(a form on the page — name, email and a message)*"]
        elif t == "warranty_check":
            out += [head, "*(a box on the page where a customer types their serial number)*"]
        elif t == "divider":
            out.append("---")   # the join is "\n\n", so this can only ever be a thematic break
    return "\n\n".join(x for x in out if x and x.strip())


def _post_list(data):
    """(posts, post-type slug). The slug is the design's per-type card variant, and it comes from
    the resolved row rather than the block's own data, so it is safe to put in a class name."""
    from . import db

    pt = db.post_type(slug=data["post_type"])
    if pt is None:
        return [], ""
    if data.get("term"):
        term = db.one(db.table("terms").select("id").eq("slug", data["term"]))
        if term is None:
            return [], pt["slug"]
        q = db.table("posts").select(db.POST_SELECT_BY_TERM).eq("post_terms.term_id", term["id"])
    else:
        q = db.select_posts()
    q = db.live(q).eq("post_type_id", pt["id"])
    if data.get("top_level"):
        q = q.is_("parent_id", "null")
    q = q.order("menu_order").order("published_at", desc=True).limit(int(data.get("limit") or 10))
    posts = db.with_paths(db.rows(q))
    if data.get("top_level") and pt["hierarchical"]:
        # the child chips under each card. db.tree() is already memoised for this request by the
        # header's services panel, so on most pages this costs nothing.
        kids = {t["id"]: t["children"] for t in db.tree(pt["slug"])}
        for p in posts:
            p["children"] = kids.get(p["id"], [])
    return posts, pt["slug"]


def warranty_active(row, today=None):
    """Is this warranty still running? ISO date strings sort as dates, so the whole check is a
    string compare — no parsing, and no timezone to get wrong. Expiring today still counts as in."""
    return bool(row.get("expiry_date")) and row["expiry_date"] >= (today or date.today().isoformat())


def _warranty():
    """The warranty the visitor asked about, for the warranty_check block:
       None = they have not asked yet (just show the form), {} = they asked and there is no such serial.
    Matched on serial_key (upper(btrim(serial)), a generated column) so case and stray spaces do not
    matter, and so the match is an exact one: a serial may contain % or _, which ilike would treat as
    wildcards.
    # ponytail: the serial alone is the key, so a guessed serial returns that customer's name and
    # email. Ask for the registered email too, or rate-limit this, if serials turn out to be guessable."""
    from flask import has_request_context, request

    from . import db

    if not has_request_context():
        return None
    key = (request.args.get("sn") or "").strip().upper()
    if not key:
        return None
    row = db.one(db.table("warranties").select("*").eq("serial_key", key))
    if row:
        row["active"] = warranty_active(row)
    return row or {}
