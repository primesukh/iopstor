# IOPSTOR CMS — Technical Documentation

A WordPress-shaped CMS for IOPSTOR (software-defined storage / cloud / HCI), written in Flask on top of a self-hosted Supabase.

Companion documents: [NON-TECHNICAL.md](NON-TECHNICAL.md) for editors, [`.claude/docs/design.md`](../.claude/docs/design.md) for the architecture spec, [`.claude/docs/requirements.md`](../.claude/docs/requirements.md) for the client brief.

---

## 1. Stack and constraints

| | |
|---|---|
| Language | Python 3.13 |
| Web | Flask 3.1, gunicorn, Jinja2 |
| Data / Auth / Files | Self-hosted **Supabase** via **supabase-py 2.x** — PostgREST, GoTrue, Storage, all through the Kong gateway |
| Tokens | PyJWT (local HS256 verification) |
| Packaging | pipenv (`Pipfile` + `Pipfile.lock`); `requirements*.txt` are generated from the lock and are what Docker installs |
| Tests | pytest |
| Deploy | Dokploy, Dockerfile + gunicorn |

Three constraints shape everything below:

1. **Supabase is the only backend, reached only through Kong.** No `DATABASE_URL`, no psycopg, no SQLAlchemy, no ORM. Rows are plain dicts.
2. **Content types are rows, not code.** Adding "Job Openings" is a `post_types` row, not a table and not a model class.
3. **Ponytail mode.** Fewest files, stdlib first, deliberate ceilings marked with `# ponytail:` comments.

---

## 2. Module map

```
iopstor/__init__.py   create_app(), /healthz, blueprint + CLI registration, Jinja globals.
                      Refuses to start without SUPABASE_URL, both keys and the JWT secret.
iopstor/config.py     env → Flask config. A plain module, not a class.
iopstor/db.py         supabase-py clients + every query helper. The single data-access seam.
iopstor/auth.py       GoTrue login/refresh/logout, verify_jwt(), require_role(), create_auth_user()
iopstor/storage.py    save_upload() / delete_media() → Supabase Storage bucket + media table
iopstor/blocks.py     BLOCKS registry, validate_blocks(), render_blocks(), blocks_text()
iopstor/seo.py        site(), build_meta(), jsonld()
iopstor/payments.py   PaymentGateway ABC, DummyGateway, GATEWAYS
iopstor/admin_api.py  /api/admin/v1 — JWT-protected REST. apply_post() is the single validation path.
iopstor/admin_ui.py   /admin — session-based browser admin, reusing admin_api's validation
iopstor/public.py     catch-all resolver, crawler endpoints, /api/v1 public read API, leads, checkout
iopstor/cli.py        flask migrate | seed | create-admin
iopstor/templates/    base/post/archive/404, blocks/<type>.html, admin/*.html
iopstor/static/       site.css (the whole public theme) + admin.css (admin extras, layered on top)
migrations/           0000_bootstrap.sql (run once by hand) + NNNN_name.sql applied by `flask migrate`
tests/                test_offline.py always runs; the rest need a live Supabase and skip without it
docs/                 this file + NON-TECHNICAL.md
```

Dependency direction: `public.py` and `admin_ui.py` both import from `admin_api.py` (for `apply_post`, error handlers and pagination helpers); everything imports `db.py`; `db.py` imports nothing from the app.

---

## 3. Data model

Eleven tables, created by `migrations/0001_initial.sql`.

| Table | Purpose | Notable columns |
|---|---|---|
| `post_types` | Content types **as data** | `slug`, `url_prefix`, `hierarchical`, `field_schema` (JSONB), `taxonomies` (JSONB), `jsonld_type`, `in_sitemap` |
| `posts` | Every piece of content | `post_type_id`, `parent_id`, `slug`, `title`, `excerpt`, `blocks` (JSONB), `meta` (JSONB), `seo` (JSONB), `status`, `published_at`, `featured_media_id`, `author_id`, `menu_order` |
| `taxonomies` / `terms` / `post_terms` | Classification, many-to-many | `terms` unique on `(taxonomy_id, slug)` |
| `media` | Uploads | `key`, `url`, `mime`, `size`, `alt`, `uploaded_by` |
| `users` | CMS roles. `id` **is** the GoTrue `sub` | `email`, `name`, `role` |
| `leads` | Form submissions | `kind`, contact fields, `data` (JSONB), `status` |
| `payments` | Orders | `provider`, `provider_ref`, `amount`, `currency`, `status`, `raw` |
| `menus` | Header/footer nav | `items` (JSONB, one level of `children`) |
| `settings` | Key/value site config | `key`, `value` (JSONB) |
| `redirects` | Legacy URL mapping | `from_path` (unique), `to_url`, `code`, `hits` |
| `schema_migrations` | Applied migration names | created by `0000_bootstrap.sql` |

Indexes: `posts (post_type_id, status, published_at)`, `leads (status, created_at)`, `payments (provider, provider_ref)`. `posts` is unique on `(post_type_id, slug)` — slugs are unique *per type*, not globally.

**Where per-type data lives.** `posts.meta` is a JSON bag described by `post_types.field_schema` — a list of `{key, label, type, required}` descriptors that the admin form renders and the detail template reads back. `posts.blocks` is the ordered page content, `[{type, data}, ...]`.

**Seeded types:** `page` (prefix `""`), `post` (`blog`, BlogPosting), `service` (`services`, hierarchical, Service), `case_study` (`case-studies`, Article), `event` (`events`, Event), `partner` (`partners`, Organization), `datasheet` (`datasheets`), `product` (`products`).

---

## 4. Data access (`db.py`)

Every query goes through this module. Nothing else builds a PostgREST query.

