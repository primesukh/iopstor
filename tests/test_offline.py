"""Pure logic — no Supabase needed."""
import io
import ipaddress
import json
import pathlib
import re
import shutil
import subprocess
from copy import deepcopy

import pytest

from iopstor import blocks
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


def test_even_rows_pick_a_count_that_divides_or_comes_closest():
    """"Items per row -> Even rows" is the fix for a logo strip whose last line was half empty:
    fourteen partners laid out 8 + 6. Nothing here touches the database."""
    from iopstor.blocks import _cols, even_cols

    assert even_cols(14) == 7          # the case that started it: 7 + 7, not 8 + 6
    assert even_cols(16) == 8          # exact divisor, and the LARGEST one -- not 4 + 4 + 4 + 4
    assert even_cols(20) == 5          # 5 divides, 8 would leave 8 + 8 + 4
    assert even_cols(13) == 7          # prime: no exact split, so the fullest last row wins (7 + 6)
    assert even_cols(6) == 6           # fewer than a row holds is one row of itself
    assert even_cols(0) is None        # nothing to lay out -> no class at all
    for n in range(9, 60):             # it always picks the emptiest-last-row count 4..8 allows,
        c = even_cols(n)               # which for 22 is 8 (8+8+6) -- no count in range does better
        assert (-n % c) == min(-n % k for k in range(4, 9)), (n, c)

    # the editor's value is parsed, never trusted: it lands in a class name
    assert _cols({"per_row": "even"}, 14) == 7
    assert _cols({"per_row": "5"}, 14) == 5
    assert _cols({}, 14) is None                      # unset -> the width decides, as before
    assert _cols({"per_row": "99"}, 14) is None       # out of the 2..8 range the CSS defines
    assert _cols({"per_row": "1; }"}, 14) is None     # anything typed is simply not a count


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

    # A path the app owns is worse than no path: the page cannot load at all (Flask matches the admin
    # blueprint first), and publishing its address tells every crawler where the CMS is.
    def page(slug):
        return with_paths([{**row(True), "slug": slug,
                            "post_type": {"slug": "page", "url_prefix": "", "hierarchical": False,
                                          "has_pages": True}}])[0]
    assert page("admin")["path"] == "/admin" and not _indexable(page("admin"))
    assert not _indexable(page("api")) and not _indexable(page("media"))
    assert _indexable(page("administration"))                   # a near miss is an ordinary page

    # noindex is a free-text box whose own hint reads "e.g. noindex,follow", so it has to be read as a
    # list of tokens. startswith() passed both of the spellings below while rendering a noindex page.
    for spelling in ("noindex", "noindex,follow", "NOINDEX", "nofollow,noindex", " noindex , follow "):
        assert not _indexable({**linked, "seo": {"robots": spelling}}), spelling
    for ok in ("", "index,follow", "nofollow", "noindexing"):
        assert _indexable({**linked, "seo": {"robots": ok}}), ok
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


def test_migrations_run_once_per_deploy_not_once_per_container():
    """Migrate is the compose stack's one-shot service, not the app's CMD. Put it back in CMD and every
    crash restart re-runs it; drop the gate and a deploy serves new code against an old schema. Both
    halves break silently, and only in production, which is the one place nothing here can be tried."""
    root = pathlib.Path(__file__).resolve().parent.parent
    cmd = [ln for ln in (root / "Dockerfile").read_text().splitlines() if ln.startswith("CMD")]
    assert len(cmd) == 1 and "migrate" not in cmd[0], cmd     # the CMD line only; comments stay free
    compose = (root / "docker-compose.yml").read_text()
    assert "command: flask migrate" in compose
    assert "condition: service_completed_successfully" in compose


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


def test_a_public_lead_cannot_store_more_than_it_is_allowed_to(app, client, monkeypatch):
    """The contact form is open to the internet and every accepted lead is stored twice -- the row,
    and the whole row again in audit_log, which is append-only with no retention job. So every field
    is capped, including the ones the endpoint does not know by name and keeps in `data`. The
    honeypot is the other half: a filled `website` is thanked and dropped without a write."""
    from iopstor import db

    saved = {}
    monkeypatch.setattr(db, "insert", lambda name, row: saved.update(row) or {"id": 1})

    r = client.post("/api/v1/leads", json={"name": "a", "email": "a@b.c", "message": "x" * 100_000,
                                           "junk": "y" * 5_000, **{f"pad{i}": "z" for i in range(60)}})
    assert r.status_code == 201
    assert len(saved["message"]) == 5_000
    assert len(saved["data"]["junk"]) == 200
    assert len(saved["data"]) == 20 and "junk" in saved["data"]   # 61 extra keys in, 20 stored

    monkeypatch.setattr(db, "insert", lambda *a: pytest.fail("a filled honeypot must not write"))
    assert client.post("/api/v1/leads", json={"name": "Bot", "email": "b@c.d", "website": "spam"}).status_code == 201


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


def _media_screen(monkeypatch, client, rows):
    """Everything /admin/media touches outside the route itself: a signed-in admin, the caches the
    sidebar reads, and a query object that is built and handed straight to the stubbed paginate()."""
    from iopstor import admin_ui, db

    monkeypatch.setattr(admin_ui, "current_user", lambda: {"id": "u1", "email": "e@x.com", "role": "admin"})
    monkeypatch.setattr(db, "post_types", lambda: [])
    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "admin_counts", lambda: {})
    monkeypatch.setattr(db, "paginate", lambda q, page, per: {"items": rows, "total": len(rows)})
    asked = {}

    class Q:
        def __getattr__(self, name):
            def call(*a, **k):
                if name == "in_":
                    asked[a[0]] = a[1]
                return self
            return call

    monkeypatch.setattr(db, "table", lambda *a, **k: Q())
    with client.session_transaction() as sess:
        sess["access_token"] = "t"
        sess["csrf"] = "x"
    return asked


def test_a_rejected_file_in_a_batch_does_not_cost_the_editor_the_good_ones(app, client, monkeypatch):
    """Several files now arrive in one request, so a bad type in the middle has to leave the rest
    uploaded and name the one that failed -- failing the whole batch would punish the wrong files."""
    from iopstor import admin_ui
    from werkzeug.exceptions import BadRequest

    tried = []

    def fake_save(fs, user_id=None):
        tried.append(fs.filename)
        if fs.filename.endswith(".txt"):
            raise BadRequest("file type not allowed")
        return {"id": len(tried), "filename": fs.filename, "alt": ""}

    monkeypatch.setattr(admin_ui, "save_upload", fake_save)
    _media_screen(monkeypatch, client, [])

    body = client.post("/admin/media", data={
        "csrf": "x",
        "file": [(io.BytesIO(b"a"), "a.png"), (io.BytesIO(b"n"), "notes.txt"), (io.BytesIO(b"b"), "b.png")],
    }, content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)

    assert tried == ["a.png", "notes.txt", "b.png"]   # the reject did not stop the one behind it
    assert "Uploaded 2 files." in body
    assert "notes.txt" in body and "file type not allowed" in body
    assert "a.png" not in body                        # a success is a count, not a list to read


def test_the_file_the_panel_is_showing_arrives_already_selected(app, client, monkeypatch):
    """Clicking a tile is a link to ?pick=, and clicking a tile has to *select* it -- so the server
    ticks that one box. This is also what makes a plain click clear the rest of a selection, and what
    gives initMediaBulk() an anchor to shift-click from with JavaScript off or before it runs."""
    rows = [{"id": n, "key": f"2026/09/{n}.png", "url": f"/media/2026/09/{n}.png",
             "filename": f"{n}.png", "mime": "image/png", "alt": "", "size": 10} for n in (1, 2, 3)]
    _media_screen(monkeypatch, client, rows)

    body = client.get("/admin/media?pick=2").get_data(as_text=True)
    assert 'value="2" aria-label="Select 2.png" checked' in body
    assert 'value="1" aria-label="Select 1.png">' in body      # the others are left alone
    assert body.count(" checked") == 1


