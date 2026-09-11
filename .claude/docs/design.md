# IOPSTOR CMS — architecture spec (current state, 2026-09-10)

**What this file is.** The map an agent reads before touching anything: what exists, where it lives, and *why* it has the shape it has. The territory is the source, and the long-form developer reference is `docs/TECHNICAL.md` (§ numbers below point into it). Client brief and client decisions: `requirements.md`. Rules and commands: `CLAUDE.md` (repo root).

**Keeping it true.** Every PR that changes the shape of the system updates this file in the same PR (CLAUDE.md rule 3), and `/after-merge` audits it against the merged diff after every merge (rule 4). If a statement here and the source disagree, the source wins — fix this file in the next PR.

---

## 0. Where things stand

| Area | State |
|---|---|
| Content model, data access, migrations | Done (13 tables, migrations `0001`–`0007`; `0007` is a data migration awaiting the user) |
| Public site with the client's design | Done — the mock in `website_assets/mock-website.html` is the reference; header is white by client decision. Pictures and PDFs come from the app itself (§7 `/media/`), so nothing a visitor loads needs Supabase |
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
| Data / auth / files | Self-hosted **Supabase**, reached **only through its Kong gateway** with `supabase-py` 2.x and the service-role key: PostgREST for rows, GoTrue for logins, Storage bucket `media` for uploads **and reads**. Only this app ever talks to it — a browser does not, not even for a picture (§7 `/media/`). No direct Postgres, no ORM — rows are dicts |
| Tokens | PyJWT verifies Supabase access tokens locally (HS256, `SUPABASE_JWT_SECRET`) |
| Packaging | pipenv (`Pipfile`, `Pipfile.lock`, in-project `.venv/`); `requirements.txt` / `requirements-dev.txt` are **generated from the lock** and are what Docker installs |
| Deploy | Dokploy → `Dockerfile` (python:3.13-slim, `flask migrate && gunicorn`; workers from `GUNICORN_CMD_ARGS` — `-w 2 --threads 8 --preload --access-logfile -` by default, `-w 30` in Dokploy; the app is stateless across workers, TECHNICAL.md §15) |
| Production | **One Dokploy Compose service** from `docker-compose.yml`: `app` (that Dockerfile) + `cloudflared`, GitHub `primesukh/iopstor` as the source, `https://www.iopstor.com`. Supabase from Dokploy's own template, a separate stack, reached at `http://<kong-service>:8000` over the external `dokploy-network`. `app` has no `ports:` and no Traefik labels — **the tunnel is the only ingress**, which is what makes `CF-Connecting-IP` trustworthy (the throttle row in §14, TECHNICAL.md §12). Runbook: TECHNICAL.md §15 |
| Tests | pytest; `tests/test_offline.py` always, the rest marked `live` and skipped without `SUPABASE_*` in `.env` |
| Admin JS | `static/admin.js`, plain browser JavaScript, progressive enhancement; one vendored library, SortableJS 1.15.6 |

Rejected on the way (user decisions, see git history): SQLAlchemy + psycopg over `DATABASE_URL`, Alembic, Flask-Admin, uv, a CDN-loaded editor, a JS framework anywhere.

---

## 2. Layout

