# IOPSTOR CMS — Technical Documentation

A WordPress-shaped CMS for IOPSTOR (software-defined storage / cloud / HCI), written in Flask on top of a self-hosted Supabase.

Companion documents: [NON-TECHNICAL.md](NON-TECHNICAL.md) for editors, [`.claude/docs/design.md`](../.claude/docs/design.md) for the architecture spec, [`.claude/docs/requirements.md`](../.claude/docs/requirements.md) for the client brief.

---

## 1. Stack and constraints

| | |
|---|---|
| Language | Python 3.13 |
| Web | Flask 3.1, gunicorn, Jinja2 |
| Data / Auth / Files | Self-hosted **Supabase** via **supabase-py 2.x** — PostgREST, GoTrue, Storage, all through the Kong gateway. Only this app talks to it: a browser never does, not even for a picture |
| Tokens | PyJWT (local HS256 verification) |
| Packaging | pipenv (`Pipfile` + `Pipfile.lock`); `requirements*.txt` are generated from the lock and are what Docker installs |
| Tests | pytest |
| Deploy | Dokploy, Dockerfile + gunicorn |

Three constraints shape everything below:

1. **Supabase is the only backend, reached only through Kong, and only by this app.** No `DATABASE_URL`, no psycopg, no SQLAlchemy, no ORM. Rows are plain dicts. Supabase is on the LAN with nothing but Flask exposed, so every byte a visitor sees — pictures and PDFs included — is served by Flask (§8, `/media/<key>`).
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
iopstor/storage.py    save_upload() / delete_media() → Supabase Storage bucket + media table.
                      public_path() is the address the site serves an object at, fetch() reads the bytes back.
