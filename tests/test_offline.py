"""Pure logic — no Supabase needed."""
from iopstor.blocks import at_path, blocks_text, col_widths, render_blocks, validate_blocks
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
    html = render_blocks([{"type": "hero", "data": {"heading": "Fast <NAS>"}}, {"type": "stats", "data": {"items": [{"value": "5PB", "label": "per rack"}]}}])
    assert "<h1>Fast &lt;NAS&gt;</h1>" in html and "5PB" in html


def test_blocks_text_flattens():
    txt = blocks_text([{"type": "rich_text", "data": {"html": "<p>Hello <b>world</b></p>"}}, {"type": "cta", "data": {"heading": "Go", "button_label": "Now", "button_url": "/x"}}])
    assert txt == "Hello world Go Now"


def test_jwt_matrix_without_db(client):
    assert client.get("/api/admin/v1/posts").status_code == 401
    assert client.get("/api/admin/v1/posts", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_editor_metadata_covers_every_block():
    """Adding a block without editor metadata leaves /admin unable to render its fields."""
    from iopstor.blocks import BLOCKS, EDITOR, REPEATERS

    for name, (required, optional) in BLOCKS.items():
        for field in required + optional:
            widget = EDITOR["widgets"].get(f"{name}.{field}") or EDITOR["widgets"].get(field) or "text"
            assert widget in ("text", "textarea", "code", "richtext", "media", "pdf", "url", "number", "checkbox", "post_type", "kind"), (name, field)
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


def test_pdf_block_renders_the_browser_viewer(app, monkeypatch):
    """The PDF section is an iframe at the file plus a download button — no viewer library, and a way
    in for the mobile browsers that will not render a framed PDF. The button saves the file under the
    name it was uploaded with, not the uuid its bucket key is made of."""
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(db, "get_media", lambda pk: {"url": "https://x/media/a.pdf", "filename": "flash array.pdf"})

    html = render_blocks([{"type": "pdf", "data": {"file_media_id": 7, "heading": "Datasheet"}}])
    assert '<iframe src="https://x/media/a.pdf#view=FitH"' in html
    assert 'href="https://x/media/a.pdf?download=flash%20array.pdf"' in html and ">Download the PDF</a>" in html
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
