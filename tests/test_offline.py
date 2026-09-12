"""Pure logic — no Supabase needed."""
from copy import deepcopy

from iopstor import display_name
from iopstor.admin_ui import _password_errors
from iopstor.blocks import at_path, blocks_md, blocks_text, col_widths, render_blocks, validate_blocks
from iopstor.db import slugify


def test_slugify():
    assert slugify("NAS Storage!") == "nas-storage"
    assert slugify("  Désktop as a Service  ") == "desktop-as-a-service"
    assert slugify("///") == "item"


def test_validate_blocks():
    assert validate_blocks("nope") == ["blocks must be a list"]
    errs = validate_blocks([{"type": "nope", "data": {}}, {"type": "hero", "data": {}}, {"type": "cta", "data": {"heading": "x", "button_label": "y", "button_url": "/z"}}])
    assert errs == ["blocks[0]: unknown type 'nope'", "blocks[1].heading required"]
    assert validate_blocks([{"type": "hero", "data": {"heading": "Hi"}}]) == []


def test_render_blocks_uses_template(app, monkeypatch):
    from iopstor import db
    monkeypatch.setattr(db, "settings", lambda: {})  # base template context processor reads site settings
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    html = render_blocks([{"type": "hero", "data": {"heading": "Fast <NAS>"}}, {"type": "stats", "data": {"items": [{"value": "5PB", "label": "per rack"}]}},
                          {"type": "spacer", "data": {"height": "large"}}, {"type": "divider", "data": {}}])
    assert "<h1>Fast &lt;NAS&gt;</h1>" in html and "5PB" in html
    # the two content-less blocks are here because nothing else asserts a template exists, and a
    # missing one is a 500 on the public page rather than a failing test
    assert '<section class="section spacer sp-large"></section>' in html and "<hr>" in html


def test_blocks_text_flattens():
    txt = blocks_text([{"type": "rich_text", "data": {"html": "<p>Hello <b>world</b></p>"}}, {"type": "cta", "data": {"heading": "Go", "button_label": "Now", "button_url": "/x"}}])
    assert txt == "Hello world Go Now"


def test_blocks_md_keeps_the_shape_blocks_text_throws_away():
    """The .md twin of a page (and llms-full.txt) is only worth serving if it keeps headings,
    lists, tables and quotes — blocks_text() flattens all of that to one line."""
    md = blocks_md([
        {"type": "hero", "data": {"heading": "Fast NAS", "subheading": "Scale-out file storage.",
                                  "cta_label": "Talk to us", "cta_url": "/contact-us"}},
        {"type": "rich_text", "data": {"html": "<h2>Why</h2><p>It is <b>fast</b> and <a href='/x'>cheap</a>.</p><ul><li>One</li><li>Two</li></ul>"}},
        {"type": "faq", "data": {"heading": "Questions", "items": [{"q": "Why?", "a": "<p>Because.</p>"}]}},
        {"type": "spec_table", "data": {"rows": [{"k": "Capacity", "v": "5 PB"}]}},
        {"type": "testimonial", "data": {"quote": "It works.", "author": "Ada", "company": "Acme"}},
        {"type": "stats", "data": {"items": [{"value": "99.999%", "label": "uptime"}]}},
        {"type": "embed_html", "data": {"html": "<iframe src='https://youtube.com/x'></iframe>"}},
        _cols([{"type": "rich_text", "data": {"html": "<p>Inside a column</p>"}}],
              [{"type": "cta", "data": {"heading": "Ready?", "button_label": "Contact", "button_url": "/c"}}]),
    ])
    assert "# Fast NAS" in md and "\n## " not in md.split("# Fast NAS")[0]   # the hero owns the only h1
    assert "[Talk to us](/contact-us)" in md
    assert "## Why" in md and "It is **fast** and [cheap](/x)." in md and "- One\n- Two" in md
    assert "## Questions" in md and "### Why?" in md and "Because." in md
    assert "| Label | Value |" in md and "| Capacity | 5 PB |" in md
    assert "> It works." in md and "> — Ada, Acme" in md
    assert "- **99.999%** — uptime" in md
    assert "youtube" not in md                      # an iframe is not words
    assert "Inside a column" in md and "[Contact](/c)" in md   # a column's blocks come along
    assert "<" not in md and "&amp;" not in md      # no HTML survives into the Markdown


def test_blocks_md_covers_every_block(app, monkeypatch):
    """A new entry in BLOCKS needs a branch in blocks_md(), or its words never reach the .md twin."""
    from iopstor import db
    from iopstor.blocks import BLOCKS, EDITOR, MD_SKIP

    monkeypatch.setattr(db, "post_type", lambda **k: None)   # post_list resolves its type offline
    for name in BLOCKS:
        block = {"type": name, "data": EDITOR["seed"].get(name) or {}}
        # the picture blocks seed to nothing until a file is chosen, which is what validate_blocks
        # already says about them: an unsaveable seed has no words to write down either
        if name in MD_SKIP or validate_blocks([block]):
            continue
        assert blocks_md([block]).strip(), name


def test_spacer_and_divider_are_layout_not_words():
    """The two sections with nothing to say still have to say nothing correctly: a divider is a
    thematic break in the .md twin, a spacer is skipped there, and the height an editor picks lands
    in a class attribute — so it goes through the whitelist and never into the page's text."""
    from iopstor.blocks import section_class

    assert blocks_md([{"type": "divider", "data": {}}]).strip() == "---"
    assert blocks_md([{"type": "spacer", "data": {"height": "large"}}]) == ""
    assert blocks_text([{"type": "spacer", "data": {"height": "large"}}]) == ""
    assert section_class({"height": "large"}) == " sp-large"
    assert section_class({"height": '40px" onload="x'}) == ""


def test_md_url_is_the_only_place_the_suffix_is_spelled():
    from iopstor.seo import md_url

    assert md_url("/") == "/index.md" and md_url("") == "/index.md"
    assert md_url("/services/nas") == "/services/nas.md"


def test_social_links_get_a_name_and_an_icon(app, monkeypatch):
    """Settings stores bare URLs. The footer needs a network name for the aria-label and a sprite id
    for the glyph; the Organization's sameAs still needs the plain strings it always had."""
    from iopstor import db, seo

    urls = ["https://www.linkedin.com/company/iopstor", "https://twitter.com/iopstor", "https://mastodon.social/@iopstor"]
    monkeypatch.setattr(db, "settings", lambda: {"social_links": urls})
    assert [(x["name"], x["icon"]) for x in seo.site()["social"]] == [
        ("LinkedIn", "linkedin"),       # a www. in front of a known host still matches
        ("X", "x"),                     # twitter.com and x.com are one glyph
        ("mastodon.social", ""),        # unknown network: hostname as the label, and text, not a blank link
    ]
    assert seo.jsonld()[0]["sameAs"] == urls


