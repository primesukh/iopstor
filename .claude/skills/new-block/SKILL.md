---
name: new-block
description: Use when adding, renaming or reshaping a section/block type in the page editor — a new entry in BLOCKS, a new field on an existing block, a new repeater — or when asked for "a new section", "a new block", "a new kind of band on the page".
---

# A block lives in eleven places

`iopstor/blocks.py` is the only place a type is *declared*, but a type that is declared and nothing else renders as a bare box, cannot be inserted, and never reaches the `.md` twins. Two offline tests fail until the set is complete (a third only for a new field key); the template is the one thing **no test checks**.

## Checklist

1. **`BLOCKS["<type>"] = (required, optional)`** — comment the shape of any repeater row (`items: [{title, text}]`). Only what must be present goes in `required`; `validate_blocks()` refuses `""`/`None`/`[]` there, so an optional link must sit in the second list. A field whose value lands in a class or style attribute is a checkbox or a whitelist, never free text (`hero.dark`, `section_class()`); a coloured strip uses the universal `tone` key or a fixed `band-*` class, not a colour field.
2. **Field names first** — five dicts key off them. Reuse an existing key (`text`, `heading`, `cta_label`/`cta_url`, `link_label`/`link_url`, `media_id`) and its widget, label and text-order come free. `EDITOR["labels"]` is keyed by the **bare** field name with no per-block override (only `widgets` has `"<type>.<field>"`), so a reused key wears the same label in the ⚙ panel (`link_label` reads "Header link text" everywhere) and there is no per-block escape hatch: widen the shared label — NON-TECHNICAL.md quotes those strings, so update it — or pick a key whose label already fits. Only the canvas placeholder can differ, via `fe('key', ph='…')`.
3. **`EDITOR`** in the same file:
   - `widgets` for every non-text field (`textarea | code | richtext | media | pdf | url | number | checkbox | choice | post_type | kind`); a `choice` also needs its `[value, label]` pairs in `choices`, keyed by the **bare** field name
   - `items["<type>"]` = the subfields of one repeater row, if it has `items | images | rows`
   - `labels` for any new key that is not readable as-is
   - `order` — where the picker offers it; a type missing from `order` is appended last
   - `names["<type>"] = (icon, plain-English name, one line ending in a full stop)`
   - `seed["<type>"]` — starting content whose keys are all declared fields and which **passes `validate_blocks()`**; only `image`, `gallery`, `pdf` are exempt (a picture cannot be faked)
4. **`templates/blocks/<type>.html`** — `<section class="section <type>{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap">…</div></section>`; a fixed band class goes *before* `{{ cls }}` so an editor's tone wins on source order — and know that `.band-blue.section` / `.band-dark.section` already carry the CTA's and the stats band's padding, so a "slim" strip that reuses one inherits 64px unless its own class overrides it. Markers tight against the tag: `<h2{{ fe('heading') }}>`, `{{ fe('items', loop.index0) }}` on a repeater row, `fe('html', rich=True)` for HTML. No `<h1>` — only `hero` owns one. No `|safe` unless the field is raw HTML by design.
5. **`blocks_md()`** — one `elif` branch producing Markdown, or add the type to `MD_SKIP` only if it is genuinely not words (an iframe).
6. **`_TEXT_ORDER` / `_NON_TEXT_KEYS`** — a new *text* key goes into the reading order; a new URL/id/flag key goes into the non-text set, or it leaks into `llms-full.txt`, the feed and admin search.
7. **Render-time data?** Extend the `extra` branch in `render_blocks()` the way `post_list` / `warranty_check` do. `edit=True` must never query the database.
8. **Nesting** — full-bleed or owns the page's H1 → add to `NEVER_NESTED` **and** the mirror array in `admin.js`. Otherwise leaving it out is the decision: it may live in a column, so check it at column width.
9. **`static/site.css`** — one rule group in the per-block region. Scope padding changes to the block's own class, never to the shared `.band-*`; declare its measure as `--w-def` on the block element so the editor's Width control works; `.column>` variant if it looks wrong as a panel.
10. **Tests** — `pipenv run pytest tests/test_offline.py -q`. The gates, in the order they break: `test_inserter_metadata_and_seeds` (`names`, `seed`, seed keys declared, seed validates) and `test_blocks_md_covers_every_block` (the branch) always; `test_editor_metadata_covers_every_block` only for a new field key with an unknown widget name or a repeater without `items`; `test_layouts_expand_and_validate` only if `LAYOUTS` changed. **Nothing asserts the template exists** — `test_render_blocks_uses_template` renders only `hero` and `stats` — so render the seeded block once (`/theme-check`, or `render_blocks([{"type": t, "data": EDITOR["seed"][t]}])` in a shell); a missing template is a 500 on the public page. Any branch or parser of its own gets one small test.
11. **Docs** — `/docs`. The type count is stated in four places and all four move: TECHNICAL.md §6 ("Sixteen types ship" + the list) and §12.1 ("the other fifteen types"), `CLAUDE.md`'s layout line for `blocks/<type>.html`, design.md §5. Then TECHNICAL.md §6's shape paragraph, §16 only if the way in changed; NON-TECHNICAL.md §4 *Adding a section* list and a §13 *Quick answers* line. Seed (`cli.py`) only if a seeded page wants it — and you do not run the seed.

Then `/theme-check` at three widths, on a page that has the section inside a Columns section too.

## What usually needs nothing

`admin.js` — the editor is driven by `SPEC` (`#editor-data` from `post_form.html`, the same `BLOCKS` + `EDITOR` that `GET /api/admin/v1/blocks` serves). Its `BLOCK_NAMES` literal is a fallback consulted after `EDITOR["names"]`. It changes only for a new *widget* type or a new nesting rule. `canvas.css` (only `pdf` needs chrome), `validate_blocks()`, `apply_post()`, `seo.py`, `public.py`, `post.html` — untouched.

## Common mistakes

| Symptom | Cause |
|---|---|
| `KeyError` in `test_inserter_metadata_and_seeds` | `EDITOR["names"]` or `EDITOR["seed"]` missing |
| Inserting it saves as invalid | seed does not satisfy `required`, or carries a key that is not declared |
| Words missing from `/page.md` | no `blocks_md()` branch |
| `<h2 >` with a space in the public HTML | marker not tight against the tag |
| A width set on it does nothing | measure written as a fixed `max-width` instead of `--w-def` |
| Every CTA band on the site changed height | padding written on `.band-blue` instead of the block's own class |
| Works on the page, broken inside Columns | never checked at column width; `.column>.section` neutralises padding |
| "This section is not finished yet" on the canvas, 500 on the page | the template is missing or throws — no test would have said so |