def test_the_grid_selection_leaves_a_plain_click_alone():
    """initMediaBulk() only exists for the two modifier clicks. A plain click has to stay a link --
    that is the whole no-JavaScript path (the server answers ?pick= with the panel and a ticked box),
    and swallowing it would leave an editor with no way to reach a file's alt text. Both modifier
    branches must call preventDefault, or the page navigates away from the selection just made.
    Measured in Firefox against this file: 8/8, including that a plain click is not intercepted."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    fn = js[js.index("function initMediaBulk("):js.index("document.addEventListener(\"DOMContentLoaded\"")]
    assert 'document.querySelector(".tiles-m")' in fn and "if (!grid) return;" in fn
    assert fn.count("e.preventDefault();") == 2             # the shift branch and the ctrl branch, and no more
    assert "e.ctrlKey || e.metaKey" in fn                    # a Mac selects with cmd, not ctrl
    # the plain branch moves the anchor and nothing else -- no preventDefault after the last else
    plain = fn[fn.rindex("} else {"):]
    assert "preventDefault" not in plain and "last = at;" in plain
    # a <label> round the box would forward a second click and toggle every ctrl-click back again
    assert ".m-pick input" not in fn and 'tile.querySelector(".m-pick")' in fn
    assert "initMediaBulk();" in js                          # actually wired into DOMContentLoaded


def test_media_delete_takes_the_ticked_files_and_nothing_else(app, client, monkeypatch):
    """One route serves both Delete buttons -- the panel's single id and the grid's tick boxes. An id
    that is not a number can only come from an edited form, so it is dropped before the query."""
    from iopstor import admin_ui, db

    rows = [{"id": n, "key": f"2026/09/{n}.png", "url": f"/media/2026/09/{n}.png",
             "filename": f"{n}.png", "mime": "image/png", "alt": "", "size": 10} for n in (1, 2, 3)]
    gone = []
    monkeypatch.setattr(admin_ui, "delete_media", lambda m: gone.append(m["id"]))
    asked = _media_screen(monkeypatch, client, rows)
    monkeypatch.setattr(db, "rows", lambda q: [r for r in rows if r["id"] in asked.get("id", [])])

    body = client.post("/admin/media/delete", data={"csrf": "x", "ids": ["1", "3", "oops"]},
                       follow_redirects=True).get_data(as_text=True)
    assert asked["id"] == [1, 3]      # 'oops' never reached the query
    assert gone == [1, 3]
    assert "Deleted 2 files." in body

    gone.clear()
    body = client.post("/admin/media/delete", data={"csrf": "x"}, follow_redirects=True).get_data(as_text=True)
    assert gone == [] and "Tick the files you want to delete first." in body


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


def test_the_admin_does_not_exist_outside_the_office(app):
    """The door in front of the password: /admin and /api/admin/v1 answer 404 from anywhere that is not
    in ADMIN_NETWORKS, including the login form, which is the one route that takes a password."""
    app.config["TESTING"] = False        # the throttle stays out of TESTING; this guard never does
    app.config["ADMIN_NETWORKS"] = (ipaddress.ip_network("192.168.0.0/16"),)
    app.config["TRUSTED_PROXIES"] = (ipaddress.ip_network("10.0.1.0/24"),)   # Traefik, as deployed
    c = app.test_client()

    def get(path, peer, **headers):
        return c.get(path, environ_base={"REMOTE_ADDR": peer},
                     headers={k.replace("_", "-"): v for k, v in headers.items()})

    # from the office, through Traefik: the login form is served
    assert get("/admin/login", "10.0.1.7", X_Forwarded_For="192.168.5.20").status_code == 200
    # from anywhere else, through the same Traefik: nothing is here -- not even a refusal that admits it
    assert get("/admin/login", "10.0.1.7", X_Forwarded_For="203.0.113.9").status_code == 404
    assert get("/admin/", "10.0.1.7", X_Forwarded_For="203.0.113.9").status_code == 404
    # the JSON API is the same power as the screens, so it is behind the same door
    assert get("/api/admin/v1/posts", "10.0.1.7", X_Forwarded_For="203.0.113.9").status_code == 404
    # ... and through the tunnel, where the visitor's address is a public one Cloudflare vouched for
    app.config["TRUSTED_PROXIES"] = (ipaddress.ip_network("172.18.0.0/16"),)
    assert get("/admin/login", "172.18.0.4", CF_Connecting_IP="203.0.113.9").status_code == 404

    # the public site is untouched by any of it -- that is the whole point of the split
    assert get("/sitemap.xml", "10.0.1.7", X_Forwarded_For="203.0.113.9").status_code == 200

    # and an empty ADMIN_NETWORKS is no restriction at all: development, and any deploy that has not set it
    app.config["ADMIN_NETWORKS"] = ()
    assert get("/admin/login", "10.0.1.7", X_Forwarded_For="203.0.113.9").status_code == 200


def test_throttle_fails_open_and_believes_only_a_proxy_we_named(app):
    from iopstor import throttle

    # a counter that cannot open its file must never lock the owner out of their own site
    app.config.update(TESTING=False, THROTTLE_DB="/nonexistent-dir/t.db", LOGIN_MAX_FAILURES=1)
    with app.test_request_context("/admin/login"):
        throttle.record_failure("ip:1.2.3.4")
        assert throttle.retry_after("ip:1.2.3.4") == 0

    def seen(peer, **headers):
        with app.test_request_context("/admin/login", environ_base={"REMOTE_ADDR": peer} if peer else {},
                                      headers={k.replace("_", "-"): v for k, v in headers.items()}):
            return throttle.client_ip()

    assert seen("127.0.0.1", CF_Connecting_IP="9.9.9.9") == "9.9.9.9"   # the tunnel: the header is the visitor
    assert seen("127.0.0.1") == "127.0.0.1"                             # dev: no proxy in the way
    # never None: the key is built with an f-string, and None would put every such request in one
    # shared bucket under the name "None"
    assert seen(None) == "-"

    # a proxy on a network we named may say who the visitor is; X-Forwarded-For is read from the RIGHT,
    # because a proxy appends the peer it saw and everything to its left came from the client
    assert seen("10.0.1.7", X_Forwarded_For="203.0.113.9") == "203.0.113.9"
    assert seen("10.0.1.7", X_Forwarded_For="1.2.3.4, 203.0.113.9") == "203.0.113.9"
    assert seen("10.0.1.7", X_Real_IP="203.0.113.9") == "203.0.113.9"
    assert seen("10.0.1.7", CF_Connecting_IP="9.9.9.9", X_Forwarded_For="203.0.113.9") == "9.9.9.9"

    # and anybody else is taken at face value: a visitor cannot hand the throttle or the activity log
    # an address that is not theirs, whichever header they try it with
    assert seen("203.0.113.5", CF_Connecting_IP="1.2.3.4") == "203.0.113.5"
    assert seen("203.0.113.5", X_Forwarded_For="1.2.3.4") == "203.0.113.5"
    app.config["TRUSTED_PROXIES"] = (ipaddress.ip_network("172.18.0.0/16"),)
    assert seen("10.0.1.7", CF_Connecting_IP="1.2.3.4") == "10.0.1.7"    # narrowed: the LAN is not a proxy
    assert seen("172.18.0.4", CF_Connecting_IP="1.2.3.4") == "1.2.3.4"


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
    "admin_ui.discard_draft": "audit_event discard -- no row of ours moves, but throwing work away is an act",
    "public_api.api_create_lead": "db.insert, with no signed-in user",
    "public_api.api_checkout": "db.insert", "public_api.api_webhook": "db.update",
    # no row of ours changes, so db.py cannot see it: an explicit db.audit_event()
    "admin_ui.login_page": "audit_event login / login_failed / login_blocked",
    "admin_ui.account": "audit_event password_changed / login_failed / login_blocked",
    "admin_ui.user_password": "audit_event password_reset",
    "admin_api.auth_login": "audit_event login / login_failed / login_blocked",
    "admin_api.auth_logout": "audit_event logout",
    # deliberately not recorded -- see TECHNICAL.md §8
    # The autosave is the one write in the app that is not logged, and the reason is a ceiling:
    # audit_log has no retention job and _diff() stores the whole blocks array on BOTH sides of
    # every row, so a row every second or two per editor would grow without bound. Note it is not
    # a route that writes nothing to the log -- it closes editing sessions that have gone quiet,
    # and each of those IS an audit row, attributed to the editor who made the changes.
    "admin_ui.autosave": "the draft write is not logged (unbounded); the sessions it flushes are",
    "admin_ui.realtime_longpoll": "a transport, not a write: it proxies the editor's channel to Realtime",
    "admin_ui.canvas": "changes nothing, renders the page into the editor",
    "admin_ui.preview": "changes nothing, renders the unsaved form as a page",
    "admin_api.auth_refresh": "session mechanics, not a step anybody takes",
    # the stress-test panel fires HTTP at a target but writes no row of ours: attackers are
    # non-destructive and the honeypot lead post is accepted and dropped, so nothing to record here
    "admin_ui.stress_run": "starts a load run; changes no data of ours (see iopstor/stress.py)",
    "admin_ui.stress_stop": "flips a stop flag in the /dev/shm progress store, no row of ours",
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


def test_the_editor_page_carries_a_room_but_never_a_token(app):
    """The channel comes back through this app now, so there is no browser-facing Supabase origin to
    send and no switch to turn off: the one remaining off state is a post with no id, which has
    nothing to collaborate under. The token is the thing that must never reach the page -- the anon
    key is meant to be public, the GoTrue session token is not."""
    from flask import g

    from iopstor import admin_ui

    with app.test_request_context("/admin/posts/7"):
        g.user = {"id": "8f14e45f-ceea-467a-9b4e-4c9d3c8b2a11", "email": "zz@zz-test.local", "name": "", "role": "admin"}
        rt = admin_ui._rt(7)
        assert rt["room"] == "post:7"
        assert rt["me"]["name"] == "Zz"              # display_name() falls back to the email's local part
        assert "url" not in rt, "the browser builds its own origin from location.origin"
        assert "token" not in json.dumps(rt), "the access token must never be rendered into the page"
        # a post with no id yet has nothing to collaborate under, so there is no room to join
        assert admin_ui._rt(None)["room"] == ""


def test_the_realtime_proxy_refuses_without_a_session_or_the_csrf(app, monkeypatch):
    """It cannot use ui_required: that reads csrf out of request.form, and a Phoenix POST is a JSON
    body with no form field, so every send would 400. It also redirects when signed out, and a
    transport handed 200 HTML cannot tell that from a reply. 403 is the one status Phoenix's LongPoll
    client reads as "stop", so both refusals have to be that and not a redirect."""
    from iopstor import admin_ui

    c = app.test_client()
    r = c.get("/admin/realtime/v1/longpoll?vsn=2.0.0")
    assert r.status_code == 403, "signed out must be a refusal, not a redirect to the login page"
    assert r.headers["Cache-Control"] == "no-store"

    with c.session_transaction() as s:
        s["csrf"] = "right"
    monkeypatch.setattr(admin_ui, "current_user", lambda: {"id": "u", "role": "admin"})
    assert c.post("/admin/realtime/v1/longpoll?csrf=wrong").status_code == 403
    assert c.post("/admin/realtime/v1/longpoll").status_code == 403, "no csrf at all is also a refusal"

    # ...and the matching one gets through, or the guard would pass by refusing everything
    class _Reply:
        status, headers = 200, {"Content-Type": "application/json"}

        def read(self):
            return b'{"status":410,"token":"t","messages":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(admin_ui.urllib.request, "urlopen", lambda *a, **k: _Reply())
    r = c.get("/admin/realtime/v1/longpoll?csrf=right&vsn=2.0.0")
    assert r.status_code == 200 and json.loads(r.get_data())["status"] == 410


def test_the_realtime_proxy_pins_the_api_key_and_keeps_our_csrf_to_itself(app):
    """Realtime reads the key from the query string -- as a header it answers {"status":403} -- so the
    proxy puts it there itself rather than forwarding whatever the caller sent. csrf is ours and means
    nothing to Phoenix."""
    from werkzeug.datastructures import MultiDict

    from iopstor import admin_ui

    q = admin_ui._rt_upstream_query(MultiDict([("vsn", "2.0.0"), ("csrf", "s3cret"), ("apikey", "someone-elses")]), "ours")
    assert "csrf" not in q and "someone-elses" not in q
    assert "apikey=ours" in q and "vsn=2.0.0" in q


def test_the_access_log_keeps_the_polls_out_but_not_their_failures(app):
    """A longpoll is one request per message plus one every ten seconds per editor, and the whole
    query string lands in the log line -- including the Phoenix session token, which is a live
    credential. So successful polls are filtered out of the access log. Failures are not: a 403 or a
    500 is exactly what somebody reading the log is looking for."""
    import logging

    from iopstor import _quiet_polls

    def line(msg):
        return _quiet_polls.filter(logging.LogRecord("werkzeug", logging.INFO, "", 0, msg, None, None))

    poll = '"GET /admin/realtime/v1/longpoll?apikey=eyJ0eXAi&csrf=abc&token=SFMyNTY.gQ HTTP/1.1" 200 -'
    assert not line(poll), "a successful poll must not reach the log"
    assert not line('127.0.0.1 - - [15/Sep/2026 15:08:35] ' + poll.replace("200 -", "204 -"))
    assert line(poll.replace('" 200 -', '" 403 -')), "a refusal must still print"
    assert line(poll.replace('" 200 -', '" 500 -')), "so must a failure"
    # and nothing else is touched, including a page whose own URL mentions the route
    assert line('"POST /admin/posts/1158/draft HTTP/1.1" 200 -')
    assert line('"GET /admin/posts?q=/admin/realtime/v1/longpoll?x HTTP/1.1" 200 -')


def test_a_status_the_poll_transport_cannot_read_becomes_a_500(app, monkeypatch):
    """The browser's LongPoll switches on the status and THROWS "unhandled poll status" on anything
    outside {200,204,403,410,500}, which wedges the transport for the life of the tab. So a Kong 401
    from a wrong anon key, or a 502 while Realtime restarts, has to arrive as the one status it knows
    how to back off from -- and then our own CHANNEL_ERROR path takes over."""
    import urllib.error

    from iopstor import admin_ui

    def boom(*a, **k):
        raise urllib.error.HTTPError("http://kong/realtime/v1/longpoll", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(admin_ui.urllib.request, "urlopen", boom)
    monkeypatch.setattr(admin_ui, "current_user", lambda: {"id": "u", "role": "admin"})
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.get("/admin/realtime/v1/longpoll?csrf=tok&vsn=2.0.0")
    assert r.status_code == 500, "401 would be an unhandled poll status in the browser"
    assert json.loads(r.get_data())["status"] == 500


def test_the_editors_colour_is_the_same_in_every_worker():
    """hash() is salted per process, so with thirty gunicorn workers the same editor would get a
    different colour depending on which one served the page. The id's own digits are stable."""
    from flask import g

    from iopstor import admin_ui, create_app

    app = create_app({"TESTING": True, "SITE_URL": "http://t", "SECRET_KEY": "k", "SUPABASE_URL": "http://x",
                      "SUPABASE_ANON_KEY": "a", "SUPABASE_SERVICE_ROLE_KEY": "b", "SUPABASE_JWT_SECRET": "c" * 32})
    uid = "8f14e45f-ceea-467a-9b4e-4c9d3c8b2a11"
    with app.test_request_context("/admin/posts/7"):
        g.user = {"id": uid, "email": "a@b.c", "name": "Asha Rao", "role": "editor"}
        assert admin_ui._rt(7)["me"]["colour"] == f"hsl({int(uid[:8], 16) % 360} 62% 45%)"


def test_the_realtime_token_route_is_a_get(app):
    """It changes nothing, so AUDITED needs no entry -- and must not have one, because the route
    accounting test asserts both directions and would fail on a name that is not a write route."""
    rule = next(r for r in app.url_map.iter_rules() if r.endpoint == "admin_ui.rt_token")
    assert not (rule.methods & {"POST", "PATCH", "PUT", "DELETE"})
    assert "admin_ui.rt_token" not in AUDITED


# ---- the working draft -------------------------------------------------------


class _SessionRecorder:
    """Enough of a PostgREST builder to watch flush_sessions() pick rows and delete them again."""

    def __init__(self, rows):
        self.rows, self.filters, self.deleted, self.stale = rows, [], False, None

    def select(self, *a, **k):
        return self

    def delete(self):
        self.deleted = True
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def lt(self, key, value):
        self.stale = (key, value)
        return self

    def in_(self, key, values):
        self.filters.append((key, tuple(values)))
        return self

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data=self.rows)


def test_a_finished_session_is_logged_against_its_own_editor(monkeypatch):
    """The load-bearing one. There is no scheduler here, so a session that has gone quiet is written
    up inside whatever request happens to notice -- usually a DIFFERENT editor's autosave. If the
    log took the actor or the address from that request it would record the wrong person, which is
    worse than recording nobody."""
    from unittest.mock import MagicMock

    from iopstor import db

    audit = MagicMock()
    monkeypatch.setattr(db, "_audit", audit)
    monkeypatch.setattr(db, "one", lambda q: {"title": "Prime ABGB"})
    sess = {"post_id": 9, "user_id": "u-priya", "user_email": "priya@example.com", "ip": "10.0.0.7",
            "changes": {"blocks": [[], [{"type": "rich_text"}]]}}
    rec = _SessionRecorder([sess])
    monkeypatch.setattr(db, "table", lambda name: rec)

    assert db.flush_sessions(9) == 1
    action, name, row_id, changes, label = audit.call_args.args
    assert (action, name, row_id, label) == ("edit", "posts", 9, "Prime ABGB")
    assert changes == sess["changes"]
    assert audit.call_args.kwargs["user"] == {"id": "u-priya", "email": "priya@example.com"}
    assert audit.call_args.kwargs["ip"] == "10.0.0.7"      # theirs, not the caller's
    assert rec.deleted and ("user_id", ("u-priya",)) in rec.filters
    assert rec.stale and rec.stale[0] == "updated_at"      # stale only, not everybody still typing


def test_a_session_with_nothing_in_it_writes_no_entry(monkeypatch):
    """Opening a page and closing it again is not an edit. The row is still cleared."""
    from unittest.mock import MagicMock

    from iopstor import db

    audit = MagicMock()
    monkeypatch.setattr(db, "_audit", audit)
    monkeypatch.setattr(db, "one", lambda q: {"title": "Prime ABGB"})
    rec = _SessionRecorder([{"post_id": 9, "user_id": "u", "user_email": "e", "ip": "", "changes": {}}])
    monkeypatch.setattr(db, "table", lambda name: rec)

    assert db.flush_sessions(9) == 1
    audit.assert_not_called()
    assert rec.deleted