def test_jwt_matrix_without_db(client):
    assert client.get("/api/admin/v1/posts").status_code == 401
    assert client.get("/api/admin/v1/posts", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_editor_metadata_covers_every_block():
    """Adding a block without editor metadata leaves /admin unable to render its fields."""
    from iopstor.blocks import BLOCKS, EDITOR, REPEATERS

    for name, (required, optional) in BLOCKS.items():
        for field in required + optional:
            widget = EDITOR["widgets"].get(f"{name}.{field}") or EDITOR["widgets"].get(field) or "text"
            assert widget in ("text", "textarea", "code", "richtext", "media", "pdf", "url", "number", "checkbox",
                              "post_type", "kind", "choice"), (name, field)
            if widget == "choice":
                assert EDITOR["choices"].get(field), f"{name}.{field} is a choice with no EDITOR['choices'] entry"
            if field in REPEATERS:
                assert EDITOR["items"].get(name) is not None, f"{name}.{field} is a repeater with no EDITOR['items'] entry"
    assert set(EDITOR["items"]) <= set(BLOCKS)


def test_inserter_metadata_and_seeds():
    """Every block must be offerable in the visual inserter, and arrive usable when inserted."""
    from iopstor.blocks import BLOCKS, EDITOR

    for name, (required, optional) in BLOCKS.items():
        icon, label, description = EDITOR["names"][name]
        assert icon and label and description.endswith("."), name
        seed = EDITOR["seed"][name]
        assert set(seed) <= set(required + optional), (name, set(seed) - set(required + optional))
    # a seeded block the editor drops in should save as-is; the file blocks are the honest exception
    for name in BLOCKS:
        if name in ("image", "gallery", "pdf"):
            continue  # no placeholder can stand in for a picture or a PDF: the editor has to choose one
        assert validate_blocks([{"type": name, "data": EDITOR["seed"][name]}]) == [], name


def test_layouts_expand_and_validate():
    from iopstor.blocks import BLOCKS, LAYOUTS, layout

    for name in LAYOUTS:
        blocks = layout(name)
        assert blocks and all(b["type"] in BLOCKS for b in blocks), name
        assert validate_blocks(blocks) == [], name
    assert layout("nope") == []
    a, b = layout("Product page"), layout("Product page")
    a[0]["data"]["heading"] = "changed"
    assert b[0]["data"]["heading"] != "changed"  # seeds must be copied, not shared


def test_menu_rows_rebuild_into_one_level_of_children():
    """The menus screen posts flat rows and a level per row; this is the only place that shape
    turns back into what base.html renders."""
    from iopstor.admin_ui import menu_items

    labels = ["Services", "Storage", "Cloud", "Blog", ""]
    urls = ["/services", "/services/storage", "/services/cloud", "/blog", "/nowhere"]
    assert menu_items(labels, urls, ["0", "1", "1", "0", "0"]) == [
        {"label": "Services", "url": "/services", "children": [
            {"label": "Storage", "url": "/services/storage"},
            {"label": "Cloud", "url": "/services/cloud"}]},
        {"label": "Blog", "url": "/blog"}]                      # the label-less row deletes itself
    # a child with nothing above it is promoted, not dropped
    assert menu_items(["Orphan"], ["/o"], ["1"]) == [{"label": "Orphan", "url": "/o"}]
    assert menu_items([], [], []) == []


def test_alt_from_name_is_a_readable_first_draft():
    """Imported files must not land with an empty alt: an undescribed picture is the one thing
    the media screen flags in red, and a bulk import could add dozens at once."""
    from iopstor.cli import alt_from_name

    assert alt_from_name("rack-96tb.png") == "rack 96tb"
    assert alt_from_name("650x180_micronlogo.png") == "650x180 micronlogo"
    assert alt_from_name("Western_Digital-logo.jpg") == "Western Digital logo"
    assert alt_from_name("a" * 400 + ".png") == "a" * 300      # the column is varchar(300)


def test_seeded_content_is_valid_blocks():
    """The seed writes these arrays straight into posts.blocks. A bad one would only show up as a
    failed insert half way through `flask seed`, on the user's database."""
    from iopstor.cli import WHY_NAS, ZFS_FEATURES, home_blocks

    # both shapes: a fresh instance with no media, and one where the pictures are imported
    for media in (lambda name: None, lambda name: 1):
        blocks = home_blocks(media)
        assert len(blocks) == 9 and validate_blocks(blocks) == []   # the design's nine sections
    assert "image" not in home_blocks()[0]["data"]   # no null key left behind before an import
    assert "images" not in home_blocks()[0]["data"]  # nor an empty rotator
    assert len(home_blocks(lambda name: 1)[0]["data"]["images"]) == 3   # the design cycles all three
    cards = [{"type": "cards", "data": {"heading": h, "items": [
        {"title": t, "text": d, "icon": "", "url": ""} for t, d in rows]}}
        for h, rows in (("Why choose our NAS?", WHY_NAS), ("ZFS, feature by feature", ZFS_FEATURES))]
    assert validate_blocks(cards) == []


def test_hero_takes_turns_only_with_two_pictures_or_more(app, monkeypatch):
    """The rotator is CSS: each slide carries its turn as --i and the container the count as --n, and
    one picture stays the single <img> it always was, dots and all switched off."""
    from iopstor import db

    # media_url() is a Jinja global over db.get_media(), not a name in blocks.py — patching it there
    # patched nothing and let the render reach for PostgREST.
    monkeypatch.setattr(db, "get_media", lambda pk: {"url": f"/m/{pk}", "alt": ""})
    monkeypatch.setattr(db, "settings", lambda: {})
    one = [{"type": "hero", "data": {"heading": "Hi", "images": [{"media_id": 1, "alt": "a"}]}}]
    three = [{"type": "hero", "data": {"heading": "Hi", "images": [
        {"media_id": i, "alt": f"a{i}"} for i in (1, 2, 3)]}}]
    assert validate_blocks(one) == [] and validate_blocks(three) == []
    with app.test_request_context("/"):
        assert "hero-slides" not in render_blocks(one)
        html = render_blocks(three)
    assert html.count("hero-slide\"") == 3 and '--n:3' in html
    assert '--i:0' in html and '--i:2' in html
    assert "hero-dots" in html


def test_a_deck_caps_its_child_chips_and_an_archive_does_not(app):
    """Every card in a row is as tall as the tallest, so one long child list padded four cards out
    with empty space. A deck shows four and counts the rest; the archive, which IS the full list,
    still shows every child as a tile you can click."""
    kids = [{"title": f"Child {i}", "path": f"/services/g/c{i}"} for i in range(7)]
    parent = {"title": "Cloud", "path": "/services/g", "excerpt": "", "meta": {}, "terms": [],
              "children": kids, "featured_media": None, "post_type": {"slug": "service"}}
    src = "{% from '_card.html' import card %}{{ card(p, 1, actions=a) }}"
    with app.test_request_context("/"):
        deck = app.jinja_env.from_string(src).render(p=parent, a=False)
        arch = app.jinja_env.from_string(src).render(p=parent, a=True)
    assert deck.count('class="chip"') == 4 and "+3 more" in deck
    assert "Child 4" not in deck                      # the ones the count stands for
    assert arch.count('class="chip"') == 7 and "+3 more" not in arch
    assert '/services/g/c6' in arch                   # and every one of them is a link


def test_rupees_groups_the_way_an_indian_price_is_read(app):
    """`{:,}` groups in threes all the way up and would print 12,50,000 as 1,250,000."""
    rupees = app.jinja_env.globals["rupees"]
    assert rupees(999) == "\u20b9 999"
    assert rupees(5000) == "\u20b9 5,000"
    assert rupees(125000) == "\u20b9 1,25,000"
    assert rupees(1250000) == "\u20b9 12,50,000"
    assert rupees(12500000) == "\u20b9 1,25,00,000"       # one crore twenty-five lakh
    assert rupees("1250000") == "\u20b9 12,50,000"        # meta holds whatever the form sent
    assert rupees("on request") == "on request"           # not a number: left exactly as written
    assert rupees(None) == ""


def test_kv_field_saves_rows_in_order_and_never_a_broken_string(app, monkeypatch):
    """The json type stored raw text when it would not parse, and the spec table then silently
    vanished from the live page. Rows cannot do that: what will not parse is no rows."""
    from iopstor import admin_ui

    pt = {"slug": "product", "field_schema": [{"key": "specs", "label": "Specifications", "type": "kv"}]}

    def body(raw):
        with app.test_request_context("/admin/x", method="POST", data={"title": "T", "meta_specs": raw, "blocks": "[]"}):
            return admin_ui._form_body(pt, None)["meta"]

    rows = '[{"k": "CPU", "v": "Xeon"}, {"k": "RAM", "v": "32GB"}]'
    assert body(rows)["specs"] == [{"k": "CPU", "v": "Xeon"}, {"k": "RAM", "v": "32GB"}]   # order kept
    assert body('[{"k": "CPU", "v": "Xeon"}, {"k": "  ", "v": "x"}]')["specs"] == [{"k": "CPU", "v": "Xeon"}]
    assert "specs" not in body("{not json")      # no rows, rather than a string nothing can render
    assert "specs" not in body("[]")


def test_a_type_without_pages_has_no_url_and_no_link(app):
    """One flag, one mechanism: has_pages=false means with_paths() hands the post no path, and
    everything that would have pointed at it falls away on its own — the resolver cannot match it,
    the crawler files skip it, and the card that shows it is not a link."""
    from iopstor.db import with_paths
    from iopstor.public import _indexable

    def row(has_pages):
        return {"slug": "micron", "parent_id": None, "title": "Micron", "excerpt": "", "meta": {}, "terms": [],
                "children": [], "featured_media": None,
                "post_type": {"slug": "partner", "url_prefix": "partners", "hierarchical": False,
                              "has_pages": has_pages}}

    linked, bare = with_paths([row(True)])[0], with_paths([row(False)])[0]
    assert linked["path"] == "/partners/micron" and bare["path"] is None
    assert _indexable(linked) and not _indexable(bare)          # out of sitemap.xml and llms.txt
    # and a database where migration 0005 has not run yet still routes exactly as it did
    older = {**row(False), "post_type": {"slug": "partner", "url_prefix": "partners", "hierarchical": False}}
    assert with_paths([older])[0]["path"] == "/partners/micron"

    src = "{% from '_card.html' import card %}{{ card(p) }}"
    with app.test_request_context("/"):
        html = app.jinja_env.from_string(src).render(p=bare)
        live = app.jinja_env.from_string(src).render(p=linked)
    assert "<a class=\"card\"" not in html and '<div class="card">' in html
    assert "Micron" in html                                     # still shown, just not clickable
    assert '<a class="card" href="/partners/micron">' in live


def test_only_numbered_files_are_migrations():
    """migrations/ holds two kinds of file: numbered steps `flask migrate` runs in order, and scripts
    run by hand in Studio. Executing one of the second kind as a step would be a bad afternoon."""
    from iopstor.cli import MIGRATION_GLOB, MIGRATIONS

    steps = {p.name for p in MIGRATIONS.glob(MIGRATION_GLOB)}
    assert "0001_initial.sql" in steps
    assert "0000_bootstrap.sql" in steps          # matched here, skipped by name in migrate()
    for p in MIGRATIONS.glob("*.sql"):
        assert p.name in steps or not p.name[:4].isdigit(), p.name
    assert "repair_schema_migrations.sql" not in steps


def test_pdf_block_renders_the_browser_viewer(app, monkeypatch):
    """The PDF section is an iframe at the file plus a download button — no viewer library, and a way
    in for the mobile browsers that will not render a framed PDF. The button saves the file under the
    name it was uploaded with, not the uuid its bucket key is made of."""
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(db, "get_media", lambda pk: {"url": "/media/2026/09/a.pdf", "filename": "flash array.pdf"})

    html = render_blocks([{"type": "pdf", "data": {"file_media_id": 7, "heading": "Datasheet"}}])
    assert '<iframe src="/media/2026/09/a.pdf#view=FitH"' in html
    assert 'href="/media/2026/09/a.pdf?download=flash%20array.pdf"' in html and ">Download the PDF</a>" in html
    assert validate_blocks([{"type": "pdf", "data": {"heading": "no file"}}]) == ["blocks[0].file_media_id required"]


def test_edit_markers_only_in_edit_mode(app, monkeypatch):
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    blocks = [{"type": "hero", "data": {"heading": "Hi"}}, {"type": "stats", "data": {"items": [{"value": "5PB", "label": "per rack"}]}}]

    public = render_blocks(blocks)
    assert "data-b=" not in public and "data-f=" not in public and "data-r=" not in public

    edit = render_blocks(blocks, edit=True)
    assert 'data-b="0"' in edit and 'data-b="1"' in edit
    assert 'data-f="heading" data-ph="Heading"' in edit
    assert 'data-r="items" data-i="0"' in edit


def test_dark_is_a_checkbox_not_a_class_name(app, monkeypatch):
    """The variant switch is a boolean the template tests for truth, so whatever an editor manages
    to put in `dark` becomes the same fixed class or none at all — never markup."""
    from iopstor import db
    monkeypatch.setattr(db, "settings", lambda: {})   # the base context processor reads site settings
    monkeypatch.setattr(db, "table", lambda *a, **k: 1 / 0)   # a hero needs no query
    with app.test_request_context("/"):
        plain = render_blocks([{"type": "hero", "data": {"heading": "Hi"}}])
        dark = render_blocks([{"type": "hero", "data": {"heading": "Hi", "dark": True}}])
        nasty = render_blocks([{"type": "hero", "data": {"heading": "Hi", "dark": '" onload="x'}}])

    assert "hero-dark" not in plain
    assert 'class="hero hero-dark"' in dark
    assert 'class="hero hero-dark"' in nasty and "onload" not in nasty

    # ...and neither the flag nor a URL is words on the page, so neither reaches llms-full.txt
    assert blocks_text([{"type": "hero", "data": {"eyebrow": "Label", "heading": "Hi",
                                                  "dark": True, "cta2_url": "/x",
                                                  "cta2_label": "More"}}]) == "Label Hi More"


def test_section_alignment_is_a_whitelist(app, monkeypatch):
    """Both alignments reach the section's class, in edit and public alike, and nothing else does."""
    from iopstor import db
    from iopstor.blocks import section_class

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    data = {"heading": "Hi", "align": "center", "align_box": "right"}
    blocks = [{"type": "cards", "data": {**data, "items": [{"title": "One", "text": "x"}]}}]

    assert section_class(data) == " al-center alb-right"
    assert 'class="section al-center alb-right"' in render_blocks(blocks)
    assert 'class="section al-center alb-right"' in render_blocks(blocks, edit=True)

    # it lands in a class attribute, so anything not on the list is dropped rather than escaped
    assert section_class({"align": 'x" onload="', "align_box": "middle"}) == ""
    assert section_class({}) == ""
    # and an alignment is layout, not words: it must not reach llms.txt, the feed or admin search
    assert blocks_text(blocks) == "Hi One x"   # the heading, not "center right"


def test_tone_is_a_whitelisted_band(app, monkeypatch):
    """The design alternates white and grey down a page, so the band is a per-section setting --
    and like align and width it is a whitelist, because it lands in a class attribute."""
    from iopstor.blocks import section_class

    assert section_class({"tone": "grey"}) == " t-grey"
    assert section_class({"tone": "dark", "align": "center"}) == " al-center t-dark"
    assert section_class({"tone": 'x" onload="'}) == ""      # not a passthrough
    assert section_class({"tone": "puce"}) == ""
    assert section_class({}) == ""
    monkeypatch.setattr("iopstor.db.settings", lambda: {})
    assert 'class="section t-grey"' in render_blocks(
        [{"type": "cards", "data": {"tone": "grey", "items": [{"title": "Hi"}]}}])


def test_section_width_is_a_named_step_or_a_plain_number(app, monkeypatch):
    """One key, two carriers: a named width is a class, an exact one is the --w custom property."""
    from iopstor import db
    from iopstor.blocks import section_class, section_style

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])

    assert section_class({"width": "wide"}) == " w-wide" and section_style({"width": "wide"}) == ""
    assert section_style({"width": 950}) == ' style="--w:950px"'
    assert section_class({"width": 950}) == ""              # a number is not a class
    # it lands in a style attribute, so only digits inside the ceiling ever get through
    for bad in ("950px", "950; background:red", "-5", "0", "9999", "", None, {}):
        assert section_style({"width": bad}) == "", bad
    assert section_style({}) == ""

    blocks = [{"type": "rich_text", "data": {"html": "<p>hi</p>", "width": 950}}]
    assert '<section class="section" style="--w:950px"' in render_blocks(blocks)
    assert '<section class="section" style="--w:950px"' in render_blocks(blocks, edit=True)
    assert 'class="section w-full"' in render_blocks([{"type": "rich_text", "data": {"html": "<p>hi</p>", "width": "full"}}])
    assert blocks_text(blocks) == "hi"                      # not "950"