| Helper | Contract |
|---|---|
| `table(name)` | Service-role PostgREST query builder |
| `one(q)` / `rows(q)` | Single dict-or-`None` / list of dicts |
| `insert()` / `update()` | Write helpers returning the row |
| `live(q)` | **The public visibility filter**: `status='published' AND published_at <= now()`. A future `published_at` is a scheduled post |
| `select_posts()` | The canonical post select — embeds `post_type`, `featured_media`, `terms` in one round trip |
| `with_paths()` / `ancestors()` | Attach the computed `path` to posts; builds one per-request hierarchy index rather than walking parents per row |
| `unique_slug()` | Slug collision resolution within a post type — `base`, else `base-xyz` (three random letters) |
| `paginate()` | Offset/limit + exact count |
| `post_types()` / `settings()` | Process-level caches, invalidated with `uncache()` |

Two hard rules:

- **Never call `.delete()` without a filter** — PostgREST interprets an unfiltered delete as "the whole table".
- Anything user-facing goes through `db.live(q)`. A public query that skips it will serve drafts.

---

## 5. URL scheme and the resolver

`public.resolve()` is a catch-all (`/<path:path>`) that tries, strictly in this order:

1. **Trailing slash** → 301 to the unslashed path
2. **`redirects` table** → hit counter incremented, then redirect with the stored code
3. **Empty path** → the `page` post with slug `home`; if none exists, an archive of everything
4. **First segment matches a `post_types.url_prefix`** → the type archive (`/services`), or a post inside it. Hierarchical types are matched on the **full computed path**, so `/services/storage/nas` resolves and `/services/nas` 404s
5. **Single segment, `page` type** → `/about-us`. `/home` 301s to `/`
6. **Two segments matching taxonomy + term** → `/industry/finance` term archive
7. Otherwise `abort(404)`

Resulting scheme:

```
/                       home page (page/home)
/<slug>                 page
/<prefix>/<slug>        post of that type
/<prefix>/<parent>/…    hierarchical type, full ancestry in the path
/<taxonomy>/<term>      term archive
```

---

## 6. Blocks

`iopstor/blocks.py` is the only place a block type is declared:

```python
BLOCKS = {  # type: (required fields, optional fields)
    "hero": (["heading"], ["subheading", "image", "cta_label", "cta_url"]),
    ...
}
```

Thirteen types ship: `hero`, `rich_text`, `image`, `gallery`, `cards`, `cta`, `faq`, `stats`, `testimonial`, `embed_html`, `post_list`, `spec_table`, `contact_form`.

**Adding one** = an entry in `BLOCKS` + `templates/blocks/<type>.html`. The template must be wrapped in `<section class="section"><div class="wrap">…`. Unknown types are rejected on save by `validate_blocks()`, which checks that every required field is present and non-empty.

Two behaviours worth knowing:

- **`hero` is the only block that renders its own `<h1>`.** `post.html` skips the page title when a post's first block is a hero.
- **`post_list` is queried at render time.** `render_blocks()` special-cases it, calling `_post_list()` to fetch live posts and passing them in as `posts`.

**Editor metadata.** Alongside `BLOCKS`, `blocks.py` exports `EDITOR` — how each field is edited in the browser admin, so the field shapes that used to live only in comments are data:

```python
EDITOR = {
    "widgets": {...},   # field key -> text | textarea | code | richtext | media | url | number | checkbox | post_type | kind
                        # "<block>.<field>" overrides the bare key (e.g. "embed_html.html": "code")
    "items":   {...},   # block type -> the subfields of one repeater row (items / images / rows)
    "labels":  {...},   # friendlier field labels; missing keys fall back to the key itself
    "kinds":   [...],   # contact_form.kind options
}
REPEATERS = ("items", "images", "rows")
```

`EDITOR` is metadata only — nothing on the render or validation path reads it, and an unknown widget just degrades to a text input. `tests/test_offline.py::test_editor_metadata_covers_every_block` fails if a new block's fields have no widget, or if a repeater field has no `EDITOR["items"]` entry.

`blocks_text()` flattens all block content to plain text for `llms-full.txt` and admin search. Because JSONB does not preserve key order, it walks fields in a fixed reading order (`_TEXT_ORDER`), with unknown keys appended alphabetically, so output is deterministic.

---

## 7. Auth

Two surfaces, one verification path.

```
Admin API   Authorization: Bearer <Supabase JWT>
Browser     tokens in the signed Flask session cookie, refreshed on expiry
            + a per-session `csrf` field on every POST, checked by ui_required
```

Both verify **locally** with `SUPABASE_JWT_SECRET` (HS256) — no network round trip per request. `users.id` equals the GoTrue `sub`, which is how a token becomes a CMS user.

**Roles are a ladder:** `ROLES = {"editor": 1, "admin": 2}`, enforced by `require_role(min_role)`. A valid GoTrue login with **no `users` row gets 403** — authentication and authorization are deliberately separate.

Login goes through a throwaway anon client (`auth.anon()`); the service-role client is never used for password sign-in.

---

## 8. HTTP surface

### `/api/admin/v1` — JWT-protected, `admin_api.py`

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `/auth/refresh`, `/auth/logout`; `GET /auth/me` |
| Post types | `GET|POST /post-types`, `GET|PATCH|DELETE /post-types/<slug>` |
| Posts | `GET|POST /posts`, `GET|PATCH|DELETE /posts/<id>` |
| Taxonomies | `GET|POST /taxonomies`, `PATCH|DELETE /taxonomies/<slug>`, `GET|POST /taxonomies/<slug>/terms`, `PATCH|DELETE /terms/<id>` |
| Media | `GET|POST /media`, `PATCH|DELETE /media/<id>` |
| Leads | `GET /leads`, `GET|PATCH|DELETE /leads/<id>` |
| Site | `GET|PUT /settings`, `GET /menus`, `PUT /menus/<slug>`, `GET|POST /redirects`, `DELETE /redirects/<id>` |
| Users | `GET|POST /users`, `PATCH|DELETE /users/<uuid>` |
| Introspection | `GET /blocks`, `GET /payments` |

**`apply_post(existing, b)` is the single validation path** for every post write — create, PATCH, and the browser admin form all funnel through it. It returns `(changes, term_ids)`, validates blocks, resolves slugs, parses datetimes and enforces the field schema. Do not add a second one.