```
CLAUDE.md .claude/            rules for agents; docs/ (this file, requirements.md), skills/, hooks/, settings.json
Pipfile Pipfile.lock requirements*.txt pytest.ini .env.example Dockerfile docker-compose.yml .dockerignore .graphifyignore
iopstor/__init__.py           create_app(): refuses to start without SUPABASE_*; Jinja globals rupees(), media_url, media_alt, media_download; /healthz
iopstor/config.py             os.environ → constants (a module, not a class)
iopstor/db.py                 the single data-access seam: table()/one()/rows()/insert()/update(), live(), select_posts(), with_paths()/ancestors()/hydrate(),
                              tree(), unique_slug(), ensure_term(), set_post_terms(), paginate(), admin_counts(), get_menu()/set_menu(), post_types()/settings() caches
iopstor/auth.py               GoTrue login/refresh/logout, verify_jwt(), current_user(), require_role(), create/delete auth user, set_password(); ROLES editor<admin
iopstor/throttle.py           failed-password counter (sqlite on /dev/shm, shared by every worker); client_ip() reads CF-Connecting-IP; fails open
iopstor/storage.py            save_upload()/delete_media() → Storage bucket + media table; ALLOWED mime → extension,
                              EXT the reverse; public_path() = /media/<key> (what media.url holds), fetch() = the bytes
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
iopstor/templates/admin/      base.html (sidebar shell) login dashboard posts post_form canvas seo_card media leads warranty menus settings users account error
iopstor/static/               site.css (the whole theme) admin.css (admin extras) canvas.css (editor chrome) admin.js favicon.svg + PNGs vendor/sortable.min.js
migrations/                   0000_bootstrap.sql (hand-run once) 0001_initial 0002_enable_rls 0003_warranty 0004_warranty_date_check
                              0005_post_types_without_pages 0006_product_fields; repair_schema_migrations.sql (hand-run, not a step)
tests/                        conftest.py test_offline.py test_auth.py test_admin_api.py test_admin_ui.py test_public.py
docs/                         TECHNICAL.md (developers) NON-TECHNICAL.md (editors)
website_assets/               the client's mock (mock-website.html), pictures and partner logos — tracked, imported into Supabase with `flask import-media`
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
| `media` | `key` (bucket path), `url` (**`/media/<key>`, the path this app serves it at — not the Storage address**), `filename, mime, size, alt, uploaded_by` |
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
- `db.post_types()` / `db.settings()` are **per-request** caches — `db._cached()` stores on `flask.g`, and `uncache()` drops the key inside the same request. Nothing survives a request, so nothing can go stale between workers however many are running; the price is one PostgREST round trip each per request (TECHNICAL.md §15, §17).
- Never `.delete()` without a filter — PostgREST would truncate the table.
- Order of every list: `menu_order`, then `published_at desc`. `menu_order` is not in the admin form (only the seed and `PATCH /posts/<id>` write it).

---

## 5. Blocks (`iopstor/blocks.py` — the only place a block type is declared)

`BLOCKS = {type: (required, optional)}`, eighteen types: `hero, rich_text, image, gallery, cards, columns, cta, faq, stats, testimonial, embed_html, post_list, spec_table, contact_form, pdf, warranty_check, spacer, divider`. Each has `templates/blocks/<type>.html` wrapped `<section class="section{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap">…`.

**Alongside `BLOCKS`:** `EDITOR` (widgets per field, repeater `items` subfields, labels, `kinds`, `choices` = `[value, label]` pairs for the generic `choice` dropdown, `order` of the picker, `names` = icon + plain name + one-liner, `seed` = starting content that must pass `validate_blocks`), `REPEATERS`, `LAYOUTS` (three starting page shapes), `NEVER_NESTED = ("columns", "hero")` (mirrored in `admin.js`), `MD_SKIP = ("embed_html",)`.

**Layout keys on any block's `data`:** `align`, `align_box`, `width` (`wide` | `full` | px), `tone` (`grey` | `dark` | `blue`), `fx` (`rise` | `gradient` | `sweep`), `height` (`small` | `medium` | `large` | `huge`). All whitelisted by `section_class()` / `section_style()` because they land in `class` / `style`; all in `_NON_TEXT_KEYS`; the first four deliberately *not* fields in `BLOCKS` so the editor renders one set of controls for every type.

**Section effects.** `fx` is the exception to that last sentence — and `height` is the second one: `section_class()` emits both for any block, but only the blocks that *declare* them get the dropdown (`fx` on `stats` and `rich_text`, `height` on `spacer`), which is what limits each to its own panel — widening either is one word in another block's optional list. `stats` also carries `count_up` (a checkbox, so nothing typed reaches a class, same reason as `hero.dark`), and both keys repeat **per item**: `EDITOR["items"]["stats"] = ["value", "label", "fx", "count_up"]` and `stats.html` resolves each `<li>` as `item.fx or section.fx`, running the per-item value through `section_class()` itself rather than a second whitelist. `count_up()` splits the first whole number out of a figure (`"Up to 5 PB"` → `(5, "Up to ", "5", " PB")`) so only the digits roll; the digits stay in the HTML and CSS draws the counter beside them. All four effects are pure CSS (§9). `--w` is the content measure override, `--w-def` the block's own designed measure (§6 explains the specificity trap that made `--w-def` necessary).

**The two blocks that are not content.** `spacer` (`([], ["height"])`) is blank height an editor picks from `HEIGHTS`; `divider` (`([], [])`) is one `<hr>` inside `.wrap`, so the universal `width`/`align_box` already shorten it and move it and it needs no field of its own. `spacer` is in `MD_SKIP`; `divider` is the one `blocks_md()` branch that is punctuation (`---`). Both are droppable inside a column. The whole cost of them is CSS: `.section{padding:80px 0}` makes an empty section 160px tall, and inside a column `.column>.section+.section{padding-top:24px}` (0,3,0) beats a bare `.spacer` — so the rule group zeroes both and ties that specificity with `.column>.section.spacer`, and the four heights are scoped `.spacer.sp-*` rather than bare like `.fx-*`, since another block could one day declare `height`. `canvas.css` outlines a spacer so the editor can see a section that is by definition invisible.

**Special cases inside `render_blocks()`:** `post_list` (queried at render time, hands the template `posts` + `pt_slug` from the DB row), `warranty_check` (looked up from `?sn=` at render time; `edit=True` never queries), `columns` (the one block that holds blocks: `data.cols` is a list of lists, one level deep, `col(n)` callable, `widths` "50/25/25"). `edit=True` also hands templates `fe()` markers (`data-b` path, `data-f`, `data-r/data-i`, `data-rich`) that cannot reach the public render. A malformed block re-raises on the public site and renders an "unfinished" notice on the canvas.

**Two flatteners:** `blocks_text()` (deterministic reading order via `_TEXT_ORDER`, for admin search and the public API `text`) and `blocks_md()` (one branch per type; the body of every `.md` twin and `llms-full.txt`). **Test gates when adding a block:** `test_editor_metadata_covers_every_block`, `test_blocks_md_covers_every_block`, `test_render_blocks_uses_template` (markers tight against the tag). Full checklist: `/new-block`.

**Rules of thumb:** `hero` is the only block with an `<h1>` (`post.html` skips the page head when a post starts with a hero *or* a columns block); variant switches are checkboxes (`hero.dark`, `testimonial.dark`), never free text; raw HTML in `rich_text`/`embed_html` is trusted staff-only (`# ponytail:` add `nh3` if untrusted authors appear).