def test_stylesheets_are_balanced():
    """A stray brace silently kills the rules after it, and no other test can see a stylesheet.

    One orphan `}` left by an edit to site.css took `.hero`'s padding out of the cascade while
    every rule around it kept working, so the page looked almost right and pytest was green."""
    import re
    from pathlib import Path

    for name in ("site.css", "admin.css", "canvas.css"):
        css = Path("iopstor/static", name).read_text()
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # a brace inside a comment is not a brace
        depth = 0
        for i, line in enumerate(css.split("\n"), 1):
            for ch in line:
                depth += (ch == "{") - (ch == "}")
                assert depth >= 0, f"{name}: unmatched closing brace, line {i}"
        assert depth == 0, f"{name}: {depth} unclosed block(s)"


def test_count_up_splits_a_figure():
    """The whole number a CSS counter can roll to, the digits as typed, and the rest."""
    from iopstor.blocks import count_up

    assert count_up("300+") == (300, "", "300", "+")
    assert count_up("25+ yrs") == (25, "", "25", "+ yrs")
    assert count_up("42") == (42, "", "42", "")
    # words on both sides of the number are left where they are: only the digits roll
    assert count_up("Up to 5 PB") == (5, "Up to ", "5", " PB")
    assert count_up("99.999%")[:3] == (99, "", "99")   # counters are integers: the decimals hold still
    assert count_up("24\u00d77")[0] == 24
    # nothing to count, or nothing a counter could spell the same way the editor did
    for bad in ("1,200 TB", "Always on", "0", "  ", "", None):
        assert count_up(bad) is None, bad


def test_section_effects_are_a_whitelist(app, monkeypatch):
    """fx lands in a class attribute, so it is a whitelist; count_up is a checkbox, so it cannot spell."""
    from iopstor import db
    from iopstor.blocks import EDITOR, FX, section_class

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])

    assert section_class({"fx": "rise"}) == " fx-rise"
    assert section_class({"fx": "sweep", "tone": "grey"}) == " t-grey fx-sweep"
    for bad in ("rise; }", "<script>", "RISE", "fx-rise", "", None, {}, 1):
        assert section_class({"fx": bad}) == "", bad
    # every option the editor is offered is one the whitelist accepts (blank = no effect)
    assert [v for v, _ in EDITOR["choices"]["fx"] if v] == list(FX)

    data = {**EDITOR["seed"]["stats"], "count_up": True, "fx": "rise"}
    html = render_blocks([{"type": "stats", "data": data}])
    assert 'class="section band-dark fx-rise"' in html
    assert html.count('<li class="fx-rise fx-count"') == 3      # the section's effect reaches every figure
    # the digits are really in the HTML, not only in a CSS counter: crawlers and copy-paste read them
    assert '<span class="cv">99</span><span class="cr"></span>.999%' in html and 'style="--to:99"' in html
    assert blocks_text([{"type": "stats", "data": data}]).count("rise") == 0    # fx is not words


