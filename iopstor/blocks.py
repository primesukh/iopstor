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
                           "cta2_label", "cta2_url", "dark", "still", "arrange", "noglow"]),
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
    # The founder pair on About Us: a picture, a name and a job title, repeated. It was written as a
    # rich_text carrying its own classes, which Quill drops -- the same reason points and definitions
    # exist (section 12.3). The picture is optional: with none, .ava draws the design's hatched circle.
    "people": (["items"], ["heading"]),  # items: [{name, role, media_id}]
    "embed_html": (["html"], []),
    # link_label/link_url are the "All services →" link in the section header.
    "post_list": (["post_type"], ["heading", "eyebrow", "term", "limit", "top_level",
                                  "link_label", "link_url", "per_row", "list_style", "open_tone"]),  # queried at render time; top_level=true → parents only
    "spec_table": (["rows"], ["heading"]),  # rows: [{k, v}]
    # A term and its description on a ruled row -- the design's "ZFS features, in plain terms".
    # Deliberately spec_table's shape: same repeater, same labels, only the markup differs. Values are
    # ESCAPED, so this is for prose and not for a list carrying links (see Contact Us, which is not
    # this block and is built from Settings instead).
    "definitions": (["rows"], ["heading"]),  # rows: [{k, v}]
    # A heading, a short intro and a dashed list of points, with an optional button: the shape the
    # design draws down one side of a two-column band. It was written as a rich_text carrying its own
    # classes, which Quill cannot hold without dropping them -- section 12.3.
    "points": (["items"], ["eyebrow", "heading", "subheading", "button_label", "button_url"]),  # items: [{text}]
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
                "cta2_url": "url", "link_url": "url", "dark": "checkbox", "still": "checkbox", "arrange": "choice", "noglow": "checkbox",
                "count_up": "checkbox", "fx": "choice", "height": "choice", "per_row": "choice",
                "list_style": "choice", "open_tone": "choice"},
    # repeater fields (items/images/rows/cols) -> the subfields of one row; [] = rows are not field rows
    "items": {"cards": ["title", "text", "icon", "url"], "faq": ["q", "a"], "stats": ["value", "label", "fx", "count_up"],
              "spec_table": ["k", "v"], "definitions": ["k", "v"], "points": ["text"],
              "people": ["name", "role", "media_id"],
              "gallery": ["media_id", "alt"], "hero": ["media_id", "alt"],
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
               # "<block>.<field>" beats the bare key, like "widgets" above. On a hero the tick is
               # the LAYOUT -- the full-width band, the picture as a backdrop -- and the section's
               # own Background dropdown decides the colour; on a testimonial it really is just the
               # colour, so the bare label stays right there.
               "hero.dark": "Full-width band, picture behind the words",
               "still": "Hold the picture still", "arrange": "Where the picture goes",
               "noglow": "Hide the glow behind the picture",
               "count_up": "Count up from zero", "fx": "Effect", "per_row": "Items per row",
               "list_style": "List style", "open_tone": "Colour when open"},
    "kinds": ["contact", "quote", "career"],
    # options for the "choice" widget, keyed by field: [value, label] pairs, so the empty one can
    # say what it means. blocks.py FX is the whitelist these values are checked against.
    "choices": {"fx": [["", "None"],
                       ["rise", "Fades in as the page loads"],
                       ["gradient", "Gradient across the big text"],
                       ["sweep", "Highlighter sweep behind the headings"]],
                "height": [["small", "Small"], ["medium", "Medium"], ["large", "Large"], ["huge", "Extra large"]],
                "arrange": [["", "Beside the words"], ["above", "Above the words"], ["below", "Below the words"]],
                "per_row": [["", "As many as fit the width"],
                            ["even", "Even rows, in as few lines as it can"]]
                           + [[str(n), f"{n} per row"] for n in range(2, 9)],
                # "" is not "cards": it is the shape _acc() picks for the type, which is the
                # accordion for a top-level services list and cards for everything else.
                "list_style": [["", "Automatic"], ["cards", "Cards"], ["accordion", "Accordion"]],
                # the accordion's open row. Compared against these literals in the template, never
                # interpolated -- the same rule hero.arrange follows.
                "open_tone": [["", "Black"], ["blue", "Blue"], ["light", "Light grey"]]},
    # order the section picker offers them in, commonest first (Jinja's tojson sorts dict keys,
    # so BLOCKS' own order does not survive the trip to the browser)
    "order": ["hero", "rich_text", "cards", "columns", "spacer", "divider", "cta", "faq", "stats",
              "testimonial", "people", "points", "spec_table", "definitions", "image", "gallery", "pdf",
              "post_list", "contact_form",
              "warranty_check", "embed_html"],
    # the visual inserter: icon, plain-English name, one line on what the visitor sees
    "names": {
        "hero": ("\U0001F3D4", "Hero", "The big opening band: headline, one line of text, one button."),
        "rich_text": ("\u00B6", "Rich text", "Words, headings and lists \u2014 type into it like a Word document."),
        "cards": ("\u25A4", "Cards", "A row of boxes, each with a title, a line of text and an optional link."),
        "points": ("\u2014", "Key points", "A heading, a short intro and a dashed list of points, with an optional button."),
        "definitions": ("\u2637", "Definitions", "Terms down one side, what each one means down the other."),
        "columns": ("\u25A5", "Columns", "Two or more columns side by side, each holding its own sections."),
        "cta": ("\U0001F4E3", "Call to action", "A coloured band that asks the visitor to do one thing."),
        "faq": ("\u2753", "Questions & answers", "Questions that open to reveal the answer. Google shows these too."),
        "stats": ("\U0001F4CA", "Numbers", "A row of big figures with a label under each one."),
        "testimonial": ("\U0001F4AC", "Customer quote", "Something a customer said, with their name and company."),
        "people": ("\U0001F464", "People", "A row of people: a photo, a name and a job title under it."),
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
        # no media_id: a person with no photo gets the design's hatched circle, which is what About Us
        # has always shown, so the section is complete without a trip to the media library.
        "people": {"items": [{"name": "Their name", "role": "What they do"},
                             {"name": "Somebody else", "role": "What they do"}]},
        "spec_table": {"heading": "Specifications", "rows": [{"k": "Capacity", "v": "Up to 5 PB"}, {"k": "Interface", "v": "NFS, SMB, S3"}]},
        "definitions": {"heading": "In plain terms", "rows": [{"k": "First term", "v": "What it means, in a sentence."},
                                                              {"k": "Second term", "v": "What it means, in a sentence."}]},
        "points": {"eyebrow": "Why it matters", "heading": "The thing this section is about",
                   "subheading": "One or two lines setting the list up.",
                   "items": [{"text": "The first point, in a line."}, {"text": "The second point, in a line."},
                             {"text": "The third point, in a line."}]},
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

# Keys whose value is never prose. Two jobs, and the second is why the underscore pair is here:
# blocks_text() skips them (a uuid in llms-full.txt and admin search would be nonsense), and the
# editor sends the set to the browser as EDITOR["scalars"] to decide which fields become a shared
# text type and which stay plain values. _id names a section for as long as it exists so two
# browsers can talk about the same one without counting positions; _rich is the Quill gate's
# verdict, stored rather than recomputed so every editor of a page agrees about it.
_NON_TEXT_KEYS = {"url", "cta_url", "cta2_url", "button_url", "link_url", "icon", "image", "media_id", "file_media_id",
                  "post_type", "term", "limit", "kind", "top_level", "dark", "still", "arrange", "noglow", "pad", "type", "widths", "align", "align_box", "width",
                  "tone", "fx", "count_up", "height", "per_row", "list_style", "open_tone", "_id", "_rich"}
EDITOR["scalars"] = sorted(_NON_TEXT_KEYS)
# JSONB does not keep key order, so text extraction walks fields in this reading order (unknown keys follow, alphabetically)
_TEXT_ORDER = ("eyebrow", "heading", "subheading", "title", "q", "a", "text", "html", "quote", "author", "name", "role", "company",
               "value", "label", "k", "v", "caption", "alt", "cta_label", "cta2_label", "button_label", "link_label",
               "items", "images", "rows", "cols")
_RANK = {k: i for i, k in enumerate(_TEXT_ORDER)}


# A column holds sections, but not another grid (one level is enough to lay a page out, and nesting
# grids is how an Elementor page becomes unmaintainable) and not a hero, which is a full-bleed band
# owning the page's only <h1>.
NEVER_NESTED = ("columns", "hero")


def validate_blocks(blocks, where="blocks", nested=False, draft=False):
    """draft=True checks the shape but not completeness: an unfinished page is what a working draft
    IS. A paragraph with the caret still in it has no text, an Image section has no picture until one
    is chosen, and neither is a reason to refuse to save somebody's work. "Required" is a rule about
    publishing, and Publish enforces it on its own through apply_post() -- which is still the one
    validation path, so nothing reaches posts.blocks without passing the full check."""
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
        if not draft:
            for field in spec[0]:
                if b["data"].get(field) in (None, "", []):
                    errors.append(f"{at}.{field} required")
        if b["type"] == "columns":
            cols = b["data"].get("cols")
            if isinstance(cols, list):
                for c, col in enumerate(cols):
                    errors += validate_blocks(col, f"{at}.cols[{c}]", nested=True, draft=draft)
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
# How much air a section keeps above and below. Absent is the design's own 80px, which is right for
# a band of content and far too much for a rule: a divider between two sections sat in 208px of
# white (80 below the one above + 24 of its own, then 24 + 80). The CSS holds the pixels, and sets
# padding-block only, so a toned section inside a column keeps the side padding that makes it a card.
#
# NOTHING LARGER THAN THE DEFAULT, deliberately. design.md's 2026-09-10 row chose Spacer and Divider
# as block types over "spacing controls on every section's gear", and that stands for ADDING air --
# a thing you can drag, copy and delete beats a dropdown. What a Spacer cannot do is take away air
# that is already there, which is all this is for. Add with a Spacer, remove with this, and the two
# never overlap. Every value below is a number the theme already uses.
PADS = ("none", "small", "medium")
MAX_W = 4000


def section_class(data):
    """The layout classes for one section, from seven optional keys — absent means the theme's own
    layout. "align" lines up what is inside it, "align_box" moves the box, "tone" is the band it sits
    on (the design alternates white and grey down a page for rhythm), "width" is either a named
    step (wide / full) or a number of pixels, which section_style() carries instead, and "fx" is
    the motion in site.css's effects group, "height" is how tall a spacer stands, and "pad" is how much air it keeps above and below. A whitelist,
    not a passthrough: the result goes straight into a class attribute, the same reason col_widths()
    is strict — which is also why stats.html calls this for one figure's own effect rather than
    building the class itself.
    Returns "" or " al-center", " al-center alb-right w-full fx-rise", …"""
    out = [p + data[k] for k, p in (("align", "al-"), ("align_box", "alb-")) if data.get(k) in ALIGNS]
    out += ["t-" + data["tone"]] if data.get("tone") in TONES else []
    out += [WIDTHS[str(data.get("width"))]] if str(data.get("width")) in WIDTHS else []
    out += ["fx-" + data["fx"]] if data.get("fx") in FX else []
    out += ["sp-" + data["height"]] if data.get("height") in HEIGHTS else []
    out += ["pad-" + data["pad"]] if data.get("pad") in PADS else []
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


DETAILS_TOP, DETAILS_END = "top", "end"


# The two types that read down the page like a piece of writing rather than across like a product
# sheet. site.css keys the stacking off .pt-<slug>, so a slug added here needs both .pt-post rules
# widening too -- "both halves or neither" (design.md, 2026-09-19).
ARTICLE_TYPES = ("post", "case_study")
# The two block types that open a page with a heading and a picture of their own.
OWN_HEAD_BLOCKS = ("hero", "columns")


def owns_head(pt_slug, blocks):
    """True when the page draws its OWN head -- title, date, term chips -- rather than letting an
    opening hero or columns section stand in for it.

    An article always does, even when a hero opens it: a hero draws a heading and a picture, but it
    has no date and no chips and could not render them if it wanted to (hero.html never receives
    `post`), so gating those on the hero lost them silently. Every other type keeps the old rule,
    because a head above the banner there is simply two headings.

    One function, three callers that MUST agree -- post.html, the .md twin (public._md_post) and the
    editor canvas. They were three separate expressions and had already drifted: the twin tested
    `hero` and not `columns`, so a columns-led page's Markdown carried a `#` its HTML did not.
    """
    # isinstance, not `or {}`: the canvas hands this straight off a browser-supplied JSON array,
    # where the first element can be anything at all.
    first = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
    return pt_slug in ARTICLE_TYPES or first.get("type") not in OWN_HEAD_BLOCKS


def details_at(post):
    """How many sections render before a type's long fields (a case study's Challenge / Solution /
    Results), from the reserved `meta._details_at`.

      -1  above the short-field strip, at the very top of the page
       0  straight after that strip, where they have always been -- and the fallback for anything
          unrecognised, so an older post and a mistyped value both render exactly as before
       n  after n sections, clamped to how many there are

    POSITIONAL, not by section identity, and that is a measurement rather than a preference: only
    9 of 81 blocks in this database carry the `_id` the editor mints (it is minted on edit, so
    seeded and untouched pages have none), so naming the section would have left most pages unable
    to choose one at all. The cost is that dragging sections about does not drag this with them.
    """
    blocks = post.get("blocks") or []
    at = str((post.get("meta") or {}).get("_details_at") or "")
    if at == DETAILS_TOP:
        return -1
    if at == DETAILS_END:
        return len(blocks)
    return min(int(at), len(blocks)) if at.isdigit() else 0


def render_blocks(blocks, edit=False, path="0", h1=True):
    """`path` is the data-b path of the FIRST block; its siblings increment the last part. The page
    itself starts at "0"; column 1 of block 2 renders with path "2.1.0".

    `h1=False` when the caller already opened a heading above this content, so a hero's heading does
    not out-rank the page's own -- the same parameter, name and meaning blocks_md() has carried since
    it was written. Only the block at path "0" can ever be the page's heading, so the flag is ANDed
    with that rather than with the loop index: post.html renders the blocks in two calls split at
    details_at(), and when the placement is the default the FIRST call is empty and the second one
    holds block 0. Both pass the same flag and the path decides, so neither call has to know about
    the other. It is also what stops a hero further down the page emitting a second <h1>, which it
    did on every page that had one."""
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
                # cols is computed here, never taken from the data, so the class is ours
                # rail is decided here for the same reason cols is: it depends on pt_slug, which came
                # from the row rather than the data. ponytail: one type is named. Make it a "Sliding
                # row" checkbox on the block when a second type wants one.
                extra = {"posts": posts, "pt_slug": pt_slug, "cols": _cols(b["data"], len(posts)),
                         "rail": pt_slug == "testimonial", "acc": _acc(b["data"], pt_slug)}
            elif b["type"] == "warranty_check":
                extra = {"found": None if edit else _warranty()}  # the admin canvas gets the bare form, never a lookup
            elif b["type"] == "columns":
                # the one block that renders other blocks: each column is its own list, one level down
                cols = b["data"].get("cols") or []
                # h1=False: a hero can never nest (NEVER_NESTED), so this is a statement of the
                # rule rather than a branch that fires.
                extra = {"col": lambda n, p=p, cols=cols: render_blocks(cols[n], edit, f"{p}.{n}.0", h1=False),
                         "widths": col_widths(b["data"])}
            out.append(render_template(f"blocks/{b['type']}.html", data=b["data"], edit=edit,
                                       cls=section_class(b["data"]), sty=section_style(b["data"]),
                                       fe=_fe(p) if edit else _no_fe, h1=h1 and p == "0", **extra))
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
    # Entities are decoded here, not left to the caller. The source is contenteditable HTML, so "R&D"
    # is stored as "R&amp;D" and the tag strip above does not touch it -- every consumer then escaped
    # it a second time and showed "R&amp;D": the feed's <description>, the audit diff, and `text` in
    # the public API. Decoding at the source is also what makes a paragraph holding nothing but
    # &nbsp; come back "" rather than truthy-but-blank, because .split() drops \xa0 as whitespace.
    return " ".join(unescape(" ".join(out)).split())


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
    for i, b in enumerate(blocks):
        t, d = b.get("type"), b.get("data") or {}
        head = f"## {d['heading']}" if d.get("heading") else ""
        if t == "hero":
            # `not i` is the Markdown twin of render_blocks()'s `p == "0"`: only the block that
            # OPENS the page can be its heading. A second hero further down used to open a second
            # `#`, which is the same bug the HTML had.
            out += [d.get("eyebrow") or "", f"{'#' if h1 and not i else '###'} {d.get('heading', '')}", d.get("subheading") or "",
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
        elif t == "people":
            out += [head, "\n".join(f"- **{i.get('name', '')}**" + (f" \u2014 {i['role']}" if i.get("role") else "")
                                    for i in d.get("items") or [] if isinstance(i, dict))]
        elif t == "definitions":
            # Markdown has no definition list, and the regex converter has no <dt>/<dd> case either --
            # which is why these ran together as prose in the .md twins for as long as they were HTML.
            rows = [r for r in d.get("rows") or [] if isinstance(r, dict)]
            out += [head] + [f"**{r.get('k', '')}**  \n{r.get('v', '')}" for r in rows]
        elif t == "points":
            out += [d.get("eyebrow") or "", head, d.get("subheading") or "",
                    "\n".join(f"- {i.get('text', '')}" for i in d.get("items") or [] if isinstance(i, dict)),
                    _md_link(d.get("button_label"), d.get("button_url")) if d.get("button_label") else ""]
        elif t == "spec_table":
            rows = [r for r in d.get("rows") or [] if isinstance(r, dict)]
            table = "\n".join(f"| {r.get('k', '')} | {r.get('v', '')} |" for r in rows)
            out += [head, f"| Label | Value |\n| --- | --- |\n{table}" if rows else ""]
        elif t == "post_list":
            # A post with no path is not a post with nothing to say: a has_pages=false type (a
            # testimonial, a technology partner) is real content that simply has no page of its own,
            # and dropping it left a heading over an empty list in the .md twins and llms-full.txt.
            # It loses the link, not the line.
            out.append(head)
            out.append("\n".join((f"- [{p['title']}]({md_url(p['path'])})" if p.get("path") else f"- **{p['title']}**")
                                 + (f": {p['excerpt']}" if p.get("excerpt") else "")
                                 for p in _post_list(d)[0]))
        elif t == "pdf":
            out += [head, _md_link("Download the PDF", _media(d.get("file_media_id"))[0])]
        elif t == "contact_form":
            out += [head, "*(a form on the page — name, email and a message)*"]
        elif t == "warranty_check":
            out += [head, "*(a box on the page where a customer types their serial number)*"]
        elif t == "divider":
            out.append("---")   # the join is "\n\n", so this can only ever be a thematic break
    return "\n\n".join(x for x in out if x and x.strip())


def even_cols(n, lo=4, hi=8):
    """How many per row lays n items out in the fewest rows, each row as full as n allows.

    Fewest rows first (2026-09-21): a fifteenth partner used to take the exact divisor 5 and turn a
    two-line strip into 5+5+5, when 8+7 is two lines. Among the counts that reach that row total the
    fullest last row wins, so 14 is still 7+7 rather than 8+6 and 16 is still 8+8; only the counts
    where an exact divisor costs a whole extra row change (20 was 5x4, is 7+7+6). Fewer than hi
    items are one row of themselves.
    `-(-n // c)` is the row count, `-n % c` the shortfall in the last row (0 when c divides n),
    and -c breaks a remaining tie upward.
    """
    if n <= hi:
        return n or None
    return min(range(lo, hi + 1), key=lambda c: (-(-n // c), -n % c, -c))


def _cols(data, n):
    """The editor's "Items per row" as a column count, or None for the width-driven default.

    Parsed here rather than trusted, because it reaches the template as a class name.
    """
    v = str(data.get("per_row") or "").strip()
    if v == "even":
        return even_cols(n)
    return int(v) if v.isdigit() and 2 <= int(v) <= 8 else None


def _acc(data, pt_slug):
    """Is this list the accordion instead of the deck of cards? An editor's choice wins; "" is
    Automatic, which is the services stack the design asks for (2026-09-21) and cards everywhere
    else. Decided here rather than read out of the data, for the same reason `cols` and `rail` are:
    pt_slug comes from the resolved post_types row, so nothing an editor typed reaches the markup."""
    v = (data.get("list_style") or "").strip()
    return v == "accordion" or (v == "" and pt_slug == "service" and bool(data.get("top_level")))


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