---

## 6. Auth

- Admin API: `Authorization: Bearer <access token>`; `POST /api/admin/v1/auth/login|refresh|logout`, `GET /auth/me`. 401 bad credentials; 403 for a GoTrue user with no `users` row (authentication ≠ authorization).
- Browser admin: same login through a form; tokens in the signed session cookie (SameSite=Lax, Secure on https), `auth._session_token()` refreshes silently, and a refresh that loses to a concurrent one leaves the session alone. Every POST carries a per-session `csrf` field checked by `ui_required`; `next` accepts relative same-origin paths only.
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
| media | `/media/<bucket key>` → `public.media_file()`: Flask fetches the object with the service-role key and serves it (`?download=<name>` = attachment; an SVG also gets a `sandbox` CSP, because same-origin now means the admin's cookie). `media` is a **reserved first segment** |
| crawler files | `/sitemap.xml /robots.txt /llms.txt /llms-full.txt /feed.xml`, `/healthz` |
| public JSON | `/api/v1/post-types`, `/posts?type=&term=&page=`, `/posts/<type>/<slug>` (with `text`), `/taxonomies/<slug>/terms`, `/menus/<slug>`, `/settings`; `POST /leads`, `POST /payments/checkout`, `POST /payments/webhook/<provider>` |
| admin | `/admin/{login,logout,,posts,posts/new,posts/<id>,posts/<id>/delete,media,media/upload,media/<id>/alt,media/<id>/delete,leads,leads/<id>/status,warranty,warranty/<id>/delete,menus,settings,users,users/<uuid>/delete,users/<uuid>/password,account,canvas,preview}` |

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
- **Logo is a fixed box, not a fixed height**: `.brand img{width:150px;height:22px;object-fit:cover}`, one rule for header and footer (2026-09-10). The mock's `height:22px;width:auto` counted an uploaded file's own padding as logo — the live 2172x724 PNG has its wordmark in the middle 271 rows and rendered at 8px. `cover` crops the box full so the file's margins stop mattering; the 6.8:1 box shaves ~1px a side off the original 180x26 artwork, and a square logo drawn edge to edge loses its top and bottom.
- **Mega panel is CSS only** (`:hover`/`:focus-within`, `:has()` to switch groups, 8-group ceiling), fed by `service_nav()` over `db.tree("service")`.
- **Hero rotator is CSS** (`--n`/`--i`, one keyframe set per picture count: 2 and 3 exist). `.hero-dots` sits *outside* `.hero-slides` — that element carries the `float` loop and anything inside it bobs with the picture; do not move the dots back in (2026-09-10).
- **Section effects are CSS** (`fx-rise`, `fx-gradient`, `fx-sweep`, `fx-count`): `@property --cv` + `counter()` for the roll, `animation-timeline: view()` for the scroll trigger. Four things not to undo. (1) The group is **base rules + a trailing `@supports (animation-timeline: view())`** that only adds `animation-timeline`/`animation-range`: every browser plays the effect at load, modern ones re-time it to the scroll. Putting the whole feature inside that gate makes it do *nothing* in Firefox ≤143, which parses the property but cannot resolve `view()` and so freezes each animation on its opening frame. (2) **No `var()` in the counter's keyframe** — Firefox will not interpolate one and the figure jumps 0 → 300 in a single frame, while Chrome tweens it, so the bug does not show in a Chromium screenshot; `--cv` runs a literal `0 → 1` and `counter-reset: cv calc(var(--to) * var(--cv))` applies the target. (3) The sweep is a **background**, not an `::after` with `z-index:-1`, which would sit behind the section's band. (4) **One effect, one element** — `animation` is a single property, so the counter is animated on its own `.cr` span or it silently replaces the sweep and the gradient on the same `<strong>`.
- **`prefers-reduced-motion` is the LAST block in the file and says `!important`** (2026-09-10). `@media` adds no specificity; from where it used to sit it lost to the block groups below it, and the hero kept moving for a reader who had asked it not to.
- **Archive grid is `auto-fill`, page deck is `auto-fit`**; four archive shapes scoped to `.arch-body` (`pl-product`, `pl-service`, `pl-event`, `pl-datasheet`); `pl-service` unpins `grid-column` under 700px.
- **Long words wrap**: `overflow-wrap:break-word` on `body`, `anywhere` on content-sized boxes only.
- **The quote form is grey, not black** (client, 2026-09-10): `contact_form` has two skins across three kinds — `quote` and `career` both take `.cf-grey`, `contact` the plain white card. The mock draws the Contact screen's form on a black card; do not restore `.cf-dark` from it.
- **Price rides on the Buy button** (`Buy · ₹ 10,000`), never a detail tile; `rupees()` groups Indian-style.
- **Product page has no hero**: the page head *is* the design's detail header.
- One `_card.html` macro for archive, page lists and post children; `actions=True` (archive only) turns product/datasheet/service cards into `<div>`s with linked titles because an `<a>` cannot nest.

---

## 10. Admin (`/admin`)

**Shell** (`admin/base.html`): 248px black sidebar with its own class names (`.adm-*`, never the public header's), counts from `db.admin_counts()` as `nav_counts`. Each row carries an icon from one inline `<svg hidden>` sprite of sixteen `<symbol>`s (`<use href="#i-…">`, stroke properties inherited from `.adm-nav .ic`); the CONTENT rows are `post_types` rows, so a Jinja `ICON` map keys slug → symbol and falls back to `i-dot`. Dark-surface colours come from `--muted-dark-2`, not `--muted`; the active row is `--black-3` with an inset blue left edge, `aria-current="page"` and a `:focus-visible` outline. The footer's user block is an avatar plus a name line and an email line, both `nowrap` + ellipsis (`min-width:0` on both flex levels, or the ellipsis never fires) with the full address in a `title`; the name is the `display_name()` Jinja global — `users.name`, written once by the Users screen's invite form, else derived from the email. No rename route. Screens: dashboard, per-type lists (search, status), post form, media (upload, alt edit, delete), leads (new/in_progress/handled), warranty register (list, search, add/edit on one page, refusal keeps what was typed), menus (flat rows → nested items, level as a `<select>`), settings (four CSS tabs — all panes stay in the DOM because the save blanks any missing key; payments provider read-only from env), users, account (`/admin/account`: change your own password, every role, linked from the sidebar footer). Failed passwords are counted by `throttle.py` — a sqlite file on `/dev/shm` (tmpfs: shared by all ~30 gunicorn workers, wiped on redeploy), keyed `ip:` for the two anonymous logins and `user:` for the password-change re-check, never by email; fails open, skipped under `TESTING`, limits in `config.py`. The signed-out screen (`login.html` under `.admin-anon`) is a **column** flex capped at 420px: `base.html` renders flashes as a sibling of the card, and in the default row two `width:100%` children split the viewport. Login refusals are an `error=` on the template, not a flash.

**Document editor** (`post_form.html` + `admin.js`, TECHNICAL §12.1): a post opens as one empty `rich_text` with the caret in it; `/` on an empty line inserts a section; every section has a hover bar (drag via SortableJS, ↑↓, duplicate, ⚙ settings popover, remove); `columns` are drop targets with their own bars. The canvas is `POST /admin/canvas` → `render_blocks(edit=True)` in an iframe via `srcdoc`; typing writes straight into the block objects, only structural changes re-render — and then one block (`?p=<path>`). *Advanced* is the raw JSON textarea, still the only field that POSTs, so `_form_body()` → `apply_post()` → `validate_blocks()` stays the single validation path. Toolbar commands run against the canvas document (`savedRange`; the bar goes dead rather than lying after a re-render). Style select offers Normal + H1–H6 (H1 present but not default); size is a separate `rem` dropdown disabled on headings; paste keeps an allowlist of tags; link/picture/table/embed are modal dialogs; table columns resize by dragging (writes a `<colgroup>`). Slug is auto from the title (`freeSlug()` mirrors `db.unique_slug()`), unlocked by *Edit* with a taken-warning; terms are a chip picker posting `new_terms` as `"<taxonomy>:<Name>"`, resolved only on save.

**Preview** (`POST /admin/preview`): the real `post.html` in the real `base.html` from the unsaved form, `noindex`, no analytics (`{% if site.ga_id and not preview %}`), device widths 1440/834/390 by scaling the iframe.

**The `[hidden]` rule:** `.admin [hidden]{display:none!important}` — author `display` rules beat the UA's `[hidden]`, which once showed two panes at once.

---

## 11. Seed, media import, assets

`flask seed` is idempotent through `_get_or_create()` — **which only ever inserts**: a change to `POST_TYPES` (field_schema, has_pages) or `SETTINGS` does *not* reach an existing row; that needs a migration that `UPDATE`s it (`0005`, `0006` are the pattern). `--reset-content` overwrites blocks/excerpt/meta of the seed-defined posts only. Seeds: 8 post types, taxonomies (industry, solution, category, tag), the services tree (5 groups / 17 services, with the ZFS columns section on the NAS page), 7 case studies, 2 events, 14 partners, pages (home with rotator hero / services / stats / case studies / CTA, about, careers, contact, technology partners), settings, header/footer menus.

`flask import-media DIR [--dry-run]` uploads every image/PDF under a folder with the same key scheme as `/admin/media`, idempotent on filename, alt text drafted from the name. The seed looks pictures up **by filename** (`cli.media_id()`), so it is valid before any import and wires them in after one: `Untitled-4.png` → home hero, `banner-homepage-96tb.png` → ZFS section / IOPStor Edge, `DSC_0305n.png` → IOPStor Classic, `background1.jpg` → About backdrop, `iopstor_logo-png1.png` → `logo_url`, `partners/*` → partner logos. Those files live in `website_assets/` (tracked since 2026-09-10, so a fresh clone can seed without hunting for the client's originals).

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
| 2026-09-10 | Section effects (count-up, fade-in, gradient, sweep) are pure CSS; the no-JS rule on the public site holds | The hero already animates in CSS; `@property` + `counter()` + `view()` timelines cover it, and a script would have made this the first JS the public site ships |
| 2026-09-10 | Counting rolls the first **whole** number only, and refuses a grouped `1,200` | A CSS counter is an integer with no thousands separator; counting to `1200` under a figure typed `1,200` would print a number the editor never wrote |
| 2026-09-10 | Effects repeat per Numbers item, resolved as `item.fx or section.fx` through the same `section_class()` | One figure often wants to differ from its band; a second whitelist would be a second thing to keep in step |
| 2026-09-10 | Section effects are base rules + an `@supports` that only re-times them; never the whole feature inside the gate | Firefox ≤143 parses `animation-timeline` but cannot resolve `view()`, and froze every effect on its opening frame — the feature did nothing at all |
| 2026-09-10 | Spacers and dividers are two block types, not spacing controls on every section's ⚙ | An editor looks for "a gap" and "a line" in the section picker, and a thing you can drag, copy and delete beats two more boxes in a panel that already has five |
| 2026-09-10 | A spacer's height is a four-value whitelist, never a number of pixels | It lands in a class attribute; the px route is `section_style()`-shaped work for a control nobody asked to be exact |
| 2026-09-10 | No `var()` in an animated custom property's keyframe | Firefox will not interpolate one and jumps in a single frame; Chrome tweens it, so a Chromium screenshot hides the bug entirely |
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
| 2026-09-10 | Pictures and PDFs are served by Flask at `/media/<bucket key>`; `media.url` stores that path, so every reader followed without a change | Supabase goes LAN-only — a browser that cannot reach the gateway must still be able to load a picture |
| 2026-09-09 | `.claude/` refreshed with every PR merge; hard rules enforced in `settings.json` | The map had drifted six days behind the territory |
| 2026-09-09 | `/after-merge` owns the whole graph refresh; the git hooks are not relied on after a pull | A fast-forward pull fires no hook, so the graph sat three commits behind `main` on the first run |
| 2026-09-09 | `gh pr merge` taken off the deny list; the agent merges only when told, on that PR | A deny cannot see consent, and the user wants to say "merge it" and have it done |
| 2026-09-10 | Logo sized by a fixed 150x22 box cropped with `object-fit:cover`, shared by header and footer | A fixed height alone does not normalise a logo: whitespace baked into the PNG was being counted as logo, so a swapped-in file rendered at less than half the size |
| 2026-09-10 | The mega panel's pane is the next sibling of its own link, opened by `+` and held open by `.mega-pane:hover` | Pairing link and pane by `nth-child` could not survive the cursor leaving the link: the pane snapped back to group one across the 55px of padding between the two columns, so only the first group's tiles were ever clickable. Sibling hover also drops the eight-group ceiling and lets `Tab` reach the tiles |
| 2026-09-10 | The login throttle counts in a `sqlite3` file on `/dev/shm`, keyed by `CF-Connecting-IP`, and fails open | Thirty gunicorn workers in one container means a module-level dict is thirty counters and thirty times the ceiling; tmpfs is the shared memory they can all reach, and it clears on redeploy, which is the right lifetime. sqlite buys the cross-process locking, expiry and unbounded keys that ~60 lines of hand-packed `mmap` would have had to get right — so `CLAUDE.md`'s "no SQLite" rule gained a carve-out for a volatile counter that is not application data (user, 2026-09-10). `ProxyFix` was wrong for a Cloudflare tunnel: several hops means `x_for=N` is a guess, while `CF-Connecting-IP` is set by the edge and unreachable around an outbound-only tunnel. Keys are the address, never the email — an email-keyed lock is a weapon against a named user. Fails open because a broken counter must never lock the owner out. Per container: two replicas would double the limit, and Redis is the upgrade |
| 2026-09-10 | A password change proves the current password by signing in with it (`login()`), not by trusting the session cookie; both paths end in `auth.set_password()`, which only calls GoTrue's admin update | A session says who logged in once, not who is at the keyboard now. The re-login afterwards is equally load-bearing: GoTrue can revoke the refresh token minted under the old password, so without fresh tokens the user is signed out one click after changing it. Reset-by-email is out until GoTrue has SMTP — this Supabase is LAN-only — so a locked-out user is handled by an admin setting a new password on the Users screen, which refuses your own row |
| 2026-09-10 | The admin sidebar's display name is derived from the email when `users.name` is empty, rather than a migration making it required | `users.name` has existed since `0001_initial.sql` but defaults to `''` and `flask create-admin` never fills it, so every install starts with no name to show. `sukhpreet.saluja@…` → *Sukhpreet Saluja* is right often enough to need no data entry, and the invite form's *Name* field covers the rest. A self-service rename screen was built and then removed (user, 2026-09-10): one field, one route and a second heading in the panel, for a value that is set once at invite and right by default everywhere else. Correcting an existing name is a Studio row edit |
| 2026-09-10 | The app is stateless across gunicorn workers by construction, so the worker count is deploy config (`GUNICORN_CMD_ARGS`, raised in Dokploy), not a number in the Dockerfile; a token refresh that loses to a concurrent one returns `None` and leaves the session alone | Asked whether thirty workers is safe (user, 2026-09-10): every cache is `db._cached()` on `flask.g` (per request), the only per-process object is the Supabase client, the throttle is per container, sessions and CSRF are the cookie, uploads are `uuid4` keys, and every read-then-write sits behind a `UNIQUE` constraint — nothing to fix for thirty processes. What more parallelism did make likelier: `_session_token()` cleared the session when a refresh failed, and the editor's paired preview requests refresh the same single-use token on two workers, so the loser's empty `Set-Cookie` could arrive after the winner's and sign the editor out mid-edit; Flask sends a cookie only for a modified session, so not touching it is the whole fix. `--preload` is on by default: the client is built after the fork, the throttle connects per call, and Python reseeds `random` in every child. Sizing lives in TECHNICAL.md §15 — 63 MB a worker unshared, thirty `--preload` workers measured at 472 MB of real memory, threads near free, PostgREST's `PGRST_DB_POOL` (10 by default) is the real ceiling |
| 2026-09-10 | Production is one Dokploy Compose service holding `app` and `cloudflared`, not an Application plus a separate tunnel service; `SECRET_KEY` and `SITE_URL` join `create_app()`'s `REQUIRED`; `/healthz` stops touching Supabase; the CSRF token is minted for `admin_ui` requests only | Splitting the tunnel into its own Dokploy service means naming the app's *generated* container as the origin — read off the host with `docker ps` and different after any recreate, so the ingress rule silently points at nothing. Inside one compose project the service name is the DNS name, so the origin is a fixed `http://app:8000`, and `docker compose up -d` still rebuilds only `app`, leaving the tunnel connected. The three code changes are all the same failure: something that broke *silently* in this topology. `SECRET_KEY` fell back to a string printed in this repo and `auth.py` takes a session token as a Bearer fallback; `SITE_URL` fell back to localhost, which both publishes localhost canonicals and computes `SESSION_COOKIE_SECURE` to `False`, so the admin cookie crossed the tunnel unflagged — dropping their defaults turns both into a refusal to boot. `/healthz` ran a PostgREST query under a 30 s `HEALTHCHECK`, making one Supabase blip restart a healthy container whose restart re-runs `flask migrate`, which needs Supabase too; migrate in `CMD` is already the boot-time gate, so liveness-only loses nothing. `app_context_processor` is app-wide despite its blueprint, so every anonymous page minted a CSRF token and answered with `Set-Cookie`, which no HTTP cache stores — the public site could never be edge-cached. `ProxyFix` stays wrong for all of this: nothing reads `request.scheme`/`host` (every absolute URL is `SITE_URL`) and every `redirect()` is relative, so there is nothing for it to correct. This also closes the 2026-09-10 worker-count row: it named `PGRST_DB_POOL` (10 by default) as the real ceiling, and `-w 30 --threads 8` is 240 slots in front of it, so raising it is now a deploy step, not a note |
| 2026-09-10 | The contact form's skin is decoupled from its `kind`: `quote` and `career` share `.cf-grey` and the `.cf-dark` rules are deleted | The client asked for the Contact page's quote panel to match Careers, colour only. Recolouring it in the admin means switching *Form type* to `career`, which also drops the two quote-only questions and files the enquiry as a career application — so the skin had to move in the template, not the content. A per-block *Panel colour* field would cost the eleven places `/new-block` lists for a choice nobody has asked for; there is exactly one quote form on the site (`cli.py:408`), so site-wide and this-page are the same thing. This overrides the mock (`requirements.md`, 2026-09-10), like the white header before it |

---

## 15. Known ceilings

Marked `# ponytail:` in source (36 at last count; `/ponytail-debt` harvests them). Deployment-side, not in source: `flask migrate` runs at boot with no lock, so two containers starting a *new* migration together leave the loser with `relation already exists` and one wasted boot (one replica is the deployed shape; `pg_advisory_xact_lock` in `apply_migration()` is the fix); the container runs as root; `/healthz` is liveness-only, so nothing polls Supabase's health. The ones an agent trips over: HS256-only JWT; hierarchy index < 2000 posts per type; one sitemap < 5000 URLs; honeypot-only spam control; raw HTML trusted; `execCommand` editor; rotator keyframes for 2 and 3 pictures only; per-request caches, so `post_types` and `settings` cost a round trip each per request; a redirect's `hits` loses counts under parallel visits; PostgREST calls wait up to 120 s; `checkout` and `index` are reserved slugs; counting rolls whole numbers only and refuses grouped ones; scroll *triggering* needs Chrome 115+ / Safari 26+ / Firefox 144+ and otherwise plays at load; the counter needs `@property` (Firefox 128+) or the figure reads 0; `_html_md()` is regex, not a parser; `/media/` is a reserved first segment, its files are read whole into memory and have no server-side cache; `DummyGateway` moves no money.

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