Errors are normalised by three handlers: `HTTPException`, PostgREST `APIError`, and GoTrue `AuthError` all become consistent JSON.

### `/api/v1` — public read-only, `public.py`

`GET /post-types`, `/posts`, `/posts/<type>/<slug>`, `/taxonomies/<slug>/terms`, `/menus/<slug>`, `/settings` — all filtered through `db.live()`.

Writes: `POST /leads` (also the target of the HTML contact form — plain form POST, honeypot `website` field, redirect back with `?sent=1`), `POST /payments/checkout`, `POST /payments/webhook/<provider>`.

### `/admin` — browser, `admin_ui.py`

`/login`, `/logout`, `/` (dashboard), `/posts`, `/posts/new`, `/posts/<id>`, `/posts/<id>/delete`, `/media`, `/media/upload`, `/media/<id>/delete`, `/leads`, `/leads/<id>/status`, `/settings`, `/users`, `/users/<uuid>/delete`. Server-rendered forms; `_form_body()` turns form fields into the same body dict the JSON API accepts, so both surfaces share validation. `_safe_next()` restricts post-login redirects to relative same-origin paths.

`POST /admin/media/upload` is the one exception to "server-rendered forms": it takes the same multipart body as `POST /admin/media` (`csrf`, `file`, optional `alt`) through the shared `_upload()` helper, and answers `201 {id, url, filename, mime, alt}` or `4xx {error}` instead of redirecting. It exists so the post form's media pickers can upload without leaving the page; session auth and CSRF come from `ui_required()` unchanged.

### Crawler endpoints

`/sitemap.xml`, `/robots.txt`, `/feed.xml`, `/llms.txt`, `/llms-full.txt`, plus `/healthz`.

---

## 9. SEO

Everything is server-rendered from `seo.py` + `public.py`; keep it there.

- `build_meta()` — title, description, canonical, Open Graph, robots
- `jsonld()` — structured data driven by `post_types.jsonld_type` plus BreadcrumbList from the resolver's crumbs
- `_indexable()` — a post whose `seo.robots` starts with `noindex` is kept out of the sitemap

> **Known gap.** The `faq` block emits Q&A markup but is not currently wired into FAQPage JSON-LD. The knowledge graph flagged this edge as AMBIGUOUS; it is a genuine, unimplemented opportunity.

---

## 10. Migrations

Plain `.sql` files in `migrations/`, named `NNNN_short_name.sql`, applied in name order and tracked in `schema_migrations`.

`0000_bootstrap.sql` is pasted **once** into Supabase Studio's SQL editor. It creates `apply_migration(name, sql)` — `SECURITY DEFINER`, executable by `service_role` only — which `flask migrate` calls per file over Kong. Each file runs in one transaction.

**Workflow for a schema change:**

1. Write the `ALTER`/`CREATE` as a new numbered file
2. `pipenv run flask migrate`
3. Update the code that reads/writes those columns
4. Commit both together

`0002_enable_rls.sql` enables RLS on every app table, so the anon key cannot read drafts or leads. The app's service-role key bypasses RLS by design.

---

## 11. Payments

`payments.py` defines the `PaymentGateway` interface (`create_checkout()`, `handle_webhook()`) and `DummyGateway`, selected by the `PAYMENT_PROVIDER` env var through `GATEWAYS`. `dummy` records the payment row and exposes `/api/v1/payments/dummy/<id>` to mark it paid, without charging anything. A real provider is a new subclass plus an env change.

---

## 12. Theme

One stylesheet, `static/site.css`, with CSS variables at the top, then header/footer, then `.cards` / `.card` / `.btn` / `.section`, then one rule-group per block. `static/admin.css` layers admin-only rules on top, so `/admin` inherits the public theme.

No CSS framework, no build step, no JavaScript framework. Mobile navigation is a checkbox-driven CSS menu with no JS, and the public site ships no JavaScript at all.

`static/admin.js` is the single exception, loaded only by `templates/admin/base.html`. It is plain ES5-ish browser JavaScript — no framework, no bundler, and nothing fetched at runtime: the one third-party file, `static/vendor/sortable.min.js` (SortableJS 1.15.6, MIT, 45 KB), is **vendored, not CDN-loaded**, because the CMS runs on a LAN and an editor without internet must still be able to drag a section. It is **progressive enhancement only**: every part is a no-op when its hook is missing, and the plain form underneath still saves with JavaScript disabled. Three parts:

- **Slug** — `#post-slug` is `readonly`; typing in `#post-title` live-fills it with a JS mirror of `db.slugify()` while the post has no saved slug. An *Edit* button unlocks the field after a confirm, for the deliberate URL change. The field also carries `data-taken` — every slug of this post type except this post's own, built by `_form_context()` from the one `siblings` select that also feeds the *Parent* dropdown (space-separated: slugs are `[a-z0-9-]`, so no JSON is needed, and it is an attribute rather than `#editor-data` because `initSlug()` runs before `initBlocks()` parses that blob). On every keystroke `check()` compares the slugified value against that list, and the two paths diverge deliberately:

  - **A new post's generated address** takes the first free one outright — `freeSlug()` (a mirror of `db.unique_slug()`, memoised per base so it does not reshuffle as you type) appends three random letters, and `#slug-hint` says *“testing” is already used, so this page is at “testing-shc”.* Nobody is stopped from writing a page because someone else used the title.
  - **A deliberate rename**, after *Edit* unlocks the field, still gets the warning: `#slug-hint` turns red with the free address on offer, and `setCustomValidity()` blocks **Save**. (A `readonly` input is barred from constraint validation, so before *Edit* the message alone does the work — which is fine, because the auto path never produces a clash.)

  `apply_post()` mirrors exactly that split and stays the authority, since the browser's list is only a page-load snapshot: **on create it takes whatever `unique_slug()` returns**, for the submitted slug and the title-derived one alike, so a create can no longer fail on a duplicate address; **on update** a taken slug is still `409 slug already in use`, with `fields.slug` a sentence (*“about-us” is already in use — try “about-us-hqz”*) rather than the bare slug, because `_save()` prints `fields[k]` straight into the form's error box the way it does for every other field.