def test_the_app_runs_before_the_draft_migration_is_applied(monkeypatch):
    """/migration step 8: the code tolerates the gap, and the code it tolerates it by is not the one
    you would guess. PostgREST answers from its schema cache and never reaches Postgres, so a missing
    table is **PGRST205**, not 42P01 -- measured against the dev Supabase before 0010 was applied,
    where assuming 42P01 meant the editor raised instead of falling back. Anything else still
    raises: a permission error swallowed here would look like "autosave is simply off"."""
    from postgrest import APIError

    from iopstor import db

    def missing(name):
        raise APIError({"code": "PGRST205", "message": "Could not find the table 'public.post_drafts' in the schema cache"})

    monkeypatch.setattr(db, "table", missing)
    assert db.get_draft(3) is None
    assert db.open_sessions(3) == []

    def broken(name):
        raise APIError({"code": "42501", "message": "permission denied"})

    monkeypatch.setattr(db, "table", broken)
    with pytest.raises(APIError):
        db.get_draft(3)


def test_the_autosave_route_is_not_the_one_that_publishes():
    """Two properties the rest of the feature leans on: the autosave never touches posts.blocks (it
    is the working draft or nothing), and Publish clears the draft afterwards -- otherwise the editor
    reopens the version that was just published and every save looks like it did nothing."""
    import inspect

    from iopstor import admin_ui

    autosave = inspect.getsource(admin_ui.autosave)
    assert "save_draft" in autosave and 'db.update("posts"' not in autosave
    save = inspect.getsource(admin_ui._save)
    assert 'action="publish"' in save and "clear_draft" in save and "flush_sessions" in save
    # the two other writers of posts.blocks have to clear it too, or they are silently undone
    assert "clear_draft" in inspect.getsource(admin_ui.audit_restore)


# ---- the Quill editing surface ----------------------------------------------


def test_quills_normalised_tags_make_no_difference_to_the_published_output():
    """admin.js's gate treats <b>/<strong> and <i>/<em> as the same tag, so a block is not refused
    for a difference nobody can see. That is only safe while the Markdown twin agrees, which is what
    this pins -- if _html_md() ever stops rendering them identically, the alias becomes a silent
    change to every .md twin and to llms-full.txt."""
    def md(html):
        return blocks_md([{"type": "rich_text", "data": {"html": html}}])

    assert md("<p><b>x</b></p>") == md("<p><strong>x</strong></p>") == "**x**"
    assert md("<p><i>y</i></p>") == md("<p><em>y</em></p>") == "*y*"


def test_a_nbsp_from_quill_would_poison_the_markdown_twin():
    """The reason admin.js's semantic() undoes &nbsp; before storing. Quill's getSemanticHTML() runs
    replaceAll(" ", "&nbsp;") over EVERY text leaf -- verified in the vendored build, not in its
    docs -- so without the fix every space in every Quill-edited block arrives here as U+00A0: the
    .md twins and llms-full.txt fill with it and the public page never wraps."""
    poisoned = blocks_md([{"type": "rich_text", "data": {"html": "<p>one&nbsp;two</p>"}}])
    assert " " in poisoned                      # this is what shipping it would look like
    clean = blocks_md([{"type": "rich_text", "data": {"html": "<p>one two</p>"}}])
    assert clean == "one two" and " " not in clean


def test_the_canvas_loads_quill_inside_the_iframe():
    """Quill binds to elements in the canvas document, so it is loaded there -- the sortable.min.js
    precedent, and the opposite of supabase.js, which lives in the parent because the socket does.
    quill.core.css and not snow: the toolbar is ours, in the parent."""
    html = (pathlib.Path(__file__).resolve().parent.parent
            / "iopstor" / "templates" / "admin" / "canvas.html").read_text()
    assert "vendor/quill.js" in html and "vendor/quill.core.css" in html
    assert "quill.snow.css" not in html


def test_a_section_name_and_the_quill_verdict_are_not_prose():
    """_id and _rich ride in a block's data so they travel with it through posts.blocks, and
    blocks_text() walks every string in data -- so without this a uuid lands in llms-full.txt, in
    the .md twins' source and in admin search results, which is nonsense an editor would see."""
    assert "_id" in blocks._NON_TEXT_KEYS and "_rich" in blocks._NON_TEXT_KEYS
    stamped = [{"type": "rich_text", "data": {"_id": "0b9d-uuid-here", "_rich": True, "html": "<p>Real words</p>"}}]
    assert blocks.blocks_text(stamped) == "Real words"
    # and the editor is told the same set, so the browser and the server agree about what is prose
    assert "_id" in blocks.EDITOR["scalars"] and "url" in blocks.EDITOR["scalars"]


def _blk(name, html, kind="rich_text"):
    return {"type": kind, "data": {"_id": name, "html": html}}


def test_every_block_type_has_a_template_that_renders(app):
    """The gap /new-block names in bold: nothing asserts a template exists. The two metadata tests
    check names, seeds and the markdown branch, and test_render_blocks_uses_template renders only
    hero and stats -- so a missing or throwing template is a 500 on the public page that the suite
    would pass straight over. render_blocks() swallows the error when edit=True, which is exactly how
    it stayed hidden, so this renders BOTH ways."""
    # A request context, not just an app one: warranty_check reads request.args at render time, and
    # that is exactly the kind of thing a template-existence check has to survive.
    # post_list is left out because it queries at render time in BOTH modes -- render_blocks()
    # computes its `extra` before looking at `edit` -- and this file has to run with no Supabase.
    with app.test_request_context("/"):
        for t, seed in blocks.EDITOR["seed"].items():
            if t == "post_list":
                continue
            for edit in (False, True):
                html = str(blocks.render_blocks([{"type": t, "data": deepcopy(seed)}], edit=edit))
                assert "not finished yet" not in html, f"{t} (edit={edit}) threw: {html[:200]}"
                assert html.lstrip().startswith("<section"), f"{t} did not render a section"


def test_the_two_sections_that_were_layout_are_block_types_now():
    """Home's ZFS panel and NAS's feature list were rich_text blocks carrying their own classes, which
    Quill drops -- so they could never be co-edited. Every field is an EXISTING key, which is what
    keeps labels, widgets, _TEXT_ORDER and _NON_TEXT_KEYS out of this change entirely."""
    known = set(blocks._TEXT_ORDER) | blocks._NON_TEXT_KEYS
    for t in ("points", "definitions"):
        required, optional = blocks.BLOCKS[t]
        assert set(required + optional) <= known, f"{t} introduces a key nothing knows how to read"
        assert t not in blocks.NEVER_NESTED          # both of the real ones live inside a column
        assert blocks.validate_blocks([{"type": t, "data": blocks.EDITOR["seed"][t]}]) == []

    # the intro is `subheading`, not `text`: EDITOR["labels"] is keyed by the bare field name with no
    # per-block override, so `text` would label the intro and the repeater rows identically
    assert "subheading" in blocks.BLOCKS["points"][1] and "text" not in blocks.BLOCKS["points"][1]
    assert blocks.EDITOR["items"]["points"] == ["text"]
    assert blocks.EDITOR["items"]["definitions"] == blocks.EDITOR["items"]["spec_table"]


def test_a_definition_list_reaches_the_markdown_twin_as_a_list():
    """_html_md() is regex with no <dt>/<dd> case, so as HTML these ran term and description together
    into one line in every .md twin. A block type gets a branch of its own."""
    md = blocks.blocks_md([{"type": "definitions", "data": {
        "heading": "In plain terms", "rows": [{"k": "RaidZ", "v": "No write hole."}]}}])
    assert "## In plain terms" in md and "**RaidZ**" in md and "No write hole." in md

    pts = blocks.blocks_md([{"type": "points", "data": {
        "eyebrow": "Why", "heading": "It matters", "subheading": "Because.",
        "items": [{"text": "First"}, {"text": "Second"}],
        "button_label": "Read on", "button_url": "/x"}}])
    assert "## It matters" in pts and "- First" in pts and "- Second" in pts and "[Read on](/x)" in pts


def test_the_content_migration_moves_the_drafts_and_the_gate_verdict_too():
    """0011 rewrites two pages' blocks -- and two more things without which the change does not stick.
    post_drafts.state is a CRDT document carrying the OLD section ids, and initShared() loads it in
    preference to blocks, so a stale draft puts the old shape straight back. And data._rich is the
    Quill gate's stored verdict, which mountQuill() reads and never recalculates, so a block that
    already carries one is deaf to the gate accepting more."""
    sql = (pathlib.Path(__file__).resolve().parent.parent
           / "migrations" / "0011_sections_that_were_layout.sql").read_text()
    assert "update public.posts" in sql and "update public.post_drafts" in sql
    assert "state  = ''" in sql                      # the draft's shared document is cleared
    assert "#- '{data,_rich}'" in sql                # the stored verdict is stripped
    # matched by content, never by id: production has its own ids
    assert "<ul class=\"dash\">" in sql and "<dl class=\"zfs\">" in sql
    assert "where id = " in sql and "p.id" in sql and "1158" not in sql and "id = 32" not in sql


def test_a_page_edit_is_reported_section_by_section_even_when_a_section_was_added():
    """_blocks_fields() used to compare the two block-TYPE lists, so adding a section threw the whole
    page into one word diff labelled "The writing on the page" -- and every other section's
    field-by-field report was lost with it. Rare when one person edited at a time; the common case
    once two do, because somebody is always adding a section. Sections carry a stable _id now, so
    they can be paired by name: exact rather than heuristic, and it survives a move."""
    from iopstor.admin_ui import _blocks_fields

    rows = _blocks_fields([_blk("a", "<p>One</p>"), _blk("b", "<p>Two</p>")],
                          [_blk("a", "<p>One changed</p>"), _blk("b", "<p>Two</p>"), _blk("c", "<p>New</p>")])
    assert any(r["note"].startswith("Added") for r in rows)          # the new section is named
    words = [r for r in rows if r["label"] == "Rich text section"]    # and so is what changed in `a`
    assert len(words) == 1 and "changed" in str(words[0]["now"])
    assert not any("Two" in str(r.get("now", "")) for r in rows)     # `b` did not move, so it is silent

    moved = _blocks_fields([_blk("a", "<p>One</p>"), _blk("b", "<p>Two</p>")],
                           [_blk("b", "<p>Two</p>"), _blk("a", "<p>One</p>")])
    assert [r["note"] for r in moved] == ["Moved the sections around."]


def test_a_page_edit_from_before_sections_had_names_still_renders():
    """Everything saved before _id existed -- most of the archive -- has no name to pair by, so the
    positional path has to stay. A row whose sections are unnamed must not crash or silently report
    nothing, and two blocks sharing a name (a duplicate that predates the fix) must not pair either."""
    from iopstor.admin_ui import _blocks_fields

    old_was = [{"type": "rich_text", "data": {"html": "<p>One</p>"}}]
    old_now = [{"type": "rich_text", "data": {"html": "<p>One changed</p>"}},
               {"type": "divider", "data": {}}]
    rows = _blocks_fields(old_was, old_now)
    assert rows and any("Added" in r["note"] for r in rows)

    twins = _blocks_fields([_blk("same", "<p>A</p>"), _blk("same", "<p>B</p>")],
                           [_blk("same", "<p>A</p>"), _blk("same", "<p>C</p>")])
    assert twins   # falls back rather than pairing two sections that answer to one name


def test_one_sitting_is_one_entry_however_many_times_they_reloaded():
    """A sitting ends after fifteen minutes with no activity -- the client's rule -- and not when
    somebody reloads or walks to another screen. But each visit starts with a fresh baseline, so
    without merging the second visit's `was` replaces the first's and the entry covers only what
    they did after coming back."""
    from iopstor.db import _merge_changes

    visit1 = {"blocks": [[_blk("a", "<p>One</p>")], [_blk("a", "<p>One edited</p>")]]}
    visit2 = {"blocks": [[_blk("a", "<p>One edited</p>"), _blk("b", "<p>Two</p>")],
                         [_blk("a", "<p>One edited</p>"), _blk("b", "<p>Two edited</p>")]]}
    was, now = _merge_changes(visit1, visit2)["blocks"]
    assert [b["data"]["html"] for b in was] == ["<p>One</p>", "<p>Two</p>"]        # earliest each
    assert [b["data"]["html"] for b in now] == ["<p>One edited</p>", "<p>Two edited</p>"]   # latest

    # nothing to merge by, and nothing to merge with: the later visit stands on its own
    unnamed = {"blocks": [[{"type": "rich_text", "data": {}}], []]}
    assert _merge_changes(unnamed, visit2) == visit2
    assert _merge_changes(None, visit2) == visit2


