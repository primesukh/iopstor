# IOPSTOR CMS — architecture spec (current state, 2026-09-09)

**What this file is.** The map an agent reads before touching anything: what exists, where it lives, and *why* it has the shape it has. The territory is the source, and the long-form developer reference is `docs/TECHNICAL.md` (§ numbers below point into it). Client brief and client decisions: `requirements.md`. Rules and commands: `CLAUDE.md` (repo root).

**Keeping it true.** Every PR that changes the shape of the system updates this file in the same PR (CLAUDE.md rule 3), and `/after-merge` audits it against the merged diff after every merge (rule 4). If a statement here and the source disagree, the source wins — fix this file in the next PR.

---

## 0. Where things stand

| Area | State |
|---|---|
| Content model, data access, migrations | Done (13 tables, migrations `0001`–`0006`) |
| Public site with the client's design | Done — the mock in `website_assets/mock-website.html` is the reference; header is white by client decision |
| Browser admin `/admin` | Done — sidebar shell, document editor with `/` sections, live preview at three widths, media, leads, warranty register, menus, settings, users |
| SEO + AI output | Done — meta/OG/JSON-LD, sitemap, robots, RSS, `llms.txt`, `llms-full.txt`, a `.md` twin of every page |
| Warranty register + public serial check | Done |
| Payments | Placeholder only (`DummyGateway`); a real provider is the one open item from the brief |
| FAQPage JSON-LD from the `faq` block | Not wired up (§9 known gap) |

---

## 1. Stack and platform

| Piece | Choice |
|---|---|
| App | Python 3.13, Flask 3.1, Jinja2; one public stylesheet, no JS on the public site, no build step |
| Data / auth / files | Self-hosted **Supabase**, reached **only through its Kong gateway** with `supabase-py` 2.x and the service-role key: PostgREST for rows, GoTrue for logins, Storage bucket `media` for uploads. No direct Postgres, no ORM — rows are dicts |
| Tokens | PyJWT verifies Supabase access tokens locally (HS256, `SUPABASE_JWT_SECRET`) |
| Packaging | pipenv (`Pipfile`, `Pipfile.lock`, in-project `.venv/`); `requirements.txt` / `requirements-dev.txt` are **generated from the lock** and are what Docker installs |
| Deploy | Dokploy → `Dockerfile` (python:3.13-slim, `flask migrate && gunicorn -w 2`) |
| Tests | pytest; `tests/test_offline.py` always, the rest marked `live` and skipped without `SUPABASE_*` in `.env` |
| Admin JS | `static/admin.js`, plain browser JavaScript, progressive enhancement; one vendored library, SortableJS 1.15.6 |

Rejected on the way (user decisions, see git history): SQLAlchemy + psycopg over `DATABASE_URL`, Alembic, Flask-Admin, uv, a CDN-loaded editor, a JS framework anywhere.

---

## 2. Layout