- **Media pickers** — one `mediaWidget()` renders a thumbnail, a "choose existing" select and a file input that uploads to `/admin/media/upload` and appends the new row to *every* picker on the page. It is applied to `select[data-media]` (featured image, per-type `media` fields) and to media fields inside blocks, so there is one code path rather than three. `data-media="images"` filters non-images out.
- **Section settings** — `blockFields(block)` renders one section's non-inline fields: labelled inputs driven by `BLOCKS` + `EDITOR`, media pickers, and repeaters for `items`/`images`/`rows`. It is what `⚙` opens in the popover (§12.1); there is no form-based content entry any more — the canvas and the popover are the only editors, and *Advanced* is the raw JSON. It mutates the block object in place, so **keys it does not render survive**, and an unknown block type falls back to an "edit it under Advanced" note. On submit `admin.js` serialises the array back into `textarea[name="blocks"]`, so `_form_body()` and `validate_blocks()` are untouched — the editor only ever writes the JSON a human could have typed. If that textarea holds unparseable JSON (a rejected save round-trip), the editor stands down, opens *Advanced* and says so.

Rich fields inside the popover get `richText()`: a `contenteditable` box with a bold/italic/H2/H3/list/link/clear toolbar plus an *HTML* toggle for the raw markup; paste goes through the same `richPaste` filter as the canvas, so headings and lists survive and Word's markup does not.

### 12.1 The document editor

The post form (`templates/admin/post_form.html`) is one screen. A bar across the top: back link, the *saved* status pill, *Edit* / *Preview*, the device widths (Preview only), *View live*, **Save**. Under it, the page column — a borderless title input, the document toolbar and `iframe#canvas` filling whatever height is left — and, on the right, the settings panel: *Publish*, *Web address*, *Summary*, *Featured image*, *Organise* (parent, taxonomies — the whole section is dropped for a type with neither), the type's *Details* (`field_schema`), then *Search engine overrides* and *Advanced* as collapsed `<details>`. `.admin-main:has(#post-form)` is sized to the viewport and the two columns scroll on their own, so the toolbar never scrolls away; under 1000px the panel stacks beneath the page.

**`menu_order` is not in the form.** A number that decides list order was the one setting no editor could explain, and every list already falls back to newest first. The column stays, and it is still the *primary* sort for `post_list` (`blocks.py`), archives, and the child lists in `render_post()` / the preview — all of which now carry `.order("menu_order").order("published_at", desc=True)`, so a hand-set order still wins and everything else is newest first. It stays writable through `PATCH /posts/<id>` and `cli.py`'s seed, which is what keeps the seeded Services in their intended order; `_form_body()` deliberately omits the key so a browser save leaves whatever is there alone rather than resetting it to `0`.

*Advanced* holds `textarea[name="blocks"]`, still the only field that POSTs, so `_form_body()` → `apply_post()` → `validate_blocks()` remains the single validation path. Opening the `<details>` writes the current array into it, a blur on a hand edit reads it back through `setBlocks()`, and submit rewrites it from the array. With JavaScript off, Advanced is what you get. Delete is a `<button form="delete-post">` pointing at a second form placed *after* `#post-form`: a form nested inside a form is dropped by the parser, so the old inline delete form's button submitted the post form instead.

**The canvas is a server render, not a second renderer.** `POST /admin/canvas` (`admin_ui.py`, `@ui_required()`, CSRF as form data) takes the blocks the browser currently holds — unsaved ones included — and returns `render_blocks(blocks, edit=True)` inside `templates/admin/canvas.html`, a standalone document linking `site.css` and `static/canvas.css`. `admin.js` puts that in `iframe#canvas` via `srcdoc`. Preview and published page therefore cannot drift. The iframe is not decoration: every `admin.css` rule is scoped to `body.admin`, which would be an ancestor of an inline canvas and would silently repaint `.specs`, `.card` and the lead form.

**Edit markers.** `render_blocks(blocks, edit=False)` hands each template an `fe` callable — `_fe(i)` in edit mode, `_no_fe` otherwise — so `data-*` attributes *cannot* reach the public site; there is no request-global flag to leak. In `blocks/*.html`:

| call | emits | means |
|---|---|---|
| `{{ fe() }}` on the root `<section>` | `data-b="2"` | this is block 2 |
| `{{ fe('heading') }}` | `data-f="heading" data-ph="Heading"` | editable text; `data-ph` is the empty-state placeholder, taken from `EDITOR["labels"]` |
| `{{ fe('items', loop.index0) }}` | `data-r="items" data-i="0"` | one repeater row: fields inside write into `data.items[0]` |
| `{{ fe('html', rich=True) }}` | `… data-rich="1"` | the value is `innerHTML`, not `innerText` |
| `{{ fe('html', ph='…') }}` | overrides `data-ph` | when the field label ("Content") is not what an empty page should say |

Write them tight against the tag (`<h1{{ fe('heading') }}>`) — a space would make the public render `<h1 >`, which `tests/test_offline.py::test_render_blocks_uses_template` catches.

**Typing never re-renders.** `contenteditable` (`plaintext-only`, with an Enter-blocking fallback for engines without it) writes straight into the block objects, which `fieldInput()` already mutates in place — canvas, settings popover and JSON textarea point at the same objects, so there is no sync layer. Only structural changes touch the server, and then only for **one** block: `POST /admin/canvas` with `i=N` returns a bare fragment that replaces that one `<section>`; deletes remove the node, drags move it, and `data-b` is renumbered client-side. `setBlocks()` is the single place the array reference is ever replaced.

**A page is a document, not a stack.** Prose lives in `rich_text` blocks; the other twelve types
are the designed bands. Nothing about the storage changed — `posts.blocks` is the same JSONB —
but the editing surface leads with writing:

- A post with no blocks opens as **one empty `rich_text` with the caret in it** (`focusOnLoad`).
  No dialog, no picker. `LAYOUTS` moved from a blocking chooser into the Insert menu.
- The gaps between sections are **click-to-type**: clicking one splices in an empty `rich_text`
  and focuses it. One mechanic instead of a separate "+" affordance, and it means there is never
  nowhere to put the caret.
- `rich_text` blocks get **no hover toolbar** — a floating bar over every paragraph would destroy
  the document feel. Sections keep theirs (name, drag, ↑ ↓, duplicate, settings, remove).
- **Empty `rich_text` blocks are stripped on submit** (`written()`), because an empty paragraph is
  the editor waiting for you, not content — and `rich_text.html` is a required field. A paragraph
  holding only an `<img>`, `<hr>` or `<table>` has no text and is still kept.

**The toolbar** (`#doc-toolbar`, `buildToolbar()`) lives in the admin page so it can use
`admin.css`, but every command runs against the *canvas* document. Clicking a button moves focus
out of the iframe, so the caret is stored on every `selectionchange` (`rememberSelection`) and put
back before the command runs (`restoreSelection` → `exec`). `syncBar()` reflects the caret back into
the bold/italic/underline/strikethrough states, the quote state, the three alignment buttons and the
style dropdown — a lit button is what tells an editor that a second click switches it off again.