def test_one_figure_can_differ_from_its_band(app, monkeypatch):
    """Numbers items carry their own fx/count_up; a row that sets nothing falls back to the section."""
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])

    html = render_blocks([{"type": "stats", "data": {"fx": "rise", "items": [
        {"value": "300+", "label": "customers", "fx": "gradient", "count_up": True},
        {"value": "5 PB", "label": "per rack"},                       # inherits fx-rise, does not count
        {"value": "Always on", "label": "support", "count_up": True},  # nothing to count: plain text
    ]}}])
    assert '<li class="fx-gradient fx-count"' in html and 'style="--to:300"' in html
    # only the number is swapped for a counter; the words either side stay put
    assert '>Up to <span class="cv">5</span><span class="cr"></span> PB</strong>' in render_blocks(
        [{"type": "stats", "data": {"count_up": True, "items": [{"value": "Up to 5 PB", "label": "x"}]}}])
    assert '<li class="fx-rise"><strong>5 PB</strong>' in html
    assert '<li class="fx-rise"><strong>Always on</strong>' in html
    # an item's effect is still a whitelist, the same one the section goes through
    assert "fx-" not in render_blocks([{"type": "stats", "data": {"items": [
        {"value": "1", "label": "x", "fx": "rise;}"}]}}])


def test_edit_mode_survives_a_half_finished_block(app, monkeypatch):
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    blocks = [{"type": "post_list", "data": {}}, {"type": "hero", "data": {"heading": "Still here"}}]
    html = render_blocks(blocks, edit=True)
    assert "iop-err" in html and "Still here" in html  # one bad block must not take the canvas down


def test_a_document_is_just_one_rich_text_block(app, monkeypatch):
    """Plain writing needs no new storage: prose is a rich_text block in the existing JSONB."""
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    doc = [{"type": "rich_text", "data": {"html": "<h2>Heads</h2><p>Words and <strong>bold</strong>.</p><ul><li>One</li></ul>"}}]
    assert validate_blocks(doc) == []
    assert blocks_text(doc) == "Heads Words and bold . One"  # extracts in reading order, no block juggling

    html = render_blocks(doc)
    assert "<h2>Heads</h2>" in html and "<li>One</li>" in html and "data-f=" not in html
    edit = render_blocks(doc, edit=True)
    assert 'data-f="html"' in edit and 'data-rich="1"' in edit  # the caret target the editor types into

    empty = render_blocks([{"type": "rich_text", "data": {"html": ""}}], edit=True)
    assert "Start writing" in empty  # a blank page invites you to type instead of naming a field


def _cols(*columns, **data):
    data["cols"] = list(columns)
    return {"type": "columns", "data": data}


def test_columns_nest_one_level():
    """A column holds sections; it does not hold another grid, and it never holds the page's <h1>."""
    text = {"type": "rich_text", "data": {"html": "<p>Hi</p>"}}
    assert validate_blocks([_cols([text], [{"type": "stats", "data": {"items": [{"value": "5", "label": "PB"}]}}])]) == []
    assert validate_blocks([_cols([])]) == []                       # an empty column is a spacer, not an error
    assert validate_blocks([{"type": "columns", "data": {}}]) == ["blocks[0].cols required"]
    assert validate_blocks([{"type": "columns", "data": {"cols": "nope"}}]) == ["blocks[0].cols must be a list of columns"]
    assert validate_blocks([_cols("nope")]) == ["blocks[0].cols[0] must be a list"]
    assert validate_blocks([_cols([{"type": "nope", "data": {}}])]) == ["blocks[0].cols[0][0]: unknown type 'nope'"]
    assert validate_blocks([_cols([text], [_cols([text])])]) == \
        ["blocks[0].cols[1][0]: a columns section cannot go inside a column"]
    assert validate_blocks([_cols([{"type": "hero", "data": {"heading": "Hi"}}])]) == \
        ["blocks[0].cols[0][0]: a hero section cannot go inside a column"]
    assert validate_blocks([_cols([{"type": "cta", "data": {"heading": "x"}}])]) == \
        ["blocks[0].cols[0][0].button_label required", "blocks[0].cols[0][0].button_url required"]


def test_columns_render_with_paths(app, monkeypatch):
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    blocks = [{"type": "hero", "data": {"heading": "Top"}},
              _cols([{"type": "rich_text", "data": {"html": "<p>Left</p>"}}],
                    [{"type": "rich_text", "data": {"html": "<p>Right</p>"}},
                     {"type": "testimonial", "data": {"quote": "Q", "author": "A"}}],
                    widths="50/25/25")]  # three numbers for two columns: ignored

    edit = render_blocks(blocks, edit=True)
    assert 'data-b="1"' in edit and 'data-col="0"' in edit and 'data-col="1"' in edit
    assert 'data-b="1.0.0"' in edit and 'data-b="1.1.0"' in edit and 'data-b="1.1.1"' in edit
    assert "--cols" not in edit                      # three widths for two columns is a mismatch

    public = render_blocks(blocks)
    assert "data-b=" not in public and "data-col=" not in public
    assert "Left" in public and "Right" in public

    blocks[1]["data"]["widths"] = "50/25/25"
    blocks[1]["data"]["cols"].append([])
    assert 'style="--cols:50fr 25fr 25fr"' in render_blocks(blocks)


def test_col_widths_only_takes_one_positive_number_per_column():
    three = {"cols": [[], [], []]}
    assert col_widths({**three, "widths": "50/25/25"}) == "50fr 25fr 25fr"
    assert col_widths({**three, "widths": " 50 / 25 / 25 "}) == "50fr 25fr 25fr"
    assert col_widths({**three, "widths": "1.5/1/1"}) == "1.5fr 1fr 1fr"
    for bad in ("", "50/50", "50/25/25/25", "a/b/c", "0/50/50", "-1/50/50", "inf/1/1", "1;color:red/1/1"):
        assert col_widths({**three, "widths": bad}) == "", bad


def test_at_path_resolves_a_nested_block():
    text = {"type": "rich_text", "data": {"html": "<p>Hi</p>"}}
    blocks = [{"type": "hero", "data": {"heading": "Top"}}, _cols([], [text])]
    assert at_path(blocks, "0")["type"] == "hero"
    assert at_path(blocks, "1")["type"] == "columns"
    assert at_path(blocks, "1.1.0") is text
    for bad in ("", "9", "1.1.9", "1.9.0", "0.0.0", "1.1", "-1", "1.x.0", "1.1.0.0.0"):
        assert at_path(blocks, bad) is None, bad


def test_blocks_text_reaches_into_columns_without_leaking_keys():
    txt = blocks_text([_cols([{"type": "rich_text", "data": {"html": "<p>Inside <b>a</b> column</p>"}}],
                             widths="50/50", heading="Side by side")])
    assert txt == "Side by side Inside a column"


def test_warranty_active_compares_iso_dates():
    """ISO date strings sort as dates — the whole warranty status is this one comparison."""
    from iopstor.blocks import warranty_active

    assert warranty_active({"expiry_date": "2027-03-14"}, today="2026-09-07")
    assert warranty_active({"expiry_date": "2026-09-07"}, today="2026-09-07")   # expires today = still in
    assert not warranty_active({"expiry_date": "2026-09-06"}, today="2026-09-07")
    assert not warranty_active({"expiry_date": None}, today="2026-09-07")
    assert not warranty_active({}, today="2026-09-07")


def test_warranty_check_renders_the_form_without_a_lookup(app, monkeypatch):
    """edit=True is the admin canvas: it must show the box and never touch the database."""
    from iopstor import db
    from iopstor.blocks import render_blocks

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "table", lambda *a, **k: 1 / 0)  # any query here is a bug
    with app.test_request_context("/warranty?sn=IOP-1"):
        html = render_blocks([{"type": "warranty_check", "data": {"heading": "Check your warranty"}}], edit=True)
    assert 'name="sn"' in html and "Check your warranty" in html
    assert "In warranty" not in html and "no record" not in html