iopstor/blocks.py     BLOCKS registry, validate_blocks(), render_blocks(), blocks_text(), blocks_md()
iopstor/seo.py        site(), build_meta(), jsonld(), md_url()
iopstor/payments.py   PaymentGateway ABC, DummyGateway, GATEWAYS
iopstor/admin_api.py  /api/admin/v1 — JWT-protected REST. apply_post() is the single validation path.
iopstor/admin_ui.py   /admin — session-based browser admin, reusing admin_api's validation
iopstor/public.py     catch-all resolver, crawler endpoints, /api/v1 public read API, leads, checkout
iopstor/cli.py        flask migrate | seed | import-media | create-admin
iopstor/templates/    base/post/archive/404, blocks/<type>.html, admin/*.html
iopstor/static/       site.css (the whole public theme) + admin.css (admin extras, layered on top)
                      + canvas.css (editor chrome), favicon.svg, vendor/sortable.min.js
migrations/           0000_bootstrap.sql (run once by hand) + NNNN_name.sql applied by `flask migrate`
tests/                test_offline.py always runs; the rest need a live Supabase and skip without it
docs/                 this file + NON-TECHNICAL.md
.claude/              the agent's workspace: docs/design.md (architecture map) + requirements.md, skills/, hooks/, settings.json — §18
```

Dependency direction: `public.py` and `admin_ui.py` both import from `admin_api.py` (for `apply_post`, error handlers and pagination helpers); everything imports `db.py`; `db.py` imports nothing from the app.

---

## 3. Data model

Eleven tables from `migrations/0001_initial.sql`, plus `warranties` from `0003_warranty.sql` and `0004_warranty_date_check.sql`.

| Table | Purpose | Notable columns |
|---|---|---|
| `post_types` | Content types **as data** | `slug`, `url_prefix`, `hierarchical`, `field_schema` (JSONB), `taxonomies` (JSONB), `jsonld_type`, `in_sitemap`, `has_pages` |
| `posts` | Every piece of content | `post_type_id`, `parent_id`, `slug`, `title`, `excerpt`, `blocks` (JSONB), `meta` (JSONB), `seo` (JSONB), `status`, `published_at`, `featured_media_id`, `author_id`, `menu_order` |
| `taxonomies` / `terms` / `post_terms` | Classification, many-to-many | `terms` unique on `(taxonomy_id, slug)` |
| `media` | Uploads | `key` (the path inside the bucket), `url` (**the path this site serves it at, `/media/<key>` — not the Storage address**), `mime`, `size`, `alt`, `uploaded_by` |
| `users` | CMS roles. `id` **is** the GoTrue `sub` | `email`, `name`, `role` |
| `leads` | Form submissions | `kind`, contact fields, `data` (JSONB), `status` |
| `warranties` | The warranty register, looked up by serial number | `serial`, `serial_key` (generated), `customer_name`, `email`, `purchase_date`, `expiry_date`, `amc`, `remarks`, `remarks_public` |
| `payments` | Orders | `provider`, `provider_ref`, `amount`, `currency`, `status`, `raw` |
| `menus` | Header/footer nav | `items` (JSONB, one level of `children`) |
| `settings` | Key/value site config | `key`, `value` (JSONB) |
| `redirects` | Legacy URL mapping | `from_path` (unique), `to_url`, `code`, `hits` |
| `schema_migrations` | Applied migration names | created by `0000_bootstrap.sql` |

Indexes: `posts (post_type_id, status, published_at)`, `leads (status, created_at)`, `payments (provider, provider_ref)`, `warranties (expiry_date)`. `posts` is unique on `(post_type_id, slug)` — slugs are unique *per type*, not globally. `warranties` is unique on `serial_key`, a `GENERATED ALWAYS AS (upper(btrim(serial))) STORED` column: it makes the public lookup case- and whitespace-insensitive, stops two records claiming the same serial in different cases, and lets the lookup be an exact `.eq()` — a serial may legitimately contain `%` or `_`, which PostgREST's `ilike` would read as wildcards. A `CHECK` constraint, `warranties_expiry_after_purchase` (`0004`), refuses a record whose `expiry_date` is before its `purchase_date`; `/admin/warranty` pre-checks the same thing so an editor gets a sentence rather than a 502, exactly as it pre-checks the duplicate serial. It was added `NOT VALID` — enforced on every write, existing rows unscanned — because the table already held a record with the dates reversed; `ALTER TABLE warranties VALIDATE CONSTRAINT warranties_expiry_after_purchase;` promotes it once those are fixed. Warranty status is **not** stored: "in warranty" is `expiry_date` vs today, worked out at render time by `blocks.warranty_active()` so it can never go stale.

**Where per-type data lives.** `posts.meta` is a JSON bag described by `post_types.field_schema` — a list of `{key, label, type, required}` descriptors that the admin form renders and the detail template reads back. Types in use: `text`, `textarea`, `number`, `date`, `url`, `media`, `json`, `kv`. **Nothing validates that list** — `post_form.html` and `_form_body()` both fall through to a plain text input on a type they do not know, so adding one is purely additive.

**`kv` is a field edited as label/value rows** and stored as an ordered array, `[{"k": …, "v": …}]` (migration `0006` moves the product `specs` field onto it). Two reasons it is not the `json` type it replaced. First, `_form_body()` used to store the raw text of anything that would not parse, so a mistyped brace saved without complaint and `post.html`'s `is mapping` test then dropped the whole table off the live page; rows that will not parse are now no rows. Second, **`jsonb` sorts an object's keys**, so a spec table could never keep the order it was written in — an array can. The widget is the `repeater()` `spec_table` already uses (`admin.js:447`): `SPEC.ui.items["spec_table"]` is `["k", "v"]` and the labels are already *Label* and *Value*, so `initMetaRows()` passes that type in and gets add / remove / reorder for nothing. It reaches the server through a hidden input written on submit, the same trick `initMediaSelects()` uses. `post.html` renders a list in its own order and a legacy object as before.

**Prices are rupees, and only rupees.** `rupees()` is a Jinja global in `__init__.py` beside `media_url`; `{:,}` groups in threes all the way up and would print `12,50,000` as `1,250,000`, so it groups the last three digits and then twos. Anything non-numeric passes through, so a price typed as "on request" still prints. The three display sites (`post.html`'s Buy button, `checkout.html`'s total, `_card.html`'s card foot) all call it. **A price is never a detail tile.** `post.html` rejects the `price` key from the meta strip and puts it on the Buy button instead (`Buy · ₹ 10,000`), the same pairing `_card.html` makes in an archive card's footer: the price is the ask, not a fact about the product the way SKU is, and showing it twice on one page made a grey band out of a single number. `seo.py` and `public.py` keep the literal `"INR"` — a currency *code* for `priceCurrency` and the payments row is not display. The per-product `currency` field and the never-read `currency` setting under Payments are both gone. `posts.blocks` is the ordered page content, `[{type, data}, ...]` — flat, except a `columns` block, whose `data.cols` holds one such list per column (one level deep, see §6).

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
| `ensure_term()` | Term id for a name in a taxonomy, creating the row the first time. Matched on `slugify(name)`, so "All-Flash" and "all flash" are one term, not two |
| `set_menu(slug, items)` | The write side of `get_menu()`, so `/admin/menus` keeps every query in this module |
| `admin_counts()` | `{post-type slug: n}` plus `_leads`, for the sidebar. One query over posts counted in Python — PostgREST has no `GROUP BY`, and an exact-count call per type would be eight round trips a page |
| `tree(type_slug)` | Top-level live posts of one type, each with `p["children"]`. One query; the parent/child split happens in Python. Feeds the header's services panel, the services archive and `post_list(top_level)` |
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
/media/<bucket key>     an uploaded picture or PDF, served by the app (§8)
```

`/media/` is a **reserved first segment**, the way `checkout` and `index` are reserved slugs. Its route is
declared literally, so Werkzeug ranks it above the catch-all — but a `post_types.url_prefix` of `media`
would be unreachable, and so would a hierarchical page whose top-level slug is `media`.

---

### 5.1 Checkout

The design's Buy flow is a modal. The public site ships no JavaScript, so it is a page instead — which the handoff offers as the alternative. It is handled **inside the catch-all**, not as its own rule: a rule shaped `/<a>/<b>/checkout` would have to out-rank `/<path:path>`, and reading the last segment where the resolver already has the post type is six lines. A trailing `checkout` under a type's prefix resolves the segment before it, and 404s unless that post is live, sits at that exact path, and has a `meta.price`.

`POST /api/v1/payments/checkout` answers both callers: a JSON body still gets JSON and a `201`, and a plain form post gets a `303` to the gateway's `redirect_url` — the same `request.is_json` split `/api/v1/leads` already uses for `_form_redirect()`.

> `# ponytail:` `checkout` is a reserved last segment, so a product slugged `checkout` would be unreachable.

---

## 6. Blocks

`iopstor/blocks.py` is the only place a block type is declared:

```python
BLOCKS = {  # type: (required fields, optional fields)
    "hero": (["heading"], ["eyebrow", "subheading", "image", "images", "cta_label", "cta_url",
                           "cta2_label", "cta2_url", "dark"]),
    ...
}
```

Sixteen types ship: `hero`, `rich_text`, `image`, `gallery`, `pdf`, `cards`, `columns`, `cta`, `faq`, `stats`, `testimonial`, `embed_html`, `post_list`, `spec_table`, `contact_form`, `warranty_check`.

`hero` takes either one picture or several. `image` is the single one; `images` is a repeater of
`{media_id, alt}` and, from two rows up, becomes the design's rotator — the pictures take turns on
their own, in CSS (§12). Both keys stay, `images` wins when it holds two or more, so a hero that was
saved before this exists is untouched.

Three types carry a variant switch, and all three are **checkboxes**, never free text: `hero.dark` (the full-bleed band, where `image` becomes a faded backdrop instead of the art beside the words), `testimonial.dark`, and `contact_form`'s existing `kind`. The template tests them for equality (`{{ ' hero-dark' if data.dark }}`), so nothing an editor types can reach a class attribute — which is the same reason `section_class()` is a whitelist.

`post_list` gained `eyebrow`, `link_label` and `link_url` (the "All services →" link in a section header), and `render_blocks()` hands its template a **`pt_slug`** extra alongside `posts`. That becomes `pl-<slug>` on the section, and `site.css` styles one card per post type from it — the number for services, the logo for partners, the 16:9 picture and date for blog posts, the industry/solution chips for case studies. One template, the variants in CSS. `pt_slug` comes from the resolved `post_types` row, never from the block's own data, so it is safe in a class name.

When `top_level` is set on a hierarchical type, `_post_list()` also hangs each parent's live children off `p["children"]` for the chips under the card, reusing `db.tree()` — already memoised for the request by the header's services panel, so on most pages it costs nothing.

`archive.html`, `post.html` and `post_list.html` all draw their card from one macro, `templates/_card.html` — the same snippet used to be copied into three templates and drift between them.

The macro takes **`actions`**, which `archive.html` passes and the other two do not. Three types answer
it with a control of their own — a product's price and **Buy**, a datasheet's **Download**, a service's
child tiles — and an `<a>` cannot contain another `<a>`, so for those three the card becomes a `<div>`
with its title linked instead. Every other type, and every list inside a page, keeps the single-anchor
card it has always been. Two more inert spans ride along and are switched on by the `pl-<slug>` rule:
`.card-date` (an event's year and month, cut out of `meta.start_date`) and `.card-pdf` (a datasheet's
outline mark).

`render_archive()` hangs children off each row for a **hierarchical** type, the same `db.tree()` lookup
`_post_list()` uses, so the services archive can draw its child tiles. `render_post()` does the mirror
of it: a page with no children of its own but a parent gets its **siblings** instead, which is the
"Other Storage services" row the design ends a service page on (`siblings=True` only changes the heading).

The seed's pictures are looked up **by filename** through `cli.media_id()`, which returns `None` when the library is empty. That is why `home_blocks()` is a function rather than a constant, and why `_clean()` drops keys whose value is `None`: a seed run before `flask import-media` must still produce a valid page, and it must not leave `"image": null` in the saved JSON. The pairing is `Untitled-4.png` → the home hero, `banner-homepage-96tb.png` → the ZFS section and IOPStor Edge, `DSC_0305n.png` → IOPStor Classic, all three of them → the home hero's rotator in that order, `background1.jpg` → the About Us backdrop, `iopstor_logo-png1.png` → `settings.logo_url`, and `partners/*` → the fourteen partner posts' `logo_media_id`.

**Adding one** = an entry in `BLOCKS` + `templates/blocks/<type>.html`. The template must be wrapped in `<section class="section{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap">…` — `cls` is the layout classes, `sty` an inline width, `fe()` the edit marker (all three below); `render_blocks()` hands all three to every block template. Unknown types are rejected on save by `validate_blocks()`, which checks that every required field is present and non-empty.

**Layout keys.** Five optional keys on any block's `data`, absent = the theme's own layout:

| Key | Values | What it does |
|---|---|---|
| `align` | `left` \| `center` \| `right` | how the content inside the section lines up (headings, text, buttons, captions, images) |
| `align_box` | `left` \| `center` \| `right` | where the section's own box sits — only visible once the box is narrower than the page |
| `width` | `wide` \| `full` \| a number of px | the section's content measure; `full` also breaks it out of the page column |
| `fx` | `rise` \| `gradient` \| `sweep` | the section's motion, `FX` in the same file — see *Section effects* below |

Two functions carry them onto the root `<section>`, both **whitelists** rather than passthroughs, because the values land in attributes — the same reason `col_widths()` is strict:

- **`section_class(data)`** → `" al-center alb-right w-full"`, interpolated into the root `class`. `ALIGNS` and `WIDTHS` are the only values that survive.
- **`section_style(data)`** → `' style="--w:950px"'` for a **digits-only** `width` in `1..MAX_W` (4000), `""` for everything else, a named width included (that one is a class).

`--w` *is* the content measure: `site.css` writes every relevant `max-width` as `var(--w, <the theme's own value>)`, so an unset section renders exactly as designed, a number narrows or widens it, and `.w-wide` / `.w-full` set `--w:100%` from CSS. `.column{--w:initial}` stops a width set on a Columns section leaking into the sections inside it.

****`tone`** is the band a section sits on — `grey`, `dark` or `blue`, absent means the page's own white. The design alternates white and grey down the home page for rhythm and drops case studies onto black, and that is a per-section decision an editor makes, not something baked into a block type. Like `align` and `width` it is a **whitelist** in `section_class()`, because the value lands in a class attribute. Its rules sit *after* `.band-*` in `site.css`, so a tone an editor picks beats a block's own default (`stats` is dark, `cta` is blue) on source order rather than needing `!important`.

`--w-def` is what makes that sentence true.** The shared rule is `.section>.wrap>*{max-width:var(--w,var(--w-def,none))}`, and it is (0,2,0); every block's own rule (`.rich-text`, `.testimonial`, `.specs`, `.faq details`, `.lead-form`) is (0,1,0) or (0,1,1) and loses to it. So the fallback `none` used to win outright and the designed measures never applied at all — a section was only ever as wide as `--w` said, and unset meant full width. Each of those blocks now declares its measure as `--w-def` on itself, which the shared rule reads *inside* the fallback. `--w` stays the override it is documented to be, and `--w:initial` in a column still falls through to the block's own measure.

All of them are in `_NON_TEXT_KEYS`, so "center", "950" and "rise" never reach `llms-full.txt`, the feed or admin search — `tone` joined them at the same time, having leaked its "grey" into all three since it was added. `align`, `align_box`, `width` and `tone` are deliberately **not** fields in `BLOCKS`: layout belongs to every section, so `admin.js` renders one set of controls for all types (§12.1) and `validate_blocks()` simply tolerates the extra keys. `fx` is the exception — `section_class()` emits it for any block, but only `stats` and `rich_text` *declare* it, which is what puts the dropdown in those two panels and nowhere else. Widening it to another block is one word in that block's optional list. `.cta` and table cells keep their own `text-align`, so a centred section does not restyle a CTA band or a spec table.

**Section effects.** `fx` picks one of three, and `stats` carries a fourth as its own checkbox, `count_up`. They **compose** — a Numbers band can count up *and* be swept — so each is its own class rather than one mutually-exclusive value, and `count_up` is a checkbox for the same reason `hero.dark` is: a bool cannot spell anything into a class attribute.

A Numbers *figure* can also override its band. `EDITOR["items"]["stats"]` is `["value", "label", "fx", "count_up"]`, so every row in the repeater carries the same two settings, and `stats.html` resolves each `<li>` as `item.fx or section.fx` — a row that sets nothing inherits, a row that sets something wins. The per-item value goes through **`section_class()` itself**, called from the template as a Jinja global: one whitelist, not a second one to keep in step.

`count_up()` (`blocks.py`) is the only real logic. It finds the first whole number in a figure and splits the words off either side, so `"Up to 5 PB"` becomes `(5, "Up to ", "5", " PB")` and only the digits move. `stats.html` renders that as `Up to <span class="cv">5</span><span class="cr"></span> PB`: the digits an editor typed stay in the HTML inside `.cv`, and `.cr` is the empty span the CSS counter rolls into. That split is deliberate — the number has to survive for crawlers, for copy-paste, for a browser without scroll timelines, and for the canvas's own `contenteditable`, whose `textContent` still reads back `"Up to 5 PB"` unchanged. Two lookarounds in the regex refuse a grouped `"1,200"`: `counter()` cannot render a thousands separator, so it would settle on a figure spelled differently from the one the editor wrote. `test_count_up_splits_a_figure` and `test_one_figure_can_differ_from_its_band` guard both.

The CSS is §12. Nothing here is JavaScript.

Two behaviours worth knowing:

- **`hero` is the only block that renders its own `<h1>`.** `post.html` skips the page title when a post's first block is a hero.
- **`post_list` is queried at render time.** `render_blocks()` special-cases it, calling `_post_list()` to fetch live posts and passing them in as `posts`.
- **`columns` is the only block that holds other blocks.** `data.cols` is a list of columns, each an ordered `[{type, data}]` of its own; `data.widths` is `"50/25/25"` or blank. It uses the same `extra` hatch as `post_list`, so `columns.html` is handed a `col(n)` callable that renders column `n` and a `widths` string — no recursion is wired into Jinja, and `__init__.py` / `public.py` are untouched.
  - **One level only.** `validate_blocks(..., nested=True)` rejects `NEVER_NESTED = ("columns", "hero")` inside a column: a grid inside a grid is how an Elementor page becomes unmaintainable, and a hero is a full-bleed band owning the page's only `<h1>`. `admin.js` mirrors the tuple so the inserter never offers them and a drag into a column is refused.
  - **`col_widths(data)`** turns `"50/25/25"` into the `--cols` custom property `"50fr 25fr 25fr"`. Anything that is not exactly one positive number per column returns `""` (equal columns) — strict, because the value is interpolated into a `style` attribute. `site.css` puts the widths in `--cols` rather than straight into `grid-template-columns` so the `max-width:800px` stacking rule can override them without `!important` beating an inline style.
  - **`at_path(blocks, path)`** resolves a `data-b` path (`"3"`, `"3.1.0"`) to one block. `/admin/canvas?p=` is its only caller.
- **`warranty_check` is queried at render time too, from the URL.** The section is a plain `method="get"` form posting back to `request.path` with one `sn` field — **no route, no endpoint, no CSRF**: the lookup is a read, and the result is a bookmarkable URL a customer can forward to support. `render_blocks()` hands the block a `found` value from `_warranty()`: `None` when nothing was asked (draw the bare form), `{}` when the serial matched nothing, otherwise the `warranties` row with `active` added. The match is `.eq("serial_key", typed.strip().upper())` — see §3 for why the generated column, and not `ilike`, is the key. `edit=True` short-circuits it to `None`, so the admin canvas draws the box without touching the database. There is deliberately no `intro` field: explanatory copy is a `rich_text` section above it.
  - **The whole record is public to anyone holding the serial**, customer name and registered email included — the client's decision, so `remarks` is the one field held back unless the record's `remarks_public` is ticked. Marked with a `# ponytail:` comment on `_warranty()`: require the registered email as a second factor, or rate-limit, if serials turn out to be guessable.
- **`pdf` is an `<iframe>` at the file, nothing more** — the browser's own PDF viewer, no pdf.js. Its field is `file_media_id`, not `media_id`, because `EDITOR["labels"]` is keyed by the bare field name and `media_id` already reads "Image" (it also matches the `file_media_id` meta convention the `datasheet` type uses in `cli.py`). Height is fixed in `site.css` (`min(80vh,900px)`); the `<a class="btn ghost">` under the frame downloads the file — its `href` is the `media_download` Jinja global (`__init__.py`), the file's `/media/<key>` address plus `?download=<filename>`, which is how `public.media_file()` sets `Content-Disposition: attachment` and names the saved file after the upload instead of the uuid in its bucket key. Supabase Storage used to answer that query string; since §8 the app does, and the contract is deliberately unchanged. That button is also the way in for iOS Safari and Android Chrome, which render only the first page of a framed PDF or nothing at all — they save it rather than open it in a tab. `.btn.ghost` has to set its own `color` (and its own `:hover`) in `site.css`: `.btn` paints `color:#fff` for the accent fill, so a ghost button that only clears the background is white text and a white `currentColor` border on the light page. Unlike `embed_html` the canvas renders it for real. It used to be safe because the src was a cross-origin Storage bucket; a `/media/` URL is **same-origin with the admin session**, so the reason is now simply that a PDF in an `<iframe>` is a document, not a script with a cookie. `canvas.css` gives it `pointer-events:none` so a click still selects the section.

**Editor metadata.** Alongside `BLOCKS`, `blocks.py` exports `EDITOR` — how each field is edited in the browser admin, so the field shapes that used to live only in comments are data:

```python
EDITOR = {
    "widgets": {...},   # field key -> text | textarea | code | richtext | media | pdf | url | number | checkbox | post_type | kind | choice
                        # "<block>.<field>" overrides the bare key (e.g. "embed_html.html": "code")
    "items":   {...},   # block type -> the subfields of one repeater row (items / images / rows / cols)
                        # [] means the rows are not rows of fields: "columns" rows are lists of blocks
    "labels":  {...},   # friendlier field labels; missing keys fall back to the key itself
    "kinds":   [...],   # contact_form.kind options
    "choices": {...},   # field key -> [[value, label], …] for the `choice` widget (currently just fx)
    "order":   [...],   # the order the / picker offers types in (a type missing here is appended last)
    "names":   {...},   # block type -> (icon, plain-English name, one line ending in a full stop) for the picker
    "seed":    {...},   # block type -> starting content; must pass validate_blocks() except image/gallery/pdf
}
REPEATERS = ("items", "images", "rows", "cols")
```

`choice` is the one generic dropdown: unlike `post_type` and `kind`, whose options come from a named source, it reads `[value, label]` pairs out of `EDITOR["choices"][field]` — which is what lets the blank option read *None* rather than the *— choose —* a required field wants. It works in a repeater row for free, which is how a Numbers *item* gets its own effect dropdown.

`EDITOR` is metadata only — nothing on the render or validation path reads it, and an unknown widget just degrades to a text input. `tests/test_offline.py::test_editor_metadata_covers_every_block` fails if a new block's fields have no widget, if a `choice` field has no `EDITOR["choices"]` entry, or if a repeater field has no `EDITOR["items"]` entry (`[]` counts — `columns` has one); `test_inserter_metadata_and_seeds` fails if `names` or `seed` is missing, or the seed does not save as-is. Nothing tests that `templates/blocks/<type>.html` exists — render the seeded block once.

`blocks_text()` flattens all block content to plain text for admin search and the public API's `text` field. Because JSONB does not preserve key order, it walks fields in a fixed reading order (`_TEXT_ORDER`), with unknown keys appended alphabetically, so output is deterministic. It already recurses through dicts and lists, so a column's blocks are picked up for free — `"type"` and `"widths"` are in `_NON_TEXT_KEYS` so the literal string `"rich_text"` and a width spec do not leak into the output.

`blocks_md()` is its structured sibling: the same content as **Markdown**, keeping the headings, lists, tables, quotes and links that `blocks_text()` throws away. It is the body of every page's `.md` twin (§8) and of `llms-full.txt`. Unlike `blocks_text()`'s generic walk it is one branch per block type, so a **new entry in `BLOCKS` needs a branch here too** — `test_blocks_md_covers_every_block` fails until it has one, or until the type is listed in `MD_SKIP` (only `embed_html`: an iframe is a video or a map, not words). `blocks_md(blocks, h1=False)` demotes a hero's `#` to `###` for callers that have already opened a heading above it; `llms-full.txt` does, since it files every page under a `##`.

Rich text and FAQ answers are HTML, converted by `_html_md()` — a regex pass over the tags the admin's contenteditable emits (`h1`–`h6`, `p`, `br`, `ul`/`ol`/`li`, `strong`/`b`, `em`/`i`, `a`, `code`, `blockquote`), everything else stripped and entities unescaped. It is deliberately not a parser: a nested list or a pasted table comes out flat. `markdownify` is the upgrade path if editors start pasting complicated HTML.

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

`/login`, `/logout`, `/` (dashboard), `/posts`, `/posts/new`, `/posts/<id>`, `/posts/<id>/delete`, `/media`, `/media/upload`, `/media/<id>/delete`, `/leads`, `/leads/<id>/status`, `/warranty`, `/warranty/<id>/delete`, `/settings`, `/users`, `/users/<uuid>/delete`. Server-rendered forms; `_form_body()` turns form fields into the same body dict the JSON API accepts, so both surfaces share validation. `_safe_next()` restricts post-login redirects to relative same-origin paths.

`POST /admin/media/upload` is the one exception to "server-rendered forms": it takes the same multipart body as `POST /admin/media` (`csrf`, `file`, optional `alt`) through the shared `_upload()` helper, and answers `201 {id, url, filename, mime, alt}` or `4xx {error}` instead of redirecting. It exists so the post form's media pickers can upload without leaving the page; session auth and CSRF come from `ui_required()` unchanged.

`/admin/warranty` is the warranty register: list, `?q=` search over serial / customer / email, and one form that adds a record or edits the one named by `?edit=<id>` — the `users` screen's shape, with `db.paginate(..., 50)` and the `page` / `has_next` idiom used by `/admin/leads`. It refuses a duplicate `serial_key` with a `flash()` before writing, rather than letting a unique violation surface as a 502 through `_pg_error`. Editors may add and edit; **only an admin may delete**, matching `/admin/posts/<id>/delete`. The public side of this table needs no endpoint at all (§6, `warranty_check`).

It is post-redirect-get only when the write **succeeds**. A refused save falls through to the same render with the submitted values back in the form and a `400`, the way `new_post` / `edit_post` re-render rather than redirect — a redirect would answer a typo by making the editor retype the record. A refusal is a `(field, message)` pair, **not** a `flash()`: the form carries it as `data-refused-field` / `data-refused`, `initWarranty()` in `admin.js` puts it on that field with `setCustomValidity()` and calls `reportValidity()`, and a `<noscript>` copy says the same sentence without JS. Only a success flashes, at the top, where a confirmation belongs. `editing` is the form's contents, from `request.form` on a refusal and from the row on `?edit=`; the template keys add-vs-edit off `editing.id`, not off `editing` being truthy, so a rejected *new* record does not come back wearing an Edit heading. `?q=` and `?page=` ride through every redirect (save, delete, cancel) so a filtered list survives the round trip.

### `/media/<bucket key>` — the file proxy, `public.media_file()`

Every picture and PDF on the site, the admin included. Supabase sits on the LAN with only Flask exposed,
so a browser cannot fetch an object out of the Storage bucket: it asks Flask, and Flask asks Storage with
the service-role key it already holds (`storage.fetch()`).

The URL **is** the bucket key — `/media/2026/09/<uuid>.png` — so the route needs no database read at all.
The extension is looked up in `storage.EXT` (the reverse of `ALLOWED`), which both names the `Content-Type`
and whitelists what is servable: anything else 404s before Storage is touched, as does a key containing
`..`. Only `StorageApiError` becomes a 404 — a gateway that is down must still be a 500, not a lie about a
missing file.

Because a key carries a uuid, the bytes behind a URL never change, so `send_file()` is handed
`max_age=31536000` + `immutable` and the key as the ETag: a repeat view costs a 304 and no Storage round
trip, and `conditional=True` brings Range support with it, which is what a phone's PDF viewer asks for.
`?download=<name>` sets `Content-Disposition: attachment` — Supabase Storage used to do that, now this does.
The name is passed through with only `\r` and `\n` removed: werkzeug quotes and RFC-2231-encodes the rest,
and `secure_filename()` would rename "flash array.pdf" to "flash_array.pdf", defeating the point of the
button.

**An SVG gets `Content-Security-Policy: default-src 'none'; sandbox`.** This is the one thing serving media
ourselves made *worse*: an SVG is a document that can carry `<script>`, and a `/media/` URL is same-origin
with the admin session cookie, which a Storage URL never was. The header sandboxes a direct visit into an
opaque origin with scripts off, and changes nothing about `<img src>`, which never executes script. It is
scoped to SVG deliberately — an empty sandbox on a PDF can stop the browser's own viewer, which §6 depends
on. Guarded by `test_media_is_served_by_the_app_not_the_storage_gateway`.

**What is stored is the path, not the address.** `media.url` holds `/media/<key>` (written by
`storage.public_path()` at upload, in `save_upload()` and in `flask import-media`), which is why nothing on
the read side had to change: `media_url()`, `media_download()`, `featured_media.url` in `post.html` and
`_card.html`, `seo._image()`, `blocks._media()` and the admin JSON all hand back the column verbatim.
`seo._abs()` promotes it to an absolute `SITE_URL/media/...` for `og:image` and JSON-LD, which is exactly
the job it was written for and never did while the column held an absolute URL.
`migrations/0007_media_through_flask.sql` rewrites the rows that were written before this.

### Crawler endpoints

`/sitemap.xml`, `/robots.txt`, `/feed.xml`, `/llms.txt`, `/llms-full.txt`, plus `/healthz`.

### Markdown twins (`/<path>.md`)

Every URL the resolver can resolve also answers with `.md` on the end, serving `text/markdown` built
from the same rows — so an AI crawler reads the content instead of the theme. Nothing is written to
disk and there is no build step: the twin is rendered per request, so it cannot go stale.

| URL | twin |
|---|---|
| `/` | `/index.md` |
| `/about-us` | `/about-us.md` |
| `/services/storage/nas` | `/services/storage/nas.md` |
| `/blog` (type archive) | `/blog.md` |
| `/industry/finance` (term archive) | `/industry/finance.md` |

`resolve()` strips the suffix before it does anything else and then resolves exactly as it would for
the HTML page, so redirects, hierarchical paths, both kinds of archive and the 404 all come along
without a rule of their own. The flag is `_wants_md()` — read off `request.path` on each call rather
than stashed in `g`, because `g` lives on the app context, which a CLI run or a test client holds
open across several requests; a stale flag there would serve Markdown to a browser.

- **A post** (`_md_post()`) → YAML front matter (`title`, `url`, `type`, `published`, `updated`,
  `description`), then the body. The `#` comes from the hero when the page starts with one and from
  the post title otherwise, mirroring `post.html`, so the twin has the same single h1 as the page.
  The type's own `field_schema` values follow (`_md_fields()`, split by shape the way `post.html`
  splits them, with `price` through `rupees()` and a `media` field as the file's `/media/<key>` path), then
  `blocks_md()`, then the child/sibling links.
- **An archive** (`_md_page()`) → front matter, `# {title}`, the page's posts as a link list, and a
  `[Next page]` line while `has_next`.
- **Front matter** is written by `_front()`, which quotes every value with `json.dumps()` — a valid
  YAML double-quoted scalar, so a title containing a colon cannot break the block.

Not every URL gets one. `_indexable()` gates the twin exactly as it gates `sitemap.xml` and
`llms.txt`, so a draft or a `noindex` post 404s as Markdown too, and `/…/checkout.md` 404s because a
form is not content. `sitemap.xml` deliberately does **not** list the twins — duplicate URLs there
would read as duplicate content to Google.

Discovery is three-way: `<link rel="alternate" type="text/markdown">` in `base.html` (from
`meta.markdown`, empty on a `noindex` page), every entry in `/llms.txt` linking the `.md` rather than
the page, and a line in that file's Machine-readable section. `seo.md_url()` is the only place the
rule `/ → /index.md`, anything else `→ path + ".md"` is spelled.

> `"index"` is a reserved page slug: `/index.md` is the home page's twin, so a page slugged `index`
> would be shadowed. Same shape as the reserved `checkout` last segment (§8).

---

## 9. SEO

Everything is server-rendered from `seo.py` + `public.py`; keep it there.

- `build_meta()` — title, description, canonical, Open Graph, robots
- `jsonld()` — structured data driven by `post_types.jsonld_type` plus BreadcrumbList from the resolver's crumbs
- `md_url()` — the one place the `.md` twin's address is spelled (§8)
- `_indexable()` — a post whose `seo.robots` starts with `noindex` is kept out of the sitemap, `llms.txt` and its `.md` twin

`base.html`'s `<head>` also carries the favicon (`static/favicon.svg`, the black square with the blue bar and white ring) and the two web fonts. The fonts come from Google Fonts on a `<link>`, which is the one external request the public site makes; `admin/canvas.html` repeats that link because it is a standalone document, and without it the editor canvas would preview the page in a different typeface from the page itself.

> **Known gap.** The `faq` block emits Q&A markup but is not currently wired into FAQPage JSON-LD. The knowledge graph flagged this edge as AMBIGUOUS; it is a genuine, unimplemented opportunity.

---

## 10. Migrations

Plain `.sql` files in `migrations/`, named `NNNN_short_name.sql`, applied in name order and tracked in `schema_migrations`. **Only a four-digit-prefixed name is a step** (`MIGRATION_GLOB` in `cli.py`); anything else in the folder is a script run by hand and is never executed as part of a run.

`0000_bootstrap.sql` is pasted **once** into Supabase Studio's SQL editor. It creates `apply_migration(name, sql)` — `SECURITY DEFINER`, executable by `service_role` only — which `flask migrate` calls per file over Kong. Each file runs in one transaction.

**Workflow for a schema change:**

1. Write the `ALTER`/`CREATE` as a new numbered file
2. `pipenv run flask migrate`
3. Update the code that reads/writes those columns
4. Commit both together

**When the ledger and the database disagree.** A schema built by pasting the files into Studio leaves every table in place and `schema_migrations` empty, so `flask migrate` starts again at the beginning and stops on `0001_initial.sql: relation "menus" already exists`. Nothing is broken — the ledger simply never recorded what was done by hand. `migrations/repair_schema_migrations.sql` fixes it: pasted into Studio, it records each file **only if the thing that file makes is actually present** — the `posts` table for `0001`, `pg_class.relrowsecurity` for `0002` (the table can exist with RLS still off, which is the very state `0002` fixes), `warranties` for `0003`, the `warranties_expiry_after_purchase` constraint for `0004`. A file that was genuinely never applied stays unrecorded and `flask migrate` then applies it normally. Safe to run twice, and safe on a database in any state. `migrate()` names that script in its own error when the failure text contains "already exists".

Not every step alters the schema. `0007_media_through_flask.sql` is a **data** migration: it rewrites the
absolute Storage URLs frozen into `media.url`, `settings`, `posts.blocks` and `posts.seo` into `/media/<key>`
paths (§8). It matches any host with a regex rather than naming one, every statement is guarded so a second
run changes nothing, and the code works before **and** after it — new uploads already write the new path,
old rows keep the address they have until it runs.

`0002_enable_rls.sql` enables RLS on every app table, so the anon key cannot read drafts or leads. The app's service-role key bypasses RLS by design. A new table repeats that one line for itself — `0003_warranty.sql` ends with `ALTER TABLE warranties ENABLE ROW LEVEL SECURITY;`, and defines no policies.

---

## 11. Payments

`payments.py` defines the `PaymentGateway` interface (`create_checkout()`, `handle_webhook()`) and `DummyGateway`, selected by the `PAYMENT_PROVIDER` env var through `GATEWAYS`. `dummy` records the payment row and exposes `/api/v1/payments/dummy/<id>` to mark it paid, without charging anything. A real provider is a new subclass plus an env change.

---

## 12. Theme

One stylesheet, `static/site.css`, with the design tokens at the top, then header / mega menu / footer, then `.cards` / `.card` / `.btn` / `.section`, then the section-layout group (`.al-*` / `.alb-*` alignment and `.w-*` / `--w` width, §6), then one rule-group per block. `static/admin.css` layers admin-only rules on top, so `/admin` inherits the public theme.

**`site.css` is shared three ways** — the public site, `body.admin` (through `templates/admin/base.html`) and the editor canvas iframe (`templates/admin/canvas.html` loads it, then `canvas.css`). A change to `.card`, `.btn`, `.specs` or `.lead-form` shows up in all three, which is the point: the canvas is a real render of the real theme.

**Tokens.** `:root` holds the palette the design ships with — `--black`/`--black-2`/`--black-3` and `--line-dark`/`--line-dark-2` for the dark bands, `--blue`/`--blue-hover`/`--blue-tint`/`--blue-light`, `--white`/`--grey`/`--line`/`--line-2` for the light ones, `--ink`/`--ink-2`/`--muted`/`--muted-dark`/`--muted-dark-2` for text, `--green`/`--red` (plus `-bg`) for status, `--wrap` (1200px) and `--reading` (760px) for measure, and `--head`/`--body`/`--mono` for the three type stacks. Headings are Manrope 800, body is IBM Plex Sans.

A second, shorter line under them maps the *old* token names (`--navy`, `--accent`, `--accent-2`, `--text`, `--card`, `--radius`) onto the new palette. `admin.css` and `canvas.css` still reference those in ~90 places; the aliases keep the admin rendering while it is restyled in its own PR, and are marked `ponytail:` for deletion once nothing uses them.

**Animations.** Three on menus: `drop` (the mega panel at .22s and the Company drop-down at .2s, `cubic-bezier(.2,.7,.2,1)`), `fade` (the mega's right pane, .2s ease-out, as the pointer moves down the group list) and `slide` (the mobile sheet, .25s ease-out). Five on the hero, from the design's own keyframes: `rise` on the words (.7s), `heroin` on the picture column (.8s), `glow` on the radial wash behind it (5s, infinite), `float` on the picture itself (6s, infinite) and `dot3`/`dot2` on the rotator's progress dots. Every one-shot is `both`-filled so it holds its end state. The entrance pair is scoped to `.hero-split` — the hero with art beside it, which is the only hero the design animates; every other opening band is still. Hover work is `transition` at .15s.

**The hero rotator is CSS.** `hero.images` renders `.hero-slides` with the picture count inline as `--n` and each `.hero-slide` carrying its turn as `--i`. Every slide runs the same loop over the whole cycle (`calc(var(--n) * 4.5s)`) delayed by `calc(var(--i) * 4.5s)`, so exactly one is showing at a time with the design's slide-in / slide-out either side of its turn. The dots are `<span>`s, not buttons: they report which picture is up — a wide, solid blue bar for the whole of that slide's 4.5 seconds, small and grey for the rest — and they are `aria-hidden` because they say nothing the pictures' `alt` text does not. Both keyframe stops inside a slide's turn hold the same values on purpose, so there is nothing to interpolate and the bar cannot creep: it used to fill left to right across the turn, which read as a countdown timer (client, 2026-09-10). There is one keyframe set per count — `slides2`/`dot2` and `slides3`/`dot3` — because a slide's share of the cycle is written into the percentages; a fourth picture needs a fourth set, marked `ponytail:` in the file. Under `prefers-reduced-motion` the slides are stood down explicitly and the first picture is left showing: the mock's blanket `animation-duration:.01ms` would have parked every slide on its final frame, which is the hidden one.

**Section effects (`fx-*`)** are the four an editor can put on a Numbers or Rich text section (§6), and they are the file's only scroll-driven animations. `fx-gradient` paints the section's big text — every heading, plus a Numbers figure, which is a `<strong>` and not a heading at all — with the brand gradient through `background-clip:text`, drifting on a plain time loop. The other three ride `animation-timeline: view()`: `fx-rise` fades and lifts `>.wrap` (never the `<section>` itself, which would fade a dark band in from white), `fx-sweep` grows a marker-pen bar as the element's *own* `background-size` from `0 .3em` to `100% .3em`, and `fx-count` rolls a registered `@property --cv` through `counter()`.

Three things about that group are not obvious:

- **The bar is a background, not an `::after`.** A pseudo-element behind the text needs `z-index:-1`, which puts it behind the section's band as well, so the marker would simply disappear on `stats`. Painting it as the heading's own background sits it behind the glyphs and in front of the band, with no stacking context to manage. It also forces `width:fit-content`, or a block heading's bar runs the width of the column.
- **The group is written in two halves, and the split matters.** The rules run on the document timeline, so every browser plays them once at load — what `.hero-text` has always done. A trailing `@supports (animation-timeline: view())` then re-times *those same animations* against the section scrolling into view; it adds `animation-timeline` and `animation-range` and nothing else, so no keyframe is duplicated. The first draft put the whole feature *inside* that gate, and a browser that parses `animation-timeline` but cannot resolve `view()` — Firefox 140 ESR — then held every `both`-filled animation on its opening frame: `fx-rise` left the section at `opacity:0`, `fx-count` left an empty box, and to an editor on that browser the feature simply did not exist. A fallback that shows nothing is not a fallback.
- **The counter's keyframe must not contain a `var()`.** The obvious `@keyframes cv{to{--cv:var(--to)}}` tweens in Chrome and **jumps in one frame in Firefox**, which refuses to interpolate a keyframe whose value is a variable — so the figure snapped 0 → 300 and the bug was invisible in a Chromium screenshot. `--cv` is therefore registered as a `<number>` running a literal `0 → 1`, and the figure's own `--to` is applied at the far end by `counter-reset: cv calc(var(--to) * var(--cv))`, which `counter-reset` rounds to an integer. Verified by holding the animation at fixed points with a negative `animation-delay` — 140 → 183 → 242 → 296 across a 2s `ease-out`.
- **One effect, one element.** `animation` is a single property, so two effects landing on the same `<strong>` silently replace each other — the counter beat the sweep's wipe and the gradient's drift, and a counted figure could never also be swept. The roll is therefore animated on `.cr`, the empty span that carries it, leaving `<strong>` free for the sweep. Any future effect on a figure needs its own element or its own longhand.

**`prefers-reduced-motion` moved to the end of the file and now says `!important`.** `@media` adds no specificity, so from where it sat — above the block groups — `.hero-text{animation:none}` lost outright to `.hero-split .hero-text{animation:rise …}` further down, and the hero kept moving for a reader who had asked it not to. The effects join the same block: `fx-count` needs three lines rather than `animation:none`, because stopping the animation alone strands `--cv` at 0, so the counter is stood down (`content:none`) and `.cv`'s real digits come back out of hiding.

**`canvas.css` renders all four at rest.** `admin.js` swaps one `<section>` per keystroke (§12.1), so every effect would replay as an editor typed; the canvas shows their finished state instead — and putting the real digits back inside `<strong>` is what keeps a figure editable in place.

**One padding for both hero shapes.** `.hero-dark` always carries `.hero` as well (`hero.html` appends the modifier), so the dark band's 96px/80px is simply what `.hero` is — neither `.hero-dark` nor the 700px rule repeats it, and the phone step is one line at 64/56. The white hero used to sit at 72/56 and read as cramped against its own headline (client, 2026-09-10); the mock's bands are 64/56, so this is deliberately roomier than the design rather than a drift back towards it.

**The header is white**, not the mock's black — the client asked for it, with the logo in its own colours rather than knocked out. The knock-out filter therefore lives on `.site-footer .brand img`, not on `.brand img`, because the footer is still the dark band. The mobile sheet follows the header: a white panel with `--line` rules and `--ink` rows. Nothing else in the design changed colour.

**The services mega panel** is CSS only, like everything else on the public site. Its markup is a child of the Services `<li>`, absolutely positioned against `.site-header` — sticky is a positioned element, so it is the containing block, which is how the panel spans the viewport instead of the 1200px column. That is also why the Services `<li>` is `position:static` while every other one is `relative`: the Company drop-down has to anchor to its own item. **Opening is plain `:hover` / `:focus-within`**, so it works everywhere; only switching the visible group needs `:has()`, and a browser without it still opens the panel showing the first group. Eight groups is the ceiling (one `:has()` rule per index), marked `ponytail:` in the file. Under 960px the panel collapses into the checkbox sheet as a plain indented list — group column hidden, every pane shown, blurbs dropped.

Its data comes from `service_nav()` (`public.py`), a template global over `db.tree("service")` — `menu('header')` carries labels and URLs only, and the panel needs each group's `excerpt` and children. It is a callable rather than a value because the context processor is app-wide and an `/admin` page has no use for a posts query.

**Long words wrap.** `body` carries `overflow-wrap:break-word`, so an unbroken string (a pasted URL, a hash) breaks instead of running off the right of its section and giving the page a horizontal scrollbar — and it is inherited, so the editor canvas gets it too. `break-word` only wraps *inside* a box, and a grid track or a table column is sized from min-content, which a 300-character word still blows out; the boxes that size to their content (`.card`, `.column`, `.stats li`, table cells) get `overflow-wrap:anywhere`, which counts in that size. Not on `body`: `anywhere` would let the header nav break mid-word.

No CSS framework, no build step, no JavaScript framework. Mobile navigation is a checkbox-driven CSS menu with no JS, the section effects and the counting figures are `@property` + `counter()` + `view()` timelines, and the public site ships no JavaScript at all.

**A blog post reads down, not across.** Every other type puts its featured picture beside the words (`.page-head.has-media`, two columns); an article stacks — title, date, the picture **at its own size**, then the rule that divides the head from the writing. `.featured` is a banner crop (`width:100%`, a 440px ceiling, `object-fit:cover`), which is right for a card or a product shot and wrong inside an article: a small picture was blown up to 1200 wide and then cut off top and bottom. `.pt-post .page-media img` hands the sizing back to the browser and only shrinks a picture wider than the column. The rule is `.pt-post .page-head`'s own bottom border, the same way the hero and an archive head draw theirs, so it spans the page rather than the 1200px column. The article also drops the eyebrow, which only repeated the breadcrumb's last link.

**An archive's grid is `auto-fill`, a page's deck is `auto-fit`.** An archive holds however many posts happen to be published, and `auto-fit` collapses its empty tracks — one blog post stretched into a full-width billboard. `auto-fill` keeps them, so a short list still reads as tiles. A deck inside a page keeps `auto-fit`, because there the editor chose the count. The measures are the design's: 300px for blog and case studies (three across at 1200), 280px for products, 220px for partners.

**A product page has no hero.** `post.html:12` gates the whole page head — including `.page-media` — behind `{% if not has_hero %}`, and a hero draws its own `data.image`, so a product's *Featured image* had nowhere to appear. Without one, the page head **is** the design's detail header: eyebrow, `h1.page-title`, the `.lead` from `excerpt`, the *Request a quote* / *Buy* pair, and the featured picture at 440px on the right. The knock-on is that the eyebrow now reads "Products", from the breadcrumb, where the hero said "Appliance".

**`has_pages=false` is a type whose entries are data, not destinations** (migration `0005`, set on
`partner`). A technology partner is a logo on somebody else's page; there is nothing to read on a page
of its own. The flag is a column rather than a slug test in the code, because a content type is a row
here and this is a property of the row like every other.

It works through **one** mechanism: `db.with_paths()` gives such a post `path = None`, and everything
that would have pointed at it falls away by itself —

- `resolve()` matches a detail page with `post["path"] == full`, which `None` can never satisfy, so
  `/partners/micron` 404s without a rule of its own;
- `_indexable()` requires a path, which drops the post from `sitemap.xml`, `llms.txt` and the `.md` twins;
- `_card.html` renders a `<div class="card">` instead of an `<a>`;
- `public_post()` reports `url: null`, and `seo.jsonld()` returns crumbs only.

The type's **archive** (`/partners`) and every `post_list` block are unaffected — neither ever needed
a per-post URL. `with_paths()` reads the flag with `.get("has_pages", True)`, so the app behaves
exactly as before against a database where `0005` has not been applied yet.

**A quote beside another column is not a panel.** `.testimonial` on its own is the design's card (grey, radius 14, 32px, a 44px portrait ring). Inside a `.column` the background, the radius, the padding and the ring all drop and the quote goes flat 20px italic on the page's own ground — two grey boxes in a row read as chrome, not as somebody talking. The pair's heading is the `columns` block's own `heading`, so it needs no new field.

**A deck caps its child chips, an archive does not.** `_card.html` shows `CHIP_CAP` (4) children and then a `.chip-more` counting the rest; the archive, which *is* the full list, shows every child as a tile you can click. Grid cards in a row are all as tall as the tallest, so Cloud's seven sub-services were padding four cards out with empty space.

**Four archive shapes**, each scoped to `.arch-body` so the same list inside a page stays the card deck the home page wants: `pl-product` (a taller picture area, the price and Buy in a footer row), `pl-service` (one full-width row per group, the words in column one and the child tiles in column two — the card's children are a flat list, so each names its own grid column rather than being wrapped in a div for it), `pl-event` (a row led by an 84px dark date tile) and `pl-datasheet` (a row with the outline PDF mark and its own Download button).

**A pinned grid column has to be unpinned to stack.** `pl-service` is the one archive shape that had to
grow a breakpoint. Its card is `repeat(auto-fit,minmax(260px,1fr))` and its child tiles name
`grid-column:2` — so under ~570px `auto-fit` collapses the explicit tracks to one and column 2 becomes
an *implicit* track, sized `grid-auto-columns:auto` and floored at 180px by the tiles' own `auto-fill`.
The card came out ~200px wider than a phone, which is what pushed `/services` sideways (the archive
head's black band then stopped at the viewport rather than the scroll width — a symptom of the same
overflow, not a second bug). Under 700px, the stylesheet's existing breakpoint, the card goes to one
column and `.chips-kids` resets **`grid-column` and `grid-row`**, not just the template: leave the
pin in place and the implicit track comes back whatever the columns say. The result is the shape a
service page already ends on — the words, then the children as full-width tiles (`.siblings .tiles`).
The other three shapes size from `auto` tracks that stay inside a 390px card (datasheet floors at
~194px, event at ~108px), so they need no query.

**Shapes the design draws inside prose**, so they need no block of their own — the same trusted-staff HTML the ZFS dash list already uses: `.founders` (the pair on About), `dl.contact-dl` (the labelled contact list), `.map-ph` (the striped box standing in for the map until an `embed_html` replaces it) and `dl.zfs` (the ruled term/description rows on a service page). A `table.specs` pasted into prose is styled as a spec table rather than a prose table.

**A toned section inside a column is a panel.** `.column>.section` normally has its padding neutralised; one carrying `t-grey`, `t-dark` or `t-blue` keeps it and takes the card radius, which is how the design's dark configuration card beside the ZFS list is built out of a `rich_text` with `tone: dark`.

**`contact_form` has three skins**, one per `kind`: `quote` is the dark panel from the Contact screen, `career` the grey one from Careers, `contact` the plain white card. The heading is rendered **inside** the form, because in the design it belongs to the panel rather than sitting above it as a section title.

**A numeric `cards` icon is a counter, not an icon.** `card-icon num` drops the tinted tile for the design's mono blue number, and the deck tightens around it (`.cards:has(.card-icon.num)`).

**Favicons.** `static/favicon.svg` plus PNGs at 16/32/48/180/192/512, generated from the SVG with ImageMagick and linked from both `base.html` and `admin/base.html`.

### The admin shell

`templates/admin/base.html` is a 230px black sidebar and a grey page canvas, not the old top nav. Three things about it are load-bearing:

- **It uses its own class names** (`.adm-shell`, `.adm-side`, `.adm-nav`, `#adm-toggle`), not `.site-header` / `.site-nav` / `.brand` / `#nav-toggle`. Those live in `site.css` and belong to the public header; restyling them here would repaint every public page, and two `#nav-toggle` checkboxes would fight over the same `:checked ~` rule.
- **One `{% block content %}`, wrapped conditionally.** Jinja refuses the same block name twice in a template even in branches that cannot both run, so the shell opens before the block and closes after it rather than the block appearing in both arms of the `if`.
- **`.admin-main:has(#post-form)` is `height:100vh`**, not `calc(100vh - 66px)`. The editor now owns a grid column rather than sitting under a top bar, so there is no header height to subtract.

**The settings tabs are CSS, and that is load-bearing.** `settings()` saves `{k: request.form.get(k, "") for k in SETTING_KEYS}`, so **any key missing from the submitted form is blanked**. Rendering only the visible tab would wipe the other three on every save. So all four panes stay in the DOM and a radio + `:checked` sibling rule shows one. The pairing uses explicit ordinal classes (`.t1`/`.p1`), not `:nth-of-type` — the form's hidden CSRF field is an `<input>` too, so type counting put every radio one place out.

The Payments tab shows the provider **read-only**. It comes from the `PAYMENT_PROVIDER` env var through `payments.GATEWAYS`; making it a setting would give the same switch two sources of truth. `currency` and `notify_email` are real settings keys.

**`/admin/menus`** is the screen `NON-TECHNICAL.md` §9 has always promised. It posts flat rows — label, URL, and a level `<select>` — which `menu_items()` rebuilds into the nested `[{label, url, children}]` shape `get_menu()` returns. The level is a **`<select>`, not a checkbox**: an unchecked box posts nothing, so the three `getlist()`s would come back different lengths and every row after the first unticked one would shift a place. `db.set_menu()` is the write side, so every query still lives in `db.py`. SortableJS is loaded by that template alone rather than by `admin/base.html` — it is 45 KB and this is the only screen outside the canvas that drags anything.

**Leads have three states** (`new`, `in_progress`, `handled`) from a whitelist, because `leads.status` is a plain varchar and a toggle would store whatever was posted. No migration.

**Media alt text can be edited after upload** (`POST /admin/media/<id>/alt`). It used to be settable only at upload time, so a picture uploaded without it could never be described. Image dimensions and a "used on" list are **not** implemented: the first needs two new columns, the second a scan of every post's blocks.

`nav_counts` (not `counts`) carries the sidebar's numbers, because the dashboard view passes its own `counts` and a view's context shadows a context processor's — the leads pill would have been empty on exactly that one page.

`static/admin.js` is the single exception, loaded only by `templates/admin/base.html`. It is plain ES5-ish browser JavaScript — no framework, no bundler, and nothing fetched at runtime: the one third-party file, `static/vendor/sortable.min.js` (SortableJS 1.15.6, MIT, 45 KB), is **vendored, not CDN-loaded**, because the CMS runs on a LAN and an editor without internet must still be able to drag a section. It is **progressive enhancement only**: every part is a no-op when its hook is missing, and the plain form underneath still saves with JavaScript disabled. Four parts:

- **Slug** — `#post-slug` is `readonly`; typing in `#post-title` live-fills it with a JS mirror of `db.slugify()` while the post has no saved slug. An *Edit* button unlocks the field after a confirm, for the deliberate URL change. The field also carries `data-taken` — every slug of this post type except this post's own, built by `_form_context()` from the one `siblings` select that also feeds the *Parent* dropdown (space-separated: slugs are `[a-z0-9-]`, so no JSON is needed, and it is an attribute rather than `#editor-data` because `initSlug()` runs before `initBlocks()` parses that blob). On every keystroke `check()` compares the slugified value against that list, and the two paths diverge deliberately:

  - **A new post's generated address** takes the first free one outright — `freeSlug()` (a mirror of `db.unique_slug()`, memoised per base so it does not reshuffle as you type) appends three random letters, and `#slug-hint` says *“testing” is already used, so this page is at “testing-shc”.* Nobody is stopped from writing a page because someone else used the title.
  - **A deliberate rename**, after *Edit* unlocks the field, still gets the warning: `#slug-hint` turns red with the free address on offer, and `setCustomValidity()` blocks **Save**. (A `readonly` input is barred from constraint validation, so before *Edit* the message alone does the work — which is fine, because the auto path never produces a clash.)

  `apply_post()` mirrors exactly that split and stays the authority, since the browser's list is only a page-load snapshot: **on create it takes whatever `unique_slug()` returns**, for the submitted slug and the title-derived one alike, so a create can no longer fail on a duplicate address; **on update** a taken slug is still `409 slug already in use`, with `fields.slug` a sentence (*“about-us” is already in use — try “about-us-hqz”*) rather than the bare slug, because `_save()` prints `fields[k]` straight into the form's error box the way it does for every other field.
- **Warranty dates** — `initWarranty()` gives `#warranty-form` the same treatment on `purchase_date` / `expiry_date`: on every keystroke it compares the two ISO strings and `setCustomValidity()` blocks **Save** when the expiry is the earlier one, so that mistake never costs a round trip. An empty purchase date clears it — nothing to compare against, exactly the arm the `warranties_expiry_after_purchase` constraint has. The duplicate serial cannot be checked this way (it would mean shipping every serial on file to the page, which `data-taken` gets away with only because slugs are per post type), so it stays a server refusal that comes back through `data-refused` and is reported on arrival. The input handler clears the server's message and re-runs the date check, so clearing a stale refusal cannot also clear a date pair that is still wrong.
- **Categories and tags** — `initTerms()` turns each `.term-pick` in *Organise* into a search box with chips. The server still renders the plain checkbox list (`.term-boxes`), which is what a browser without JS gets; when JS is up it is removed and replaced. Matching is entirely client-side against `data-all` — `_form_context()` already embeds every term of this post type's taxonomies as `[{id, name}]`, so the picker makes **no request at all**, the same trick as `data-taken` on the slug field (and an attribute rather than `#editor-data` for the same reason: `initTerms()` runs beside `initSlug()`, before that blob is parsed). The suggestion list reuses the slash menu's `.iop-slash` / `.iop-slash-row` markup and CSS verbatim.

  The wire format is where the design lives. A chip for a term that already exists posts the id under `terms`, exactly as the checkbox did, so nothing downstream changed. A name you just typed posts `"<taxonomy-slug>:<Name>"` under **`new_terms`** — a separate field because `_form_body()` does an unguarded `int()` on every `terms` value, and because `_form_body()` is shared with `/admin/preview`, which must never write. `_new_term_ids(pt)` resolves them through `db.ensure_term()` and is called from `_save()` **only** — so nothing is created until you actually save, and previewing a post with a pending chip writes nothing. It runs *before* `apply_post()`, which is what makes a rejected save round-trip for free: the draft carries the new ids under `terms`, and `_form_context()` re-reads the taxonomies and finds them. It also drops any taxonomy not in `pt["taxonomies"]` — the field is client-supplied, and without that check an editor could file a term into a taxonomy the type does not use.

  Both sides match on the slug, not the string: `slugify()` in `admin.js` mirrors `db.slugify()`, so typing "All-Flash" when "all flash" exists offers the existing term instead of *Create*, and if the browser's snapshot is stale `db.ensure_term()` reuses the row anyway rather than making a second one. Enter in the search box `preventDefault()`s unconditionally — it sits inside `#post-form`, where a bare Enter would submit the post.
- **Media pickers** — one `mediaWidget()` renders a thumbnail, a "choose existing" select and a file input that uploads to `/admin/media/upload` and appends the new row to *every* picker on the page. It is applied to `select[data-media]` (featured image, per-type `media` fields) and to media fields inside blocks, so there is one code path rather than three. Its third argument is a mime prefix that narrows both the list and the file input: `"image/"` (every image field, and `data-media="images"`), `"application/pdf"` (the `pdf` widget), `""` for anything the server accepts.
- **Section settings** — `blockFields(block)` renders one section's non-inline fields, starting with the three layout controls every type shares (§6): *Align the content* → `data.align`, *Align the section* → `data.align_box`, and *Width* → `data.width`, whose select (Default / Wide / Full width) and number box both write that one key and clear each other — *Custom* is a disabled option shown only while a number is in play. They are type-agnostic, so they are built here rather than from `BLOCKS`, and picking *Default* or emptying the box **deletes** the key, so an untouched section stays byte-identical in the saved JSON. Then labelled inputs driven by `BLOCKS` + `EDITOR`, media pickers, and repeaters for `items`/`images`/`rows` — with two exceptions. `rich_text`'s `html` is skipped, because the canvas is where a document is edited and a second editor in a 23rem popover is a trap. And `fieldsOf()` sorts **repeaters last** whatever order `BLOCKS` declares them in: a repeater is as tall as it has rows, so a setting declared after one (a Numbers section's *Effect*, a Cards *heading*) sat below six rows of fields and was never found. It is what `⚙` opens in the popover (§12.1); there is no form-based content entry any more — the canvas and the popover are the only editors, and *Advanced* is the raw JSON. It mutates the block object in place, so **keys it does not render survive**, and an unknown block type falls back to an "edit it under Advanced" note. On submit `admin.js` serialises the array back into `textarea[name="blocks"]`, so `_form_body()` and `validate_blocks()` are untouched — the editor only ever writes the JSON a human could have typed. If that textarea holds unparseable JSON (a rejected save round-trip), the editor stands down, opens *Advanced* and says so.

Rich fields inside the popover get `richText()`: a `contenteditable` box with a bold/italic/H2/H3/list/link/clear toolbar plus an *HTML* toggle for the raw markup; paste goes through the same `richPaste` filter as the canvas, so headings and lists survive and Word's markup does not.

### 12.1 The document editor

The post form (`templates/admin/post_form.html`) is one screen. A bar across the top: back link, the *saved* status pill, *Edit* / *Preview*, the device widths (Preview only), *View live*, **Save**. Under it, the page column — a borderless title input, the document toolbar and `iframe#canvas` filling whatever height is left — and, on the right, the settings panel: *Publish*, *Web address*, *Summary*, *Featured image*, *Organise* (parent, and a chip picker per taxonomy — the whole section is dropped for a type with neither), the type's *Details* (`field_schema`), then *Search engine overrides* and *Advanced* as collapsed `<details>`. `.admin-main:has(#post-form)` is sized to the viewport and the two columns scroll on their own, so the toolbar never scrolls away; under 1000px the panel stacks beneath the page.

**`menu_order` is not in the form.** A number that decides list order was the one setting no editor could explain, and every list already falls back to newest first. The column stays, and it is still the *primary* sort for `post_list` (`blocks.py`), archives, and the child lists in `render_post()` / the preview — all of which now carry `.order("menu_order").order("published_at", desc=True)`, so a hand-set order still wins and everything else is newest first. It stays writable through `PATCH /posts/<id>` and `cli.py`'s seed, which is what keeps the seeded Services in their intended order; `_form_body()` deliberately omits the key so a browser save leaves whatever is there alone rather than resetting it to `0`.

*Advanced* holds `textarea[name="blocks"]`, still the only field that POSTs, so `_form_body()` → `apply_post()` → `validate_blocks()` remains the single validation path. Opening the `<details>` writes the current array into it, a blur on a hand edit reads it back through `setBlocks()`, and submit rewrites it from the array. With JavaScript off, Advanced is what you get. Delete is a `<button form="delete-post">` pointing at a second form placed *after* `#post-form`: a form nested inside a form is dropped by the parser, so the old inline delete form's button submitted the post form instead.

**The canvas is a server render, not a second renderer.** `POST /admin/canvas` (`admin_ui.py`, `@ui_required()`, CSRF as form data) takes the blocks the browser currently holds — unsaved ones included — and returns `render_blocks(blocks, edit=True)` inside `templates/admin/canvas.html`, a standalone document linking `site.css` and `static/canvas.css`. `admin.js` puts that in `iframe#canvas` via `srcdoc`. Preview and published page therefore cannot drift. The iframe is not decoration: every `admin.css` rule is scoped to `body.admin`, which would be an ancestor of an inline canvas and would silently repaint `.specs`, `.card` and the lead form.

**Edit markers.** `render_blocks(blocks, edit=False)` hands each template an `fe` callable — `_fe(i)` in edit mode, `_no_fe` otherwise — so `data-*` attributes *cannot* reach the public site; there is no request-global flag to leak. In `blocks/*.html`:

| call | emits | means |
|---|---|---|
| `{{ fe() }}` on the root `<section>` | `data-b="2"` | this is block 2 (`data-b="2.1.0"` inside a column — see below) |
| `{{ fe('heading') }}` | `data-f="heading" data-ph="Heading"` | editable text; `data-ph` is the empty-state placeholder, taken from `EDITOR["labels"]` |
| `{{ fe('items', loop.index0) }}` | `data-r="items" data-i="0"` | one repeater row: fields inside write into `data.items[0]` |
| `{{ fe('html', rich=True) }}` | `… data-rich="1"` | the value is `innerHTML`, not `innerText` |
| `{{ fe('html', ph='…') }}` | overrides `data-ph` | when the field label ("Content") is not what an empty page should say |

Write them tight against the tag (`<h1{{ fe('heading') }}>`) — a space would make the public render `<h1 >`, which `tests/test_offline.py::test_render_blocks_uses_template` catches.

**Typing never re-renders.** `contenteditable` (`plaintext-only`, with an Enter-blocking fallback for engines without it) writes straight into the block objects, which `fieldInput()` already mutates in place — canvas, settings popover and JSON textarea point at the same objects, so there is no sync layer. Only structural changes touch the server, and then only for **one** block: `POST /admin/canvas` with `p=PATH` returns a bare fragment that replaces that one `<section>`; deletes remove the node, drags move it, and `data-b` is renumbered client-side. `setBlocks()` is the single place the array reference is ever replaced.

**A block's address is a path, not an index.** `data-b` used to be an integer into one flat array. With `columns` it is a dotted path — `"3"` is a top-level block, `"3.1.0"` is block 3's column 1, first block; parts alternate block/column so the count is always odd. `render_blocks(blocks, edit, path)` takes the path of the *first* block and increments its last part for the siblings, which is why the `?p=` fragment comes back already carrying its own path and the browser no longer patches `data-b` after a swap. In `admin.js` everything routes through six helpers instead of parsing an integer:

| helper | answers |
|---|---|
| `listAt(path)` | `{arr, i}` — the array a path lives in, and where in it. Every splice goes through this. |
| `blockAt(path)` / `siblingPath(path, n)` / `isNested(path)` | the block; a sibling's path; is this inside a column |
| `blocksIn(box)` | the blocks a container owns — `n.parentNode.closest("[data-col],#main") === box` |
| `boxFor(path)` / `pathIn(box, i)` / `listIn(box)` | container ⇄ path ⇄ MODEL array |

Blocks live in **containers**: `#main`, or one `[data-col]` of a columns block (written only under `{% if edit %}`, so it cannot reach the public page). Three consequences:

- **`renumber()` recurses.** Document order over one flat `querySelectorAll("[data-b]")` would number a column's children into their parent's sequence and corrupt the whole mapping, so it walks container by container.
- **`bars()` and Sortable run per container.** Every column gets its own click-to-type strips, so an empty column is a place to type rather than a dead box — and because an empty column contains nothing *but* that strip, `.column>.iop-add:only-child` drops the hover-to-reveal and draws it as a dashed drop target, or the column reads as exactly the dead box it is not; every column gets its own `Sortable` in the shared `group: "iop"`, so a section drags between the page and any column. The group's `put` refuses `NEVER_NESTED` types, and `onEnd` reads the source path off the item (before `renumber()` rewrites it) and the destination out of `blocksIn(e.to)` — `oldIndex`/`newIndex` count the `.iop-add` strips too.
- **`splitAt()` adds no trailing paragraph inside a column.** On the page, `/` inserts the chosen section *and* an empty `rich_text` under it, because a page is a document you keep writing down. A column is a slot you place things in, so there the paragraph goes in only when the split left real text behind, and the caret lands on the section itself.
- **Wiring is scoped to the owning block.** `wireBlock()` binds only fields where `f.closest("[data-b]") === node` and guards its `mousedown` the same way, or a Columns block would claim its children's fields and clicks. `wireTree()` is `wireBlock` plus every nested block and a `sortable()` for every new `[data-col]`, and is what a replaced fragment goes through.

The `⚙` panel for a Columns block manages the column *list* — `repeater()` gained two optional hooks (a row factory, a cell renderer) because a column row is an array of blocks rather than a row of fields, which is cheaper than a second ↑ ↓ ✕ splice loop. Removing a column that holds sections asks first. The sections themselves are edited on the page, like everything else.

**A page is a document, not a stack.** Prose lives in `rich_text` blocks; the other fifteen types
are the designed bands. Nothing about the storage changed — `posts.blocks` is the same JSONB —
but the editing surface leads with writing:

- A post with no blocks opens as **one empty `rich_text` with the caret in it** (`focusOnLoad`).
  No dialog, no picker. `LAYOUTS` moved from a blocking chooser into the Insert menu.
- The gaps between sections are **click-to-type**: clicking one splices in an empty `rich_text`
  and focuses it. One mechanic instead of a separate "+" affordance, and it means there is never
  nowhere to put the caret.
- **Every section carries the hover toolbar, `rich_text` included** (name, drag, ↑ ↓, duplicate,
  settings, remove). Typed sections were exempt at first, to protect the document feel — but the
  bar is one per block of writing, not one per paragraph, and it is the only way to reach a typed
  section's alignment and width (§6). It hangs off the `<section>`, outside the `[data-f]`
  editable, so nothing it adds can reach the saved HTML.
- **Empty `rich_text` blocks are stripped on submit** (`prune()`, which applies `written()` all the way down into columns and returns new arrays so a rejected save cannot eat the paragraph you still have the caret in), because an empty paragraph is
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
tests/test_offline.py    always runs — slugify, validate_blocks, render_blocks, JWT matrix, the /media route
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

`SUPABASE_URL` needs to be reachable **from the app only**. Nothing a visitor's browser loads points at it
any more (§8), so the gateway can sit on a private network with Flask as the only exposed service. `SITE_URL`
is what the outside world sees, and it is what `seo._abs()` puts in front of a `/media/` path.

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
2. Studio → Storage: create a bucket named `media`. Public or private no longer matters to the app — it uploads and reads with the service-role key (§8), and nothing a visitor loads points at the bucket. The instances built so far use a public one
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
| New block | `BLOCKS` entry + `EDITOR` names/seed/order (+ widgets/items/labels for new keys) + `templates/blocks/<type>.html` + a `blocks_md()` branch + a `site.css` rule group; `/new-block` in `.claude/skills/` is the checklist |
| New taxonomy | A `taxonomies` row + the type's `taxonomies` array |
| Schema change | A new `migrations/NNNN_*.sql`, then `flask migrate`, then the code. A seeded `post_types` or `settings` row that already exists needs the migration to `UPDATE` it — the seed only inserts |
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
- The hero rotator has a keyframe set per picture count, and two are written (2 and 3). A fourth picture needs a fourth set.
- A counted figure rolls the **first whole number** in it and only that: `"99.999%"` counts 0→99 and holds `".999%"`, because a CSS counter is an integer. A grouped `"1,200"` is refused outright and stays plain text — `counter()` has no thousands separator, so it would settle on `1200` under a figure the editor wrote as `1,200`. Both are in `count_up()`.
- Scroll *triggering* needs `animation-timeline: view()` (Chrome 115+, Safari 26+, Firefox 144+). Without it the same effects still play, once, as the page loads — see §12.
- The counting figure needs `@property` (Chrome 85+, Safari 16.4+, Firefox 128+) for `--cv` to interpolate at all. Below that floor a counted figure reads `0`; untick *Count up from zero* for it. The floor is older than the `:has()` the mega panel already depends on, so nothing that can open the menu is caught by it.
- A page whose **first** section is a `hero` or a `columns` writes its own opening, so `post.html` draws no page head for it. That is what lets the Contact screen put its H1 beside the form — and it means a page an editor starts with a Columns section shows no title until they type one into it.
- `--w` is one measure per section, so a hero's headline and its paragraph (820px and 720px by default) take the same custom width. Per-element widths would need a key per element, which no editor has asked for.
- A custom width is pixels only — no `%`, `rem` or `vw`. The three named steps cover the proportional cases, and `section_style()` stays a digits-only check rather than a unit parser.
- `.cta` and table cells keep their own explicit `text-align`, so a centred section does not restyle a CTA band or a spec table's columns. `align_box` likewise only moves a section narrower than the page; a full-width one has nowhere to go.
- `public.media_file()` reads the whole file into memory before answering — `MAX_CONTENT_LENGTH` caps an upload at 20 MB, so the worst case is bounded. Stream it through httpx if big PDFs ever land.
- No server-side cache in front of Storage: a cold client costs one LAN round trip per file. The immutable year plus the ETag mean repeat views cost nothing, and `gunicorn --threads 8` keeps a page's images off each other's way; put a CDN or a disk cache in front if that stops being enough.
- `DummyGateway` moves no money.
- `post_types` and `settings` are cached per process, not per cluster. A multi-worker deployment sees an update after `uncache()` runs in *that* worker.
- FAQPage JSON-LD is not wired up (§9).

Run `/ponytail-debt` to harvest the current ledger from source.

---

## 18. Working on it with an agent (`.claude/`)

`CLAUDE.md` at the repo root is the rulebook Claude Code loads every session; `.claude/` is what makes the rules cheap to follow.

| Path | What it does |
|---|---|
| `.claude/docs/design.md` | The architecture map — what exists, where, and the dated decision log. Updated in every PR that changes the shape of the system (the third doc, beside this one and NON-TECHNICAL.md) |
| `.claude/docs/requirements.md` | The client brief verbatim, the dated client decisions, and the status of each brief item |
| `.claude/skills/*/SKILL.md` | Slash-command procedures: `/pr`, `/docs`, `/new-block`, `/migration`, `/theme-check`, `/after-merge`. Each is a checklist of a thing that has gone wrong before |
| `.claude/settings.json` | Permission rules. The **deny** list is the hard rules made mechanical: no `flask migrate`/`seed`/`import-media`/`create-admin`, no `pip install`, no `git merge`, no push to `main`, no hand edits to the generated `requirements*.txt`, `Pipfile.lock` or `.env`. `includeCoAuthoredBy: false` keeps the agent out of git authorship |
| `.claude/hooks/session-start.sh` | Runs at session start: branch, dirty files, last 12 commits, and how many commits behind `HEAD` the knowledge graph is |

The knowledge graph (`graphify-out/`, gitignored) has two halves. Its code nodes are re-extracted by git hooks (`graphify hook install`: `post-commit`, `post-checkout`) after every commit and branch switch, with no LLM. Its prose nodes and community labels come from the LLM pass, which runs only on `main`, after a merge, from `/after-merge` — which also audits `.claude/` against the merged diff so the map never drifts more than one PR behind the code. Anything that drifted goes into its own `chore/claude-sync` PR.