def test_an_entry_covers_only_this_editors_own_sections_from_when_they_touched_them():
    """Two faults in one function. `sitting()` sent a whole-page `was` beside a narrowed `now`, so the
    two halves described different documents and an entry claimed a colleague's sentence -- a real row
    read WAS '<p></p>' NOW '<p>Good Hello Afternoon</p>...' for somebody who had added one word to it.
    And `touched()` fired only from the two TYPING handlers, so a section this person deleted, moved,
    or added without typing into never appeared in their entry at all."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    sit = js[js.index("function sitting(now)"):js.index("function body(now, close)")]
    assert "return [JSON.stringify(wasOut), JSON.stringify(nowOut)];" in sit   # both sides, together
    assert "wasOut.push(mine[id]);" in sit          # the snapshot, not the page-load document
    assert "if (!mine[id]) return;" in sit          # somebody else's section: silent on both sides

    # the snapshot is taken in touched() itself, so a deletion is captured while it is still in MODEL
    at = js.index("touched = function (id) {")
    tch = js[at:js.index("nudgeSave = function ()", at)]
    assert "if (!id || mine[id]) return;" in tch and "JSON.parse(JSON.stringify(b))" in tch
    assert 'touched(rootIdOf(path));        // while it is still here' in js
    for site in ("function delBlock(", "function moveBlock(", "function dupBlock(", "function addParagraph("):
        at = js.index(site)
        assert "touched(" in js[at:at + 700], site

    # leaving the page flushes, it does not end the sitting; only the idle timer does
    assert 'window.addEventListener("pagehide", function () { closeSession(false); });' in js
    assert "closeSession(true); }, 15 * 60 * 1000)" in js


def test_a_draft_that_could_not_be_stored_does_not_report_itself_as_saved():
    """0010 may not be applied, and the editor has to run when it is not -- but silently is the one
    way it must not, because the page then serves the PUBLISHED version back on the next reload and
    the editor's work appears to vanish. save_draft() returns False, the route passes it on, and the
    editor says so in words an editor can act on (no table names: the console gets that half)."""
    src = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "db.py").read_text()
    body = src[src.index("def save_draft("):src.index("def clear_draft(")]
    assert "return _tolerate_0010(store, default=False)" in body

    route = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "admin_ui.py").read_text()
    assert '"stored": stored' in route
    assert "stored = db.save_draft(" in route

    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    assert "if (j && j.stored === false) {" in js
    told = js[js.index("if (j && j.stored === false) {"):js.index("savedAt = Date.now();")]
    assert "Tell a developer." in told and "0010_working_draft.sql" in told
    # the sentence an editor reads names no table, column or migration -- that is the console's job
    shown = told[told.index('show("'):told.index('", true)')]
    assert "0010" not in shown and "post_drafts" not in shown


def test_an_editor_that_cannot_bind_yet_waits_instead_of_giving_up():
    """canvasFull()'s onload runs wireDoc() -- which mounts Quill -- BEFORE initCollab() has a
    channel, so canWrite() is false for every editor on a page's first paint. Treating that as "not
    my job" meant the shared text was never created, nothing ever bound, and from then on typing
    reached MODEL and stopped there: no throw, no warning, because reconcileOut skips a rich block's
    html by design. A stored draft was found whose html read "Prime Testing  is available only
    monday to Friday" beside a shared text that still read "Prime Test"."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    share = js[js.index("function shareQuill("):js.index("function shareWaiting(")]
    assert "WAITING.push(" in share and "return;" in share
    # every event that can change the answer has to drain the queue, or waiting is just a slower giving up
    assert js.count("shareWaiting();") >= 4
    for trigger in ('say("seeded the shared document', "dedupe();", "if (!Object.keys(peers).length) seedDoc();",
                    'if (status === "SUBSCRIBED") {'):
        at = js.index(trigger)
        assert "shareWaiting();" in js[at:at + 400], trigger
    # a replaced section's binding must go, or two bindings feed one text and write to each other
    assert "old.quill.root.isConnected" in js


def test_a_second_browser_does_not_seed_a_second_document():
    """Two browsers that each seed from the same blocks give Yjs two independent histories, and
    merging them shows every section twice. With no stored state -- every load before 0010 is
    applied -- that is not a rare race, it happens every time. So the seed waits for the roster to
    say we are alone, and dedupe() repairs the instant where both saw an empty one."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    seed = js[js.index("function initShared("):js.index("function seedDoc(")]
    assert "setTimeout(seedDoc, 4000);" in seed          # backstop, not the normal path
    assert "return seedDoc();" in seed                    # single player seeds at once
    assert "if (!Object.keys(peers).length) seedDoc();" in js    # the roster is what releases it
    assert "dedupe();" in js and "function dedupe()" in js


def test_a_draft_may_be_unfinished_but_not_misshapen():
    """The autosave route validates with draft=True. A working draft is unfinished by definition --
    the empty paragraph the caret sits in has no text, an Image section has no picture until one is
    chosen -- and refusing to SAVE somebody's work because they have not finished it is the worst
    possible moment to enforce a publishing rule. Publish enforces it anyway through apply_post().
    What must still be refused is a shape that is wrong rather than incomplete."""
    unfinished = [{"type": "rich_text", "data": {"html": "", "_id": "a", "_rich": True}},
                  {"type": "image", "data": {"caption": ""}}]
    assert blocks.validate_blocks(unfinished, draft=True) == []
    assert len(blocks.validate_blocks(unfinished)) == 2        # publishing still asks for both

    misshapen = [{"type": "nope", "data": {}},
                 {"type": "columns", "data": {"cols": [[{"type": "hero", "data": {"heading": "x"}}]]}}]
    assert len(blocks.validate_blocks(misshapen, draft=True)) == 2   # and draft=True reaches a column

    src = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "admin_ui.py").read_text()
    assert "validate_blocks(blocks, draft=True)" in src
    # the publish path is untouched: apply_post() is still the one full check into posts.blocks
    api = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "admin_api.py").read_text()
    assert "validate_blocks(b[\"blocks\"])" in api


def test_an_editor_who_is_not_the_writer_still_gets_an_activity_entry():
    """The autosave route carries two unrelated payloads. `blocks`/`state` are the shared document,
    and only the elected writer sends them. `was`/`now` are one person's sitting and EVERY editor
    sends their own -- so the document half has to be optional, or the activity log would credit all
    of everybody's work to whoever happened to be elected."""
    src = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "admin_ui.py").read_text()
    body = src[src.index("def autosave("):src.index("def _record_session(")]
    # Presence of the field, not truthiness: .get("blocks") or "[]" reads a missing field as an
    # empty page, so a non-writer's autosave would wipe the draft every second and a half.
    assert 'if "blocks" in request.form:' in body
    assert 'request.form.get("blocks") or "[]"' not in body
    # _record_session is outside that branch: everybody's sitting is recorded.
    assert body.index("_record_session(pk)") > body.index("db.save_draft(")