def test_warranty_form_hands_back_what_was_typed_when_the_save_is_refused(app, client, monkeypatch):
    """A refused save must not cost the editor the record they just typed in."""
    import pytest

    from iopstor import admin_ui, db

    class Q:  # every query the route makes is stubbed below; this only has to chain and come back empty
        data, count = [], 0

        def __getattr__(self, _name):
            return lambda *a, **k: self

        def execute(self):
            return self

    monkeypatch.setattr(admin_ui, "current_user", lambda: {"id": "u1", "email": "e@x.com", "role": "admin"})
    monkeypatch.setattr(db, "post_types", lambda: [])
    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "table", lambda name: Q())
    monkeypatch.setattr(db, "one", lambda q: None)  # no duplicate serial
    monkeypatch.setattr(db, "paginate", lambda *a, **k: {"items": [], "total": 0})
    monkeypatch.setattr(db, "insert", lambda *a: pytest.fail("a refused save must not write"))
    monkeypatch.setattr(db, "update", lambda *a: pytest.fail("a refused save must not write"))

    with client.session_transaction() as s:
        s["csrf"] = "tok"
    typed = {"csrf": "tok", "serial": "IOP-A%1", "customer_name": "Acme & Co", "email": "ram@acme.com",
             "purchase_date": "2026-06-01", "expiry_date": "2024-06-01", "amc": "yes",
             "remarks": "PSU swapped", "remarks_public": "on"}
    r = client.post("/admin/warranty?q=iop", data=typed)
    body = r.get_data(as_text=True)

    assert r.status_code == 400
    # the message rides on the field it is about, for admin.js to hand to the browser's validation bubble
    assert 'data-refused-field="expiry_date"' in body and "cannot be before the purchase date" in body
    assert "<noscript>" in body                              # ...and is still readable without JS
    assert 'value="IOP-A%1"' in body and "Acme &amp; Co" in body and 'value="2024-06-01"' in body
    assert "PSU swapped" in body and "checked" in body        # textarea and the remarks toggle survive too
    assert "Add a warranty record" in body and 'name="id"' not in body   # a refused new record is still new

    # a refused EDIT comes back as an edit, id and all, so Save changes still targets the same record
    r = client.post("/admin/warranty", data={**typed, "id": "7"})
    body = r.get_data(as_text=True)
    assert r.status_code == 400 and 'name="id" value="7"' in body and "Save changes" in body

    # an empty purchase date leaves the expiry unconstrained: same dates, and it saves
    saved = {}
    monkeypatch.setattr(db, "insert", lambda name, r: saved.update(r) or {"id": 1})
    r = client.post("/admin/warranty", data={**typed, "purchase_date": ""})
    assert r.status_code == 302 and saved["expiry_date"] == "2024-06-01" and saved["purchase_date"] is None


def test_media_is_served_by_the_app_not_the_storage_gateway(app, client, monkeypatch):
    """Supabase is LAN-only, so every picture and PDF comes through /media/<bucket key>: Flask fetches
    the bytes server-side, caches them for a year, and turns ?download into an attachment. Only the
    extensions the uploader allows are servable, and that check happens before Storage is touched."""
    from iopstor import db, storage

    monkeypatch.setattr(db, "settings", lambda: {})          # chrome for the 404 page at the end
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(db, "post_type", lambda **kw: None)
    monkeypatch.setattr(db, "table", lambda *a, **k: 1 / 0)  # a media request must not query PostgREST
    monkeypatch.setattr(storage, "fetch", lambda key: b"\x89PNG" + key.encode())

    r = client.get("/media/2026/09/abc.png")
    assert r.status_code == 200 and r.data == b"\x89PNG2026/09/abc.png"
    assert r.mimetype == "image/png"
    assert r.cache_control.max_age == 31536000 and r.cache_control.immutable and r.cache_control.public
    assert client.get("/media/2026/09/abc.png", headers={"If-None-Match": r.headers["ETag"]}).status_code == 304

    r = client.get("/media/2026/09/a.pdf?download=flash array.pdf")
    assert r.mimetype == "application/pdf"
    assert r.headers["Content-Disposition"] == 'attachment; filename="flash array.pdf"'  # the name survives
    r = client.get("/media/2026/09/a.pdf?download=x%0d%0aX-Evil:%201")
    assert r.status_code == 200 and "X-Evil" not in r.headers                             # ...but a header cannot be split

    # an SVG can carry <script> and this origin has the admin's cookie, so it is served sandboxed
    r = client.get("/media/2026/09/logo.svg")
    assert r.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert "Content-Security-Policy" not in client.get("/media/2026/09/a.pdf").headers  # would break the viewer

    monkeypatch.setattr(storage, "fetch", lambda key: 1 / 0)  # reaching Storage for these is a bug
    assert client.get("/media/2026/09/notes.txt").status_code == 404      # not an allowed type
    assert client.get("/media/%2e%2e/%2e%2e/etc/passwd.png").status_code == 404  # nothing climbs out of the bucket


def test_media_public_address_is_one_url_whichever_shape_the_row_is_in(app, client, monkeypatch):
    """The address an editor copies out of Media has to be absolute — and has to stay one URL while
    migration 0007 is still unapplied and the rows hold the old Storage address."""
    from iopstor import admin_ui, db

    old = "http://supabase.lan/storage/v1/object/public/media/2026/09/a.png"
    rows = [{"id": 1, "key": "2026/09/a.png", "url": old, "filename": "a.png", "mime": "image/png", "alt": "", "size": 10},
            {"id": 2, "key": "2026/09/b.png", "url": "/media/2026/09/b.png", "filename": "b.png", "mime": "image/png", "alt": "", "size": 10}]

    monkeypatch.setattr(admin_ui, "current_user", lambda: {"id": "u1", "email": "e@x.com", "role": "admin"})
    monkeypatch.setattr(db, "post_types", lambda: [])
    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "admin_counts", lambda: {})
    monkeypatch.setattr(db, "paginate", lambda q, page, per: {"items": rows, "total": len(rows)})
    class Q:  # the query is built then handed straight to the stubbed paginate()
        def __getattr__(self, _name):
            return lambda *a, **k: self

    monkeypatch.setattr(db, "table", lambda *a, **k: Q())

    with client.session_transaction() as sess:
        sess["access_token"] = "t"

    body = client.get("/admin/media?pick=1").get_data(as_text=True)
    assert f'value="{old}"' in body                       # still on Storage: shown as it stands
    body = client.get("/admin/media?pick=2").get_data(as_text=True)
    assert 'value="http://test/media/2026/09/b.png"' in body   # migrated: SITE_URL in front, once


def test_display_name_falls_back_to_the_email():
    assert display_name({"name": "Sukhpreet Saluja", "email": "s@x.com"}) == "Sukhpreet Saluja"
    # users.name defaults to '' and `flask create-admin` never fills it, so the fallback is the
    # common case, not the edge one
    assert display_name({"name": "", "email": "sukhpreet.saluja@primeabgb.com"}) == "Sukhpreet Saluja"
    assert display_name({"name": "   ", "email": "jane_doe@x.com"}) == "Jane Doe"
    assert display_name({"email": "a-b@x.com"}) == "A B"


def test_password_errors():
    assert _password_errors("shortie", "shortie")[0].startswith("The new password must be")
    assert _password_errors("longenough", "longenoug")[0].startswith("The two new passwords")
    assert _password_errors("longenough", "longenough") == []
    # the admin's one-field reset has nothing to confirm against, so the second check must not fire
    assert _password_errors("longenough") == []
    assert _password_errors("short")


def test_throttle_counts_failures_per_key(app, tmp_path):
    from iopstor import throttle

    app.config.update(TESTING=False, THROTTLE_DB=str(tmp_path / "t.db"),
                      LOGIN_MAX_FAILURES=3, LOGIN_WINDOW=900)
    with app.test_request_context("/admin/login"):
        assert throttle.retry_after("ip:1.2.3.4") == 0
        for _ in range(3):
            throttle.record_failure("ip:1.2.3.4")
        wait = throttle.retry_after("ip:1.2.3.4")
        assert 0 < wait <= 900
        assert throttle.retry_after("ip:9.9.9.9") == 0    # one key's failures are not another's
        throttle.clear("ip:1.2.3.4")                       # a correct password wipes the slate
        assert throttle.retry_after("ip:1.2.3.4") == 0
        # a failure older than the window has rolled off
        app.config["LOGIN_WINDOW"] = 0
        throttle.record_failure("ip:1.2.3.4")
        assert throttle.retry_after("ip:1.2.3.4") == 0


def test_throttle_fails_open_and_reads_cloudflares_header(app):
    from iopstor import throttle

    # a counter that cannot open its file must never lock the owner out of their own site
    app.config.update(TESTING=False, THROTTLE_DB="/nonexistent-dir/t.db", LOGIN_MAX_FAILURES=1)
    with app.test_request_context("/admin/login"):
        throttle.record_failure("ip:1.2.3.4")
        assert throttle.retry_after("ip:1.2.3.4") == 0
    base = {"REMOTE_ADDR": "127.0.0.1"}
    with app.test_request_context("/admin/login", environ_base=base, headers={"CF-Connecting-IP": "9.9.9.9"}):
        assert throttle.client_ip() == "9.9.9.9"         # behind the tunnel: the header is the visitor
    with app.test_request_context("/admin/login", environ_base=base):
        assert throttle.client_ip() == "127.0.0.1"       # dev: no proxy in the way
    with app.test_request_context("/admin/login"):
        # never None: the key is built with an f-string, and None would put every such request in
        # one shared bucket under the name "None"
        assert throttle.client_ip() == "-"


