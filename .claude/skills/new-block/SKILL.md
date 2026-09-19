---
name: new-block
description: Use when adding, renaming or reshaping a section/block type in the page editor — a new entry in BLOCKS, a new field on an existing block, a new repeater — or when asked for "a new section", "a new block", "a new kind of band on the page".
---

# A block lives in eleven places

`iopstor/blocks.py` is the only place a type is *declared*, but a type that is declared and nothing else renders as a bare box, cannot be inserted, and never reaches the `.md` twins. Two offline tests fail until the set is complete (a third only for a new field key), and since 2026-09-15 a fourth renders every seeded type so a missing or throwing template is caught too.

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
4. **`templates/blocks/<type>.html`** — `<section class="section{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap"><div class="<type>">…</div></div></section>`. **The block's own class goes on an INNER element, not on the `<section>`** — `.rich-text`, `.cta`, `.specs` and `.lead-form` all do, and step 9's measure is why: `.wrap` is the page gutter, so a `max-width` on the section shrinks the section itself and it stops centring, and the band loses its gutter and sits against the left edge (seen 2026-09-15 on `points`; no test catches it, only a before/after render did). A fixed *band* class like `band-blue` is the exception and does go on the section, *before* `{{ cls }}` so an editor's tone wins on source order — and know that `.band-blue.section` / `.band-dark.section` already carry the CTA's and the stats band's padding, so a "slim" strip that reuses one inherits 64px unless its own class overrides it. Markers tight against the tag: `<h2{{ fe('heading') }}>`, `{{ fe('items', loop.index0) }}` on a repeater row, `fe('html', rich=True)` for HTML. No `<h1>` — only `hero` owns one. No `|safe` unless the field is raw HTML by design.
5. **`blocks_md()`** — one `elif` branch producing Markdown, or add the type to `MD_SKIP` only if it is genuinely not words (an iframe).
6. **`_TEXT_ORDER` / `_NON_TEXT_KEYS`** — a new *text* key goes into the reading order; a new URL/id/flag key goes into the non-text set, or it leaks into `llms-full.txt`, the feed and admin search. The set has a second reader since 2026-09-15: it reaches the browser as `EDITOR["scalars"]`, and the editor turns **every string key not in it into shared, word-by-word text** (a `Y.Text`) — so a URL left out of the set is not only leaked, it is co-edited as prose. Repeater rows (`items`/`rows`) ride as one value and stay focus-wins; that is a named ceiling, not a bug to fix in passing.
7. **Render-time data?** Extend the `extra` branch in `render_blocks()` the way `post_list` / `warranty_check` do. `edit=True` must never query the database.
8. **Nesting** — full-bleed or owns the page's H1 → add to `NEVER_NESTED` **and** the mirror array in `admin.js`. Otherwise leaving it out is the decision: it may live in a column, so check it at column width.
9. **`static/site.css`** — one rule group in the per-block region. Scope padding changes to the block's own class, never to the shared `.band-*`; declare its measure as `--w-def` on the block element so the editor's Width control works; `.column>` variant if it looks wrong as a panel.
10. **Tests** — `pipenv run pytest tests/test_offline.py -q`. The gates, in the order they break: `test_inserter_metadata_and_seeds` (`names`, `seed`, seed keys declared, seed validates), `test_blocks_md_covers_every_block` (the branch) and `test_every_block_type_has_a_template_that_renders` (every seeded type, both modes; `post_list` excluded because it queries at render time in both) always; `test_editor_metadata_covers_every_block` only for a new field key with an unknown widget name or a repeater without `items`; `test_layouts_expand_and_validate` only if `LAYOUTS` changed. `test_render_blocks_uses_template` checks the markers on `hero` and `stats` only, so a marker with a space in it on a new type is found by rendering, not by that test. Any branch or parser of its own gets one small test.
11. **Docs** — `/docs`. The type count is stated in four places and all four move: TECHNICAL.md §6 ("Twenty types ship" + the list) and §12.1 ("the other nineteen types"), `CLAUDE.md`'s layout line for `blocks/<type>.html`, design.md §5. Then TECHNICAL.md §6's shape paragraph, §16 only if the way in changed; NON-TECHNICAL.md §4 *Adding a section* list and a *Quick answers* line (that section is last; its number moves). Seed (`cli.py`) only if a seeded page wants it — and you do not run the seed.

12. **Moving live content into the new type** — when the type exists because a designed section had been living as `rich_text` (`points`, `definitions`, 2026-09-15), the live rows move by a content migration (`/migration`: matched by content, `post_drafts` and `_rich` handled in the same file) and the seed (`cli.py`) builds the shape instead of flattening it into a string. Prove the render is unchanged with `/theme-check`'s one-document before/after — on the page and in its column, which is where both of those actually live.

Then `/theme-check` at three widths, on a page that has the section inside a Columns section too.

## What usually needs nothing

`admin.js` — the editor is driven by `SPEC` (`#editor-data` from `post_form.html`, the same `BLOCKS` + `EDITOR` that `GET /api/admin/v1/blocks` serves). Its `BLOCK_NAMES` literal is a fallback consulted after `EDITOR["names"]`. It changes only for a new *widget* type, a new nesting rule — **or a new universal control, which is not a block field at all; see below**. `canvas.css` (only `pdf` needs chrome), `validate_blocks()`, `apply_post()`, `seo.py`, `public.py`, `post.html` — untouched.

## A universal control is not a block type

Every step above is written for a new *type*. A control that belongs to **every** section — the ⚙'s
Align, Background, Width, Spacing — is a different, shorter path, and nothing here covered it until
`pad` was added on 2026-09-19:

1. **A whitelist tuple in `blocks.py`** beside `ALIGNS`/`TONES`/`WIDTHS`/`FX`/`HEIGHTS`, and one line
   in `section_class()`. The value lands in a class attribute, so it is a whitelist, never a
   passthrough.
2. **The key into `_NON_TEXT_KEYS`** — it reaches the browser as `EDITOR["scalars"]` and decides
   whether the editor co-edits it letter by letter. That is the whole of the collaboration story;
   `admin.js` reads the list generically and needs nothing.
3. **A picker in `blockFields()`**, copying `tonePick`, appended unconditionally — and it **must**
   `delete data[key]` when empty, or an untouched section stops being byte-identical in the saved
   JSON. Its vocabulary is a hand-written JS literal duplicating the Python tuple, like the other
   four; **nothing checks they agree**, so write the test that compares them.
4. **No block templates**, unlike a new field: every root already interpolates `{{ cls }}`.
5. **A CSS group whose placement is the mechanism.** The rules you must beat are nearly all
   *specificity ties* (`.band-*.section`, `.column>.section.t-*`, `.column>.section.divider`), so
   the group goes after the last of them and wins on source order. Remember `.hero` is **not** a
   `.section` and needs a selector of its own, and that `.column>` variants need (0,3,0).
6. **Docs:** TECHNICAL §6's layout-key table *and* §12.1's list of the shared controls, design.md §5
   and §9, NON-TECHNICAL §4 *Changing a section* plus a Quick answer. Every one of those lists has
   been found stale at least once — count them rather than trusting the prose.

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
| "This section is not finished yet" on the canvas, 500 on the page | the template is missing or throws |
| The band loses its page gutter and sits at the left edge | `max-width` put on the `<section>` instead of an inner element (step 4) |
| The page still shows the old section after the type exists | the live rows were never moved — a content migration (step 12), and the seed still writes the old shape |
| A URL or id on the new block is co-edited word by word | the key is not in `_NON_TEXT_KEYS`, so the editor took it for prose (step 6) |