**A section's settings belong to the section.** There is no sidebar card: `⚙` on a section's own
hover bar calls `openPanel(i)`, which floats `blockFields()` over that section. The popover has to be
built in the *admin* document — `blockFields`, `mediaWidget` and `richText` all create parent-document
nodes — so it is positioned over the iframe from two rects (`FRAME.getBoundingClientRect()` plus the
section's), exactly the trick `openSlash()` uses for the `/` menu. `place()` re-runs on the canvas
document's `scroll` (`#canvas` fills its column and scrolls inside itself), on window `scroll`/`resize`, and
clamps into the viewport. Esc, the ✕, a click outside and a second press of `⚙` all close it; so do
move / duplicate / delete / `setBlocks()`, because the block index it holds would otherwise be
stale. The popover holds the fields alone — the section's hover bar already carries the name, move,
duplicate and delete. A 250 ms debounce on the popover's
`input`/`change`/`click` calls `canvasBlock()`, so the section updates live as you edit.

**The toolbar goes dead rather than lying.** `liveField()` is the gate: the remembered field must
still be inside the *current* canvas document (`d.contains(savedField)` — `isConnected` is not
enough, a node from a replaced `srcdoc` stays connected to its own dead document and handing that
range to the live selection throws) and must carry `data-rich`, which is exactly the set of fields
where `execCommand` does anything. Fail either test and `syncBar()` disables every control that
needs a caret, greys the bar (`.tb-off`) and swaps `#pane-hint` for "Click in the page to start
editing". Only **↶ ↷** and **+ Section** stay live. Without this the select silently reset itself to
*Normal text* after any re-render, which reads as "the dropdown is broken".

**That disabled set is a registry, not a list.** `b()` pushes every button it builds into `cmds`
unless the caller passes `free`, and `colour()` pushes its two swatches; `syncBar()` disables
`cmds` plus the style select. The hand-written array it replaces had drifted: `Tx`, the two list
buttons, the divider, both colour swatches and all four insert buttons were outside it, so they
stayed clickable with no caret and `exec()` dropped them at `restoreSelection()`. Harmless while a
click was the whole interaction; with dialogs it means filling in a form for nothing. `canvasFull()`'s `onload` and `canvasBlock()` both call `syncBar()` because they are the
two places a caret is destroyed and no `selectionchange` follows.

Four `execCommand`/selection details the toolbar cannot do without:

- **`caretBlock()` descends through `startOffset`.** At a block boundary — the caret at the end of a
  line, which is where it is after you type — Gecko reports the range's container as the editing
  *host*, not the block. Taken at face value that makes quote-off undetectable
  (`closest("blockquote")` from the host is `null`) and reads alignment off the wrong element.

- **`styleWithCSS` is on for the colour *and* the justify commands.** Colours emit `<span style>`
  rather than `<font>`; alignment emits `style="text-align:…"` rather than the legacy presentational
  `align=""`. That attribute maps to a UA-level rule that ranks *below* author CSS, so inside any
  section `site.css` centres (`.cta`, `.stats`, …) it is silently ignored. It stays off for
  bold/italic/underline so those still emit `<b>/<i>/<u>`.
- **A block command needs a block.** Write-back stores `f.innerHTML` (`bindField`), which excludes
  the contenteditable host's own attributes — so when the field holds bare text with no wrapper, an
  alignment written onto the host is thrown away by the next re-render. `exec()` runs
  `formatBlock:<p>` first whenever `caretBlock()` resolves to the field itself.
- **`formatBlock` only ever wraps.** Quote is a toggle: `outdent` when `caretBlock("blockquote")`
  hits, `formatBlock:<blockquote>` otherwise.

`hold()` (cancel `mousedown` so the click cannot blur the canvas) is applied to **buttons only**.
On a `<select>` or an `<input type="color">` cancelling `mousedown` suppresses the native popup, and
it is not needed anyway — `savedRange` already survives the blur.

**Nothing may touch the style `<select>`'s value on `mousedown`.** From Firefox 137 the dropdown is
DOM-rendered rather than an OS popup, so clicking an *option* fires a second `mousedown` that
bubbles to the select. A handler there runs again and wipes the pick before `change` reads it —
`change` then arrives with `value === ""`, `formatBlock` is handed `"<>"`, and the only visible
effect is `ensureBlock` wrapping the line in a `<p>`: the control appears to snap back to *Normal
text*. It reproduces only on Firefox ≥137; Firefox 140 ESR and Chrome fire no such event.

The select stays honest instead. It carries a `hidden` `value=""` option, and `syncBar()` selects it
whenever the caret's block is not one of `p`/`h2`/`h3`/`h4` — a blockquote, a bare text node. Coercing
those to `"p"` was the original reason for the mousedown hack: it made the select claim the caret was
already on *Normal text*, so picking *Normal text* changed nothing and raised no `change`. With a real
"none of these" value, every pick is a genuine change. The handler still ignores an empty value.

The style dropdown offers **Normal text** plus **H1–H6**, labelled by number and by role
(*H2 — Heading*, *H3 — Sub-heading*, …) so it reads to an editor and to anyone who thinks in tags.
**Size is a second dropdown, and it is not a heading level.** A level says what a line *is* and
Google reads it; a size only says how big it looks. `TEXT_SIZES` holds absolute `rem` values, so a
size inside a size does not compound, and `"normal"` *removes* the wrapper rather than writing
`1rem` — a true reset.

`setSize()` cannot just call `execCommand("fontSize")`: Gecko ignores `styleWithCSS` for that command
and always emits `<font size>`, an obsolete tag the paste filter strips on the next round trip. So it
runs the command with a marker size — which usefully also clears any size already inside the
selection — then swaps the `<font size="7">` tags it produced for spans carrying a real CSS size, or
for nothing at all on *Normal*. `execLine()` wraps it: a collapsed caret means "this whole line",
because otherwise picking a size with nothing selected only sets a pending style and nothing visibly
happens, which reads as another dead control.

**Setting a heading clears any inline size inside the line** (`applyLevel()`): the size is stripped,
an emptied `<span>` is unwrapped rather than left as noise, and *Normal text* is exempt because `p` +
a size is the whole point of the size control. Without this a heading kept wearing the span that
overrode it — and since the size dropdown is disabled on headings, there was no way back out of it
from the toolbar.

`syncBar()` disables the size dropdown whenever the caret's block is `h1`-`h6`. A heading's size *is*
its level, and offering both there invites an H2 that looks like an H4 — the outline Google reads and
the one a reader sees disagreeing.

`caretNode()` is shared by `caretBlock()` and `caretSize()`, and it descends **all the way** to the
node at the range's start rather than one level. Two different bugs came out of getting this wrong.
At a block boundary Gecko names the range's container as the *parent* with an offset, not the node
you are standing in — walking up from that misses everything below it, so `syncBar` never saw the
inline size and the control snapped back to *Normal* after every pick. And a **selection** that
*contains* a sized span (drag-select a line, or Ctrl-A) resolves to the block, with the span a level
further down — one level of descent still landed above it. Climbing back up to the block afterwards
is unaffected, so `caretBlock()` gets the deeper start for free.

A mixed selection reports the size at its start; saying "several" would mean walking the end too,
for a case an editor hits rarely (`ponytail:` in the source).

`HEAD_LEVELS` (one table, shared by the `<option>` list and `syncBar`'s recognised set) is the only
place a level is declared. Adding or renaming one is that array.

**H1 is offered but is not the default.** `post.html:9` already emits the page title as the page's
only `<h1>`, and a hero block emits its own, so an H1 in body text is a *second* `<h1>` on the page —
an SEO signal error. It is in the list because an editor asked to set levels by hand; H2 remains the
right way to open a section.

Pasted `<h1>` is still demoted to `<h2>`: a Word or Docs file always carries its title as an H1 and
the page already has one, so the demotion is right for the bulk path even though the toolbar can set
H1 deliberately. `<h5>`/`<h6>` are no longer demoted — the toolbar can produce them, so paste has to
agree about which levels exist or a pasted H5 lands as an H4 you cannot reproduce with the dropdown.

`site.css` gives every level an explicit `font-size` inside `.rich-text` and nothing else — the
browser defaults put `h5`/`h6` *below* body size, which reads as broken text rather than as a
heading. Size only: colour and casing stay the same as every other heading, because the control is
called a heading level and an editor picking H6 is asking for a size, not for a restyle.

**Paste keeps its formatting.** `richPaste()` reads the `text/html` clipboard flavour, strips
conditional comments, and walks it against an allowlist (`PASTE_OK`), renaming `b`→`strong`,
`i`→`em`, `div`→`p`, `h1`→`h2` (`PASTE_AS`), deleting `script`/`style`/`iframe` and friends outright
(`PASTE_DROP` — unwrapping those would spill their source as visible text), unwrapping everything
else, and keeping only `href`/`src`/`alt`. Plain-text fields (a heading, a button label) still use
`plainPaste`. This is a **quality filter, not a security boundary** — block HTML is still
trusted-staff-only on the server. It replaced the old handler that forced every paste through
`insertText`, which threw away exactly the headings and lists an editor had drafted elsewhere.

**`/` inserts a section at the caret.** Typing `/` on an otherwise empty line opens a filtered
list positioned under the caret; typing filters, Enter takes the first, Escape cancels. `splitAt()`
does the surgery at the HTML level rather than with Range extraction: the children of the field
before the `/` line stay in this block, the chosen section goes next, and the children after it
become a second `rich_text`. If the `/` line *was* the whole paragraph, the block is replaced
outright rather than leaving an empty one behind.

**Link, picture, table and embed are dialogs.** All four used to be a `prompt()`: unstyled,
single-line (so an embed snippet was unreadable), impossible to validate, and on Firefox carrying a
"prevent this page from creating additional dialogs" checkbox that kills the button for the rest of
the session. `modal(title, kids, wide)` is the shared shell — `.iop-modal` over `.iop-modal-in`,
Esc / ✕ / backdrop click, returns `close()`. `chooser()` is now four lines on top of it.

A dialog mounts on `document.body`, **outside `#post-form`**, which is load-bearing twice over:
Enter in a field cannot submit the post, and the form's 500 ms preview debounce
(`form.addEventListener("input")`) never sees the typing. The caret needs no special handling —
focusing an admin `<input>` does not disturb a selection living in the iframe, so `savedRange`
survives exactly as it does for `chooser()`'s search box, and every dialog commits through `exec()`.

- **`linkDialog(cur, save, remove)`** — address, link text, "open in a new tab", and *Remove link*
  when there is one. It is deliberately callback-shaped because it has two callers in two different
  documents: `docLink()` finds the anchor with `caretBlock("a")` and commits through `exec()`, while
  `richText()`'s `link` button works on the admin document and therefore needs its own four-line
  range stash (taken on the toolbar's `mousedown`, which fires before focus moves — a `blur` handler
  is too late). Editing an existing link points the range at the whole anchor first (`rangeOn()`),
  the same trick `execLine()` uses to turn a collapsed caret into a whole line.
  The `<a>` is **built as a DOM node and inserted as `outerHTML`**, so the browser does the escaping
  and there is no hand-rolled entity table. `safeUrl()` is a scheme *allowlist* —
  `http(s)`/`mailto`/`tel`, a `/` path, a `#` anchor, otherwise `https://` in front of a bare
  domain — because a `javascript:` blocklist alone still lets `data:` through.
- **`pictureDialog()`** replaces `altPrompt()` and the hidden `<input type=file>`. The picker is
  `mediaWidget()`, the same widget as every other image field, so an inline picture can now reuse a
  library image instead of only ever uploading a new one; alt text is prefilled from the media row
  and asked for *before* the insert, because `media_alt()` cannot reach inside `rich_text` HTML.
- **`tableDialog()`** is a Word/Docs hover grid: 80 `.tb-cell` spans, **one** `mousemove` listener
  reading `data-r`/`data-c`, and Rows/Columns number boxes beside it that drive the same state.
  The boxes are the keyboard path and the only way past the visible 8 × 10 (the clamps are 50 × 12,
  as before), so the grid carries `aria-hidden` rather than being read out as eighty empty cells —
  cheaper and clearer than a roving tabindex over 80 buttons. `tableHtml()` emits a real `<thead>`
  when *First row is a header* is ticked (`PASTE_OK` already allows `THEAD`, so a copy round-trips)
  and skips `<tbody>` entirely for a one-row all-header table. Typing in a box repaints the grid but
  does not rewrite the box mid-keystroke; the value is normalised on `change`.
- **Columns resize by dragging their edge.** One capture-phase `mousedown` on the canvas document
  (`startColDrag`, registered in `wireDoc()`, so it survives every single-block re-render) picks up
  a press within 6px of a cell's right edge; `canvas.css` puts a `::after` grip there so the
  `col-resize` cursor costs no JS. `colgroupFor()` builds a `<colgroup>` on the *first* drag, seeded
  from the measured widths **as percentages** so the table still reflows on a phone, and the two
  columns either side of the edge trade width so the table itself never changes size. `site.css`
  switches to `table-layout:fixed` only via `:has(colgroup)` — a table nobody has resized keeps
  auto-fitting, so no existing page changes shape. `fire(field)` on mouseup writes the HTML back
  through the same path as any other edit; `rich_text` is unsanitised on the server
  (`blocks.py:10`), so the `<colgroup>` round-trips. Widths are lost on copy-paste, because
  `PASTE_ATTR` keeps only `href`/`src`/`alt` — the table simply falls back to auto layout.
  `.rich-text` cells also gained the column borders they never had: they only ever carried a
  `border-bottom`, which reads as a list rather than a grid.
- **`embedDialog()`** is a monospace paste box. The snippet still goes in **inline and unfiltered**:
  block HTML is trusted-staff-only on the server and the `embed_html` block already takes raw
  markup, so filtering here alone would make the two disagree.

**Sections still work.** Each non-prose block keeps its floating bar, drags via the vendored
SortableJS, and opens `blockFields()` over itself for everything that is not inline text. The canvas is a live page, so `submit` and `a`/`button` clicks
are cancelled in the capture phase: a `contact_form` block would otherwise post a real lead.


### 12.2 Preview

The canvas is honest about content but silent about everything around it, and a **draft cannot be
seen any other way**: `db.live()` (`db.py:106-108`) gates every public lookup on
`status='published'` with no bypass, no token and no role check.

`POST /admin/preview?type=<slug>&pk=<id>` renders the real `post.html` inside the real
`base.html`. It reuses two things whole: `_form_body(pt, existing)` — the same parser `Save` runs —
and `crumbs_for()` from `public.py`. `_preview_post()` shapes the result like a hydrated row, and
`db.hydrate()`/`db.ancestors()` work on it unchanged because they read only `post_type`,
`post_type_id`, `parent_id` and `slug` — never `id`. `?part=card` returns just the search/social
fragment (`admin/seo_card.html`) from the same data. Nothing needed rewiring: `public.py:22-24`
registers `site`, `menu`, `render_blocks` and `year` with `app_context_processor`, so they are
already live in admin templates.

Three things it must get right, all of them latent traps:

| | |
|---|---|
| **Analytics** | `base.html`'s gate was `{% if site.ga_id %}` alone, so every preview refresh would have sent a real gtag pageview to production, attributed to a URL that does not exist. It is now `{% if site.ga_id and not preview %}` — `preview` is undefined on public pages, so it stays falsy there. |
| **`published_at`** | `apply_post()` (`admin_api.py:211`) stores a `datetime`, but `post.html:11` does `published_at[:10]` and `seo.jsonld()` hands it to `\|tojson`. The preview dict keeps the form's **string**; both problems go at once. Covered by a test. |
| **`post["id"]`** | `render_post()` (`public.py:43`) queries children by id. The preview builds its own context and only queries children when there actually is a saved id. |

`meta.robots` is forced to `noindex,nofollow` after `build_meta()` — the default is `index,follow`
(`seo.py:25`) and a post's own SEO override would otherwise win.

`render_blocks(edit=False)` re-raises on a malformed block, which is right for the public site and
wrong for a pane you are typing into, so the render is wrapped and reports which section is unfinished.

Client side: `admin.js` posts `new FormData(#post-form)` with `blocks` taken from `MODEL` (the
textarea is only written on submit). Preview mode runs `wirePreview()` instead of `wireDoc()` — no
`contenteditable`, no section bars, no Sortable — plus capture-phase handlers that cancel `submit`
and open links in a new tab rather than navigating the preview away. Device widths render at
1440/834/390 and `transform: scale()` down to `#canvas-wrap`, which Preview sizes to the rest of the
window (from the frame's top to the bottom, `flex:none` so the search and share cards under it cannot
squeeze it; the column scrolls to them), with the iframe's height divided by the same factor so the
scaled result fills it exactly; the iframe *is* the viewport, so the site's own
breakpoints answer honestly. A 500 ms debounce on any form `input` keeps it a step behind your typing.

One CSS rule underpins all the show/hide: `.admin [hidden]{display:none!important}`. Author display
rules outrank the UA's `[hidden]{display:none}`, so toggling `hidden` on a flex or grid element
silently does nothing — the bug that once showed the layout chooser and the canvas at the same time.

---

## 13. Tests

```
tests/test_offline.py    always runs — slugify, validate_blocks, render_blocks, JWT matrix
tests/conftest.py        app/client fixtures, admin_headers/editor_headers, seeded corpus, cleanup
tests/test_auth.py       JWT matrix, mocked GoTrue login, real bad-password rejection
tests/test_admin_api.py  create/publish visibility, scheduled-post hiding, terms/settings/menus
tests/test_admin_ui.py   browser login and post creation
tests/test_public.py     hierarchical URLs + breadcrumbs, leads, redirects, sitemap/feed/llms, upload, checkout, seed idempotency
```

Everything except `test_offline.py` is marked `live` and skips when `.env` has no Supabase.

---

## 14. Configuration

`SECRET_KEY`, `SITE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `MEDIA_BUCKET`, `PAYMENT_PROVIDER`. `FLASK_DEBUG=1` in `.env` gives the dev server the debugger and auto-reload.

`SUPABASE_JWT_SECRET`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are the same values as `JWT_SECRET`, `ANON_KEY` and `SERVICE_ROLE_KEY` in the Supabase compose environment.

Dev gateway: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io` — LAN, self-signed cert on https, so use http until a real certificate exists.

---

## 15. Running it

```bash
pipenv install --dev                        # pipenv auto-loads .env
pipenv run dev                              # flask run --debug
pipenv run flask migrate                    # apply migrations/*.sql through Supabase
pipenv run flask seed                       # idempotent site-map seed; --reset-content overwrites seed blocks
pipenv run flask create-admin EMAIL PASS    # Supabase Auth user + CMS admin row
pipenv run pytest
```

**First-time setup on a Supabase instance:**

1. Studio → SQL editor: run `migrations/0000_bootstrap.sql`
2. Studio → Storage: create a **public** bucket named `media`
3. `flask migrate` → `flask seed` → `flask create-admin`

After any `Pipfile` change, regenerate both lockfile exports:

```bash
pipenv requirements > requirements.txt
pipenv requirements --dev-only > requirements-dev.txt
```

---

## 16. Extending it

| Task | What to touch |
|---|---|
| New content type | A `post_types` row — seed entry or admin API call. No table, no model |
| New per-type field | Add to that type's `field_schema`; the admin form and detail list follow |
| New block | One `BLOCKS` entry + `templates/blocks/<type>.html` |
| New taxonomy | A `taxonomies` row + the type's `taxonomies` array |
| Schema change | A new `migrations/NNNN_*.sql`, then `flask migrate`, then the code |
| New payment provider | A `PaymentGateway` subclass in `payments.py` + `PAYMENT_PROVIDER` |
| Theme change | `static/site.css` (admin extras in `static/admin.css`) |

---

## 17. Known ceilings

Marked in code with `# ponytail:` comments.

- `rich_text` and `embed_html` render raw HTML with `|safe`. Fine for trusted staff; add `nh3` sanitising if untrusted authors are ever given accounts.
- The rich-text toolbar uses `document.execCommand` — deprecated but universally implemented, and 40 lines against a bundled editor. Swap for a real editor if a browser drops it.
- `admin.js` re-renders whole lists on every reorder, and media pickers are refreshed by iterating every picker on the page. Fine at page scale; revisit only if a page grows to hundreds of blocks.
- The canvas re-renders one whole block per settings change rather than patching the one field that moved. A round trip is a few tens of milliseconds on the LAN; patch per field only if it ever feels slow.
- Undo/redo is `execCommand` inside one `rich_text` block; it does not span block boundaries.
- The document toolbar remembers one caret (`savedRange`/`savedField`). A re-render — `canvasBlock()`
  or `canvasFull()` — replaces the node, and the caret is **refused, not recovered**: the toolbar
  switches itself off until the editor clicks back into the canvas. Recovering it would mean
  addressing the field by block index + field key + repeater row and inventing an offset into DOM
  nodes that no longer exist. Do that only if the extra click ever costs more than it saves.
- The paste normaliser walks the DOM, so it has no unit test — Node ships no DOM and this project
  has no npm toolchain. Its check is the manual "paste a Google Doc in" step.
- `embed_html` shows a placeholder on the canvas instead of running. That is partly UX (you cannot click-edit a YouTube embed) and partly safety: the canvas is same-origin with a live admin session, so `|safe` block HTML would execute with the admin's cookie. The trust model is unchanged from the public site, but an `editor` authoring HTML that an `admin` later opens is a path worth knowing about.
- Inline editing is opt-in per element. Anything without an `fe()` marker — `post_list`'s titles and excerpts, which belong to *other* posts — simply is not editable, which is the point.
- `DummyGateway` moves no money.
- `post_types` and `settings` are cached per process, not per cluster. A multi-worker deployment sees an update after `uncache()` runs in *that* worker.
- FAQPage JSON-LD is not wired up (§9).

Run `/ponytail-debt` to harvest the current ledger from source.