def test_a_losing_token_refresh_keeps_the_winners_cookie(app, monkeypatch):
    """Two overlapping admin requests refresh the same single-use token. The loser must not clear the
    session: its Set-Cookie can land after the winner's fresh pair and sign the editor out mid-edit."""
    import time

    import jwt
    from flask import session
    from supabase_auth.errors import AuthError

    from iopstor import auth

    expired = jwt.encode({"sub": "u", "aud": "authenticated", "exp": int(time.time()) - 1},
                         app.config["SUPABASE_JWT_SECRET"], algorithm="HS256")

    def lose(_token):
        raise AuthError("Invalid Refresh Token: Already Used", None)

    monkeypatch.setattr(auth, "refresh", lose)
    with app.test_request_context("/admin/"):
        session["access_token"], session["refresh_token"] = expired, "the-winner-already-rotated-this"
        assert auth._session_token() is None
        assert session.get("refresh_token") == "the-winner-already-rotated-this"


def test_boot_refuses_without_secret_key_or_site_url(app):
    """A production env that forgets either one used to boot silently: SECRET_KEY fell back to a string
    printed in this repo (and auth.py accepts a session token as a Bearer fallback), and SITE_URL fell
    back to localhost, which both publishes localhost canonicals and computes SESSION_COOKIE_SECURE to
    False. Empty values, not missing keys: pipenv loads .env, so an omitted key inherits a real one."""
    import pytest

    from iopstor import create_app

    good = {k: app.config[k] for k in
            ("SECRET_KEY", "SITE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
             "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET")}
    good["TESTING"] = True
    create_app(dict(good))  # the control: all six present, no refusal

    for key in ("SECRET_KEY", "SITE_URL"):
        with pytest.raises(RuntimeError, match=key):
            create_app({**good, key: ""})


def test_public_pages_mint_no_session_cookie(app):
    """The CSRF token is minted by an app_context_processor, which is app-wide, not blueprint-scoped.
    Without the blueprint guard every public page answers with Set-Cookie, and no HTTP cache stores
    such a response — so the site behind the Cloudflare tunnel could never be cached at the edge."""
    from iopstor.admin_ui import _globals

    with app.test_request_context("/"):
        assert _globals() == {}                     # public: nothing minted, session untouched
    with app.test_request_context("/admin/login"):
        assert _globals()["csrf"]                   # admin: the editor still gets a token


def test_audit_records_only_the_fields_that_changed():
    """The whole audit log is this one function: what the row was, what it became, per field.
    updated_at has to stay out of it — the moddatetime trigger moves it on every single write, so
    including it would mean every entry claims a change even when nothing changed."""
    from iopstor import db

    before = {"id": 3, "title": "Old", "status": "draft", "updated_at": "2026-09-10T00:00:00Z"}
    after = {"id": 3, "title": "New", "status": "draft", "updated_at": "2026-09-11T00:00:00Z"}
    assert db._diff(before, after) == {"title": ["Old", "New"]}

    # a create is the same shape with nothing on the left, and a delete with nothing on the right,
    # which is what lets one template render all three and one Restore reverse any of them.
    assert db._diff({}, {"id": 9, "title": "New"}) == {"id": [None, 9], "title": [None, "New"]}
    assert db._diff({"id": 9, "title": "Gone"}, {}) == {"id": [9, None], "title": ["Gone", None]}
    assert db._diff({"title": "Same"}, {"title": "Same"}) == {}
    # a column that was null and stayed null is not a change worth a row
    assert db._diff({}, {"parent_id": None}) == {}


def test_restore_reverses_a_diff():
    """Restore is the left-hand half of every pair, and nothing more. It works for any table
    because the format does not vary by table."""
    changes = {"title": ["Old", "New"], "blocks": [[{"type": "text"}], []]}
    assert {k: pair[0] for k, pair in changes.items()} == {"title": "Old", "blocks": [{"type": "text"}]}


def test_audit_is_silent_on_the_command_line():
    """`flask seed` writes hundreds of rows and none of them is a person doing something. There is
    no request context there, and that one test is the whole exclusion — no flag to remember."""
    from iopstor import db

    assert db._audit("create", "posts", 1, {"title": [None, "x"]}) is None   # no request, no row, no error
    assert db.audit_event("login", "someone@example.com") is None


def test_ist_is_five_and_a_half_hours_ahead():
    """Editors are in India and every admin date used to read as unlabelled UTC, so a 9.51 am stamp
    was really 3.21 pm to the person looking at it. A fixed offset, not a named zone: India has
    never observed daylight saving, and tzdata is not in the slim container image."""
    from iopstor import db

    assert db.ist("2026-09-11T09:51:00+00:00") == "11 Sep 2026, 15:21 IST"
    assert db.ist("2026-09-11T20:00:00+00:00") == "12 Sep 2026, 01:30 IST"   # and it rolls the date
    assert db.ist(None) == "—"
    # the publish box and the list have to agree, or the editor sees two times for one instant
    assert db.ist_input("2026-09-11T09:51:00+00:00") == "2026-09-11T15:21"
    assert db.ist_input(None) == ""


def test_the_publish_box_reads_as_ist():
    """<input type="datetime-local"> posts a bare wall clock, and every parser downstream reads a
    missing offset as UTC — so 2 pm typed in Mumbai was stored as 7.30 pm. Stamped at the form, not
    in db.parse_dt(), which the JSON API shares and where no offset should still mean UTC."""
    from iopstor.admin_ui import _as_ist

    assert _as_ist("2026-09-11T14:00") == "2026-09-11T14:00+05:30"
    assert _as_ist("") == ""
    assert _as_ist("2026-09-11T14:00+05:30") == "2026-09-11T14:00+05:30"    # not stamped twice
    assert _as_ist("2026-09-11T14:00Z") == "2026-09-11T14:00Z"


def test_a_trashed_post_is_not_live():
    """Deleting a post moves it to the trash instead of removing the row, so the one thing that
    must hold is that the public site never sees it. It holds because every public read goes
    through db.live(), which asks for status='published' and nothing else."""
    from iopstor import db

    assert not db.is_live({"status": "trash", "published_at": "2020-01-01T00:00:00+00:00"})
    assert db.is_live({"status": "published", "published_at": "2020-01-01T00:00:00+00:00"})


def test_every_table_has_something_to_call_a_row():
    """The audit screen names the row a line is about. One ordered tuple stands in for a per-table
    map, so the order is the whole logic: media carries a filename and a bucket key, a user a name
    and an email, a term a name and a slug — and the first match has to be the readable one."""
    from iopstor import db

    assert db._label({"title": "About Us", "slug": "about"}) == "About Us"           # posts
    assert db._label({"filename": "hero.png", "key": "2026/09/a1b2.png"}) == "hero.png"   # media
    assert db._label({"name": "", "email": "priya@iopstor.com"}) == "priya@iopstor.com"   # users
    assert db._label({"serial": "IOP-2231"}) == "IOP-2231"                           # warranties
    assert db._label({"from_path": "/old-page"}) == "/old-page"                      # redirects
    assert db._label({"hits": 3}) == ""                                              # nothing to name


def test_only_a_change_and_a_trashed_post_can_be_put_back():
    """Restore is offered per entry, and the rule is not "anything that was a delete". A deleted
    post went to the trash and is still there; a deleted user, picture or category is really gone,
    and re-creating the row would produce something half-working — a login with no Supabase account
    behind it, a picture row pointing at a file that left the bucket."""
    from iopstor.admin_ui import _restorable

    assert _restorable({"action": "update", "table_name": "posts"})
    assert _restorable({"action": "update", "table_name": "settings"})
    assert _restorable({"action": "delete", "table_name": "posts"})       # the trash
    assert not _restorable({"action": "delete", "table_name": "users"})   # really gone
    assert not _restorable({"action": "delete", "table_name": "media"})
    assert not _restorable({"action": "create", "table_name": "posts"})   # nothing to go back to
    assert not _restorable({"action": "login_failed", "table_name": ""})