def test_the_draft_is_stored_unpruned_and_publish_still_prunes():
    """prune() drops an empty paragraph and rebuilds a columns block as a fresh object, so a block
    an editor still has the caret in loses its _id and every later section answers to a different
    one -- and a remote edit is then applied to the wrong section. The draft is the live document;
    the submit still prunes, because that is where an empty paragraph really is not content."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    assert "function saveable() { return JSON.stringify(MODEL); }" in js
    assert "AREA.value = JSON.stringify(prune(MODEL), null, 2);" in js


def test_the_quill_verdict_is_read_at_mount_and_never_recomputed_there():
    """mountQuill runs once per peer per repaint. A "work it out if it is missing" fallback there is
    the per-peer gate again: three browsers opening one page all reach it at once and can disagree,
    and a peer that builds a shared text type where another has a plain string is a split no merge
    repairs. Only the elected writer decides, and the answer is stored."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    mount = js[js.index("function mountQuill("):js.index("function bindField(")]
    assert "if (!canWrite()) { node.setAttribute(\"data-legacy\", \"1\"); return false; }" in mount
    assert mount.count("quillKeeps(") == 1          # the one writer-gated call, nowhere else
    assert "if (!target._rich) {" in mount


def test_painting_the_toolbar_never_asks_quill_to_focus_itself():
    """`q.getFormat()` with no argument means `getFormat(this.getSelection(true))`, which focuses the
    editor and returns null when the canvas document has no caret -- and getFormat then reads .index
    off that null and throws. It became reachable the moment a peer's words could mutate the canvas:
    canvasFull()'s onload wires the document (binding Quill, whose QuillBinding calls setContents)
    BEFORE focusBlock(), so the first paint of a shared page asked a Quill nobody was in."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    assert "var q = qHere(), qat = q && q.getSelection();" in js
    assert "if (q && !qat) live = false;" in js
    # Nowhere may ask for the format of "wherever the caret is": every call passes a range it has
    # already checked. Comments are stripped first -- the prose above says `getFormat()` too, and an
    # assertion that reads the explanation rather than the code is not an assertion.
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$", "", code)
    assert re.search(r"getFormat\(\s*\)", code) is None


def test_a_peers_words_are_not_mistaken_for_this_editors_caret():
    """selectionchange stopped meaning "the person at this keyboard moved their caret": y-quill
    applies a peer's words by mutating the canvas DOM and fires it too. Without the activeElement
    test the editor records a caret it does not have and broadcasts "I am typing here" for a field
    nobody is in. The iframe keeps its own activeElement when focus moves to the parent's toolbar,
    so a toolbar click still counts as a caret in the canvas."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    fn = js[js.index("function rememberSelection()"):js.index("function liveField()")]
    assert 'var here = d.activeElement;' in fn
    assert 'if (!here || !here.closest || !here.closest("[data-f]")) return;' in fn
    assert fn.index("d.activeElement") < fn.index("savedField = f")


def test_a_peers_words_are_written_back_the_same_way_they_are_read():
    """The short fields are contentEditable="plaintext-only", so Enter makes a <br> and bindField()
    reads them back with innerText. Writing a peer's value with textContent would put a bare newline
    in the DOM, innerText would read it back with the break collapsed, and the next keystroke would
    splice the peer's line break away -- on every keystroke, until one of them stopped typing."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    assert "f.innerText = b.data[key];" in js            # the write, in reconcileIn
    assert "target[key] = rich ? f.innerHTML : f.innerText;" in js   # the read, in bindField
    assert "f.textContent = b.data[key]" not in js


def test_two_people_in_one_paragraph_keep_both_sets_of_words():
    """The acceptance test for this whole run of changes, run against the real Yjs: two editors type
    into one field at the same moment, neither having seen the other, and both sets of words are
    there afterwards. tests/reconcile.mjs cuts the shared-document section straight out of admin.js,
    so it cannot drift into testing a copy of the logic."""
    root = pathlib.Path(__file__).resolve().parent.parent
    if shutil.which("node") is None:
        pytest.skip("node is not installed; the shared document cannot be exercised here")
    r = subprocess.run(["node", "tests/reconcile.mjs"], cwd=root, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "two people in one paragraph keep both sets of words" in r.stdout


def test_the_editor_persists_semantic_html_and_never_inner_html():
    """root.innerHTML wraps every list in <ol> with <li data-list="bullet"> plus injected
    <span class="ql-ui">, and the public page loads no Quill CSS -- so storing it would render every
    bulleted list on the live site as a numbered one. getSemanticHTML() emits a real <ul>."""
    js = (pathlib.Path(__file__).resolve().parent.parent / "iopstor" / "static" / "admin.js").read_text()
    # One expression, asserted whole: what a Quill field stores is getSemanticHTML() with the &nbsp;
    # undone, and the two halves cannot drift apart into different functions where one gets forgotten.
    # (Not "root.innerHTML is absent" -- the comment explaining why it must not be used says it too,
    # so that assertion would be reading prose rather than behaviour.)
    assert 'return q.getSemanticHTML().replace(/&nbsp;/g, " ");' in js


class _FakeQ:
    """Any PostgREST chain, remembering only which table it started from. Every builder method returns
    self, so db.live()/db.select_posts()/.eq()/.order()/.limit() all work untouched and db.rows() can
    answer from a canned dict instead of a network."""

    def __init__(self, name):
        self.name = name

    def __getattr__(self, _):
        return lambda *a, **k: self


def test_no_crawler_output_can_carry_an_address_the_app_owns(app, monkeypatch):
    """The client's rule: sitemap.xml, feed.xml, llms.txt and llms-full.txt must never publish an admin
    or private-API address (user, 2026-09-15).

    The collision is seeded deliberately -- a page slugged "admin", a post type prefixed "admin", a
    taxonomy slugged "admin" -- because an assertion that passes on a site with none of those proves
    nothing, and each of the three reaches the sitemap by a different route: the post's own path, the
    archive prefix, and the term archive. Only the first passes through _indexable() at all."""
    from iopstor import db

    def pt(slug, prefix, **kw):
        return {"id": abs(hash(slug)) % 999, "slug": slug, "name": slug.title(), "url_prefix": prefix,
                "in_sitemap": True, "has_pages": True, "hierarchical": False, "field_schema": [], **kw}

    blog, page, bad = pt("post", "blog"), pt("page", ""), pt("secret", "admin")

    def post(slug, type_row, **kw):
        return {"id": abs(hash(slug)) % 999, "slug": slug, "title": slug.title(), "excerpt": "x",
                "blocks": [], "meta": {}, "seo": {}, "terms": [], "children": [], "parent_id": None,
                "featured_media": None, "post_type": type_row, "updated_at": "2026-09-15T00:00:00+00:00",
                "published_at": "2026-09-01T00:00:00+00:00", "menu_order": 0, **kw}

    canned = {
        "settings": [], "post_types": [blog, page, bad], "post_terms": [{"term_id": 1}, {"term_id": 2}],
        "terms": [{"id": 1, "slug": "finance", "taxonomy": {"slug": "industry"}},
                  {"id": 2, "slug": "anything", "taxonomy": {"slug": "admin"}}],
        "posts": [post("real", blog), post("admin", page), post("api", page),
                  post("hidden", blog, seo={"robots": "NOINDEX"}), post("buried", bad)],
    }
    monkeypatch.setattr(db, "table", lambda n: _FakeQ(n))
    monkeypatch.setattr(db, "rows", lambda q: canned.get(q.name, []))

    bodies = {p: app.test_client().get(p).data.decode()
              for p in ("/sitemap.xml", "/feed.xml", "/llms.txt", "/llms-full.txt", "/robots.txt")}

    for path, body in bodies.items():
        assert "/admin" not in body, f"{path} published an admin address"
        assert "/api/admin" not in body, f"{path} published the private API"
        assert "/media/" not in body and "/static/" not in body, path
        assert "Hidden" not in body, f"{path} published a noindex page"

    # the ordinary page is still there -- a gate that publishes nothing passes every assertion above
    assert "http://test/blog/real" in bodies["/sitemap.xml"] and "http://test/blog/real" in bodies["/feed.xml"]
    assert "http://test/industry/finance" in bodies["/sitemap.xml"]      # the innocent term archive survives
    assert "/blog/real.md" in bodies["/llms.txt"]

    # the PUBLIC api stays advertised: it is read-only published content and that is what llms.txt is for
    assert "/api/v1/posts" in bodies["/llms.txt"]
    # and robots.txt no longer names the admin at all -- those lines were its only public mention
    assert "Disallow" not in bodies["/robots.txt"] and "Sitemap: http://test/sitemap.xml" in bodies["/robots.txt"]


def test_the_words_the_app_owns_are_refused_when_a_page_is_named(app, monkeypatch):
    """reserved() is what stops the collision existing in the first place. A page slugged "admin" used
    to save cleanly and then 404 for ever -- Flask matches the admin blueprint before public.py's
    catch-all -- with nothing to tell the editor why."""
    from iopstor import db
    from iopstor.admin_api import apply_post
    from werkzeug.exceptions import HTTPException

    assert db.reserved("admin") and db.reserved("/admin/thing") and db.reserved("API/v1")
    assert not db.reserved("administration") and not db.reserved("blog") and not db.reserved("")

    page = {"id": 1, "slug": "page", "name": "Page", "url_prefix": "", "in_sitemap": True,
            "has_pages": True, "hierarchical": False, "field_schema": []}
    blog = {**page, "id": 2, "slug": "post", "url_prefix": "blog"}
    monkeypatch.setattr(db, "post_types", lambda: [page, blog])
    monkeypatch.setattr(db, "unique_slug", lambda tid, base, exclude=None: base)

    def save(post_type, title):
        with app.test_request_context("/api/admin/v1/posts"):
            return apply_post(None, {"post_type": post_type, "title": title, "status": "draft"})

    with pytest.raises(HTTPException) as e:
        save("page", "Admin")
    # fail() aborts with a built Response, so the status is on that rather than on exc.code
    assert e.value.response.status_code == 400 and b"cannot be used" in e.value.response.data

    # ...but only where the slug is the FIRST segment. A blog post honestly titled "Admin" is
    # /blog/admin, which collides with nothing, and refusing it would be a rule nobody could follow.
    changes, _ = save("post", "Admin")
    assert changes["slug"] == "admin"


def test_every_setting_the_app_reads_is_passed_into_the_container():
    """A key config.py reads but docker-compose.yml never passes is not a small omission: compose's
    `environment:` is an explicit list, so the variable is simply absent inside the container and the
    setting silently takes its default.

    ADMIN_NETWORKS was shipped that way. Its default is "no restriction", so the office-only admin lock
    read as OFF in production while the Dokploy environment screen showed the value set -- nothing in a
    log, nothing on screen, the admin open to the whole internet. LOGIN_MAX_FAILURES and LOGIN_WINDOW
    had the same hole, which made TECHNICAL.md's "tune it while under attack, no code change" untrue.

    Every failure here is of that shape: the value looks set and is not."""
    root = pathlib.Path(__file__).resolve().parent.parent
    read = set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', (root / "iopstor" / "config.py").read_text()))
    anchor = (root / "docker-compose.yml").read_text().split("x-app-env:")[1].split("\nservices:")[0]
    passed = set(re.findall(r"^\s{2}([A-Z_]+):", anchor, re.M))
    assert read, "no settings found -- the regex stopped matching config.py"
    assert not (read - passed), f"config.py reads these but docker-compose.yml never passes them: {sorted(read - passed)}"


# ---- stress-test engine (iopstor/stress.py) ----------------------------------------------------

def test_validate_target_accepts_a_base_and_rejects_junk():
    from iopstor import stress
    assert stress.validate_target("http://host:5000/") == "http://host:5000"
    assert stress.validate_target(" https://www.iopstor.com ") == "https://www.iopstor.com"
    for bad in ("", "host:5000", "ftp://host", "http://host/a/path", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            stress.validate_target(bad)


def test_clamp_holds_the_ceiling_and_survives_nonsense():
    from iopstor import stress
    assert stress.clamp(5, 0, 200) == 5
    assert stress.clamp(9999, 0, 200) == 200
    assert stress.clamp(-3, 1, 300) == 1
    assert stress.clamp("not a number", 1, 300) == 1


def test_percentile_is_nearest_rank_in_ms():
    from iopstor import stress
    assert stress.percentile([], 95) == 0.0
    # ten samples 0.01s..0.10s: p95 lands on the top sample
    sample = [i / 100 for i in range(1, 11)]
    assert stress.percentile(sample, 95) == 100.0
    assert stress.percentile(sample, 50) == 50.0


def test_progress_store_roundtrips_and_stops(tmp_path):
    from iopstor import stress
    db = str(tmp_path / "s.db")
    rid = stress.create({"visitors": 2}, path=db)
    run = stress.read(rid, path=db)
    assert run["state"] == "starting" and run["params"]["visitors"] == 2 and run["stop"] is False
    assert stress.read("nope", path=db) is None
    # stop only bites a running run
    assert stress.request_stop(rid, path=db) is False
    stress._write(rid, "running", {"sent": 1}, db)
    assert stress.request_stop(rid, path=db) is True
    assert stress.read(rid, path=db)["stop"] is True


def test_run_load_hits_a_real_server_and_the_honeypot_leaves_no_row(tmp_path):
    """Measured, not assumed: run the engine against a throwaway stdlib server and prove requests are
    sent, statuses tallied, real pages answer 200, and every lead post arrives with the honeypot filled
    so nothing is stored (the accept-and-drop path public.py takes)."""
    import http.server
    import threading
    import time
    from iopstor import stress

    tally = {"rows": 0, "honeypot": 0, "hits": 0}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            tally["hits"] += 1
            if self.path == "/sitemap.xml":
                body = (b"<urlset><url><loc>%s/</loc></url>"
                        b"<url><loc>%s/about</loc></url></urlset>"
                        % (self._base(), self._base()))
                self._send(200, body)
            elif self.path in ("/", "/about"):
                self._send(200, b"ok")
            else:
                self._send(404, b"no")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if body.get("website"):
                tally["honeypot"] += 1        # accepted and dropped, exactly like public.py
            else:
                tally["rows"] += 1
            self._send(201, b"ok")

        def _base(self):
            return b"http://127.0.0.1:%d" % self.server.server_address[1]

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    db = str(tmp_path / "run.db")
    try:
        rid = stress.start(base, visitors=3, attackers=3, seconds=2, path=db)
        deadline = time.time() + 20
        while time.time() < deadline:
            run = stress.read(rid, path=db)
            if run and run["state"] in ("done", "error"):
                break
            time.sleep(0.2)
    finally:
        srv.shutdown()

    assert run["state"] == "done", run
    p = run["progress"]
    assert p["sent"] > 0 and tally["hits"] > 0
    assert p["status"].get("200", 0) > 0           # visitors read the real pages
    assert tally["rows"] == 0                       # the honeypot spared the target every time


def test_nprocs_and_split():
    """The fan-out: one process below the threshold, more above it (capped), and the split sums back."""
    from iopstor import stress
    assert stress._nprocs(10, 5) == 1                       # under PER_PROC -> in-thread
    assert 1 <= stress._nprocs(5000, 1000) <= stress.MAX_PROCS
    assert stress._split(10, 3) == [4, 3, 3] and sum(stress._split(10, 3)) == 10
    assert stress._split(0, 4) == [0, 0, 0, 0]


def test_merge_parts_sums_children(tmp_path):
    """The coordinator sums every generator's raw counts into the one progress dict the poll reads."""
    from iopstor import stress
    db = str(tmp_path / "m.db")
    stress._write_part("r1", 0, {"sent": 10, "errors": 1, "status": {"200": 9},
                                 "kind": {"visitor": 10, "attacker": 0}, "lat": [0.01] * 5}, db)
    stress._write_part("r1", 1, {"sent": 20, "errors": 2, "status": {"200": 15, "429": 3},
                                 "kind": {"visitor": 0, "attacker": 20}, "lat": [0.02] * 5}, db)
    agg = stress._merge_parts("r1", db, 2.0)
    assert agg["sent"] == 30 and agg["errors"] == 3
    assert agg["status"]["200"] == 24 and agg["throttled"] == 3
    assert agg["kind"] == {"visitor": 10, "attacker": 20}
    assert agg["req_per_sec"] == 15.0                       # 30 sent / 2s


def test_a_multiprocess_run_completes(tmp_path, monkeypatch):
    """Measured: force the fan-out to real spawned processes and prove they run, report through the parts
    table and merge into one finished run. Two children hit a throwaway server over TCP."""
    import http.server
    import threading
    import time
    from iopstor import stress

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/sitemap.xml":
                b = b"<urlset><url><loc>http://127.0.0.1:%d/</loc></url></urlset>" % self.server.server_address[1]
            else:
                b = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    db = str(tmp_path / "mp.db")
    monkeypatch.setattr(stress, "_nprocs", lambda v, a: 2)   # force the spawn path regardless of CPU count
    try:
        rid = stress.start(base, visitors=4, attackers=0, seconds=2, path=db)
        deadline = time.time() + 30
        while time.time() < deadline:
            run = stress.read(rid, path=db)
            if run and run["state"] in ("done", "error"):
                break
            time.sleep(0.2)
    finally:
        srv.shutdown()

    assert run["state"] == "done", run
    assert run["progress"]["sent"] > 0
    assert len(stress._read_parts(rid, db)) == 2             # both spawned children reported


def test_plan_caps_real_concurrency():
    """The fix for a big self-test hanging: real concurrency never exceeds nprocs x PER_PROC, so a huge
    entered number is scaled down instead of spawning tens of thousands of threads."""
    from iopstor import stress
    n, v, a = stress._plan(20, 10)                          # small: one process, nothing scaled
    assert n == 1 and sum(v) == 20 and sum(a) == 10
    n, v, a = stress._plan(10000, 0)                        # huge: capped, per-process <= PER_PROC
    assert n <= stress.MAX_PROCS
    assert sum(v) <= n * stress.PER_PROC
    assert all(x <= stress.PER_PROC for x in v)
    assert stress._plan(0, 0) == (1, [0], [0])              # nothing to do, still well-formed


# ---- the page cache and the cross-request cache ----------------------------
# The public site's whole capacity story: a home page measured 29 PostgREST round trips and 219 ms,
# and ten thousand people browsing needs a few hundred views a second. These pin the two things that
# make that possible and the three that make it safe.

def test_proc_cached_serves_from_the_process_until_a_write_or_the_ttl(app, tmp_path, monkeypatch):
    from iopstor import db
    monkeypatch.setattr(db, "EPOCH_FILE", str(tmp_path / "epoch"))
    db._proc_cache.clear()
    hits = []

    def load():
        hits.append(1)
        return len(hits)

    assert db._proc_cached("k", load) == 1
    assert db._proc_cached("k", load) == 1          # second reader pays nothing
    assert len(hits) == 1

    db.bump_epoch()                                  # any write invalidates every worker
    assert db._proc_cached("k", load) == 2
    assert len(hits) == 2

    db._proc_cached("lapsing", load, ttl=-1)         # stored already expired
    assert len(hits) == 3
    db._proc_cached("lapsing", load, ttl=-1)         # a lapsed entry reloads even with no write
    assert len(hits) == 4


def test_content_epoch_survives_a_missing_file(app, tmp_path, monkeypatch):
    """First boot, or a container with no /dev/shm: everyone reads 0.0 and the TTL carries it,
    rather than the cache raising on every request."""
    from iopstor import db
    monkeypatch.setattr(db, "EPOCH_FILE", str(tmp_path / "nope" / "deeper" / "epoch"))
    assert db.content_epoch() == 0.0
    db.bump_epoch()                                  # unwritable path: must not raise
    assert db.content_epoch() == 0.0


def test_only_whole_public_pages_are_cacheable(app):
    """An allow-list, not a list of exclusions: /media/<key> is on the same blueprint and serves
    files up to MAX_CONTENT_LENGTH, so a deny-list that missed it would buffer 512 x 20 MB."""
    from iopstor import public
    with app.test_request_context("/media/some-key.jpg"):
        assert public._cache_key() is None           # the file proxy, not a page
    with app.test_request_context("/products/thing/checkout"):
        assert public._cache_key() is None           # a form
    with app.test_request_context("/warranty?sn=ABC123"):
        assert public._cache_key() is None           # answers per serial number
    with app.test_request_context("/", method="POST"):
        assert public._cache_key() is None
    with app.test_request_context("/about-us"):
        assert public._cache_key() is not None
    with app.test_request_context("/blog?page=2"):
        key = public._cache_key()
    with app.test_request_context("/blog?page=3"):
        assert public._cache_key() != key            # a paged archive is its own entry


def test_a_public_page_tells_shared_caches_it_may_be_served_again(app):
    """Cloudflare is what actually removes the traffic from the box. max-age=0 keeps the visitor's
    own browser revalidating, so a reader never holds a stale page."""
    from flask import Response

    from iopstor import public
    with app.test_request_context("/about-us"):
        cc = public._public_cache_headers(Response("hi", status=200)).headers["Cache-Control"]
    assert "s-maxage=60" in cc and "max-age=0" in cc and "public" in cc

    with app.test_request_context("/about-us"):      # a response that sets a cookie is per-person
        r = Response("hi", status=200)
        r.headers["Set-Cookie"] = "session=abc"
        assert "Cache-Control" not in public._public_cache_headers(r).headers

    with app.test_request_context("/nope"):          # only a 200 is worth repeating
        assert "Cache-Control" not in public._public_cache_headers(Response("no", status=404)).headers


def test_the_page_cache_returns_the_stored_page_and_a_write_drops_it(app, tmp_path, monkeypatch):
    from flask import Response, g

    from iopstor import db, public
    monkeypatch.setattr(db, "EPOCH_FILE", str(tmp_path / "epoch"))
    public._page_cache.clear()

    with app.test_request_context("/about-us"):
        assert public._page_cache_read() is None                     # cold: nothing to serve
        public._public_cache_headers(Response("PAGE ONE", status=200))
    with app.test_request_context("/about-us"):
        served = public._page_cache_read()                           # warm: served without rendering
        assert served is not None and served.get_data() == b"PAGE ONE"
        assert g.page_cached is True

    db.bump_epoch()
    with app.test_request_context("/about-us"):
        assert public._page_cache_read() is None                     # a write drops it at once


def test_a_page_that_stops_existing_is_dropped_not_left_stale(app, tmp_path, monkeypatch):
    """The trap in serve-stale-while-refreshing: if the re-render is a 404 -- the page was trashed or
    unpublished -- the old 200 must go. Leaving it means every CONCURRENT request keeps being handed a
    page that no longer exists, which is the exact traffic shape this cache exists for."""
    from flask import Response

    from iopstor import db, public
    monkeypatch.setattr(db, "EPOCH_FILE", str(tmp_path / "epoch"))
    public._page_cache.clear()

    with app.test_request_context("/going-away"):
        public._page_cache_read()
        public._public_cache_headers(Response("PAGE ONE", status=200))
    db.bump_epoch()                                          # the editor trashes it
    with app.test_request_context("/going-away"):
        assert public._page_cache_read() is None             # stale: this caller re-renders
        public._public_cache_headers(Response("gone", status=404))
    assert "/going-away?" not in public._page_cache
    assert not [k for k in public._page_cache if k.startswith("/going-away")]

    # ...but a failing database must NOT wipe a good page: keep serving the last copy instead.
    public._page_cache.clear()
    with app.test_request_context("/still-here"):
        public._page_cache_read()
        public._public_cache_headers(Response("GOOD", status=200))
    db.bump_epoch()
    with app.test_request_context("/still-here"):
        public._page_cache_read()
        public._public_cache_headers(Response("boom", status=502))
    assert [k for k in public._page_cache if k.startswith("/still-here")]


def test_the_page_cache_stays_within_its_ceiling(app, tmp_path, monkeypatch):
    """full_path includes the query, so a campaign's ?utm_* fills this fast. It must evict rather
    than grow, and storing must not trip over its own trim."""
    from flask import Response

    from iopstor import db, public
    monkeypatch.setattr(db, "EPOCH_FILE", str(tmp_path / "epoch"))
    public._page_cache.clear()
    for i in range(public.PAGE_MAX + 25):
        with app.test_request_context(f"/?utm_source=camp{i}"):
            public._page_cache_read()
            public._public_cache_headers(Response(f"p{i}", status=200))
    assert len(public._page_cache) == public.PAGE_MAX
    with app.test_request_context(f"/?utm_source=camp{public.PAGE_MAX + 24}"):
        assert public._page_cache_read() is not None         # the newest survived the trim


# --- testimonials -------------------------------------------------------------------------------
# A testimonial is a post of a has_pages=false type, so the four things below are the ones that can
# only break silently: a number reaching the page unclamped, the row losing its controls, a card
# with nothing filled in emitting empty markup, and the quotes vanishing from the .md twin because
# they have no URL.

def _testimonial(title="Ada", excerpt="It works.", **meta):
    return {"id": 1, "title": title, "excerpt": excerpt, "meta": meta, "path": None, "terms": [],
            "children": [], "featured_media": None, "published_at": None,
            "post_type": {"slug": "testimonial"}}


def _render_testimonials(app, monkeypatch, posts):
    from iopstor import db
    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(blocks, "_post_list", lambda data: (posts, "testimonial"))
    with app.test_request_context():
        return render_blocks([{"type": "post_list", "data": {"post_type": "testimonial"}}])


def test_a_rating_is_clamped_to_five_stars_and_absent_when_unset(app, monkeypatch):
    """The stars are drawn server-side from a number an editor types into a plain box, so 9 and -3
    have to come out as something sane. And no rating at all means no markup, not five empty stars:
    every field on a testimonial is optional and the card is supposed to close up without them."""
    html = _render_testimonials(app, monkeypatch, [_testimonial(rating=9)])
    assert html.count("★") == 5 and "☆" not in html

    html = _render_testimonials(app, monkeypatch, [_testimonial(rating=-3)])
    assert "stars" not in html

    html = _render_testimonials(app, monkeypatch, [_testimonial(rating=4)])
    assert html.count("★") == 4 and html.count("☆") == 1

    assert "stars" not in _render_testimonials(app, monkeypatch, [_testimonial()])


def test_a_testimonial_card_with_only_a_name_renders_nothing_else(app, monkeypatch):
    """Every field but the name is optional. None of them filled in must not leave an empty <p> or a
    stray comma on the card — which is what a single `role or company` check would have done."""
    html = _render_testimonials(app, monkeypatch, [_testimonial(excerpt="")])
    assert "Ada" in html
    assert "stars" not in html and "card-where" not in html

    html = _render_testimonials(app, monkeypatch, [_testimonial(company="Acme")])
    assert ">Acme<" in html and ", " not in html.split('card-where">')[1].split("<")[0]


def test_only_a_testimonial_list_becomes_a_sliding_row(app, monkeypatch):
    """pl-rail and the arrows are what site.js looks for. They are decided in blocks.py from the
    resolved post type, never from block data, and no other type gets them."""
    html = _render_testimonials(app, monkeypatch, [_testimonial()])
    assert "pl-rail" in html and 'class="rail-nav" hidden' in html and 'data-rail="1"' in html
    # the dots are built by the browser from measured widths, so the server sends the box empty
    assert '<span class="rail-dots"></span>' in html

    from iopstor import db
    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(blocks, "_post_list", lambda data: ([], "partner"))
    with app.test_request_context():
        html = render_blocks([{"type": "post_list", "data": {"post_type": "partner"}}])
    assert "pl-rail" not in html and "rail-nav" not in html


def test_the_rail_controls_stay_hidden_without_the_script():
    """The nav ships `hidden` so a blocked script leaves no buttons that do nothing, and site.js
    re-hides it when the row has nothing to scroll. Neither works without this one CSS rule: the UA
    sheet's `[hidden]{display:none}` is a bare attribute selector and loses to `.rail-nav{display:flex}`
    on specificity, so the attribute silently does nothing — which is what the first screenshot of the
    real home page showed, two dead arrows under two quotes that fit."""
    css = (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "site.css").read_text()
    assert ".rail-nav[hidden]{display:none}" in css


def _site_css():
    return (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "site.css").read_text()


def test_the_hero_clips_the_overshoot_of_its_own_entry_animations():
    """Three hero animations start the element 40-60px to the right and slide it home, and a
    transform counts toward scrollable overflow — so without this the whole PAGE scrolled sideways on
    a phone (measured 61px at 390, 81px at 320). It is invisible to pytest and to a screenshot that
    does not go looking, and `body{overflow-x:clip}` does NOT substitute for it (measured: no change
    at all, and it would cost .site-header its position:sticky)."""
    css = _site_css()
    assert "overflow-x:clip" in css.split(".hero{")[1].split("}")[0]


def test_a_short_testimonial_does_not_pad_out_with_dead_air():
    """Cards in the sliding row are all as tall as the tallest, so the shortest quote gets the
    slack. `align-content:start` dumped it under the card — 65px of white at 390, 92px at 360, and
    worse the narrower the screen. The `1fr` on the quote row hands it to the quote instead, so the
    name and photo sit on the bottom edge."""
    card = _site_css().split(".pl-testimonial .card{")[1].split("}")[0]
    assert "grid-template-rows:auto 1fr auto auto" in card
    assert "align-content:start" not in card


def test_the_mega_menu_keeps_the_order_both_layouts_depend_on():
    """One markup order serves two behaviours, and swapping it breaks both silently. The desktop
    panel opens a pane with `.mega-g:hover+.mega-pane`, which needs the link IMMEDIATELY before its
    pane; the phone's disclosure is `.mg-toggle:checked+.mg-row+.mega-g+.mega-pane`, adjacent the
    whole way because the groups are flat siblings and a `~` would open every group below the one
    tapped. So the checkbox and its label go BEFORE the link, never between it and the pane."""
    html = (pathlib.Path(__file__).parent.parent / "iopstor" / "templates" / "base.html").read_text()
    cats = html.split('class="mega-cats"')[1].split("</div>\n")[0]
    order = [cats.index(x) for x in ('class="mg-toggle"', 'class="mg-row"',
                                     'class="mega-g"', 'class="mega-pane"')]
    assert order == sorted(order), "the mega group's four parts are out of order"

    css = _site_css()
    assert ".mg-toggle:checked+.mg-row+.mega-g+.mega-pane{display:block}" in css
    assert ".mega-g:hover+.mega-pane" in css


def test_a_top_level_menu_item_that_holds_others_collapses_the_same_way():
    """Services and Company get the same four-part order one level up, and the link they replace is
    hidden rather than left to render a second row saying the same word."""
    html = (pathlib.Path(__file__).parent.parent / "iopstor" / "templates" / "base.html").read_text()
    li = html.split("{% for i in menu('header') %}")[1].split("{% endfor %}")[0]
    order = [li.index(x) for x in ('class="nv-toggle"', 'class="nv-row"', '<a href="{{ i.url }}"')]
    assert order == sorted(order), "the top-level item's three parts are out of order"

    css = _site_css()
    assert ".nv-toggle:checked+.nv-row+a+.mega,.nv-toggle:checked+.nv-row+a+.sub{display:block}" in css
    # and it must out-specify `.site-nav>ul>li>a`, which sets display:block at (0,1,3). A bare
    # `.nav-group>a` loses to it and every group renders twice -- once as the row, once as the link.
    assert ".site-nav>ul>li.nav-group>a{display:none}" in css


def test_a_pointer_only_menu_rule_never_escapes_the_desktop_query():
    """`:hover` latches on a touch screen and `:focus-within` fires when a link inside takes focus, so
    a drop-down opened by pointer jams open on a phone. The "nothing hovered, so show the first group"
    rule is worse: at (0,4,0) it out-specifies the phone's plain `.mega-pane{display:none}`, so group
    one would be stuck open. All of them live behind min-width:961px, and the closed default is the
    only thing the two layouts share."""
    css = _site_css()
    assert "@media(min-width:961px){.nav-mega:hover>.mega,.nav-mega:focus-within>.mega{display:block}}" in css
    assert "@media(min-width:961px){.site-nav li:hover>.sub,.site-nav li:focus-within>.sub{display:block}}" in css

    desktop = css.split("@media(min-width:961px){\n")[1].split("\n}")[0]
    assert ".mega-cats:not(:has(:hover,:focus)) .mega-g:nth-of-type(1)+.mega-pane{display:block}" in desktop
    assert ".mega-g:hover+.mega-pane" in desktop
    # the shared closed default is NOT in there: both layouts start from it
    assert ".mega-pane{display:none}" not in desktop and ".mega-pane{display:none}" in css


# --- a case study reads as an article -----------------------------------------------------------
# post.html renders post.featured_media in exactly ONE place, inside the page head, and the page
# head is skipped whole whenever the first block is a hero or a columns -- a hero draws its own
# <h1> and carries its own picture, so two heads on one page is neither. Every case study was
# seeded with a hero holding nothing but the title, which closed that gate on all of them: the
# excerpt, the Industry/Solution chips and the "Main picture" an editor had chosen all vanished
# and the empty hero replaced none of them. The three tests below are the ones that can only fail
# silently -- a page that renders, and is simply missing things nobody notices for a year.

def _case_study(blocks_=(), **kw):
    return {"id": 1, "title": "KLPL — Logistics", "slug": "klpl", "path": "/case-studies/klpl",
            "excerpt": "One platform for trading, accounts and reporting.", "blocks": list(blocks_),
            "meta": {"client": "KLPL"}, "seo": {}, "children": [], "parent_id": None, "menu_order": 0,
            "published_at": "2026-09-01T00:00:00+00:00",
            "featured_media": {"url": "/media/2026/09/klpl.png", "alt": "The KLPL racks"},
            "terms": [{"name": "Logistics", "slug": "logistics", "taxonomy": {"slug": "industry"}}],
            "post_type": {"slug": "case_study", "name": "Case Studies", "url_prefix": "case-studies",
                          "hierarchical": False, "has_pages": True,
                          "field_schema": [{"key": "client", "label": "Client", "type": "text"}]},
            **kw}


def _render_post(app, monkeypatch, post):
    """post.html through base.html, which is the only way the page head is exercised at all. The
    three patches are exactly what public.py's app-wide context processor reaches for."""
    from flask import render_template
    from iopstor import db, public
    monkeypatch.setattr(db, "settings", lambda: {})             # seo.site() reads these
    monkeypatch.setattr(db, "get_menu", lambda slug: [])        # the header and footer menus
    monkeypatch.setattr(public, "_service_nav", lambda: None)   # the mega panel's own posts query
    with app.test_request_context("/case-studies/klpl"):
        return render_template("post.html", post=post, children=[], siblings=False, meta={}, jsonld=[],
                               crumbs=[("Home", "/"), ("Case Studies", "/case-studies"), ("KLPL", "/case-studies/klpl")])


def test_a_case_study_shows_the_main_picture_the_editor_chose(app, monkeypatch):
    """The bug itself: featured_media set, and nothing on the page. Everything else the closed gate
    swallowed is asserted beside it, because each one went missing for the same single reason and
    would go missing again together."""
    html = _render_post(app, monkeypatch, _case_study())
    assert 'class="featured"' in html and "/media/2026/09/klpl.png" in html
    assert 'alt="The KLPL racks"' in html                    # the alt text, not the title fallback
    assert '<h1 class="page-title">' in html                 # the head's own title, not a hero's
    assert "One platform for trading" in html                # the excerpt reads as the lead
    assert '/industry/logistics' in html                     # and the term chips are back


def test_a_case_study_stacks_like_an_article_rather_than_sitting_beside_its_picture(app, monkeypatch):
    """`article` drives three things at once in post.html and the stacking half of it lives in
    site.css, keyed off .pt-<slug>. A slug added to one and not the other renders stacked markup
    with the 440px banner crop meant for a card, which looks deliberate and is not."""
    html = _render_post(app, monkeypatch, _case_study())
    assert "has-media" not in html          # single column: the picture goes under the words
    assert '<p class="eyebrow">' not in html  # the breadcrumb already says "Case Studies"
    assert "<time datetime=" in html        # an article is dated

    css = _site_css()
    assert ".pt-post .page-head,.pt-case_study .page-head{" in css
    assert ".pt-post .page-media img,.pt-case_study .page-media img{" in css


def test_a_hero_still_replaces_the_page_head_for_every_other_page(app, monkeypatch):
    """The gate is not a bug -- it is what stops a hero-led page drawing two titles and two
    pictures. Widening it to "show the featured picture anyway" is the fix that looks obvious and
    puts an editor's Main picture on top of the hero's own. Case studies were taken OUT of the
    hero, not the gate out of post.html."""
    html = _render_post(app, monkeypatch, _case_study([{"type": "hero", "data": {"heading": "KLPL"}}]))
    assert "/media/2026/09/klpl.png" not in html    # no second picture
    assert '<h1 class="page-title">' not in html    # and no second title
    assert html.count("<h1") == 1


def test_a_hero_led_page_gives_its_breadcrumb_room_under_the_header(app, monkeypatch):
    """The hero branch draws the breadcrumb on its own, and .wrap is the side gutter and nothing
    else -- so it sat 10px under the header rule (measured at 1440: text top y=75 against y=123
    on a page with a .page-head). .crumb-bar carries the 48px that .page-head already had, which
    is why the class belongs on that branch only: adding it to both would double the gap."""
    hero = _render_post(app, monkeypatch, _case_study([{"type": "hero", "data": {"heading": "KLPL"}}]))
    assert '<div class="wrap crumb-bar">' in hero
    assert "crumb-bar" not in _render_post(app, monkeypatch, _case_study())
    css = (pathlib.Path(__file__).resolve().parents[1] / "iopstor/static/site.css").read_text()
    assert ".crumb-bar{padding-block:48px 0}" in css


def test_the_seed_does_not_invent_a_hero_for_a_type_that_asked_for_no_blocks(monkeypatch):
    """Where all of the above came from. _post() used to default blocks to a hero holding nothing
    but the title, so any type whose seed entry passed no blocks= -- case studies and events --
    was born with the page-head gate already closed. Products were written around it one call at
    a time; the default is gone from the shared helper instead, so the next type added to the seed
    cannot inherit the same bug a third time."""
    from iopstor import cli, db
    written = {}
    monkeypatch.setattr(db, "table", lambda n: _FakeQ(n))
    monkeypatch.setattr(db, "one", lambda q: None)                       # nothing exists yet
    monkeypatch.setattr(db, "now_iso", lambda: "2026-09-19T00:00:00+00:00")
    monkeypatch.setattr(db, "insert", lambda name, row: (written.update(row), {"id": 1})[1])

    cli._post({"id": 7}, "KLPL — Logistics (Private Cloud)", meta={"client": "KLPL"})
    assert written["blocks"] == []

    # and a caller that does want one still gets exactly what it passed
    cli._post({"id": 7}, "Storage", blocks=[{"type": "hero", "data": {"heading": "Storage"}}])
    assert written["blocks"] == [{"type": "hero", "data": {"heading": "Storage"}}]


def test_a_field_the_editor_cleared_takes_its_whole_section_with_it(app, monkeypatch):
    """Emptying a box does not remove the key -- meta_ keeps "client": "" -- and every section in
    post.html used to draw its container before looking at what went inside, so a cleared field
    left a 32px band with an empty <dl> in it, and a cleared long field an empty section under
    that. The container has to go, not just the row. 0 is a value and stays (user, 2026-09-19)."""
    assert "meta-strip" in _render_post(app, monkeypatch, _case_study())      # the control

    cleared = _render_post(app, monkeypatch, _case_study(meta={"client": ""}))
    assert "meta-strip" not in cleared and "Client" not in cleared

    prose_pt = dict(_case_study()["post_type"],
                    field_schema=[{"key": "challenge", "label": "Challenge", "type": "textarea"}])
    blank = _render_post(app, monkeypatch, _case_study(meta={"challenge": ""}, post_type=prose_pt))
    assert "meta-prose" not in blank and "Challenge" not in blank

    kept = _render_post(app, monkeypatch, _case_study(meta={"challenge": "Three systems."}, post_type=prose_pt))
    assert "meta-prose" in kept and "Three systems." in kept

    zero_pt = dict(_case_study()["post_type"],
                   field_schema=[{"key": "rating", "label": "Rating", "type": "number"}])
    assert ">0<" in _render_post(app, monkeypatch, _case_study(meta={"rating": 0}, post_type=zero_pt))


def test_a_types_short_fields_are_page_content_rather_than_a_callout():
    """The client asked for the value not to be highlighted (user, 2026-09-19): the grey band and
    the white card are both gone, and the label/value pairing is what is left. The band's padding
    stays -- it is the gap between the head and the writing -- so only the paint is removed."""
    css = _site_css()
    assert ".meta-strip{padding:32px 0}" in css          # no background
    assert ".details>div{" not in css                    # no card around each pair
    assert ".details dt{" in css and ".details dd{" in css   # the pairing itself is untouched


# --- the hero's two new switches ----------------------------------------------------------------
# Both land in a class attribute, so both are whitelists rather than anything an editor types:
# `still` is a checkbox and `arrange` is compared against three literals. The pair below is what
# can only fail silently -- a class that stops matching, and a value that reaches the attribute.

def _hero(**data):
    from iopstor.blocks import render_blocks
    with _hero.app.test_request_context("/"):
        return render_blocks([{"type": "hero", "data": {"heading": "H", "image": 1, **data}}])


def _hero_classes(html):
    return re.search(r'<section class="([^"]*)"', html).group(1).split()


def test_the_hero_picture_can_sit_beside_above_or_below_the_words(app):
    """Three arrangements out of one grid: .hero>.wrap is already a single column, so "below" is the
    markup on its own, "beside" is the two-column .hero-split it has always been, and only "above"
    needs a rule. `order`, not a DOM swap, so the heading is still read first either way."""
    _hero.app = app
    assert "hero-split" in _hero_classes(_hero())                       # unchanged default
    assert "hero-above" in _hero_classes(_hero(arrange="above"))
    assert "hero-below" in _hero_classes(_hero(arrange="below"))
    for pos in ("above", "below"):                                      # an arrangement is not a split
        assert "hero-split" not in _hero_classes(_hero(arrange=pos))

    # a dark hero has no arrangement -- its picture is the backdrop, not a column
    assert _hero_classes(_hero(dark=True, arrange="above")) == ["hero", "hero-dark"]
    # and with no picture there is nothing to arrange
    assert _hero_classes(_hero(image=None, arrange="above")) == ["hero"]

    css = _site_css()
    assert ".hero-above .hero-media{order:-1}" in css
    assert ".hero-split .hero-text,.hero-above .hero-text,.hero-below .hero-text{" in css


def test_nothing_an_editor_types_reaches_the_hero_class_attribute(app):
    """`arrange` is compared against three literals and never interpolated -- the same rule
    hero.dark follows, and the reason section_class() exists. Anything else falls back to the
    layout the hero has always had."""
    _hero.app = app
    for junk in ('" onload="x', "<script>", "above below", "ABOVE", "  above", "hero-dark"):
        classes = _hero_classes(_hero(arrange=junk))
        assert classes == ["hero", "hero-split"], f"{junk!r} produced {classes}"


def test_holding_the_hero_still_stops_the_loops_and_keeps_the_entrance(app):
    """The ask was "it settles, then holds still": the one-shot arrival plays, the two perpetual
    loops do not. So the rule names the elements carrying `float` and `glow` and deliberately NOT
    .hero-media, whose own animation IS the entrance -- and not .hero-slide, so several pictures
    go on taking turns."""
    _hero.app = app
    assert "hero-still" in _hero_classes(_hero(still=True))
    assert "hero-still" not in _hero_classes(_hero())

    css = _site_css()
    rule = ".hero-still .hero-media::before,.hero-still .hero-media>img,.hero-still .hero-slides{animation:none}"
    assert rule in css
    assert ".hero-still .hero-media{" not in css      # the entrance survives
    assert ".hero-still .hero-slide{" not in css      # and so does the rotation
    # the two loops it switches off are still there for a hero that does not ask
    assert "animation:float 6s ease-in-out infinite" in css and "animation:glow 5s ease-in-out infinite" in css


def test_both_new_hero_keys_are_scalars_not_prose(app):
    """EDITOR["scalars"] is what the editor consults to decide which keys become shared, word-by-word
    text. A flag left out of it is not just leaked into llms-full.txt and admin search -- it is
    co-edited as prose by two browsers."""
    from iopstor.blocks import BLOCKS, EDITOR, blocks_text
    for key in ("still", "arrange"):
        assert key in BLOCKS["hero"][1], f"{key} is not a declared hero field"
        assert key in EDITOR["scalars"], f"{key} would be co-edited as prose"
    assert "above" not in blocks_text([{"type": "hero", "data": {"heading": "H", "arrange": "above"}}])


def test_the_form_warns_when_an_opening_section_will_hide_the_featured_image(app, monkeypatch):
    """The trap this closes cost a real page: a Featured image was chosen, the page opened with a
    Hero, and post.html's page head -- the only thing that renders that picture -- was skipped, so
    nothing appeared and nothing said why. The flag is read off the WORKING content, so it follows
    the unpublished draft the editor is looking at rather than what is live."""
    from iopstor import db
    from iopstor.admin_ui import _form_context

    monkeypatch.setattr(db, "table", lambda n: _FakeQ(n))
    monkeypatch.setattr(db, "rows", lambda q: [])
    pt = {"id": 1, "slug": "case_study", "hierarchical": False, "taxonomies": [], "field_schema": []}

    def flag(blocks, draft=None):
        from flask import g
        monkeypatch.setattr(db, "get_draft", lambda pk: draft)
        with app.test_request_context("/admin/posts/7"):
            g.user = {"id": "0f8b2c1a-0000-4000-8000-000000000001",   # _rt() reads the first 8 hex for a colour
                      "email": "zz@zz-test.local", "name": "", "role": "admin"}
            return _form_context(pt, {"id": 7, "blocks": blocks, "terms": []})["leads_with_own_head"]

    assert flag([{"type": "hero", "data": {}}]) is True
    assert flag([{"type": "columns", "data": {}}]) is True      # columns draws its own head too
    assert flag([{"type": "rich_text", "data": {}}]) is False
    assert flag([]) is False
    assert flag([{"type": "rich_text", "data": {}}, {"type": "hero", "data": {}}]) is False   # only the FIRST

    # the draft wins over what is published, because the draft is what the editor is looking at
    assert flag([{"type": "rich_text", "data": {}}], draft={"blocks": [{"type": "hero", "data": {}}]}) is True
    assert flag([{"type": "hero", "data": {}}], draft={"blocks": [{"type": "rich_text", "data": {}}]}) is False


def test_the_glow_behind_the_hero_picture_can_be_taken_out_not_just_stilled(app):
    """Two controls, deliberately not one. `still` only stops the keyframes, and `glow` runs its
    0%/100% at opacity .7 — so a STILLED glow sits at the element's own opacity 1 and reads as more
    present, not less. Hiding it is therefore its own switch, and the two compose."""
    _hero.app = app
    assert "hero-noglow" in _hero_classes(_hero(noglow=True))
    assert "hero-noglow" not in _hero_classes(_hero())
    assert _hero_classes(_hero(still=True, noglow=True)) == ["hero", "hero-still", "hero-noglow", "hero-split"]

    css = _site_css()
    assert ".hero-noglow .hero-media::before{display:none}" in css
    # the two rules are separate: stilling must not start hiding, or the pair stops composing
    assert ".hero-still .hero-media::before,.hero-still .hero-media>img,.hero-still .hero-slides{animation:none}" in css
    # and the glow is still there for a hero that asks for neither
    assert "animation:glow 5s ease-in-out infinite" in css

    from iopstor.blocks import BLOCKS, EDITOR
    assert "noglow" in BLOCKS["hero"][1] and "noglow" in EDITOR["scalars"]


# --- where a type's long fields land among the sections -----------------------------------------
# Challenge / Solution / Results are the type's own boxes, not sections, so they are the one piece
# of page content an editor cannot drag. `meta._details_at` says where they go and details_at()
# turns it into a cut. Everything below is an ordering, which no assertion about markup existing
# would catch -- the old bug was that they were ALWAYS above the hero, and every section rendered.

def _prose_pt(**kw):
    return {"id": 1, "slug": "case_study", "name": "Case Studies", "url_prefix": "case-studies",
            "hierarchical": False, "has_pages": True,
            "field_schema": [{"key": "client", "label": "Client", "type": "text"},
                             {"key": "challenge", "label": "Challenge", "type": "textarea"}], **kw}


def _ordered(app, monkeypatch, at, n_sections=3):
    post = {"id": 1, "title": "T", "slug": "t", "path": "/x", "excerpt": "", "terms": [], "children": [],
            "published_at": None, "featured_media": None, "seo": {}, "post_type": _prose_pt(),
            "meta": {"client": "KLPL", "challenge": "It was hard.", "_details_at": at},
            "blocks": [{"type": "rich_text", "data": {"html": f"<p>S{i}</p>"}} for i in range(1, n_sections + 1)]}
    html = _render_post(app, monkeypatch, post)
    body = html[html.find("<article"):html.find("</article>")]
    return re.findall(r"meta-strip|meta-prose|<p>S[0-9]</p>", body)


def test_the_long_details_land_where_the_setting_says(app, monkeypatch):
    """Six positions and two fallbacks, asserted as an ORDER. A page that renders every part in the
    wrong sequence passes any "is it there" check, which is exactly how they ended up above the
    hero on every case study."""
    S1, S2, S3, STRIP, PROSE = "<p>S1</p>", "<p>S2</p>", "<p>S3</p>", "meta-strip", "meta-prose"
    assert _ordered(app, monkeypatch, "") == [STRIP, PROSE, S1, S2, S3]        # unchanged default
    assert _ordered(app, monkeypatch, "top") == [PROSE, STRIP, S1, S2, S3]
    assert _ordered(app, monkeypatch, "1") == [STRIP, S1, PROSE, S2, S3]
    assert _ordered(app, monkeypatch, "2") == [STRIP, S1, S2, PROSE, S3]
    assert _ordered(app, monkeypatch, "end") == [STRIP, S1, S2, S3, PROSE]
    # a section that has since been deleted clamps; anything unrecognised reads as the default,
    # so an older post and a mistyped value both render exactly as they did before this existed
    assert _ordered(app, monkeypatch, "99") == [STRIP, S1, S2, S3, PROSE]
    assert _ordered(app, monkeypatch, "nonsense") == [STRIP, PROSE, S1, S2, S3]
    assert _ordered(app, monkeypatch, "") == _ordered(app, monkeypatch, None)


def test_details_at_reads_the_setting_and_clamps_it():
    """The cut on its own: -1 above the strip, 0 where they have always been, n after n sections."""
    from iopstor.blocks import details_at
    p = lambda at, n=3: {"blocks": [{"type": "rich_text"}] * n, "meta": {"_details_at": at}}
    assert details_at(p("top")) == -1
    assert details_at(p("")) == 0 and details_at(p(None)) == 0 and details_at(p("nope")) == 0
    assert details_at(p("1")) == 1 and details_at(p("3")) == 3
    assert details_at(p("end")) == 3
    assert details_at(p("9")) == 3                      # the sections it counted past are gone
    assert details_at(p("2", n=0)) == 0                 # and a page with none at all
    assert details_at({}) == 0                          # no blocks, no meta


def test_the_form_offers_a_spot_per_section_and_keeps_the_choice(app, monkeypatch):
    """Offered only for a type that HAS a long field, or it is a control over nothing. And it must
    survive a save it was not part of -- the JSON API posts no form, and blanking the setting on
    every API write would move the content without anybody asking."""
    from flask import g
    from iopstor import db
    from iopstor.admin_ui import _form_body, _form_context
    monkeypatch.setattr(db, "table", lambda n: _FakeQ(n))
    monkeypatch.setattr(db, "rows", lambda q: [])
    monkeypatch.setattr(db, "get_draft", lambda pk: None)
    post = {"id": 7, "blocks": [{"type": "hero", "data": {}}, {"type": "cta", "data": {}}],
            "terms": [], "meta": {"_details_at": "1"}}

    with app.test_request_context("/admin/posts/7"):
        g.user = {"id": "0f8b2c1a-0000-4000-8000-000000000001", "email": "t@t", "name": "", "role": "admin"}
        ctx = _form_context(_prose_pt(), post)
        assert [v for v, _ in ctx["details_spots"]] == ["top", "", "1", "2", "end"]
        assert "Hero" in ctx["details_spots"][2][1] and "Call to action" in ctx["details_spots"][3][1]
        assert ctx["details_at"] == "1"
        # a type with no long field is offered nothing
        bare = dict(_prose_pt(), field_schema=[{"key": "client", "label": "Client", "type": "text"}])
        assert _form_context(bare, post)["details_spots"] == []

    with app.test_request_context("/admin/posts/7", method="POST",
                                 data={"title": "T", "slug": "t", "status": "published", "details_at": "2"}):
        assert _form_body(_prose_pt(), post)["meta"]["_details_at"] == "2"
    with app.test_request_context("/admin/posts/7", method="POST",
                                  data={"title": "T", "slug": "t", "status": "published"}):
        assert _form_body(_prose_pt(), post)["meta"]["_details_at"] == "1"      # untouched, not blanked


# --- how much air a section keeps ----------------------------------------------------------------
# The seventh layout key. Only ever LESS than the design's 80px: adding space is a Spacer, and
# keeping the two apart is what lets both exist (design.md, 2026-09-10). The whole mechanism rests
# on CSS source order, which no assertion about a rule merely existing would catch.

def test_section_padding_is_a_whitelist():
    """Same shape as the other six: the value lands in a class attribute, so nothing an editor can
    type reaches it. 'large' is refused on purpose -- it is not a step, it is a Spacer."""
    from iopstor.blocks import PADS, section_class
    assert PADS == ("none", "small", "medium")
    assert section_class({"pad": "none"}) == " pad-none"
    assert section_class({"pad": "medium"}) == " pad-medium"
    for junk in ('x" onload="', "<script>", "large", "PAD-NONE", "none small", " none", "", None, 1, {}):
        assert section_class({"pad": junk}) == "", f"{junk!r} reached the class attribute"
    # and it composes with the six that were already there, in section_class's own order
    assert section_class({"pad": "small", "tone": "grey", "align": "center"}) == " al-center t-grey pad-small"

    from iopstor.blocks import BLOCKS, EDITOR
    assert "pad" in EDITOR["scalars"], "pad would be co-edited as prose"
    assert not any("pad" in req + opt for req, opt in BLOCKS.values()), "pad is universal, not a block field"


def test_the_padding_rules_sit_after_everything_they_have_to_beat():
    """Every conflict is a specificity TIE, so placement is the mechanism rather than tidiness.
    Move the group earlier and it silently loses to whichever rule it now precedes -- and a
    stylesheet cannot report that. Three selectors because `.hero` is not a `.section`."""
    css = _site_css()
    for step, px in (("none", "0"), ("small", "24px"), ("medium", "40px")):
        rule = (f".section.pad-{step}:not(.spacer),.hero.pad-{step},"
                f".column>.section.pad-{step}:not(.spacer){{padding-block:{px}}}")
        assert rule in css, f"missing or reshaped: {rule}"

    first = css.index(".section.pad-none")
    for earlier in (".column>.section.divider{", ".band-dark.section{", ".divider{padding",
                    ".column>.section.t-grey", ".column>.section+.section{"):
        assert css.index(earlier) < first, f"{earlier} must come BEFORE the pad group, or the tie goes the wrong way"

    # padding-block, not the shorthand: a toned section in a column is a card and keeps its sides
    assert "pad-none:not(.spacer){padding:" not in css
    # and the canvas gives a flattened divider something to click, which the page must not have
    canvas = (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "canvas.css").read_text()
    assert ".iop-canvas .divider.pad-none{padding-block:8px}" in canvas
    assert ".iop-canvas" not in css


def test_the_editors_spacing_options_match_the_python_whitelist():
    """ALIGNMENTS, WIDTHS and TONES are hand-written JS duplicating a Python whitelist with nothing
    checking they agree -- only `fx` is guarded, because it travels through EDITOR["choices"].
    This is the one of the five that cannot drift silently."""
    from iopstor.blocks import PADS
    js = (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "admin.js").read_text()
    literal = re.search(r"var PADS = \[(.*?)\];", js, re.S)
    assert literal, "the PADS literal in admin.js has moved or been renamed"
    values = re.findall(r'\["([^"]*)",', literal.group(1))
    assert values == [""] + list(PADS), f"admin.js offers {values}, blocks.py allows {PADS}"
    # offered on every section but a spacer, whose Height already is its spacing
    assert 'if (block.type !== "spacer") body.appendChild(padPick(block.data));' in js
    assert "else delete data.pad;" in js, "an untouched section must stay byte-identical in the JSON"
def test_opening_a_dropdown_in_the_section_panel_does_not_repaint_the_section():
    """The settings popover schedules a section re-render on input, change AND click, because
    fieldInput() mutates in place and reports nothing. `click` is there for the panel's BUTTONS --
    a repeater's + Add and its X, the media browser -- which change data and fire nothing else.

    It must not fire for a click on a form control. That click changes nothing by itself, and on a
    <select> it is the click that OPENS the native dropdown: 250ms later canvasBlock() replaces the
    section under it and the menu is dismissed before anybody can choose. Reported by the client as
    "it kind of refreshes and the dropdown closes before i select something".

    A source assertion because the handler is a closure inside openPanel(), which no harness here
    can reach -- the same reason /collab-check pins some of admin.js by shape. It was proved in a
    real browser instead: driving the actual editor with the database stubbed and counting
    /admin/canvas round trips, clicking a <select> went 1 -> 0 while changing one stayed at 1 and a
    repeater button stayed at 1."""
    js = (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "admin.js").read_text()
    guard = 'if (ev === "click" && /^(SELECT|OPTION|INPUT|TEXTAREA|LABEL)$/.test(e.target.tagName)) return;'
    assert guard in js, "the settings panel would repaint on merely opening a dropdown again"

    # the guard is worthless if the handler stops receiving the event, or stops watching clicks at
    # all -- buttons are the reason click is in the list
    handler = js[js.index('["input", "change", "click"].forEach'):]
    handler = handler[:handler.index("panelPlace =")]
    assert "function (e) {" in handler, "the handler needs the event to read e.target"
    assert guard in handler, "the guard must live in the popover's own listener, not somewhere else"
    assert "canvasBlock(panelAt)" in handler and "markDirty()" in handler


# --- the search and share cards are a view, not a postscript --------------------------------------
# Preview shows the page and nothing else; the cards are the fourth button in the width row. The
# switching lives in closures admin.js never exports, so these pin the shape and the browser
# measurement is the evidence: page view 1 render + 0 cards, cards view 0 + 1, where both halves
# used to be fetched on every beat.

def _admin_js():
    return (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "admin.js").read_text()


def test_each_half_of_preview_fetches_only_itself():
    """renderPreview() asked the server for the page AND the cards every time, in parallel, and
    both are a full _form_body() + _preview_post() + build_meta() -- the page one 8-11 Supabase
    round trips. Measured through the real buttons: 2 renders a beat became 1."""
    js = _admin_js()
    assert 'var VIEW = "edit", DEVICE = 1440, PVPART = "page";' in js

    body = js[js.index("function renderPreview()"):]
    body = body[:body.index("function fitPreview")]
    assert 'if (PVPART === "seo") {' in body, "renderPreview no longer routes by half"
    assert body.count("askPreview(") == 2, "one fetch per half, not both every time"
    # the card fetch must be inside the seo branch, i.e. before the page fetch returns
    assert body.index('askPreview("card"') < body.index('askPreview("", function'), \
        "the card fetch drifted back out of the branch and runs unconditionally again"


def test_the_cards_view_is_a_sub_state_so_the_twelve_VIEW_reads_keep_their_meaning():
    """Three of the reads of VIEW are collaboration, not rendering -- peer markers, `edit:` on the
    presence wire, and canWrite() disqualifying a previewing tab from autosaving. A fourth VIEW
    value would have had to be audited into all of them; a sub-state leaves every one alone."""
    js = _admin_js()
    assert js.count('VIEW = ') == 2, "VIEW should still be written in exactly one place (plus its declaration)"
    for collab in ('if (VIEW === "preview") return;', 'edit: VIEW !== "preview"',
                   'if (!chan || VIEW === "preview") return false;'):
        assert collab in js, f"a collaboration guard changed shape: {collab}"


def test_returning_from_the_cards_cannot_leave_the_frame_scaled_to_nothing():
    """#canvas-wrap hidden means clientWidth 0, so fitPreview() would compute scale(0) and the page
    would come back invisible. pvParts() unhides first; the order is the fix, so pin the order."""
    js = _admin_js()
    assert 'if (VIEW !== "preview" || PVPART === "seo") {' in js, "fitPreview would measure a hidden wrap"

    handler = js[js.index("function initPreview()"):]
    handler = handler[:handler.index("window.addEventListener(\"resize\"")]
    assert handler.index("pvParts();") < handler.index("fitPreview();"), \
        "pvParts() must unhide BEFORE fitPreview() measures, or the frame returns at scale(0)"
    assert 'if (b.hasAttribute("data-pv")) PVPART = "seo";' in handler
    assert 'DEVICE = +b.getAttribute("data-w")' in handler
    # the fourth button carries data-pv, never data-w, or DEVICE becomes NaN
    form = (pathlib.Path(__file__).parent.parent / "iopstor" / "templates" / "admin" / "post_form.html").read_text()
    assert '<button type="button" data-pv="seo">' in form
    assert form.count('data-w="') == 3, "the width buttons should still be exactly three"

    css = (pathlib.Path(__file__).parent.parent / "iopstor" / "static" / "admin.css").read_text()
    assert ".ed-main:has(#canvas-wrap[hidden]) #seo-card{" in css, "the cards never take the pane"
    # the bar was already clipping Publish at 700 before a fourth button existed; it wraps now
    assert ".ed-bar{flex-wrap:wrap}" in css, "a fourth button with no room pushes Save off the bar"