```
CLAUDE.md .claude/            rules for agents; docs/ (this file, requirements.md), skills/, hooks/, settings.json
Pipfile Pipfile.lock requirements*.txt pytest.ini .env.example Dockerfile .dockerignore .graphifyignore
iopstor/__init__.py           create_app(): refuses to start without SUPABASE_*; Jinja globals rupees(), media_url, media_alt, media_download; /healthz
iopstor/config.py             os.environ → constants (a module, not a class)
iopstor/db.py                 the single data-access seam: table()/one()/rows()/insert()/update(), live(), select_posts(), with_paths()/ancestors()/hydrate(),
                              tree(), unique_slug(), ensure_term(), set_post_terms(), paginate(), admin_counts(), get_menu()/set_menu(), post_types()/settings() caches
iopstor/auth.py               GoTrue login/refresh/logout, verify_jwt(), current_user(), require_role(), create/delete auth user; ROLES editor<admin
iopstor/storage.py            save_upload()/delete_media() → Storage bucket + media table; ALLOWED mime → extension
iopstor/blocks.py             BLOCKS, EDITOR, LAYOUTS, NEVER_NESTED, validate_blocks(), section_class()/section_style()/col_widths(),
                              render_blocks(), blocks_text(), blocks_md(), at_path(), _post_list(), _warranty()/warranty_active()
iopstor/seo.py                site(), build_meta(), jsonld(), md_url()
iopstor/payments.py           PaymentGateway, DummyGateway, GATEWAYS
iopstor/admin_api.py          /api/admin/v1 JSON API; apply_post() is the one validation path for posts; error handlers
iopstor/admin_ui.py           /admin: session login, CSRF, every screen, POST /admin/canvas (editor render), POST /admin/preview
iopstor/public.py             catch-all resolve() (+ .md twins, checkout), archives, crawler files, /api/v1, leads, checkout, service_nav()
iopstor/cli.py                flask migrate | seed [--reset-content] | import-media DIR [--dry-run] | create-admin
iopstor/templates/            base.html post.html archive.html 404.html checkout.html _card.html (the one card macro)
iopstor/templates/blocks/     one <section> template per block type (16)
iopstor/templates/admin/      base.html (sidebar shell) login dashboard posts post_form canvas seo_card media leads warranty menus settings users error
iopstor/static/               site.css (the whole theme) admin.css (admin extras) canvas.css (editor chrome) admin.js favicon.svg + PNGs vendor/sortable.min.js
migrations/                   0000_bootstrap.sql (hand-run once) 0001_initial 0002_enable_rls 0003_warranty 0004_warranty_date_check
                              0005_post_types_without_pages 0006_product_fields; repair_schema_migrations.sql (hand-run, not a step)
tests/                        conftest.py test_offline.py test_auth.py test_admin_api.py test_admin_ui.py test_public.py
docs/                         TECHNICAL.md (developers) NON-TECHNICAL.md (editors)
website_assets/               the client's mock (mock-website.html), pictures and partner logos — untracked, imported with `flask import-media`
graphify-out/                 the knowledge graph (gitignored); code nodes rebuilt by git hooks per commit, prose + labels only on main via /after-merge
```

Dependency direction: `public.py` and `admin_ui.py` import from `admin_api.py`; everything imports `db.py`; `db.py` imports nothing from the app.

---

## 3. Tables (`migrations/0001_initial.sql` + `0003`–`0006`)

| Table | Purpose / notable columns |
|---|---|
| `post_types` | content types **as rows**: `slug, name, url_prefix ("" = top-level pages), hierarchical, field_schema [{key,label,type,required}], taxonomies [slugs], jsonld_type, in_sitemap, has_pages (0005)` |
| `posts` | everything editable: `post_type_id, parent_id, slug, title, excerpt, blocks [{type,data}], meta {}, seo {title,description,canonical,robots,og_image}, status draft/published, published_at (future = scheduled), featured_media_id, author_id, menu_order`; unique `(post_type_id, slug)` |
| `taxonomies`, `terms`, `post_terms` | classification; `post_terms` has a composite PK so PostgREST can embed `terms(*)` |
| `media` | `key` (bucket path), `url`, `filename, mime, size, alt, uploaded_by` |
| `users` | `id` = GoTrue `sub`; `email, name, role editor/admin` — the row is what grants CMS access |
| `leads` | `kind contact/quote/career, name, email, phone, company, message, post_id, data {}, status new/in_progress/handled` |
| `warranties` (0003, 0004) | `serial`, `serial_key` = `upper(btrim(serial))` **generated, unique** (the lookup key: case- and space-insensitive, exact `.eq()` because serials may hold `%`/`_`), `customer_name, email, purchase_date, expiry_date, amc, remarks, remarks_public`; CHECK `expiry_date >= purchase_date` added `NOT VALID` |
| `settings` | `key` → JSON `value` (site_name, tagline, logo_url, default_og_image, social_links, ga_id, contact_email, contact_phone, address, robots_extra, notify_email) |
| `menus` | `slug` header/footer → `items [{label, url, children}]`, one level |
| `redirects` | `from_path → to_url`, `code`, `hits` |
| `payments` | `provider, provider_ref, post_id, lead_id, amount, currency, status, raw` |
| `schema_migrations` | applied file names, created by the bootstrap |