# Every route that can change something, and how the audit log catches it. The value is the reason,
# kept as prose so a reader can check the claim rather than trust the key being present.
AUDITED = {
    # content, media, leads, warranty, settings, menus, users, redirects, taxonomies:
    # the write goes through db.insert()/update()/delete()/set_*(), which record it themselves
    "admin_api.create_post": "db.insert", "admin_api.update_post": "db.update",
    "admin_api.delete_post": "db.update to trash", "admin_api.create_post_type": "db.insert",
    "admin_api.update_post_type": "db.update", "admin_api.delete_post_type": "db.delete",
    "admin_api.create_taxonomy": "db.insert", "admin_api.update_taxonomy": "db.update",
    "admin_api.delete_taxonomy": "db.delete", "admin_api.create_term": "db.insert",
    "admin_api.update_term": "db.update", "admin_api.delete_term": "db.delete",
    "admin_api.upload_media": "db.insert", "admin_api.update_media": "db.update",
    "admin_api.remove_media": "db.delete", "admin_api.update_lead": "db.update",
    "admin_api.delete_lead": "db.delete", "admin_api.put_settings": "db.set_settings",
    "admin_api.put_menu": "db.set_menu", "admin_api.create_redirect": "db.insert",
    "admin_api.delete_redirect": "db.delete", "admin_api.create_user": "db.insert",
    "admin_api.update_user": "db.update", "admin_api.delete_user": "db.delete",
    "admin_ui.new_post": "db.insert", "admin_ui.edit_post": "db.update",
    "admin_ui.delete_post": "db.update to trash", "admin_ui.restore_post": "db.update",
    "admin_ui.media": "db.insert", "admin_ui.media_upload": "db.insert",
    "admin_ui.media_alt": "db.update", "admin_ui.media_delete": "db.delete",
    "admin_ui.lead_status": "db.update", "admin_ui.warranty": "db.insert/update",
    "admin_ui.warranty_delete": "db.delete", "admin_ui.menus": "db.set_menu",
    "admin_ui.settings": "db.set_settings", "admin_ui.users": "db.insert",
    "admin_ui.user_delete": "db.delete", "admin_ui.audit_restore": "the helper it writes through",
    "public_api.api_create_lead": "db.insert, with no signed-in user",
    "public_api.api_checkout": "db.insert", "public_api.api_webhook": "db.update",
    # no row of ours changes, so db.py cannot see it: an explicit db.audit_event()
    "admin_ui.login_page": "audit_event login / login_failed / login_blocked",
    "admin_ui.account": "audit_event password_changed / login_failed / login_blocked",
    "admin_ui.user_password": "audit_event password_reset",
    "admin_api.auth_login": "audit_event login / login_failed / login_blocked",
    "admin_api.auth_logout": "audit_event logout",
    # deliberately not recorded -- see TECHNICAL.md §8
    "admin_ui.canvas": "changes nothing, renders the page into the editor",
    "admin_ui.preview": "changes nothing, renders the unsaved form as a page",
    "admin_api.auth_refresh": "session mechanics, not a step anybody takes",
}


def test_every_route_that_can_change_something_is_accounted_for(app):
    """The password change went unlogged because nothing checked. This is that check: add a route
    that accepts a POST and the suite fails until somebody writes down how it is recorded — or that
    it deliberately is not. It cannot prove a row lands, only that the decision was made."""
    changing = {r.endpoint for r in app.url_map.iter_rules()
                if r.methods & {"POST", "PATCH", "PUT", "DELETE"}}
    assert changing - set(AUDITED) == set(), "a route that can change something, with nobody having decided whether it is logged"
    assert set(AUDITED) - changing == set(), "a route named here no longer exists"


def test_a_lockout_is_recorded_once_not_on_every_blocked_attempt(app, tmp_path):
    """retry_after() says "wait" on every attempt for the whole window, so logging from there would
    let anyone hammering a locked login write a row per request straight into the audit log. The
    entry belongs at the crossing, which is the only thing record_failure() reports True for."""
    from iopstor import throttle

    app.config.update(TESTING=False, THROTTLE_DB=str(tmp_path / "t.db"),
                      LOGIN_MAX_FAILURES=3, LOGIN_WINDOW=900)
    with app.test_request_context("/admin/login"):
        crossings = [throttle.record_failure("ip:1.2.3.4") for _ in range(6)]
    assert crossings == [False, False, True, False, False, False], crossings


def test_the_words_that_changed_are_marked_not_the_json():
    """The complaint that started this: a one-word edit rendered as two blocks of JSON. The screen
    shows the writing, with what went struck out and what arrived marked."""
    from iopstor.admin_ui import _word_diff

    was, now = _word_diff("Always Believe in Better", "Always Believe in Getting Better.")
    assert was == "Always Believe in <del>Better</del>"
    assert now == "Always Believe in <ins>Getting Better.</ins>"
    assert _word_diff("same words", "same words") == ("same words", "same words")
    # and it escapes: a page saying <script> is text, not markup
    assert "&lt;script&gt;" in _word_diff("<script>", "")[0]


def _fields(was, now):
    """The audit screen's rows for a blocks change, as (label, note, was, now) tuples of plain str."""
    from iopstor.admin_ui import _blocks_fields

    return [(r["label"], r["note"], str(r["was"]), str(r["now"])) for r in _blocks_fields(was, now)]


def _stats(*fx):
    return [{"type": "stats", "data": {"heading": "By the numbers",
                                       "items": [{"value": f"{i}", "label": "x", "fx": f} for i, f in enumerate(fx)]}}]


def test_a_page_edit_says_which_section_and_which_setting_changed(app):
    """The complaint that started this: a page edit rendered as two identical ninety-line walls of
    text. This is the real entry behind that screenshot -- the effect on two rows of a Numbers
    section -- and the whole detail it should produce is two lines naming the row and the setting."""
    assert _fields(_stats("", "", ""), _stats("", "gradient", "sweep")) == [
        ("Numbers section, row 2 \u2014 Effect", "", "None", "Gradient across the big text"),
        ("Numbers section, row 3 \u2014 Effect", "", "None", "Highlighter sweep behind the headings")]


def test_one_section_changed_is_one_section_diffed(app):
    """The words that moved, under the name of the section they moved in -- not the whole page."""
    page = [{"type": "hero", "data": {"heading": "Always Believe in Better"}},
            {"type": "rich_text", "data": {"html": "<p>A paragraph nobody touched.</p>"}}]
    changed = deepcopy(page)
    changed[0]["data"]["heading"] = "Always Believe in Getting Better."
    rows = _fields(page, changed)
    assert len(rows) == 1
    assert rows[0][0] == "Hero section"
    assert rows[0][2] == "Always Believe in <del>Better</del>"
    assert rows[0][3] == "Always Believe in <ins>Getting Better.</ins>"
    assert "paragraph nobody touched" not in rows[0][2]


def test_the_two_diffs_do_not_report_the_same_change_twice(app):
    """blocks_text() collects a value only when the key is outside _NON_TEXT_KEYS *and* the value is
    a string, so that is the line between the words diff and the settings diff. Both halves matter:
    a checkbox is a bool and is in nobody's text, whichever set its key is in."""
    from iopstor.admin_ui import _unwritten

    assert _unwritten("media_id", 4) and _unwritten("fx", "rise")       # in the set
    assert _unwritten("count_up", True) and _unwritten("limit", 6)      # not a string
    assert not _unwritten("heading", "Storage")                         # the words already show it

    # a repeater of plain strings is the case most likely to be reported twice: it must not be
    rows = _fields([{"type": "spec_table", "data": {"rows": [{"k": "Capacity", "v": "10 TB"}]}}],
                   [{"type": "spec_table", "data": {"rows": [{"k": "Capacity", "v": "20 TB"}]}}])
    assert rows == [("Specification table section", "", "Capacity <del>10</del> TB", "Capacity <ins>20</ins> TB")]

    # and a checkbox inside one is reported, because nothing else can show it
    assert _fields(_stats(""), [{"type": "stats", "data": {"heading": "By the numbers",
                                                           "items": [{"value": "0", "label": "x", "fx": "",
                                                                      "count_up": True}]}}]) == \
        [("Numbers section, row 1 \u2014 Count up from zero", "", "No", "Yes")]


def test_a_change_the_words_cannot_show_is_described_instead(app):
    """Adding, removing or moving a section breaks the one-for-one comparison -- position 3 stops
    meaning the same thing on both sides -- so the shape gets a sentence and the words get one
    page-wide diff. And a save that only bolded a phrase says so, rather than claiming nothing
    happened: blocks_text() strips the tags, so both sides read identically."""
    text = [{"type": "rich_text", "data": {"html": "<p>Hello</p>"}}]
    label, note, was, now = _fields(text, text + [{"type": "cards", "data": {}}])[0]
    assert (label, note) == ("The writing on the page", "Added Cards.")
    assert was == now == ""                        # nothing to put in a Was/Now grid
    assert _fields(text + [{"type": "cards", "data": {}}], text)[0][1] == "Removed Cards."
    assert _fields([{"type": "hero", "data": {}}, {"type": "cards", "data": {}}],
                   [{"type": "cards", "data": {}}, {"type": "hero", "data": {}}])[0][1] == "Moved the sections around."
    plain = [{"type": "rich_text", "data": {"html": "<p>Hello there</p>"}}]
    assert _fields(plain, [{"type": "rich_text", "data": {"html": "<p>Hello <b>there</b></p>"}}]) == \
        [("Rich text section", "Formatting changed \u2014 bold, a link or a heading.", "", "")]


