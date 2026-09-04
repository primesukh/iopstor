"""Pure logic — no Supabase needed."""
from iopstor.blocks import blocks_text, render_blocks, validate_blocks
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
                assert EDITOR["items"].get(name), f"{name}.{field} is a repeater with no EDITOR['items'] entry"
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
    """The PDF section is an iframe at the file plus a link out — no viewer library, and a way in
    for the mobile browsers that will not render a framed PDF."""
    from iopstor import db

    monkeypatch.setattr(db, "settings", lambda: {})
    monkeypatch.setattr(db, "get_menu", lambda slug: [])
    monkeypatch.setattr(db, "get_media", lambda pk: {"url": "https://x/media/a.pdf"})

    html = render_blocks([{"type": "pdf", "data": {"file_media_id": 7, "heading": "Datasheet"}}])
    assert '<iframe src="https://x/media/a.pdf#view=FitH"' in html
    assert 'href="https://x/media/a.pdf"' in html and ">Open the PDF</a>" in html
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