RLS is on for every table (`0002`; a new table repeats the one `ENABLE ROW LEVEL SECURITY` line, no policies) so the anon key sees nothing; the service-role key bypasses it. NOT NULL columns carry defaults; `updated_at` via `moddatetime` triggers.

**`field_schema` types in use:** `text, textarea, number, date, url, media, json, kv`. Nothing validates the list — an unknown type falls through to a text input, so adding one is additive. `kv` (0006) is label/value rows stored as an ordered **array** `[{k,v}]`, because `jsonb` sorts an object's keys and a spec table must keep its order.

**Seeded types:** `page ""`, `post blog`, `service services` (hierarchical), `case_study case-studies`, `event events`, `partner partners` (`has_pages=false`), `datasheet datasheets`, `product products` (price in rupees, `specs` kv, `sku`, `datasheet_media_id`).

**Migrations.** One numbered `.sql` per schema edit, applied in name order by `flask migrate` through the `apply_migration(name, sql)` RPC (SECURITY DEFINER, service_role only, one transaction per file; `0000_bootstrap.sql` creates it and is pasted into Studio once). Only `[0-9][0-9][0-9][0-9]_*.sql` is a step (`MIGRATION_GLOB`); `repair_schema_migrations.sql` is a hand-run repair for a database that was built by pasting files before the ledger existed (`migrate()` names it when a run fails with "already exists"). Agents never apply migrations — see `/migration`.

---

## 4. Data access contracts

