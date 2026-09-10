"""Pure logic — no Supabase needed."""
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