def test_a_section_inside_a_column_names_its_column(app):
    """A column holds sections, and they drift out of line the way a page's do. Same types: compare
    them one for one and say which column. Different types: a sentence, because position 2 in a
    column of three is not position 2 in a column of four."""
    def cols(inner):
        return [{"type": "columns", "data": {"cols": inner, "heading": "Side by side"}}]

    left, right = [{"type": "rich_text", "data": {"html": "<p>Left</p>"}}], [{"type": "image", "data": {"media_id": 1}}]
    rows = _fields(cols([left, right]), cols([[{"type": "rich_text", "data": {"html": "<p>Left side</p>"}}], right]))
    # one row, from inside the column -- the outer section must not diff its children a second time
    assert rows == [("Column 1, Rich text section", "", "Left", "Left <ins>side</ins>")]
    assert _fields(cols([left]), cols([left + [{"type": "image", "data": {"media_id": 2}}]])) == \
        [("Columns section, column 1", "Added Picture.", "", "")]


def test_a_long_unchanged_stretch_collapses_to_its_ends(app):
    """Per-section diffing bounds the common case; one rich text block can still hold a whole page,
    and a mark buried in two hundred unchanged words is a mark nobody finds."""
    from iopstor.admin_ui import _word_diff

    words = " ".join(f"w{i}" for i in range(40))
    was, now = _word_diff(f"{words} old", f"{words} new")
    assert "<del>old</del>" in was and "<ins>new</ins>" in now
    assert "w0 w1 w2 w3 w4 w5 w6 w7" in was and "w32 w33" in was
    assert "w20" not in was and 'class="aud-gap"' in was


def test_the_rows_own_id_is_not_shown_as_a_field(app):
    """Creating a person records `id`, and it is the GoTrue uuid the entry is already about. Printed
    as a field it is a 36-character string an editor cannot use, under a heading reading "Id"."""
    from iopstor.admin_ui import _present

    uid = "7867beee-5f1b-4591-a58e-52f849ba17ef"
    entry = {"action": "create", "table_name": "users", "row_id": uid, "label": "Test Account",
             "user_id": None, "user_email": None, "changes": {"id": [None, uid], "name": [None, "Test Account"]}}
    assert [f["label"] for f in _present(entry, {}, {})["fields"]] == ["Name"]


def test_a_column_name_never_reaches_the_screen():
    """Every field an editor can see has a label; anything unmapped still reads as words rather than
    as a column, using the same transform the Settings screen uses so the two agree."""
    from iopstor.admin_ui import _label_of

    assert _label_of("blocks") == "The writing on the page"
    assert _label_of("featured_media_id") == "Main picture"
    assert _label_of("remarks_public") == "Show the remarks to the customer"
    assert _label_of("some_future_column") == "Some future column"


def test_a_stored_value_is_shown_as_something_a_person_reads():
    """Never the word "trash", never a bare timestamp, never a raw true."""
    from iopstor.admin_ui import _value

    assert _value("status", "trash") == "Deleted"
    assert _value("status", "published") == "Published"
    assert _value("status", "in_progress") == "In progress"   # leads share the column, and the word
    assert _value("amc", True) == "Yes"
    assert _value("amc", False) == "No"
    assert _value("expiry_date", "2027-03-14T00:00:00+00:00") == "14 Mar 2027, 05:30 IST"
    assert _value("title", "") == '<span class="muted">nothing</span>'
    assert _value("published_at", "not a date at all") == "not a date at all"   # falls through, does not raise
    assert _value("items", [{"label": "Home"}, {"label": "About"}]) == "Home, About"


def test_every_row_reads_as_a_sentence():
    """A page, a service and a datasheet are all rows of `posts`; the screen has to name each one the
    way the editor's own sidebar does, or the log looks like it is missing what it is in fact showing."""
    from iopstor.admin_ui import _sentence

    posts = {"12": ("service", {}), "13": ("datasheet", {})}
    assert _sentence({"action": "update", "table_name": "posts", "label": "Managed Storage", "row_id": "12"},
                     posts) == "edited the service <b>Managed Storage</b>"
    assert _sentence({"action": "delete", "table_name": "posts", "label": "Old sheet", "row_id": "13"},
                     posts) == "deleted the datasheet <b>Old sheet</b>"
    assert _sentence({"action": "update", "table_name": "settings", "label": "contact_phone", "row_id": "contact_phone"},
                     {}) == "edited the setting <b>Contact phone</b>"
    assert _sentence({"action": "create", "table_name": "media", "label": "hero.png", "row_id": "4"},
                     {}) == "added the picture or file <b>hero.png</b>"
    assert _sentence({"action": "password_reset", "table_name": "", "label": "priya@x.com", "row_id": ""},
                     {}) == "set a new password for <b>priya@x.com</b>"
    # an unknown post type still reads, and an unknown action still reads
    assert "page or post" in _sentence({"action": "update", "table_name": "posts", "label": "X", "row_id": "99"}, {})
    assert "wibbled" in _sentence({"action": "wibbled", "table_name": "leads", "label": "X", "row_id": "1"}, {})


def test_the_test_suite_never_writes_to_the_audit_log(app, monkeypatch):
    """audit_log is append-only by trigger, and the live suite runs against the real Supabase — so
    without this guard every run left zz-test rows in the client's Activity screen that the cleanup
    fixture is forbidden to remove. throttle._off() sits out of TESTING for the same reason.
    migrations/purge_test_audit_rows.sql clears up after the runs that happened before this."""
    from iopstor import db

    touched = []
    monkeypatch.setattr(db, "table", lambda name: touched.append(name) or _NeverExecutes())
    with app.test_request_context("/admin/posts"):
        app.config["TESTING"] = True
        db._audit("create", "posts", 1, {"title": [None, "zz-test"]}, user={"id": "u", "email": "e"})
        assert touched == []            # nothing reached for a table at all

    # and the guard is the TESTING flag, not the lack of a database: with it off it does try
    with app.test_request_context("/admin/posts"):
        app.config["TESTING"] = False
        db._audit("create", "posts", 1, {"title": [None, "x"]}, user={"id": "u", "email": "e"})
    assert touched == ["audit_log"], touched


class _NeverExecutes:
    """A PostgREST query builder that records the attempt and refuses to make it. _audit() swallows
    everything, so the failure has to be visible in what was reached for, not in an exception."""

    def insert(self, *a, **k):
        return self

    def execute(self):
        raise AssertionError("the test suite must not write to audit_log")


class _UpdateRecorder:
    """Enough of a PostgREST builder to see which filters an UPDATE actually carried."""

    def __init__(self, rows):
        self.rows, self.filters, self.changes = rows, [], None

    def update(self, changes):
        self.changes = changes
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data=self.rows)


def test_a_save_that_lost_the_race_writes_nothing_and_logs_nothing(monkeypatch):
    """The conflict check has to be a filter on the UPDATE, never a comparison in Python: ~30 gunicorn
    workers share no memory, so two saves can pass a Python compare a millisecond apart and both
    write. This is the test that fails if somebody later "simplifies" the guard back into a compare."""
    from unittest.mock import MagicMock

    from iopstor import db

    audit = MagicMock()
    monkeypatch.setattr(db, "_audit", audit)
    stamp = "2026-09-12T10:33:21.123456+00:00"

    lost = _UpdateRecorder(rows=[])                      # PostgREST matched no row: somebody got there first
    monkeypatch.setattr(db, "table", lambda name: lost)
    assert db.update("posts", 7, {"title": "mine"}, if_unchanged=stamp) is None
    assert ("id", 7) in lost.filters and ("updated_at", stamp) in lost.filters
    # not "the audit recorder is empty" -- _audit returns early under TESTING anyway, so the claim
    # worth pinning is that `if after:` never reached it at all.
    audit.assert_not_called()

    won = _UpdateRecorder(rows=[{"id": 7, "title": "mine"}])
    monkeypatch.setattr(db, "table", lambda name: won)
    assert db.update("posts", 7, {"title": "mine"}, if_unchanged=stamp) == {"id": 7, "title": "mine"}
    assert audit.call_count == 1

    plain = _UpdateRecorder(rows=[{"id": 7}])            # no token: exactly the filter it always had
    monkeypatch.setattr(db, "table", lambda name: plain)
    db.update("posts", 7, {"title": "mine"})
    assert plain.filters == [("id", 7)]


def test_the_timestamp_survives_the_query_string():
    """PostgREST hands back "+00:00" and the guard puts it straight back into a query string, where a
    bare "+" decodes as a space -- which would match nothing and make every single save look like a
    conflict. ponytail: reaches into postgrest's request object, the only place the encoding is
    visible without a network."""
    from postgrest import SyncPostgrestClient

    stamp = "2026-09-12T10:33:21.123456+00:00"
    q = SyncPostgrestClient("http://x", headers={}).table("posts").update({"title": "x"}).eq("id", 1).eq("updated_at", stamp)
    assert "%2B00%3A00" in str(q.request.params), str(q.request.params)