- `db.select_posts()` embeds `post_type:post_types(*)`, `featured_media:media(*)`, `terms(*, taxonomy:taxonomies(*))` in one round trip; term filtering adds `post_terms!inner(term_id)`.
- `db.with_paths()` / `db.hydrate()` attach `path` from a per-request hierarchy index; a `has_pages=false` type gets `path=None`, and *that one value* is what removes its detail page, sitemap entry, `.md` twin, card link and JSON `url` — no per-feature checks.
- `db.live(q)` = `status='published' AND published_at <= now()`; every public query goes through it.
- `db.tree(type)` = top-level live posts with `children`, memoised per request; feeds the header mega panel, the services archive and `post_list(top_level)`.
- `db.post_types()` / `db.settings()` are **per-process** caches invalidated by `uncache()` (a multi-worker deploy sees an update after that worker's own `uncache()`).
- Never `.delete()` without a filter — PostgREST would truncate the table.
- Order of every list: `menu_order`, then `published_at desc`. `menu_order` is not in the admin form (only the seed and `PATCH /posts/<id>` write it).

---

## 5. Blocks (`iopstor/blocks.py` — the only place a block type is declared)

`BLOCKS = {type: (required, optional)}`, sixteen types: `hero, rich_text, image, gallery, cards, columns, cta, faq, stats, testimonial, embed_html, post_list, spec_table, contact_form, pdf, warranty_check`. Each has `templates/blocks/<type>.html` wrapped `<section class="section{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap">…`.

**Alongside `BLOCKS`:** `EDITOR` (widgets per field, repeater `items` subfields, labels, `kinds`, `order` of the picker, `names` = icon + plain name + one-liner, `seed` = starting content that must pass `validate_blocks`), `REPEATERS`, `LAYOUTS` (three starting page shapes), `NEVER_NESTED = ("columns", "hero")` (mirrored in `admin.js`), `MD_SKIP = ("embed_html",)`.

**Layout keys on any block's `data`:** `align`, `align_box`, `width` (`wide` | `full` | px), `tone` (`grey` | `dark` | `blue`). All whitelisted by `section_class()` / `section_style()` because they land in `class` / `style`; all in `_NON_TEXT_KEYS`; deliberately *not* fields in `BLOCKS` so the editor renders one set of controls for every type. `--w` is the content measure override, `--w-def` the block's own designed measure (§6 explains the specificity trap that made `--w-def` necessary).

**Special cases inside `render_blocks()`:** `post_list` (queried at render time, hands the template `posts` + `pt_slug` from the DB row), `warranty_check` (looked up from `?sn=` at render time; `edit=True` never queries), `columns` (the one block that holds blocks: `data.cols` is a list of lists, one level deep, `col(n)` callable, `widths` "50/25/25"). `edit=True` also hands templates `fe()` markers (`data-b` path, `data-f`, `data-r/data-i`, `data-rich`) that cannot reach the public render. A malformed block re-raises on the public site and renders an "unfinished" notice on the canvas.

**Two flatteners:** `blocks_text()` (deterministic reading order via `_TEXT_ORDER`, for admin search and the public API `text`) and `blocks_md()` (one branch per type; the body of every `.md` twin and `llms-full.txt`). **Test gates when adding a block:** `test_editor_metadata_covers_every_block`, `test_blocks_md_covers_every_block`, `test_render_blocks_uses_template` (markers tight against the tag). Full checklist: `/new-block`.

**Rules of thumb:** `hero` is the only block with an `<h1>` (`post.html` skips the page head when a post starts with a hero *or* a columns block); variant switches are checkboxes (`hero.dark`, `testimonial.dark`), never free text; raw HTML in `rich_text`/`embed_html` is trusted staff-only (`# ponytail:` add `nh3` if untrusted authors appear).

---

## 6. Auth

- Admin API: `Authorization: Bearer <access token>`; `POST /api/admin/v1/auth/login|refresh|logout`, `GET /auth/me`. 401 bad credentials; 403 for a GoTrue user with no `users` row (authentication ≠ authorization).
- Browser admin: same login through a form; tokens in the signed session cookie (SameSite=Lax, Secure on https), `auth._session_token()` refreshes silently. Every POST carries a per-session `csrf` field checked by `ui_required`; `next` accepts relative same-origin paths only.
- Roles: `editor` (content, media, leads, warranty add/edit) < `admin` (delete, post types, settings, users, redirects, warranty delete).
- Sign-in uses a throwaway anon client, never the service-role client.

---

## 7. URLs

| Type | URL |
|---|---|
| page | `/<slug>`; slug `home` = `/` (`/home` → 301) |
| post | `/blog/<slug>`, archive `/blog` |
| service (hierarchical) | `/services/<group>/<slug>`, `/services/<group>`, archive `/services` (groups with child tiles) |
| case_study / event / datasheet / product | `/<prefix>/<slug>`, archive `/<prefix>` |
| partner (`has_pages=false`) | archive `/partners` only; `/partners/<slug>` 404s |
| product checkout | `/products/<slug>/checkout` — handled inside the resolver; `checkout` is a reserved last segment |
| term archive | `/<taxonomy>/<term>` |
| Markdown twin | any resolvable URL + `.md`; `/` → `/index.md` (`index` is a reserved page slug); gated by `_indexable()` like the sitemap |
| crawler files | `/sitemap.xml /robots.txt /llms.txt /llms-full.txt /feed.xml`, `/healthz` |
| public JSON | `/api/v1/post-types`, `/posts?type=&term=&page=`, `/posts/<type>/<slug>` (with `text`), `/taxonomies/<slug>/terms`, `/menus/<slug>`, `/settings`; `POST /leads`, `POST /payments/checkout`, `POST /payments/webhook/<provider>` |
| admin | `/admin/{login,logout,,posts,posts/new,posts/<id>,posts/<id>/delete,media,media/upload,media/<id>/alt,media/<id>/delete,leads,leads/<id>/status,warranty,warranty/<id>/delete,menus,settings,users,users/<uuid>/delete,canvas,preview}` |

Resolver order: trailing slash → 301; `.md` suffix stripped (flag read from `request.path`, never `g`); `redirects` table; post type by first segment (hierarchical matched on the full path); page slug; taxonomy/term; 404 (HTML, JSON under `/api/`). A form POST to `/api/v1/leads` redirects back with `?sent=1`; `website` is a honeypot.

---

## 8. SEO and AI output (`seo.py` + `public.py`, server-rendered)

`build_meta()` → title, description, canonical, robots, OG/Twitter image, `markdown` (the twin URL, empty on `noindex`). `jsonld()` → Organization + WebSite on home, BreadcrumbList elsewhere, then per `jsonld_type`: BlogPosting/Article, Product (offers in INR), Service, Event, Organization. `_indexable()` (published, has a path, not `noindex`) gates sitemap, `llms.txt` and the twins alike. `llms.txt` links the `.md` twins; `llms-full.txt` is `blocks_md()` per page under a `##`. The sitemap never lists twins. Base template links the favicon set and Google Fonts (the one external request).

---

## 9. Theme (`static/site.css`)

Tokens at the top (`--black*`, `--blue*`, `--grey`, `--line*`, `--ink*`, `--muted*`, `--green/--red`, `--wrap` 1200px, `--reading` 760px, `--head` Manrope 800 / `--body` IBM Plex Sans / `--mono`), then header + mega panel + footer, `.cards/.card/.btn/.section`, the layout group (`.al-*`, `.alb-*`, `.w-*`, `.t-*`), then one rule group per block. A second line of **legacy aliases** (`--navy`, `--accent`, …) keeps `admin.css`/`canvas.css` rendering until they are restyled (`ponytail:` delete when unused).

Shared three ways: public pages, `body.admin` (via `admin/base.html`), and the editor canvas iframe (`admin/canvas.html` + `canvas.css`) — so the canvas is a real render of the real theme.

Decisions that are easy to undo by accident:

- **Header is white** with the logo in its own colours (client, 2026-09-08); the footer stays dark and knocks the logo out.
- **`--grey` (`#edf1f6`) is the only light-band fill**, and `body.admin` shares it. It has to stay clear of `--line` (`#e5e9ef`): close the gap and the white cards on a grey band lose their edge. Darkened from `#f4f6f9` on 2026-09-09.
- **Mega panel is CSS only** (`:hover`/`:focus-within`, `:has()` to switch groups, 8-group ceiling), fed by `service_nav()` over `db.tree("service")`.
- **Hero rotator is CSS** (`--n`/`--i`, one keyframe set per picture count: 2 and 3 exist).
- **Archive grid is `auto-fill`, page deck is `auto-fit`**; four archive shapes scoped to `.arch-body` (`pl-product`, `pl-service`, `pl-event`, `pl-datasheet`); `pl-service` unpins `grid-column` under 700px.
- **Long words wrap**: `overflow-wrap:break-word` on `body`, `anywhere` on content-sized boxes only.
- **Price rides on the Buy button** (`Buy · ₹ 10,000`), never a detail tile; `rupees()` groups Indian-style.
- **Product page has no hero**: the page head *is* the design's detail header.
- One `_card.html` macro for archive, page lists and post children; `actions=True` (archive only) turns product/datasheet/service cards into `<div>`s with linked titles because an `<a>` cannot nest.

---

## 10. Admin (`/admin`)

**Shell** (`admin/base.html`): 230px black sidebar with its own class names (`.adm-*`, never the public header's), counts from `db.admin_counts()` as `nav_counts`. Screens: dashboard, per-type lists (search, status), post form, media (upload, alt edit, delete), leads (new/in_progress/handled), warranty register (list, search, add/edit on one page, refusal keeps what was typed), menus (flat rows → nested items, level as a `<select>`), settings (four CSS tabs — all panes stay in the DOM because the save blanks any missing key; payments provider read-only from env), users.

**Document editor** (`post_form.html` + `admin.js`, TECHNICAL §12.1): a post opens as one empty `rich_text` with the caret in it; `/` on an empty line inserts a section; every section has a hover bar (drag via SortableJS, ↑↓, duplicate, ⚙ settings popover, remove); `columns` are drop targets with their own bars. The canvas is `POST /admin/canvas` → `render_blocks(edit=True)` in an iframe via `srcdoc`; typing writes straight into the block objects, only structural changes re-render — and then one block (`?p=<path>`). *Advanced* is the raw JSON textarea, still the only field that POSTs, so `_form_body()` → `apply_post()` → `validate_blocks()` stays the single validation path. Toolbar commands run against the canvas document (`savedRange`; the bar goes dead rather than lying after a re-render). Style select offers Normal + H1–H6 (H1 present but not default); size is a separate `rem` dropdown disabled on headings; paste keeps an allowlist of tags; link/picture/table/embed are modal dialogs; table columns resize by dragging (writes a `<colgroup>`). Slug is auto from the title (`freeSlug()` mirrors `db.unique_slug()`), unlocked by *Edit* with a taken-warning; terms are a chip picker posting `new_terms` as `"<taxonomy>:<Name>"`, resolved only on save.

**Preview** (`POST /admin/preview`): the real `post.html` in the real `base.html` from the unsaved form, `noindex`, no analytics (`{% if site.ga_id and not preview %}`), device widths 1440/834/390 by scaling the iframe.

**The `[hidden]` rule:** `.admin [hidden]{display:none!important}` — author `display` rules beat the UA's `[hidden]`, which once showed two panes at once.

---

## 11. Seed, media import, assets

`flask seed` is idempotent through `_get_or_create()` — **which only ever inserts**: a change to `POST_TYPES` (field_schema, has_pages) or `SETTINGS` does *not* reach an existing row; that needs a migration that `UPDATE`s it (`0005`, `0006` are the pattern). `--reset-content` overwrites blocks/excerpt/meta of the seed-defined posts only. Seeds: 8 post types, taxonomies (industry, solution, category, tag), the services tree (5 groups / 17 services, with the ZFS columns section on the NAS page), 7 case studies, 2 events, 14 partners, pages (home with rotator hero / services / stats / case studies / CTA, about, careers, contact, technology partners), settings, header/footer menus.

`flask import-media DIR [--dry-run]` uploads every image/PDF under a folder with the same key scheme as `/admin/media`, idempotent on filename, alt text drafted from the name. The seed looks pictures up **by filename** (`cli.media_id()`), so it is valid before any import and wires them in after one: `Untitled-4.png` → home hero, `banner-homepage-96tb.png` → ZFS section / IOPStor Edge, `DSC_0305n.png` → IOPStor Classic, `background1.jpg` → About backdrop, `iopstor_logo-png1.png` → `logo_url`, `partners/*` → partner logos. Those files live in `website_assets/` (untracked; the client's).

---

## 12. Payments

`PaymentGateway` (`create_checkout()`, `handle_webhook()`) + `DummyGateway` (`redirect_url = /api/v1/payments/dummy/<id>`, webhook `{payment_id, status}`), selected by `PAYMENT_PROVIDER` through `GATEWAYS`. `POST /api/v1/payments/checkout` answers JSON with 201 and a plain form with a 303 to the gateway. A real provider = subclass with signature verification + env change; the checkout *page* (`checkout.html`) already exists.

---

## 13. Tests

`tests/test_offline.py` always runs (slugify, validate/render/text/md of blocks, editor metadata coverage, layout whitelists, columns, warranty status, rupees, kv rows, has_pages, migration glob, JWT matrix). `conftest.py` builds the app, admin/editor headers and a seeded corpus, cleaning up after; `test_auth.py`, `test_admin_api.py`, `test_admin_ui.py`, `test_public.py` are marked `live`. Known flake: `test_browser_admin_login_and_create_post` asserts `data-taken=""` for Blog and fails while leftover `zz-test-*` rows sit in the dev database. `/services?page=2` past the last page returns 500 (`db.paginate()` raises `PGRST103` before the 404 guard) — pre-existing, unfixed.

---

## 14. Engineering decision log

| Date | Decision | Why |
|---|---|---|
| 2026-09-03 | Supabase through Kong only, dict rows, `.sql` migrations, pipenv | Client's platform; no second database, no ORM to fight |
| 2026-09-03 | Content types are rows; per-type fields in `posts.meta` described by `field_schema` | "Job Openings" must not need a developer |
| 2026-09-03 | The graph's LLM pass (prose, labels) runs only on `main`; since 2026-09-04 git hooks keep the code nodes current per commit | A branch may never land; labelling it wastes tokens. Code re-extraction is free, so it can follow the branch |
| 2026-09-04 | Document editor over a form-based block editor; JSON textarea stays the one POSTed field | Editors type; one validation path survives |
| 2026-09-04 | Canvas is a server render in an iframe | Preview and published page cannot drift; `admin.css` cannot leak in |
| 2026-09-04 | Block address is a dotted path, `columns` nest one level, `NEVER_NESTED` | Grids in grids are how Elementor pages rot |
| 2026-09-04 | Layout keys (`align`, `width`, `tone`) are whitelists, not block fields | Values land in attributes; one control set for every type |
| 2026-09-04 | `menu_order` dropped from the form, kept in the table | Nobody could explain it; lists fall back to newest first |
| 2026-09-04 | Agents never write to the database; migrations are handed over | The dev database is shared and live |
| 2026-09-07 | Warranty lookup on a generated `serial_key`, no endpoint, whole record public by serial | Client wanted one box; `ilike` treats `%`/`_` as wildcards |
| 2026-09-07 | Theme from the client's mock, tokens at the top, SortableJS vendored | LAN editors without internet must still drag |
| 2026-09-08 | Header white with the logo in colour | Client request |
| 2026-09-09 | `has_pages` column on `post_types` (partners have no pages) | A type is a row; "does it get pages" is a property of the row |
| 2026-09-09 | Rupees only; `specs` is `kv` rows | A currency choice should not exist; `jsonb` sorts object keys |
| 2026-09-09 | `.md` twin of every page, rendered on request | AI crawlers read Markdown, not the theme; nothing to keep in sync |
| 2026-09-09 | `.claude/` refreshed with every PR merge; hard rules enforced in `settings.json` | The map had drifted six days behind the territory |
| 2026-09-09 | `/after-merge` owns the whole graph refresh; the git hooks are not relied on after a pull | A fast-forward pull fires no hook, so the graph sat three commits behind `main` on the first run |
| 2026-09-09 | `gh pr merge` taken off the deny list; the agent merges only when told, on that PR | A deny cannot see consent, and the user wants to say "merge it" and have it done |
| 2026-09-09 | `--grey` darkened to `#edf1f6`; one token still covers the site and the admin | The bands read as near-white on a bright screen. A public-only grey would add a second token and a per-rule choice for no gain |

---

## 15. Known ceilings

Marked `# ponytail:` in source (28 at last count; `/ponytail-debt` harvests them). The ones an agent trips over: HS256-only JWT; hierarchy index < 2000 posts per type; one sitemap < 5000 URLs; honeypot-only spam control; raw HTML trusted; `execCommand` editor; 8 mega-panel groups; rotator keyframes for 2 and 3 pictures only; per-process caches; `checkout` and `index` are reserved slugs; `_html_md()` is regex, not a parser; `DummyGateway` moves no money.

---

## 16. Agent tooling in `.claude/`

| Path | Role |
|---|---|
| `settings.json` | Permission **deny** list that enforces the hard rules mechanically (no `flask migrate/seed/create-admin/import-media`, no `pip install`, no `git merge`/push to main, no hand edits to generated `requirements*.txt` / `Pipfile.lock` / `.env`; `gh pr merge` is *not* denied so the user can delegate a merge by saying so); allow list for the read-only commands used every session; `includeCoAuthoredBy: false`; the session-start hook |
| `hooks/session-start.sh` | Prints branch, dirty files, the last 12 commits and how far behind `HEAD` the graph is (non-zero is normal right after a pull, until `/after-merge`; otherwise a git-hook rebuild failed — see `~/.cache/graphify-rebuild.log`) — rule 0 and the graph-freshness check, for free, every session |
| `skills/pr` | branch → checks → push → PR body → **stop** |
| `skills/docs` | which of the three docs a change touches, and in what voice |
| `skills/new-block` | the eleven places a block type lives |
| `skills/migration` | write a numbered `.sql`, never run it, code that tolerates the gap |
| `skills/theme-check` | Firefox-headless screenshots at 1440/834/390 on port 5001 against the mock |
| `skills/after-merge` | pull `main`, refresh the graph's prose and labels, audit `.claude/` against the merged diff |
| `docs/requirements.md` | the client brief verbatim + dated client decisions |

Per-machine facts (which CLI is installed, how screenshots work) go to Claude's memory directory, not this folder.
