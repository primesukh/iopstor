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
| Deploy | Dokploy. Development: the `Dockerfile` alone. Production: `docker-compose.yml` — that same image as `app`, plus `cloudflared`, one Compose service, the tunnel the only way in (§15) |

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
iopstor/stress.py     the owner-only load simulator behind /admin/stress: fires visitors + attackers at
                      a target, progress in a sqlite file on /dev/shm. Stdlib only (urllib, threading). §12
iopstor/cli.py        flask migrate | seed | import-media | create-admin
iopstor/templates/    base/post/archive/404, blocks/<type>.html, admin/*.html
iopstor/static/       site.css (the whole public theme) + site.js (the sliding row, and nothing else)
                      + admin.css (admin extras, layered on top)
                      + canvas.css (editor chrome), favicon.svg, vendor/sortable.min.js
migrations/           0000_bootstrap.sql (run once by hand) + NNNN_name.sql applied by `flask migrate`
tests/                test_offline.py always runs; the rest need a live Supabase and skip without it
docs/                 this file + NON-TECHNICAL.md
.claude/              the agent's workspace: docs/design.md (architecture map) + requirements.md, skills/, hooks/, settings.json — §18
```

Dependency direction: `public.py` and `admin_ui.py` both import from `admin_api.py` (for `apply_post`, error handlers and pagination helpers); everything imports `db.py`; `db.py` imports **only** `throttle.client_ip` from the app (the audit log records who an action came from, and there is one reader of `CF-Connecting-IP`; `throttle.py` imports nothing back).

---

## 3. Data model

Eleven tables from `migrations/0001_initial.sql`, plus `warranties` from `0003_warranty.sql` and `0004_warranty_date_check.sql`, `audit_log` from `0008_audit_log.sql`, and `post_drafts` + `post_sessions` from `0010_working_draft.sql`.

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
| `post_drafts` | The unpublished edits of one page. `posts.blocks` stays the **published** content | `post_id` (PK, cascades), `blocks` (JSONB), `state` (base64 CRDT, empty until the shared-document PR), `updated_at`, `updated_by` |
| `post_sessions` | One person's open sitting on one page, so the log can still say what each editor changed | `(post_id, user_id)` PK, `user_email`, `ip`, `changes` (`{field: [was, now]}`), `started_at`, `updated_at` |
| `menus` | Header/footer nav | `items` (JSONB, one level of `children`) |
| `settings` | Key/value site config | `key`, `value` (JSONB) |
| `redirects` | Legacy URL mapping | `from_path` (unique), `to_url`, `code`, `hits` |
| `audit_log` | **Who did what, and what it was before** | `at`, `user_id`, `user_email`, `ip`, `action`, `table_name`, `row_id`, `label`, `changes` (JSONB) |
| `schema_migrations` | Applied migration names | created by `0000_bootstrap.sql` |

Indexes: `posts (post_type_id, status, published_at)`, `leads (status, created_at)`, `payments (provider, provider_ref)`, `warranties (expiry_date)`. `posts` is unique on `(post_type_id, slug)` — slugs are unique *per type*, not globally. `warranties` is unique on `serial_key`, a `GENERATED ALWAYS AS (upper(btrim(serial))) STORED` column: it makes the public lookup case- and whitespace-insensitive, stops two records claiming the same serial in different cases, and lets the lookup be an exact `.eq()` — a serial may legitimately contain `%` or `_`, which PostgREST's `ilike` would read as wildcards. A `CHECK` constraint, `warranties_expiry_after_purchase` (`0004`), refuses a record whose `expiry_date` is before its `purchase_date`; `/admin/warranty` pre-checks the same thing so an editor gets a sentence rather than a 502, exactly as it pre-checks the duplicate serial. It was added `NOT VALID` — enforced on every write, existing rows unscanned — because the table already held a record with the dates reversed; `ALTER TABLE warranties VALIDATE CONSTRAINT warranties_expiry_after_purchase;` promotes it once those are fixed. Warranty status is **not** stored: "in warranty" is `expiry_date` vs today, worked out at render time by `blocks.warranty_active()` so it can never go stale.

**`audit_log` breaks three of this schema's own conventions, each for a reason.** Its id is `BIGINT GENERATED ALWAYS AS IDENTITY`, not `SERIAL`: it grows per *action* rather than per page, and `GENERATED ALWAYS` additionally refuses an INSERT that supplies its own id. Its strings are `TEXT`, not `VARCHAR(n)`: a title longer than the limit would fail the audit INSERT, and that INSERT is deliberately swallowed (see `db._audit()` in §4), so a length limit would buy silent gaps in the one table that must not have them. And `user_id` has **no foreign key** to `users` — the log has to outlive the row it names, which is why `user_email` is copied in beside it. Index: `(user_id, id DESC)`, one, for the "everything one person did" filter; the screen's default order is `id DESC`, which the primary key already serves.

**Append-only is enforced in Postgres, not by the app.** `audit_log_no_change`, a `BEFORE UPDATE OR DELETE` trigger, raises `audit_log is append-only`. Leaving it to the app declining to offer a delete would be worthless: the app holds the service-role key and could rewrite its own evidence. The cost is that nothing can tidy up after itself, and the live suite is what found it: it runs against the real Supabase, so every run left its `zz-test` writes in the client's Activity screen with the `cleanup` fixture forbidden to remove them. **`db._audit()` therefore returns early under `TESTING`**, the way `throttle._off()` does and for the same shape of reason — the log is a client-facing screen, and a test corpus in it is worse than an untested write path (`test_the_test_suite_never_writes_to_the_audit_log` proves the guard is the flag, not the absence of a database). For the runs that happened before that, `migrations/purge_test_audit_rows.sql` is a hand-run script carrying the `DISABLE TRIGGER` / `DELETE` / `ENABLE TRIGGER` sequence. It is the only sanctioned delete from this table; reaching for it for anything but test rows defeats the point of the trigger.

Note `0008`'s own header still describes the pre-guard behaviour. It is applied, and an applied migration is never edited — a mistake in one becomes a new file.

**`posts.status` has a third value, `trash`.** Deleting a post moves it there instead of removing the row; nothing is destroyed and the id survives, so child pages keep their `parent_id`, `post_terms` links stay, and enquiries go on pointing at it — none of which re-creating a row from the log could do. It needed no migration and no new filter because every public read already passes `db.live()`, which asks for `status='published'`: the sitemap, the `.md` twins, the archives, the resolver, the mega panel and the RSS feed all exclude it exactly as they exclude a draft (`test_a_trashed_post_is_not_live`). The four places that *do* need a rule are the ones that were not filtering by status at all — `admin_ui.posts()`, `admin_ui.dashboard()`, `admin_api.list_posts()` and `db.admin_counts()` — plus `admin_ui.edit_post()` and `admin_api._post_or_404()`, which 404 a trashed post so that saving one cannot quietly un-trash it (the form posts `status=draft` by default). A trashed post's slug stays taken by `unique_slug()`, which is the property that makes restore collision-free.

**Where per-type data lives.** `posts.meta` is a JSON bag described by `post_types.field_schema` — a list of `{key, label, type, required}` descriptors that the admin form renders and the detail template reads back. Types in use: `text`, `textarea`, `number`, `date`, `url`, `media`, `json`, `kv`. **Nothing validates that list** — `post_form.html` and `_form_body()` both fall through to a plain text input on a type they do not know, so adding one is purely additive.

**`kv` is a field edited as label/value rows** and stored as an ordered array, `[{"k": …, "v": …}]` (migration `0006` moves the product `specs` field onto it). Two reasons it is not the `json` type it replaced. First, `_form_body()` used to store the raw text of anything that would not parse, so a mistyped brace saved without complaint and `post.html`'s `is mapping` test then dropped the whole table off the live page; rows that will not parse are now no rows. Second, **`jsonb` sorts an object's keys**, so a spec table could never keep the order it was written in — an array can. The widget is the `repeater()` `spec_table` already uses (`admin.js:447`): `SPEC.ui.items["spec_table"]` is `["k", "v"]` and the labels are already *Label* and *Value*, so `initMetaRows()` passes that type in and gets add / remove / reorder for nothing. It reaches the server through a hidden input written on submit, the same trick `initMediaSelects()` uses. `post.html` renders a list in its own order and a legacy object as before.

**Prices are rupees, and only rupees.** `rupees()` is a Jinja global in `__init__.py` beside `media_url`; `{:,}` groups in threes all the way up and would print `12,50,000` as `1,250,000`, so it groups the last three digits and then twos. Anything non-numeric passes through, so a price typed as "on request" still prints. The three display sites (`post.html`'s Buy button, `checkout.html`'s total, `_card.html`'s card foot) all call it. **A price is never a detail tile.** `post.html` rejects the `price` key from the meta strip and puts it on the Buy button instead (`Buy · ₹ 10,000`), the same pairing `_card.html` makes in an archive card's footer: the price is the ask, not a fact about the product the way SKU is, and showing it twice on one page made a grey band out of a single number. `seo.py` and `public.py` keep the literal `"INR"` — a currency *code* for `priceCurrency` and the payments row is not display. The per-product `currency` field and the never-read `currency` setting under Payments are both gone. `posts.blocks` is the ordered page content, `[{type, data}, ...]` — flat, except a `columns` block, whose `data.cols` holds one such list per column (one level deep, see §6).

**Seeded types:** `page` (prefix `""`), `post` (`blog`, BlogPosting), `service` (`services`, hierarchical, Service), `case_study` (`case-studies`, Article), `event` (`events`, Event), `partner` (`partners`, Organization), `datasheet` (`datasheets`), `product` (`products`), `testimonial` (`testimonials`, `has_pages=false`, `0014`).

---

## 4. Data access (`db.py`)

Every query goes through this module. Nothing else builds a PostgREST query.

| Helper | Contract |
|---|---|
| `table(name)` | Service-role PostgREST query builder |
| `one(q)` / `rows(q)` | Single dict-or-`None` / list of dicts |
| `insert()` / `update()` / `delete()` | Write helpers returning the row — **and the only place anything is written to `audit_log`** |
| `live(q)` | **The public visibility filter**: `status='published' AND published_at <= now()`. A future `published_at` is a scheduled post |
| `select_posts()` | The canonical post select — embeds `post_type`, `featured_media`, `terms` in one round trip |
| `with_paths()` / `ancestors()` | Attach the computed `path` to posts; builds one per-request hierarchy index rather than walking parents per row |
| `unique_slug()` | Slug collision resolution within a post type — `base`, else `base-xyz` (three random letters) |
| `ensure_term()` | Term id for a name in a taxonomy, creating the row the first time. Matched on `slugify(name)`, so "All-Flash" and "all flash" are one term, not two |
| `set_menu(slug, items)` | The write side of `get_menu()`, so `/admin/menus` keeps every query in this module |
| `admin_counts()` | `{post-type slug: n}` plus `_leads`, for the sidebar. One query over posts counted in Python — PostgREST has no `GROUP BY`, and an exact-count call per type would be eight round trips a page |
| `tree(type_slug)` | Top-level live posts of one type, each with `p["children"]`. One query; the parent/child split happens in Python. Feeds the header's services panel, the services archive and `post_list(top_level)` |
| `paginate()` | Offset/limit + exact count |
| `_audit()` / `audit_event()` | One `audit_log` row. `audit_event()` is for the things that are not a row write — login, logout, a wrong password |
| `ist()` / `ist_input()` | A stored UTC timestamp as the clock an editor in India was looking at, for display and for `<input type="datetime-local">` |
| `post_types()` / `settings()` / `get_menu()` / `get_media()` / `redirect_for()` | Cached **per process** for `CACHE_TTL`, dropped the moment any write bumps the content epoch (below) |
| `content_epoch()` / `bump_epoch()` | The cross-worker invalidation stamp: one file's mtime on `/dev/shm`, touched by every write |

**Two caches, and the difference matters.** `_cached()` memoises on `flask.g` and dies with the
request — that is still the right place for anything derived, like `seo.site()` or `tree()`. `_proc_cached()`
lives in the worker process and survives requests, which is what removed the round trips that dominated the
public site: measured, `GET /` cost **29 PostgREST round trips and 219 ms**, of which 17 were `media` (one per
picture, `media_url()`/`media_alt()` calling `get_media()` per id — 14 of them the partner logos in `_card.html`)
and 2 were `get_menu()`, which had no cache of any kind. With the process cache a first-time page costs 3–5 and
a repeat costs 0.

Because thirty workers share no memory, the process cache needs an answer to "has anything changed since?", and
that is `bump_epoch()`: every write touches one empty file on `/dev/shm` — `throttle.py`'s trick — and every read
compares its mtime and drops anything stamped older. A stat on tmpfs is microseconds against a 219 ms render, so
asking every time is cheaper than being stale. **It is called from `insert()`/`update()`/`delete()`**, the same
three funnels the audit log uses, so a write path added later invalidates without anybody remembering; the three
writers that do not go through them — `set_settings()`, `set_menu()`, `set_post_terms()` — call it themselves,
and the comment beside each says why. `save_draft()` and `touch_session()` deliberately do **not**: they are
autosaves, they change no public page, and bumping on each would empty every cache every few seconds while
somebody types.

`bump_epoch()` also drops the current request's `_cached()` memos, which is not belt-and-braces but a bug that
was caught by `test_terms_settings_menus`: a writer routinely reads the old row first (`set_menu()` calls
`get_menu()` for its audit diff), and that read caches the value the write is about to make wrong. `_cached()`
records its keys on `g._cache_keys` so one call can drop them all.

**The audit log records itself into the write helpers, not into the routes.** `insert()`, `update()` and `delete()` each call `_audit()` with a `{field: [was, now]}` diff, so a write path added later is logged without anybody remembering to log it — and the diff is field-level, which an `after_request` hook could never produce because it sees the response, not the row. `update()` reads the row first to get the "was" half; that read is skipped entirely outside a request context, which is also the whole of the `flask seed` / `import-media` exclusion — `_audit()` returns immediately when `has_request_context()` is false, so there is no flag to remember and no way to forget it. `update(name, pk, changes, action=…)` takes an action label because moving a post to the trash *is* an UPDATE but has to read as `delete` on the screen. The three writers that are not keyed by `id` keep their own calls: `set_settings()` emits **one entry per changed key** (the Settings form posts all eleven every time, and "which setting did they change" is the question the log is asked), `set_menu()` diffs against `get_menu()`, and `set_post_terms()` logs one entry against the *post* rather than the join-table churn.

Two writes are deliberately not recorded: `public.py`'s `redirects.hits` bump, which is a counter on an anonymous page view and would bury the log (it is the one place that still builds its own `.update()` chain, with a comment saying why), and anything the CLI does.

**`update(..., if_unchanged=<updated_at>)` is the optimistic-concurrency guard**, and where it lives is the whole point. The value is the row's `updated_at` as the caller last saw it, and it goes into the UPDATE's **own filter** — `UPDATE … WHERE id=? AND updated_at=?` — never into a comparison in Python. Production runs `-w 30 --threads 8` and the app keeps nothing between requests, so two saves can pass a Python compare a millisecond apart and both write; only Postgres can decide this, and it does so atomically. No rows back means somebody saved first, and `None` is already what a vanished row returns, so no caller had to learn a new shape — and because `_audit()` already sits behind `if after:`, a refused write logs nothing for free. The version token needs no maintenance: the `posts_updated_at` moddatetime trigger (`0001`) moves it on every write, which is also why `updated_at` is in `NOT_A_CHANGE` and never appears in a diff.

The callers that deliberately **do not** pass it, so nobody "fixes" them later: `PATCH /api/admin/v1/posts/<id>` and `flask seed --reset-content` are machine callers with no screen to warn, and **`/admin/audit/<pk>/restore` is an intentional overwrite of whatever is there now** — that is the entire point of the button. The column is hardcoded rather than a parameter because `updated_at` is the only version token that exists; a second one can add the argument when it has a second caller. `tests/test_offline.py::test_a_save_that_lost_the_race_writes_nothing_and_logs_nothing` asserts the filter reached the UPDATE and that `_audit` was never called, and `test_the_timestamp_survives_the_query_string` pins the encoding: PostgREST returns `+00:00`, and a bare `+` in a query string decodes as a space, which would match nothing and make *every* save look like a conflict. httpx percent-encodes it to `%2B`, verified rather than assumed.

Three hard rules:

- **Never call `.delete()` without a filter** — PostgREST interprets an unfiltered delete as "the whole table". `db.delete(name, pk)` is the version you cannot forget the filter on; every by-id delete in the app goes through it.
- Anything user-facing goes through `db.live(q)`. A public query that skips it will serve drafts.
- **Never write to `audit_log` through `insert()`** — it would recurse. `_audit()` uses `table("audit_log")` directly.

---

**The working draft, and the only two writes in the app that are not audited.** `get_draft()` /
`save_draft()` / `clear_draft()` and `touch_session()` / `flush_sessions()` / `open_sessions()` sit
beside the post helpers and never touch `posts.blocks`.

`save_draft()` and `touch_session()` are upserts on their own key (the `on_conflict=` shape
`set_menu()` and `set_settings()` already use, because neither table is keyed by `id`) and **neither
writes an `audit_log` row**. That is a deliberate departure from "every write is audited", and the
reason is a ceiling that already existed: `audit_log` has no retention job and `_diff()` stores the
whole `blocks` array on *both* sides of every row, so routing an autosave through `db.update()` would
add a full copy of the page every second or two, per editor, without bound. The per-person record is
not lost, it is deferred — `flush_sessions()` writes **one** row per person per sitting (§12.1).

`flush_sessions(post_id, idle_minutes=15, user_id=None)` writes those rows and deletes the sessions.
Two details are load-bearing. It passes `user=` and `ip=` from the **session row**, not from the
current request, because with no scheduler here a stale session is closed inside whoever next touches
the page — usually a different editor — and taking either from that request would record the wrong
person; `_audit()` already took `user` for exactly this shape of reason (a login is logged before
`g.user` exists) and now takes `ip` too. And a session with an empty `changes` writes nothing: opening
a page and reading it is not an edit, though the row is still cleared.

**`_tolerate_0010()` is how the app runs before the migration is applied**, and the error code in it
is not the one you would guess. PostgREST answers from its schema cache and never reaches Postgres, so
a missing table is **`PGRST205`**, not Postgres's `42P01` — measured against the dev Supabase, where
assuming `42P01` made the editor raise instead of falling back. Both are accepted, since a function or
a view would reach Postgres and report the other. Anything else still raises: a permission error
swallowed there would look like "autosave is simply off". Guarded by
`test_the_app_runs_before_the_draft_migration_is_applied`.

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

`/media/` is a **reserved first segment** — one of five in `db.RESERVED_SEGMENTS` (`admin`, `api`,
`media`, `static`, `healthz`), which is now enforced rather than merely noted. Flask matches a
blueprint's static prefix before `public.py`'s catch-all, so a page that claims one of these **cannot
load at all**: a page slugged `admin` used to save cleanly and then 404 for ever with nothing to say
why. `db.reserved()` refuses a new one at save time — a post's slug only when its type has no
`url_prefix`, since a blog post honestly titled "Admin" is `/blog/admin` and collides with nothing; a
post type's `url_prefix` and a taxonomy's slug always, because those are always the first segment.
`checkout` and `index` are a different thing: taken by routing order, not owned by a blueprint, and
still only `# ponytail:` comments. Its route is
declared literally, so Werkzeug ranks it above the catch-all — but a `post_types.url_prefix` of `media`
would be unreachable, and so would a hierarchical page whose top-level slug is `media`.

---

### 5.1 Checkout

The design's Buy flow is a modal. The public site's one script (`site.js`) drives the sliding row and nothing else, so checkout is a page instead — which the handoff offers as the alternative. It is handled **inside the catch-all**, not as its own rule: a rule shaped `/<a>/<b>/checkout` would have to out-rank `/<path:path>`, and reading the last segment where the resolver already has the post type is six lines. A trailing `checkout` under a type's prefix resolves the segment before it, and 404s unless that post is live, sits at that exact path, and has a `meta.price`.

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

Twenty types ship: `hero`, `rich_text`, `image`, `gallery`, `pdf`, `cards`, `columns`, `cta`, `faq`, `stats`, `testimonial`, `embed_html`, `post_list`, `spec_table`, `definitions`, `points`, `contact_form`, `warranty_check`, `spacer`, `divider`.

**`points` and `definitions` exist because the design draws sections that are not prose.** A heading, an intro, a dashed list and a button down one side of a band; a term-and-description list. Both were written as `rich_text` blocks carrying their own classes (`eyebrow`, `section-title`, `lead`, `dash`, `zfs`) — which Quill drops, so those sections could never join the shared document (§12.3). Measured against the vendored build: `Parchment.ClassAttributor(attrName, keyName)` matches classes shaped `keyName-value`, which is how `ql-align-center` works, and every class here is a bare boolean — so teaching Quill them needs a custom Blot and a clipboard matcher per class. They are block types instead, every field is an existing key, and `site.css` names the new blocks in the same rules it already had, so both pages render unchanged. `migrations/0011_sections_that_were_layout.sql` moves the two live pages across.

`hero` takes either one picture or several. `image` is the single one; `images` is a repeater of
`{media_id, alt}` and, from two rows up, becomes the design's rotator — the pictures take turns on
their own, in CSS (§12). Both keys stay, `images` wins when it holds two or more, so a hero that was
saved before this exists is untouched.

**Two keys in `data` are not fields and are not typed by anybody.** `_id` names a section for as long as it exists, and `_rich` records whether Quill can hold that section's markup without losing any of it (§12.1). They are written by the editor, travel with the block through `posts.blocks` and `post_drafts.blocks`, and exist so two browsers can agree about which section is which and about how it is edited (§12.3). `validate_blocks()` ignores extra `data` keys — it checks required fields and the type name, never an allow-list — and both are in `_NON_TEXT_KEYS` so `blocks_text()` skips them.

Three types carry a variant switch, and all three are **checkboxes**, never free text: `hero.dark` (the full-bleed band, where `image` becomes a faded backdrop instead of the art beside the words), `testimonial.dark`, and `contact_form`'s existing `kind`. The template tests them against fixed values (`{{ ' hero-dark' if data.dark }}`, `{{ ' cf-grey' if data.kind in ('quote', 'career') }}`), so nothing an editor types can reach a class attribute — which is the same reason `section_class()` is a whitelist.

`spacer` and `divider` are the two types that are not content, and both are shaped by what they do
*not* carry. `spacer` declares one field, `height`, a **whitelist** (`HEIGHTS = ("small", "medium",
"large", "huge")`) emitted by `section_class()` as `sp-*` — a number of pixels was the obvious
alternative and is the one thing the project forbids, because the value lands in a class attribute.
`divider` declares nothing at all: the universal `width` and `align_box` keys already shorten the
line and move it, since its `<hr>` is a direct child of `.wrap` and so is picked up by the shared
`.section>.wrap>*{max-width:var(--w,…)}` rule. Both are in the `.md` twins' two extremes —
`divider` is the one block whose Markdown branch is punctuation (`---`, safe as a thematic break
because `blocks_md()` joins with `\n\n` and can never make a setext heading), and `spacer` is in
`MD_SKIP` beside `embed_html`. `height` is in `_NON_TEXT_KEYS`, or `"medium"` would show up in
`llms-full.txt`, the feed and admin search, the way `tone` did.

Their CSS is the trap. `.section{padding:80px 0}` means a section that declares nothing at all is
already 160px tall, so both rule groups zero it first. Inside a Columns section the stacking gap is
`padding-top` on the section that *follows* (`.column>.section+.section`, (0,3,0)), which a bare
`.spacer` (0,1,0) loses to — a Small spacer came out 40px instead of 16px, and the gap doubled under
it. `.column>.section.spacer` ties that specificity and wins on source order, and
`.column>.spacer+.section` stands the following gap down so the height an editor picked is the whole
gap. The four heights are written `.spacer.sp-small` rather than bare `.sp-small` like `.fx-*`,
because `height` is a plausible future field on another block (there is a `# ponytail:` note
proposing exactly that on `pdf`) and `sp-*` is emitted for whoever declares it. `canvas.css` gives
`.iop-canvas .spacer` a faint dashed outline: on the page a blank section is the point, in the
editor it is a section nobody can see to hover, drag or delete.

`post_list` gained `eyebrow`, `link_label` and `link_url` (the "All services →" link in a section header), and **`per_row`** (2026-09-16), and `render_blocks()` hands its template a **`pt_slug`** extra alongside `posts` and **`cols`**. `per_row` is a `choice`: empty keeps the width-driven `auto-fit` every list had before, `even` asks `even_cols()` to work the count out from `len(posts)`, and `2`–`8` pin it. `even_cols()` takes the largest exact divisor in 4–8 (14 → 7, 16 → 8 rather than 4×4) and, when there is none, the count leaving the fullest last row (13 → 7, i.e. 7 + 6); fewer items than a row holds are one row of themselves. The number reaches the template as `cols` and becomes `pl-cols-<n>` on the section — **computed in `_cols()`, never read from the block's data**, which is why it is safe in a class name, the same rule `pt_slug` follows. `per_row` is in `_NON_TEXT_KEYS`, so it neither leaks into `llms-full.txt` nor gets co-edited as prose. The CSS applies the fixed track count only above **760px** and never inside a `.column`: a fixed count in half the width squashes the tracks, and a phone has to wrap by width. That becomes `pl-<slug>` on the section, and `site.css` styles one card per post type from it — the number for services, the logo for partners, the 16:9 picture and date for blog posts, the industry/solution chips for case studies. One template, the variants in CSS. `pt_slug` comes from the resolved `post_types` row, never from the block's own data, so it is safe in a class name.

**`rail` (2026-09-16) is the third computed extra**, and it is `pt_slug == "testimonial"` — a `post_list` of
testimonials renders as a sliding row rather than a grid. It is decided in `render_blocks()` beside `cols` and for
the same reason: it depends on the resolved type, so it can never be something an editor typed. It adds `pl-rail`
to the section and a `.rail-nav` after the cards, and `§12`'s *The sliding row* has the mechanism. There is
deliberately **no "Sliding row" checkbox** on the block — one content type wants this, and a field nobody sets is
a field that still has to be validated, seeded, labelled and tested (`# ponytail:` in `blocks.py` names the
upgrade path).

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
| `height` | `small` \| `medium` \| `large` \| `huge` | how tall a `spacer` stands, `HEIGHTS` in the same file; the pixels are in `site.css` |

Two functions carry them onto the root `<section>`, both **whitelists** rather than passthroughs, because the values land in attributes — the same reason `col_widths()` is strict:

- **`section_class(data)`** → `" al-center alb-right w-full"`, interpolated into the root `class`. `ALIGNS` and `WIDTHS` are the only values that survive.
- **`section_style(data)`** → `' style="--w:950px"'` for a **digits-only** `width` in `1..MAX_W` (4000), `""` for everything else, a named width included (that one is a class).

`--w` *is* the content measure: `site.css` writes every relevant `max-width` as `var(--w, <the theme's own value>)`, so an unset section renders exactly as designed, a number narrows or widens it, and `.w-wide` / `.w-full` set `--w:100%` from CSS. `.column{--w:initial}` stops a width set on a Columns section leaking into the sections inside it.

****`tone`** is the band a section sits on — `grey`, `dark` or `blue`, absent means the page's own white. The design alternates white and grey down the home page for rhythm and drops case studies onto black, and that is a per-section decision an editor makes, not something baked into a block type. Like `align` and `width` it is a **whitelist** in `section_class()`, because the value lands in a class attribute. Its rules sit *after* `.band-*` in `site.css`, so a tone an editor picks beats a block's own default (`stats` is dark, `cta` is blue) on source order rather than needing `!important`.

`--w-def` is what makes that sentence true.** The shared rule is `.section>.wrap>*{max-width:var(--w,var(--w-def,none))}`, and it is (0,2,0); every block's own rule (`.rich-text`, `.testimonial`, `.specs`, `.faq details`, `.lead-form`) is (0,1,0) or (0,1,1) and loses to it. So the fallback `none` used to win outright and the designed measures never applied at all — a section was only ever as wide as `--w` said, and unset meant full width. Each of those blocks now declares its measure as `--w-def` on itself, which the shared rule reads *inside* the fallback. `--w` stays the override it is documented to be, and `--w:initial` in a column still falls through to the block's own measure.

All of them are in `_NON_TEXT_KEYS`, so "center", "950" and "rise" never reach `llms-full.txt`, the feed or admin search — `tone` joined them at the same time, having leaked its "grey" into all three since it was added. `align`, `align_box`, `width` and `tone` are deliberately **not** fields in `BLOCKS`: layout belongs to every section, so `admin.js` renders one set of controls for all types (§12.1) and `validate_blocks()` simply tolerates the extra keys. `fx` and `height` are the exceptions — `section_class()` emits both for any block, but only the blocks that *declare* them get the dropdown: `fx` on `stats` and `rich_text`, `height` on `spacer`. Widening either to another block is one word in that block's optional list. `.cta` and table cells keep their own `text-align`, so a centred section does not restyle a CTA band or a spec table.

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

**The `csrf` token is minted for admin requests only, and the guard that does it is one line in the wrong-looking place.** `_globals()` in `admin_ui.py` is an `@ui.app_context_processor`, and Flask's `app_context_processor` is **app-wide despite the blueprint it is registered on** — so it ran on every `render_template`, public pages included, and put a `csrf` value in the session of every anonymous visitor. Nothing was insecure about that; what it cost was cacheability. A touched session means `Set-Cookie` on the response, and no HTTP cache stores a response carrying one, so behind the Cloudflare tunnel the public site could never be cached at the edge no matter what rules were written. `if not has_request_context() or request.blueprint != ui.name: return {}` fixes it, and it is safe because no public template reads `csrf`, `admin_user`, `post_types` or `nav_counts`, while `/admin/canvas` and `/admin/preview` are `admin_ui` routes and keep theirs. `test_public_pages_mint_no_session_cookie` asserts both halves — `{}` on `/`, a token on `/admin/login`.

`SESSION_COOKIE_SECURE` is derived from `SITE_URL`, not from `request.is_secure` (`config.py`), which is the right way round behind a TLS-terminating tunnel: the app only ever sees plain HTTP from cloudflared, so a request-derived flag would never set. `SESSION_COOKIE_SAMESITE = "Lax"` is load-bearing rather than hygienic — `/api/admin/v1` accepts the session cookie when there is no `Authorization` header and `require_role()` does not check CSRF, so SameSite is what keeps a cross-site POST from reaching it. Never relax it to `None`.

**Roles are a ladder:** `ROLES = {"editor": 1, "admin": 2}`, enforced by `require_role(min_role)`. A valid GoTrue login with **no `users` row gets 403** — authentication and authorization are deliberately separate.

Login goes through a throwaway anon client (`auth.anon()`); the service-role client is never used for password sign-in.

**A refresh that loses does not sign anyone out.** The access token lives an hour; the first request after that trades the single-use refresh token for a new pair (`_session_token()`, `auth.py`). The editor sends its preview requests in pairs without waiting for each other (`askPreview("")` and `askPreview("card")`), so two requests routinely carry the same expired pair to two different gunicorn workers and both call GoTrue. GoTrue answers a reused token with the same new pair for ten seconds (`SECURITY_REFRESH_TOKEN_REUSE_INTERVAL`), so both usually win; when one loses, it returns `None` and **leaves the session alone**. It used to `session.clear()`, and Flask sends a `Set-Cookie` only for a modified session, so the loser's empty cookie could land after the winner's fresh pair and sign the editor out mid-edit. Untouched, the loser sends no cookie at all, the next request carries the winner's tokens, and a token that is truly dead still ends on the login page, because `ui_required` redirects on `None`. Guarded by `test_a_losing_token_refresh_keeps_the_winners_cookie`.

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

`/login`, `/logout`, `/` (dashboard), `/posts`, `/posts/new`, `/posts/<id>`, `/posts/<id>/delete`, `/posts/<id>/restore`, `/media`, `/media/upload`, `/media/delete`, `/leads`, `/leads/<id>/status`, `/warranty`, `/warranty/<id>/delete`, `/settings`, `/users`, `/users/<uuid>/delete`, `/audit`, `/audit/<id>/restore`. Server-rendered forms; `_form_body()` turns form fields into the same body dict the JSON API accepts, so both surfaces share validation. `_safe_next()` restricts post-login redirects to relative same-origin paths.

`POST /admin/media/upload` is the one exception to "server-rendered forms": it takes the same multipart body as `POST /admin/media` (`csrf`, `file`, optional `alt`) through the shared `_upload()` helper, and answers `201 {id, url, filename, mime, alt}` or `4xx {error}` instead of redirecting. It exists so the post form's media pickers can upload without leaving the page; session auth and CSRF come from `ui_required()` unchanged.

`/admin/warranty` is the warranty register: list, `?q=` search over serial / customer / email, and one form that adds a record or edits the one named by `?edit=<id>` — the `users` screen's shape, with `db.paginate(..., 50)` and the `page` / `has_next` idiom used by `/admin/leads`. It refuses a duplicate `serial_key` with a `flash()` before writing, rather than letting a unique violation surface as a 502 through `_pg_error`. Editors may add and edit; **only an admin may delete**, matching `/admin/posts/<id>/delete`. The public side of this table needs no endpoint at all (§6, `warranty_check`).

It is post-redirect-get only when the write **succeeds**. A refused save falls through to the same render with the submitted values back in the form and a `400`, the way `new_post` / `edit_post` re-render rather than redirect — a redirect would answer a typo by making the editor retype the record. A refusal is a `(field, message)` pair, **not** a `flash()`: the form carries it as `data-refused-field` / `data-refused`, `initWarranty()` in `admin.js` puts it on that field with `setCustomValidity()` and calls `reportValidity()`, and a `<noscript>` copy says the same sentence without JS. Only a success flashes, at the top, where a confirmation belongs. `editing` is the form's contents, from `request.form` on a refusal and from the row on `?edit=`; the template keys add-vs-edit off `editing.id`, not off `editing` being truthy, so a rejected *new* record does not come back wearing an Edit heading. `?q=` and `?page=` ride through every redirect (save, delete, cancel) so a filtered list survives the round trip.

**Every `/admin` and `/api/admin/v1` route sits behind a `before_request` that answers 404 when `ADMIN_NETWORKS` is set and the caller is outside it** (§12) — the login form and the token endpoint included, because those are the two that take a password.

`/admin/audit` is the activity log: every entry `audit_log` holds, newest first, admin-only, with `?user=` / `?action=` / `?table=` filters and the same `db.paginate(..., 50)` + `page` / `has_next` idiom as `/admin/leads`. It orders by `id DESC` rather than by `at` — ids are handed out in time order so the two agree, and the primary key then does the sorting without a second index. No `/api/admin/v1` mirror exists: nothing consumes the admin API but this browser admin. It opens with a shut `<details>` from `throttle.connection()` saying where the site thinks you are connecting from, so the *From* column can be checked against what the app is actually receiving (§12).

**The screen is translated in `admin_ui.py`, not in the template.** The test it is written against is that somebody who has never seen the database can read a row aloud, so the route hands the template finished rows — `who`, `sentence`, `fields` — and `audit.html` does no thinking. The translators are pure functions living above the routes and importing nothing from them, which is how the offline tests call them directly:

| | |
|---|---|
| `VERB` | action → a sentence template with `{kind}` and `{name}` (`update` → "edited the {kind} {name}"). An unknown action still reads as itself |
| `KIND` | table → the noun an editor uses — `media` → "picture or file", `leads` → "enquiry", `users` → "person" |
| `POST_KIND` + `_post_context()` | **`posts` is eight different things**, and a log that calls a datasheet edit "posts" looks like it is missing what it is in fact showing. The content type's own name does it, singularised by a slug map that falls back to `post_types.name` for a type added later — the same shape as `base.html`'s `ICON` map and for the same reason. One batched `.in_("id", ids)` query per page, never one per row |
| `FIELD` + `_label_of()` | column → the label the editor sees elsewhere; `blocks` → *The writing on the page*. The fallback is `settings.html:17`'s own transform, so the two screens cannot disagree |
| `id` | **not shown as a field** when it equals the entry's `row_id` — creating a person records the GoTrue uuid the entry is already about, and 36 characters under a heading reading *Id* is noise an editor cannot use (`test_the_rows_own_id_is_not_shown_as_a_field`) |
| `_value()` | a stored value as something readable: statuses by name (never the word `trash`), timestamps through `ist()`, media ids as filenames, term ids as term names, menus as their labels, `meta`/`seo` as `label: value` lines using the type's `field_schema` labels. JSON is the last resort, not the normal case |

**A page edit is diffed per section, and returns a list of rows.** `blocks` skips `_value()` for `_blocks_fields()`, which is the only field that can produce more than one row in `fields`. The page-wide version shipped first and was unreadable: a real edit to the Home page rendered as **two identical ninety-line walls of text**, because the words had not changed at all — what moved was `fx` on two rows of a `stats` repeater, two levels down. The whole detail that entry produces now is two lines: *Numbers section, row 2 — Effect · None → Gradient across the big text*.

The shape, all of it in `admin_ui.py` above the routes and all of it pure:

- `_blocks_fields()` — **types identical** (the common case) → compare index by index, because position means the same thing on both sides; **types differ** → `_structural()` for a sentence plus one page-wide word diff, because the indices have drifted and comparing position 3 with position 3 would compare two different sections.
- `_section_rows()` — per changed block: a word-diff row if its own text moved, then `_data_rows()` for what the words cannot show. `_own_text()` excludes `cols`, or a Columns section would diff its children and then diff them again through the recursion.
- `_data_rows()` / `_repeater_rows()` / `_cols_rows()` — one level into a repeater (*row 2*) and one level into a column (*Column 2*, with the same types-identical test, for the same reason).
- `_block_field()` / `_block_value()` — `EDITOR["labels"]` for the field (`fx` → *Effect*) and `dict(EDITOR["choices"][key])` for the value (`gradient` → *Gradient across the big text*). Storing a value and showing it are two different strings, and only the second one answers the question.

**The rule that keeps the two halves from reporting the same change twice** (`_unwritten()`): `blocks_text()`'s `walk()` collects a value only when the key is outside `_NON_TEXT_KEYS` **and** `isinstance(v, str)`. Fail either half and the words cannot show it, so the settings diff must. The `isinstance` half is the one that is easy to forget — `count_up` is a bool and `limit` is a number, and neither appears in the text whichever set its key is in. Guarded by `test_the_two_diffs_do_not_report_the_same_change_twice`.

When the words are identical, no setting moved and the two blocks still differ, what is left is markup — a bolded phrase, a link, a heading level — and the row says *Formatting changed*. The previous version said "Nothing an editor would see", which was a lie about a save that plainly did something. `_structural()` still names sections from `EDITOR["names"]` ("Added Cards", "Moved the sections around"), now only where the indices drifted. Guarded by `test_a_page_edit_says_which_section_and_which_setting_changed` and `test_a_change_the_words_cannot_show_is_described_instead`.

The template renders the Was/Now grid **only when a row has one** (`{% if f.was or f.now %}`), so a row that is just a sentence is one line. **Restore stays one button per entry, after all the rows**: it writes the whole `blocks` array back, not the field you are looking at, and a button per row would promise otherwise.

**`POST /admin/posts/<id>/draft`** is the editor saving itself, every ~1.5 s. It writes the working
draft and never `posts.blocks`, runs `validate_blocks()` first (an invalid draft would otherwise be
refused by `apply_post()` at the worst possible moment — the press of the button), and answers JSON
with `Cache-Control: no-store`. It carries `blocks`, `state`, and the session's `was` / `now` /
`close`; `navigator.sendBeacon()` posts the same `FormData` with `close=1` on `pagehide`, which is
why the body is form-encoded rather than JSON — `ui_required` reads `csrf` out of `request.form`.
Like every admin `fetch()`, the caller must test `r.redirected`: a finished session is a 302 to the
login page that `fetch()` follows, arriving as 200 HTML rather than a 401.

**`POST /admin/posts/<id>/draft/discard`** throws the unpublished edits away and is logged with
`db.audit_event("discard", …)` — no row of ours changes in a way `db.py` can see, and a deletion
nobody recorded is exactly the gap the log exists to close.

**What is deliberately not recorded**, each because recording it would make the log worse rather than better:

- **The autosave itself** — and only the autosave. `audit_log` has no retention job and holds a whole
  `blocks` array on both sides of every row, so a row every second or two per editor would grow
  without bound. Note what this is *not*: `POST /admin/posts/<id>/draft` is not a route that writes
  nothing to the log. It closes editing sessions that have gone quiet, and each of those **is** an
  audit row, attributed to the editor who made the changes rather than to whoever happened to trigger
  the flush. The `AUDITED` entry says exactly that, because the route-accounting test cannot.
- **Reads.** Opening a page, viewing Leads. A working day is roughly fifty lines of looking per line of doing, and the change somebody came to find would be buried.
- **Session and token mechanics** — the CSRF token, the cookie, and the GoTrue refresh rotation `_session_token()` performs on *every* admin request including GETs. A session staying alive is not a step anybody takes; logging it would add a line per page load. This covers `POST /auth/refresh` and the re-login inside `account()` after a password change, where the password change itself is the event.
- **Refusals other than a blocked login.** A rejected save or a permission refusal changed nothing and the person simply tried again. A *blocked* login is the line that shows an attack, and is recorded — **once, at the crossing**. `throttle.record_failure()` returns `True` only for the attempt that reaches `LOGIN_MAX_FAILURES`; logging from `retry_after()` instead would write a row on every attempt for the whole window, handing anyone hammering a locked login the ability to fill the audit log at will (`test_a_lockout_is_recorded_once_not_on_every_blocked_attempt`).
- **The bucket and GoTrue halves** of an upload, a delete, a user create and a user delete — each already sits beside a logged row write carrying the key or the email.
- **Rows removed by a Postgres cascade** when a taxonomy is deleted: the app never writes them, so it cannot log them. The taxonomy's own entry holds what it was.
- **`flask seed` and `flask import-media`** — content, reproducible, no actor. `flask create-admin` is the one command-line exception (see §4).
- **Anything under `TESTING`.** The live suite writes to the real database; without this the client's Activity screen fills with `zz-test` rows that the append-only trigger forbids anyone to remove. See §3.

**`POST /admin/audit/<id>/restore`** writes the "was" half of an entry back — `{k: pair[0] for k, pair in changes.items()}` — and because the restore goes through the ordinary write helpers it is itself logged, as `action="restore"`. One stored format, four writers, because not every entry's fields are columns of the table it names: `settings` and `menus` are keyed by their own column rather than `id`, so they need `set_settings()` / `set_menu()`; a `posts` entry whose one field is `terms` came from `set_post_terms()` and goes back the same way (`posts` has no `terms` column — `db.update()` would 400 on it); everything else takes `db.update()`. Two refusals are flashes rather than 502s: a `settings` entry whose "was" half is `None` (the key did not exist, and `settings.value` is `NOT NULL`), and blocks that no longer validate. `blocks` is re-run through `validate_blocks()` first, because a block type can have been renamed or dropped since the version was saved, and a failure is a `flash()` rather than a 502.

**Restore also clears the working draft** when it puts a `posts` entry's `blocks` back, and without
that line it would appear not to have worked at all: `posts.blocks` goes back, then the editor opens
and loads the draft — which is still the version that was just undone — and its next autosave writes
that straight over the restore. `flask seed --reset-content` carries the same line for the same
reason. Restore keeps its two existing carve-outs: it deliberately does **not** pass `if_unchanged`
(an intentional overwrite is the whole point of the button), and `_restorable()` below is unchanged.

**What is restorable is not what it first looks like** (`_restorable()`). An `update` always is. A `delete` is only for `posts`, because that is a move to the trash and the row is still there. Every other delete is real, and re-creating the row would be a lie: a deleted user's GoTrue account is gone so the row would come back unable to log in, a deleted media row would point at a bucket object already removed, `warranties.serial_key` is `GENERATED ALWAYS` and refuses to be written back, and a deleted taxonomy's terms cascaded away. Those entries still *show* the whole row they removed, which is what makes them evidence. `POST /admin/posts/<id>/restore` is the same undo reached from the Posts list's trash filter, and it comes back as a **draft** — the page has been off the site for a while and whoever restores it should be the one to decide it goes live again.

### `/media/<bucket key>` — the file proxy, `public.media_file()`

Every picture and PDF on the site, the admin included. Supabase sits on the LAN with only Flask exposed,
so a browser cannot fetch an object out of the Storage bucket: it asks Flask, and Flask asks Storage with
the service-role key it already holds (`storage.fetch()`).

**This is a pattern, not a one-off, and it now has a second member**: `/admin/realtime/v1/longpoll`
(`admin_ui.realtime_longpoll()`, §12.3) carries the page editor's collaboration channel through the app
for the same reason and with the same shape — the browser addresses Flask, Flask addresses Kong, and
Supabase is never on the tunnel. The differences are that the realtime proxy is behind the admin session
rather than public, and that it forwards a query string and a body rather than looking up a bucket key.

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

### Caching the public site

**The public site answers identical bytes to every visitor, and used to build them every time.** Two layers
now stop that, both in `public.py`.

**The page cache** keeps the finished response in the worker process, keyed by `request.full_path`, and
`_page_cache_read()` returns it as a `before_request` without the view ever running. Measured against a real
server: **220 ms → 2.9 ms, 29 PostgREST round trips → 0.** Three things about its shape are load-bearing:

- **`_cache_key()` is an allow-list, not a list of exclusions.** Only `public.resolve` is cacheable.
  `/media/<key>` is on the *same blueprint* and serves files up to `MAX_CONTENT_LENGTH` (20 MB), so a
  deny-list that ever missed it would buffer 512 × 20 MB. A request carrying `?sn=` (the `warranty_check`
  block answers per serial number) and anything ending `/checkout` are refused as well, and `?page=2` is its
  own entry.
- **Freshness is not a timer.** An entry is dropped the moment `db.content_epoch()` is newer than its stamp,
  so the origin is never behind a publish — `PAGE_TTL` is only a backstop. Proven across processes: a
  `bump_epoch()` from a *separate* Python process made the running server re-render on its next request.
- **A lapsed entry is served stale while one thread re-renders it** (`_refreshing`, guarded by a lock). Without
  that, a TTL expiring on a busy page becomes 240 simultaneous 219 ms renders. The key is released in
  `teardown_request`, not `after_request`, because an unhandled exception skips the latter and would pin that
  page's stale copy until the worker restarted.

**`Cache-Control` on public responses** is what actually takes the traffic off the box, because Cloudflare is
already in front of the tunnel. `_public_cache_headers()` sends
`public, max-age=0, s-maxage=60, stale-while-revalidate=300` on any `pub` 200 that carries no `Set-Cookie`.
`max-age=0` keeps the visitor's own browser revalidating, so a reader never holds a stale page, while
`s-maxage` lets the edge answer. This only works because anonymous pages carry no cookie — see §7 on why the
CSRF token is withheld from public blueprints; that decision is what makes this possible and must not be
undone. **It is opt-in at Cloudflare**: the header alone does nothing, because Cloudflare does not cache HTML
without a Cache Rule, which must exclude `/admin/*` and `/api/*` (§15).

Guarded by `test_only_whole_public_pages_are_cacheable`,
`test_a_public_page_tells_shared_caches_it_may_be_served_again` and
`test_the_page_cache_returns_the_stored_page_and_a_write_drops_it`.

### Crawler endpoints

`/sitemap.xml`, `/robots.txt`, `/feed.xml`, `/llms.txt`, `/llms-full.txt`, plus `/healthz`. These carry the
same `Cache-Control` (they are on `pub` and are public), but are **not** in the page cache — only
`public.resolve` is. Add them if a crawler ever makes them hot; `/sitemap.xml` is one query of up to 5000 posts.

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
- `_indexable()` — **the one gate for everything a crawler reads** (`public.py`), below

**Nothing a crawler reads may carry an address the app owns** (client, 2026-09-15). `_indexable()` asks
three things: has this post a path, is that path ours to publish (`db.reserved()`), and is it not
`noindex`. `CLAUDE.md` has called it "the one gate" for a while; this is the change that made the
sentence true, because four surfaces were quietly skipping it:

| Surface | Before | Now |
|---|---|---|
| `sitemap.xml`, `llms.txt`, `llms-full.txt`, post `.md` twins | `_indexable()` | unchanged route, but the gate now also asks `db.reserved(path)` |
| `feed.xml` | `db.live()` only — a `noindex` post was in the RSS | `_indexable()` |
| archive `.md` twins, *Related pages* inside a post's twin | `_md_list()` filtered on `path` alone | `_md_list()` filters on `_indexable()` |
| a post type's archive URL, a term archive | never seen by `_indexable()` — neither is a post | `db.reserved()` in the sitemap's two non-post loops |

`_kids()` is deliberately **not** filtered: it feeds the rendered HTML page as well, and `noindex`
means do not index, not do not link. Only the Markdown twin — the crawler's copy — drops them.

**`noindex` is read as a token list, not a prefix.** `_noindex()` lowercases and splits on commas,
because `.startswith("noindex")` let `NOINDEX` and `nofollow,noindex` — both spellings the form's own
hint invites — render a `noindex` page that stayed in the sitemap, which is the single failure that
field exists to prevent.

**`/api/v1` stays advertised in `llms.txt` on purpose.** It is the read-only public API: published
content, no auth, no writes, the same rows the pages already show. Pointing AI crawlers at it is what
`llms.txt` is for. Only `/api/admin/v1` is private, and it sits behind `ADMIN_NETWORKS` and a token.

**`robots.txt` no longer names the admin.** It carried `Disallow: /admin` and `Disallow: /api/admin`,
which protected nothing once `/admin` began answering 404 outside `ADMIN_NETWORKS` — while `robots.txt`
is world-readable and the first file a scanner fetches, which made those two lines the only public
statement that this site has an admin at all (user, 2026-09-15). `robots_extra` still appends whatever
the client types, unfiltered: an admin who writes `Allow: /admin` there undoes this, which is accepted
rather than policed.

**Measured, 2026-09-15**, against the live development database on a real server: all five crawler
endpoints answer with content (sitemap 60 `<loc>`s, llms-full 19 KB) and **zero** occurrences of
`/admin` or `/api/admin` between them. The offline guard seeds the collision deliberately — a page
slugged `admin`, a post type prefixed `admin`, a taxonomy slugged `admin` — because an assertion that
passes on a site containing none of those proves nothing; removing any one of the three gates makes
`test_no_crawler_output_can_carry_an_address_the_app_owns` fail, which was checked one gate at a time.

`base.html`'s `<head>` also carries the favicon (`static/favicon.svg`, the black square with the blue bar and white ring) and the two web fonts. The fonts come from Google Fonts on a `<link>`, which is the one external request the public site makes; `admin/canvas.html` repeats that link because it is a standalone document, and without it the editor canvas would preview the page in a different typeface from the page itself.

> **Known gap.** The `faq` block emits Q&A markup but is not currently wired into FAQPage JSON-LD. The knowledge graph flagged this edge as AMBIGUOUS; it is a genuine, unimplemented opportunity.

---

## 10. Migrations

Plain `.sql` files in `migrations/`, named `NNNN_short_name.sql`, applied in name order and tracked in `schema_migrations`. **Only a four-digit-prefixed name is a step** (`MIGRATION_GLOB` in `cli.py`); anything else in the folder is a script run by hand and is never executed as part of a run. There are two: `repair_schema_migrations.sql`, for a database built by pasting files before the ledger existed, and `purge_test_audit_rows.sql`, the only sanctioned delete from the append-only `audit_log` (§3).

`0000_bootstrap.sql` is pasted **once** into Supabase Studio's SQL editor. It creates `apply_migration(name, sql)` — `SECURITY DEFINER`, executable by `service_role` only — which `flask migrate` calls per file over Kong. Each file runs in one transaction.

In production nobody types that command: `flask migrate` is a service of its own in `docker-compose.yml`, run once per deploy, with `app` gated on it finishing successfully (§15).

**Workflow for a schema change:**

1. Write the `ALTER`/`CREATE` as a new numbered file
2. `pipenv run flask migrate`
3. Update the code that reads/writes those columns

The code must run against a database where the newest file is **not yet applied**. `0008_audit_log.sql` is the clearest case: `db._audit()` swallows the missing-table error, so every save works and the only sign is a warning in the log.
4. Commit both together

**When the ledger and the database disagree.** A schema built by pasting the files into Studio leaves every table in place and `schema_migrations` empty, so `flask migrate` starts again at the beginning and stops on `0001_initial.sql: relation "menus" already exists`. Nothing is broken — the ledger simply never recorded what was done by hand. `migrations/repair_schema_migrations.sql` fixes it: pasted into Studio, it records each file **only if the thing that file makes is actually present** — the `posts` table for `0001`, `pg_class.relrowsecurity` for `0002` (the table can exist with RLS still off, which is the very state `0002` fixes), `warranties` for `0003`, the `warranties_expiry_after_purchase` constraint for `0004`. A file that was genuinely never applied stays unrecorded and `flask migrate` then applies it normally. Safe to run twice, and safe on a database in any state. `migrate()` names that script in its own error when the failure text contains "already exists".

Not every step alters the schema. `0007_media_through_flask.sql` is a **data** migration: it rewrites the
absolute Storage URLs frozen into `media.url`, `settings`, `posts.blocks` and `posts.seo` into `/media/<key>`
paths (§8). It matches any host with a regex rather than naming one, every statement is guarded so a second
run changes nothing, and the code works before **and** after it — new uploads already write the new path,
old rows keep the address they have until it runs.

`0002_enable_rls.sql` enables RLS on every app table, so the anon key cannot read drafts or leads. The app's service-role key bypasses RLS by design. A new table repeats that one line for itself — `0003_warranty.sql` ends with `ALTER TABLE warranties ENABLE ROW LEVEL SECURITY;`, and defines no policies.

`0014_testimonials.sql` is the shape to copy for **a content change that the seed cannot carry**, and it is three
things in one file: the `post_types` row for `testimonial`, the two quotes that used to be typed into the home page
as `posts` rows, and the swap of the home page's section from a `columns` block to a `post_list` one. That last part
is `0012`'s pattern — `jsonb_agg(... ORDER BY ord)` over `jsonb_array_elements(blocks) WITH ORDINALITY`, matching the
block **by its content** (`type = 'columns' AND data->>'heading' = 'What our clients say'`) and never by its index
or a row id, because production has its own ids and a block's position in the array was never a promise. It runs the
identical update against **`post_drafts`, setting `state = ''`**: a working draft holds its own copy of the blocks and
`state` is the stored shared document, so a draft left behind puts the old section straight back the next time
somebody opens the page. The seed (`cli.py`) makes the same three changes for a fresh database, because
`_get_or_create()` only ever inserts and so never reaches one that already exists.

**A hand-applied file does not bump the cache epoch.** `flask migrate` calls the `apply_migration` RPC, not
`db.insert()/update()`, so nothing calls `bump_epoch()` — a server that is already running keeps serving its cached
`post_types()` and its cached rendering of the page until it restarts or somebody saves something in the admin
(§4, §8 *Caching the public site*). Every content migration should say so in its own header comment; `0014` does.

---

## 11. Payments

`payments.py` defines the `PaymentGateway` interface (`create_checkout()`, `handle_webhook()`) and `DummyGateway`, selected by the `PAYMENT_PROVIDER` env var through `GATEWAYS`. `dummy` records the payment row and exposes `/api/v1/payments/dummy/<id>` to mark it paid, without charging anything. A real provider is a new subclass plus an env change.

---

## 12. Theme

One stylesheet, `static/site.css`, with the design tokens at the top, then header / mega menu / footer, then `.cards` / `.card` / `.btn` / `.section`, then the section-layout group (`.al-*` / `.alb-*` alignment and `.w-*` / `--w` width, §6), then one rule-group per block. `static/admin.css` layers admin-only rules on top, so `/admin` inherits the public theme.

**`site.css` is shared three ways** — the public site, `body.admin` (through `templates/admin/base.html`) and the editor canvas iframe (`templates/admin/canvas.html` loads it, then `canvas.css`). A change to `.card`, `.btn`, `.specs` or `.lead-form` shows up in all three, which is the point: the canvas is a real render of the real theme.

**Tokens.** `:root` holds the palette the design ships with — `--black`/`--black-2`/`--black-3` and `--line-dark`/`--line-dark-2` for the dark bands, `--blue` (`#3573b9`, the brand blue — the fill inside the client's logo artwork) with `--blue-hover` `#29588e`, `--blue-tint` `#e5eef8` and `--blue-light` `#78a6d8` — the same hue and saturation at three other lightnesses, so a change to the brand blue is four values, not one, plus **eight** `rgba(53,115,185,alpha)` literals on seven declarations (`site.css:370` carries two) that no token could carry — tinted tiles, the hero glow, the sweep gradient, and `admin.css`'s media-picker selection ring — `--white`/`--grey`/`--line`/`--line-2` for the light ones, `--ink` (`#2e3133`, the Deep Charcoal of the logo's *STOR* — headings and body, never a fill)/`--ink-2`/`--muted`/`--muted-dark`/`--muted-dark-2` for text, `--green`/`--red` (plus `-bg`) for status, `--wrap` (1200px) and `--reading` (760px) for measure, and `--head`/`--body`/`--mono` for the three type stacks. Headings are Manrope 800, body is IBM Plex Sans.

A second, shorter line under them maps the *old* token names (`--navy`, `--accent`, `--accent-2`, `--text`, `--card`, `--radius`) onto the new palette. `admin.css` and `canvas.css` still reference those in ~90 places; the aliases keep the admin rendering while it is restyled in its own PR, and are marked `ponytail:` for deletion once nothing uses them.

**Animations.** Three on menus: `drop` (the mega panel at .22s and the Company drop-down at .2s, `cubic-bezier(.2,.7,.2,1)`), `fade` (the mega's right pane, .2s ease-out, as the pointer moves down the group list) and `slide` (the mobile sheet, .25s ease-out). Five on the hero, from the design's own keyframes: `rise` on the words (.7s), `heroin` on the picture column (.8s), `glow` on the radial wash behind it (5s, infinite), `float` on the picture itself (6s, infinite) and `dot3`/`dot2` on the rotator's progress dots. Every one-shot is `both`-filled so it holds its end state. The entrance pair is scoped to `.hero-split` — the hero with art beside it, which is the only hero the design animates; every other opening band is still. Hover work is `transition` at .15s.

**`.hero` carries `overflow-x:clip`, and it is load-bearing** (2026-09-18). Three of the hero's entry animations
start the element to the *right* of where it lands — `heroin` at `translateX(40px)` on `.hero-media`, and
`slides2`/`slides3` at `translateX(60px)` per slide — and a transform counts toward scrollable overflow. A desktop
band has slack either side and nothing shows; a phone has none, so **the whole page grew and slid sideways under the
reader's thumb**: measured on the real home page, `documentElement.scrollWidth` was 451 against a 390 viewport
(61px) and 401 against 320 (81px). Toggling one thing at a time accounted for every pixel — the rotator was 48 of
the 61, `heroin` the rest, the `glow` contributed nothing, and **the testimonial row contributed zero**, which is
worth knowing because the sliding row is what looks guilty.

Two things the fix had to be, and both were decided by measuring rather than by reasoning:

- **`clip`, not `hidden`.** `hidden` would make the band a scroll container.
- **On `.hero`, not on `body`.** `body{overflow-x:clip}` was tried and left the overflow at 61px / 81px — **exactly
  unchanged, it does nothing here** — which is the trap, because it is the first thing anyone reaches for. It would
  also have been wrong on principle: `.site-header` is `position:sticky`, and any non-`visible` overflow on an
  ancestor takes that away.

`.hero-media` keeps its exact width with the rule in place (336px at 390, 289px at 320, 538px at 1440), so it clips
the animation's transient overshoot and never the layout. `test_the_hero_clips_the_overshoot_of_its_own_entry_animations`
guards it, because a page-wide horizontal scroll is invisible to pytest and to a screenshot that is not looking for it.

**The hero rotator is CSS.** `hero.images` renders `.hero-slides` with the picture count inline as `--n` and each `.hero-slide` carrying its turn as `--i`. Every slide runs the same loop over the whole cycle (`calc(var(--n) * 4.5s)`) delayed by `calc(var(--i) * 4.5s)`, so exactly one is showing at a time with the design's slide-in / slide-out either side of its turn. The dots are `<span>`s, not buttons: they report which picture is up and fill blue across its 4.5 seconds, and they are `aria-hidden` because they say nothing the pictures' `alt` text does not. **`.hero-dots` is a sibling of `.hero-slides`, not a child of it** — `.hero-slides` carries the `float` loop, so a dot inside it drifted up and down with the picture, and an indicator that bobs is hard to read against. Being absolutely positioned it now measures from `.hero-media` instead, which only has the one-shot entrance; the picture still floats and the dots hold still. Measured rather than eyeballed: with `.hero-slides` held at each end of its float, `.hero-dots` reports the same `getBoundingClientRect().top` while `.hero-slides` moves 9.6px. There is one keyframe set per count — `slides2`/`dot2` and `slides3`/`dot3` — because a slide's share of the cycle is written into the percentages; a fourth picture needs a fourth set, marked `ponytail:` in the file. Under `prefers-reduced-motion` the slides are stood down explicitly and the first picture is left showing: the mock's blanket `animation-duration:.01ms` would have parked every slide on its final frame, which is the hidden one.

**Section effects (`fx-*`)** are the four an editor can put on a Numbers or Rich text section (§6). All four run on the document timeline and play once as the page loads, in every browser. `fx-gradient` paints the section's big text — every heading, plus a Numbers figure, which is a `<strong>` and not a heading at all — with the brand gradient through `background-clip:text`, drifting on a plain time loop. The other three are one-shot entrances: `fx-rise` fades and lifts `>.wrap` (never the `<section>` itself, which would fade a dark band in from white), `fx-sweep` grows a marker-pen bar as the element's *own* `background-size` from `0 .3em` to `100% .3em`, and `fx-count` rolls a registered `@property --cv` through `counter()`.

Three things about that group are not obvious:

- **The bar is a background, not an `::after`.** A pseudo-element behind the text needs `z-index:-1`, which puts it behind the section's band as well, so the marker would simply disappear on `stats`. Painting it as the heading's own background sits it behind the glyphs and in front of the band, with no stacking context to manage. It also forces `width:fit-content`, or a block heading's bar runs the width of the column.
- **They must not be re-timed against the scroll.** Two drafts tried `animation-timeline: view()` and both were wrong. Putting the *whole* group inside `@supports (animation-timeline: view())` made every effect do nothing in Firefox 140 ESR, which parses the property but cannot resolve `view()` and so held each `both`-filled animation on its opening frame — `fx-rise` at `opacity:0`, `fx-count` an empty box. Splitting it into base rules plus a trailing `@supports` that only added `animation-timeline`/`animation-range` fixed that browser and broke the content instead: **a scroll timeline pins the animation to where the reader is, not to a clock**, so a section sitting in the first viewport is already part-way through its range at scroll position 0 and loads part-way through its animation. The Numbers band under the hero rendered **270 for a figure the editor had typed as 300** — the client's own number, understated, in every browser that resolves `view()` (Chrome 115+, Safari 26+, Firefox 144+). Reloading with the band mid-screen, past the end of the range, read 300. One timeline, the document's, is now the whole story. The cost is named and accepted: a section far down the page finishes before the reader reaches it.
- **The counter's keyframe must not contain a `var()`.** The obvious `@keyframes cv{to{--cv:var(--to)}}` tweens in Chrome and **jumps in one frame in Firefox**, which refuses to interpolate a keyframe whose value is a variable — so the figure snapped 0 → 300 and the bug was invisible in a Chromium screenshot. `--cv` is therefore registered as a `<number>` running a literal `0 → 1`, and the figure's own `--to` is applied at the far end by `counter-reset: cv calc(var(--to) * var(--cv))`, which `counter-reset` rounds to an integer. Verified by holding the animation at fixed points with a negative `animation-delay` — 140 → 183 → 242 → 296 across a 2s `ease-out`.
- **One effect, one element.** `animation` is a single property, so two effects landing on the same `<strong>` silently replace each other — the counter beat the sweep's wipe and the gradient's drift, and a counted figure could never also be swept. The roll is therefore animated on `.cr`, the empty span that carries it, leaving `<strong>` free for the sweep. Any future effect on a figure needs its own element or its own longhand.

**`prefers-reduced-motion` moved to the end of the file and now says `!important`.** `@media` adds no specificity, so from where it sat — above the block groups — `.hero-text{animation:none}` lost outright to `.hero-split .hero-text{animation:rise …}` further down, and the hero kept moving for a reader who had asked it not to. The effects join the same block: `fx-count` needs three lines rather than `animation:none`, because stopping the animation alone strands `--cv` at 0, so the counter is stood down (`content:none`) and `.cv`'s real digits come back out of hiding.

**`canvas.css` renders all four at rest.** `admin.js` swaps one `<section>` per keystroke (§12.1), so every effect would replay as an editor typed; the canvas shows their finished state instead — and putting the real digits back inside `<strong>` is what keeps a figure editable in place.

**The header is white**, not the mock's black — the client asked for it, with the logo in its own colours rather than knocked out. The knock-out filter therefore lives on `.site-footer .brand img`, not on `.brand img`, because the footer is still the dark band. The mobile sheet follows the header: a white panel with `--line` rules and `--ink` rows. Nothing else in the design changed colour.

**The logo is a fixed box, not a fixed height.** `.brand img` is `width:150px;height:22px;object-fit:cover`, shared by the header and the footer — the footer rule now carries nothing but the knock-out filter. The mock sized the logo `height:22px;width:auto`, which only works for artwork with the whitespace already trimmed off: the file an editor put in `settings.logo_url` is 2172×724 with the wordmark occupying the middle 271 rows, so at a fixed height the padding was counted as logo and the mark rendered at 8px instead of 19px. `cover` crops the box full instead of fitting the file inside it, which is what makes the file's own margins stop mattering. The box is 6.8:1 to match a wordmark, so the client's original 180×26 artwork loses about a pixel off each side. **The ceiling, marked `ponytail:` in the file: a logo whose artwork fills a square or tall canvas edge to edge loses its top and bottom.** `flex:none` is on the rule because `.brand` is a flex container and an item with an explicit width would otherwise shrink at 390px.

**The footer's social row is a sprite, and `site()["social"]` is no longer a list of strings.** The profile URLs an editor types into Settings → Contact details used to render as one `<li>` per URL *inside the Contact column*, labelled with the bare hostname (`www.instagram.com` between the email address and "Datasheets"). Four or five profiles made that column a stack of domain names, so the list moved out into its own `<ul class="social">` under the footer brand, address and tagline. `seo.site()` now maps each URL through `_social()` to `{url, name, icon}`: `SOCIAL` keys the five networks the client uses by registrable host (`host == k or host.endswith("." + k)`, so `in.linkedin.com` and a leading `www.` both match, and `twitter.com` and `x.com` share one glyph), and **anything not in the map keeps its hostname and an empty `icon`** — a network an editor pastes next year renders as a text link instead of a blank one. `jsonld()` therefore takes `[x["url"] for x in s["social"]]`; `sameAs` is still a flat array of strings, and `public.py`'s `PUBLIC_SETTINGS` serves the raw setting and is untouched. The glyphs are simple-icons paths (CC0) in one `<svg hidden>` sprite inside the `{% if site.social %}`, the same `<symbol>`/`<use>` pattern as the admin sidebar — but they are **solid** paths, so `.site-footer .social .si` sets `fill:currentColor` where `.adm-nav .ic` inherits stroke properties. `currentColor` is what makes the existing `.site-footer a` / `a:hover` colours drive the icons with no second rule. **The trap: `hidden` does not hide an inline `<svg>`.** The UA's `[hidden]{display:none}` is declared inside the HTML namespace, so it never matches an SVG element, and the sprite silently reserved a replaced element's default 300×150 box — a 150px hole between the address and the icons, which only a screenshot catches. `.site-footer svg[hidden]{display:none}` is the fix, and `admin.css:124` is the same rule scoped to `.admin`. `display:block` sits on the glyph rather than `line-height:0` on the link because the same `<a>` carries the hostname fallback as text; `align-items:center` on the row is what lines that word up against the icons beside it. **These are the one set of links on the public site that open in a new tab** (`target="_blank"`, client, 2026-09-11) — a visitor sent to Instagram should not lose the page they were reading. `rel` already carried `noopener`, which is what a `_blank` link needs to keep the opened tab off `window.opener`. `test_social_links_get_a_name_and_an_icon` guards the mapping, the `www.`/twitter aliases, the unknown-host fallback and the `sameAs` shape.

**The services mega panel** is CSS only, like everything else on the public site. Its markup is a child of the Services `<li>`, absolutely positioned against `.site-header` — sticky is a positioned element, so it is the containing block, which is how the panel spans the viewport instead of the 1200px column. That is also why the Services `<li>` is `position:static` while every other one is `relative`: the Company drop-down has to anchor to its own item. **Opening is plain `:hover` / `:focus-within`**, so it works everywhere; only switching the visible group needs `:has()`, and a browser without it still opens the panel showing the first group.

**Each pane is the next sibling of its own link**, both grid items of one `.mega-cats` container (`grid-template-columns:260px minmax(0,1fr)`; the links are pinned to column one, the pane to column two with `grid-row:1/span 99`, which is "every row of the list" so the pane is beside the last link too). That shape is what makes the panel usable: `.mega-g:hover + .mega-pane` opens it and `.mega-pane:hover` keeps it open, so the pointer can leave the link and land on the tiles. There must be no unhoverable strip between the two — the links fill the 260px column and the divider is the pane's own `border-left`, so the padding that used to sit between them (18px on the group column, 36px on the pane column) is now inside one hover target or the other. `.mega-g:has(+ .mega-pane:hover)` walks the highlight back from a hovered pane to its link, and `.mega-cats:not(:has(:hover,:focus))` is the whole "nothing chosen yet" state that shows group one. `:focus` and `:focus-within` arms on the same rules mean `Tab` reaches each group and then its own tiles. There is no ceiling on the group count — index pairing is gone, and with it the eight `nth-child` rules that used to break on a ninth service. `.mega::before` bridges the few pixels of bare header between the 59px nav link and the panel's top edge; it exists only while the panel is open, so it can hold a panel open but never open one. Under 960px the panel collapses into the checkbox sheet — number column hidden, blurbs dropped, and **every group closed, opening on a tap** (2026-09-18). It used to show every pane expanded at once, which turned five service groups into one flat wall of twenty-odd links you had to scroll past to reach Blog or Contact; the client reported it.

**The phone disclosure is the same trick the burger itself uses** — a `display:none` checkbox driven by its `<label>`, no script — and the ordering of the four parts is the whole design:

```html
<input class="mg-toggle"> <label class="mg-row"> <a class="mega-g"> <div class="mega-pane">
```

The checkbox and its label go **before** the group link, never between the link and its pane. Put them in the middle and `.mega-g:hover + .mega-pane` stops being adjacent, and the entire desktop panel above has to be rewritten. This way the only desktop casualties were three `:first-child`s that became `:nth-of-type(1)` — "the first `<a>` child", which is what they always meant, and which is still true now that an input is the literal first child. The phone's chain is `.mg-toggle:checked + .mg-row + .mega-g + .mega-pane`, **adjacent the whole way**: the groups are flat siblings of one `.mega-cats`, so a `~` anywhere in it would open every group below the one that was tapped as well. `test_the_mega_menu_keeps_the_order_both_layouts_depend_on` pins the order, because getting it wrong breaks both layouts and neither complains.

**The same disclosure runs one level up** (2026-09-18). A top-level item that holds others — Services and Company — gets `input.nv-toggle`, `label.nv-row`, then its `<a>`, then its `.mega` or `.sub`, and `.nv-toggle:checked + .nv-row + a + .mega` (or `+ .sub`) opens it. The link is **hidden rather than doubled**, and that costs no destination: Services repeats itself as *All services →* in the panel's own foot, and Company's URL **is** `/about-us`, which is already its first child. `.nav-group` is on the `<li>`, added whenever the item has children.

That hide needs `.site-nav>ul>li.nav-group>a{display:none}` and **not** a bare `.nav-group>a`: `.site-nav>ul>li>a` sets `display:block` at (0,1,3), so (0,1,1) loses to it and every group renders **twice** — once as the row, once as the link it was supposed to replace. The probe did not catch it (it counted only non-group links); the screenshot did. `test_a_top_level_menu_item_that_holds_others_collapses_the_same_way` asserts the winning selector.

Fully closed, the phone menu is **490px** — six rows and the CTA, the whole thing on one screen. It used to run past a screen and a half before Blog.

Everything that opens a pane **by pointer** moved into `@media(min-width:961px)`. Two reasons, and the first is not cosmetic: `.mega-cats:not(:has(:hover,:focus)) .mega-g:nth-of-type(1)+.mega-pane{display:block}` out-specifies a phone's plain `.mega-pane{display:none}`, so left unscoped it jams group one permanently open on a touch screen. And `.mega-pane:hover` latches on a touch device, which would stop a group closing again. `.mega-pane{display:none}` stays outside the query as the shared default — closed is now what both layouts start from. Verified with the panel forced open the way `:hover` leaves it: at 1440 nothing hovered still shows pane 1 with group 1 highlighted and its arrow at `opacity:1`, and standing in for a hover on group 3 opens pane 3.

Its data comes from `service_nav()` (`public.py`), a template global over `db.tree("service")` — `menu('header')` carries labels and URLs only, and the panel needs each group's `excerpt` and children. It is a callable rather than a value because the context processor is app-wide and an `/admin` page has no use for a posts query.

**Long words wrap.** `body` carries `overflow-wrap:break-word`, so an unbroken string (a pasted URL, a hash) breaks instead of running off the right of its section and giving the page a horizontal scrollbar — and it is inherited, so the editor canvas gets it too. `break-word` only wraps *inside* a box, and a grid track or a table column is sized from min-content, which a 300-character word still blows out; the boxes that size to their content (`.card`, `.column`, `.stats li`, table cells) get `overflow-wrap:anywhere`, which counts in that size. Not on `body`: `anywhere` would let the header nav break mid-word.

No CSS framework, no build step, no JavaScript framework. Mobile navigation is a checkbox-driven CSS menu with no JS, and the section effects and the counting figures are `@property` + `counter()` on the document timeline. The public site ships **one** first-party script, `static/site.js` (2026-09-16) — see *The sliding row* below for what it does and what it deliberately does not. Everything else on the site is still server-rendered HTML and CSS.

**A blog post reads down, not across.** Every other type puts its featured picture beside the words (`.page-head.has-media`, two columns); an article stacks — title, date, the picture **at its own size**, then the rule that divides the head from the writing. `.featured` is a banner crop (`width:100%`, a 440px ceiling, `object-fit:cover`), which is right for a card or a product shot and wrong inside an article: a small picture was blown up to 1200 wide and then cut off top and bottom. `.pt-post .page-media img` hands the sizing back to the browser and only shrinks a picture wider than the column. The rule is `.pt-post .page-head`'s own bottom border, the same way the hero and an archive head draw theirs, so it spans the page rather than the 1200px column. The article also drops the eyebrow, which only repeated the breadcrumb's last link.

**The header menu no longer carries Technology Partners** (client, 2026-09-16, `0013`). `/technology-partners` is untouched — it resolves, keeps its `.md` twin and its `sitemap.xml` entry, and stays in the footer menu; `_indexable()` never consulted a menu. Menus are rows, so the seed edit in `cli.py` only reaches a fresh database and `0013` carries it to one that already exists. Note for any future menu migration: a hand-applied `.sql` does not pass through `db.update()`, so `bump_epoch()` never fires and `get_menu()`'s process cache clears on its own `CACHE_TTL` (30s) instead — plus up to another minute of Cloudflare `s-maxage` on a public page.

**The partner strip is full colour and has a hover rule of its own.** `.pl-partner:not(.arch-body)` is the logo row a `post_list` draws inside a page (the home page and Technology Partners); `.arch-body.pl-partner` is the archive, which keeps named cards and never had a filter. The strip used to run at `filter:grayscale(1)` + `opacity:.7` with colour returning on hover, which is what the mock draws; the client asked for the marks in the colour their own files carry (2026-09-16, `requirements.md`), so both declarations are gone. The hover that replaced them is `transform:scale(1.14)` over `.3s cubic-bezier(.2,.7,.3,1)` — deliberately **not** the site's `translateY(-2px)`, because a logo sits on no card edge and a 2px rise on a bare mark reads as nothing. `transform-origin` is left at the centre so the mark grows in place and the grid never reflows, and `position:relative;z-index:1` raises the growing tile over its neighbours' edges for the duration. Measured at 390: the scaled tile's right edge lands at 381.8 against a 390 viewport, so it adds no horizontal overflow. **On a phone the strip re-flows to three across** (2026-09-18). The base floor is `minmax(130px,1fr)`, which at every phone width only ever fits **two** tracks — so fourteen partners became a 675px wall of marks half the screen wide each, the opposite of the quiet strip it is meant to be, and the client reported it. Under 700px the floor drops to **80px**, which is not a guess: it is the largest floor that still fits three tracks at 320, so the count holds steady across the phone range instead of flipping between two and three on a few pixels of viewport. The side padding drops 16px → 8px with it, because 16px of a 169px track is fine and 16px of an 85px one is a fifth of the space the mark has to read in. Measured:

| floor | 430 | 390 | 360 | 320 | strip height |
|---|---|---|---|---|---|
| 130 (was) | 2×7 | 2×7 | 2×7 | 2×7 | 675px |
| 100 | 3×5 | 3×5 | 2×7 | 2×7 | — |
| 90 | 3×5 | 3×5 | 3×5 | 2×7 | — |
| **80** | 4×4 | 3×5 | 3×5 | 3×5 | **523px** |

Nothing in that query applies at 760px and up, where the `pl-cols-*` count from `even_cols()` takes over — 1440 and 834 stay at 7×2 and 295px.

It is still a lift in kind — but it needs a **separate rule**, because a tile here is a `<div class="card">`, not an `<a>`: a partner has `has_pages=false`, so `p.path` is `None` and `_card.html`'s `box = act or not p.path` opens a `<div>`. `a.card:hover` cannot match it. For the same reason the selector had to be **added by hand to the `prefers-reduced-motion` block**, which stood only `a.card:hover` down; it sits later in the file at equal specificity, so it wins without `!important`.

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

**`contact_form` has two skins across three kinds**: `quote` and `career` both take `.cf-grey`, the soft grey panel from Careers; `contact` is the plain white card. The mock draws the Contact screen's quote form on a black card and the theme followed it (`.cf-dark`), but the client asked for the Careers panel there instead (2026-09-10, `requirements.md`), so those rules are gone — the base `.lead-form` inputs stay white on the grey, which is what makes the panel readable without a dark set of its own. `kind` still decides the routing and the two quote-only questions; it just no longer decides the colour. The heading is rendered **inside** the form, because in the design it belongs to the panel rather than sitting above it as a section title.

**A numeric `cards` icon is a counter, not an icon.** `card-icon num` drops the tinted tile for the design's mono blue number, and the deck tightens around it (`.cards:has(.card-icon.num)`).

**Favicons.** `static/favicon.svg` plus PNGs at 16/32/48/180/192/512, generated from the SVG with **Inkscape** — `inkscape --export-type=png --export-width=N --export-height=N --export-filename=static/favicon-N.png static/favicon.svg`, once per size — and linked from both `base.html` and `admin/base.html` (only svg/16/32/180 are linked; 48/192/512 are kept for a web manifest that does not exist yet). Recolouring the mark means editing the SVG and re-running the six. **Not ImageMagick**, which these were generated with until 2026-09-12: `convert` has no usable SVG delegate here and falls back to its own MSVG rasteriser, whose antialiasing turns the ring into a blob at 16-48px and quantises the result to a 256-colour palette. Inkscape renders each size natively in RGBA; compare before replacing the tool again.

### The sliding row

`static/site.js` is the public site's only first-party script, it is ~5 KB unminified, it is `defer`-loaded from
`base.html`, and it touches nothing but `.pl-rail` sections. It exists because the client asked for testimonials
that scroll on their own *and* that a visitor can drive — arrows and dots, which nothing in CSS can do (2026-09-16,
`requirements.md`).

**The row works without it, and that is the design.** `.pl-testimonial:not(.arch-body) .cards` is
`display:flex; overflow-x:auto; scroll-snap-type:x mandatory` — a native scroll container. The wheel, a trackpad and
a finger on a phone all move it on a page served with scripts blocked, and the snap settles it on a card. What the
script adds on top is the drift, the arrows, the dots and click-drag. `post_list.html` therefore renders `.rail-nav`
with **`hidden`**, and `site.js` is what removes it: no script, no buttons that do nothing.

**Nothing in it is a hard-coded number.** The step is the first card's measured `getBoundingClientRect().width` plus
the container's computed `columnGap`, because the card is `flex:0 0 min(340px, 100% - 68px)` and the gap is CSS — both move
with the viewport. The **dots are built by the script, not by Jinja**, and rebuilt on `resize`, because the count is
`ceil((scrollWidth − clientWidth) / step) + 1` and not the number of cards: at 1440 the row shows 3.22 cards, so six
testimonials have four stops, and a dot per card would have left the last two pointing at the same end position.

Measured in Firefox 140 headless, which is also what the numbers in the commit body are:

| viewport | card | step | peek | rail width | stops |
|---|---|---|---|---|---|
| 1440 | 340 | 360 | 800 | 1160 | 4 |
| 834 | 340 | 360 | 434 | 794 | 5 |
| 390 | 282 | 302 | 48.0 | 350 | 6 |
| 360 | 252 | 272 | 48.0 | 320 | — |
| 320 | 212 | 232 | 48.0 | 280 | — |

**It is the peek that is held constant, not the card** (2026-09-18). `100%` on a `flex-basis` resolves against the
rail's inner width, so `min(340px, 100% - 68px)` gives the card everything except a 20px gap and a 48px sliver, and
above about 420px the `340px` arm wins so no desktop width moves. The first version was `74vw`, which did the
opposite of what it was for: the card *and* its container both shrank with the viewport, so the affordance fell away
exactly where it was needed — measured 41.4px at 390, 33.6 at 360, **23.2 at 320**. It is now 48.0 at all three.
`100vw` is deliberately not used; it includes the scrollbar, and would put back the overflow the hero rule removes.

**The controls hide themselves when there is nothing to drive, and that took two fixes.** `buildDots()` sets
`nav.hidden = stops <= 1` and rebuilds on `resize`, because the same two published quotes *fit* 1440 (one stop, nav
hidden) and *overflow* 390 (two stops, nav shown) — a fixed decision would have been wrong at one of the two. The
second fix is one CSS line, `.rail-nav[hidden]{display:none}`, and it is load-bearing rather than tidy: the UA
sheet's `[hidden]{display:none}` is a bare attribute selector and loses on specificity to `.rail-nav{display:flex}`,
so **the `hidden` attribute did nothing at all** — the template's own `hidden` included, which quietly voided the
whole no-script promise. The first screenshot of the real home page is what caught it: two dead arrows under two
quotes that fit. `test_the_rail_controls_stay_hidden_without_the_script` asserts the rule is still there.

**`justify-content: safe center`, not `center`.** Two published quotes do not fill the row, and left-aligned under a
centred heading they read as a broken layout. Plain `center` fixes that and breaks the overflowing case instead: a
centred flex line puts its overflow on *both* sides, and a scroll container cannot scroll to a negative offset, so
the first card becomes permanently unreachable. `safe` is the keyword for exactly this. Measured in Firefox 140 with
six cards: first card's left edge 140 against a rail left edge of 140 at `scrollLeft` 0, and still 140 after
scrolling to the end and back.

**`scroll-snap-type: x mandatory` was verified to refuse nothing.** The worry is real — the last card's
`scroll-snap-align:start` position lies past `maxScroll`, so a mandatory snap could make the final stop unreachable
and strand the last dot. Every stop was asked for and read straight back at all three widths: each landed exactly
where asked and the last clamped to `maxScroll` (1440: asked 1080, landed 980). `at()` is
`Math.min(Math.round(scrollLeft / step), stops - 1)`, and that `min` is what makes the clamped end still report as
the last stop, so the dot marks and *Next* disables.

**The drift is off by default for anyone who asked for that.** Under `prefers-reduced-motion: reduce` the interval
is never created and `scrollTo` uses `behavior:'auto'`, but the nav still shows and the arrows still work — verified
in a Firefox profile with `ui.prefersReducedMotion=1`: nav shown, four dots, *Next* moved the row 0 → 360 with no
animation. It also pauses on `pointerenter`/`focusin`, and any arrow, dot or drag holds it off for ten seconds;
drifting out from under somebody mid-sentence is the thing that makes carousels hated.

Click-drag sets `scroll-snap-type:none` and `user-select:none` for the duration and restores both on `pointerup`,
and sits out `pointerType === 'touch'` entirely — the browser's own touch scrolling is better than anything this
would do. `admin/canvas.html` does not extend `base.html`, so **the editor canvas gets the row as a plain scroller**
with no arrows and no drift, which is deliberate: autoplay under somebody's caret is hostile.

### The testimonial card

`.pl-testimonial` shapes `_card.html` into a quote card, and the card rules sit outside the
`:not(.arch-body)` guard so the archive at `/testimonials` gets the same card in a plain grid.

The card is a **grid**, not a stack, because the photo has to sit beside the name *and* the job title:
`grid-template-areas:"stars stars" "quote quote" "avatar name" "avatar role"`. There is deliberately **no
`row-gap`** — a gap is applied between empty tracks as well as full ones, and every field on a testimonial is
optional, so a card with no stars would have carried a band of dead air for a row that renders nothing. The spacing
is margins on the elements, which cost nothing when the element is absent.

**`grid-template-rows:auto 1fr auto auto`, and the `1fr` is the whole point** (2026-09-18). Cards in the row are
flex items, so every one is as tall as the tallest — and the original `align-content:start` packed the rows to the
top and dumped the leftover height *under* the card. With the real home page's two quotes that was **65px of white
at 390 and 92px at 360**, over a third of the card, and it got worse as the screen narrowed because the taller quote
wrapped to more lines. Handing the slack to the quote's row instead pins the photo and name to the bottom edge,
which is what the reference designs draw; measured dead air is now **0px at every width**, and as a free side effect
the two cards' attributions line up with each other on desktop, where before they sat at different heights.

Where a quote's parts live: `posts.title` is the name, `posts.excerpt` is the quote, `posts.featured_media_id` is
the photo, and `meta.role` / `meta.company` / `meta.rating` are the three optional extras in the type's
`field_schema`. There is no `quote` field because `excerpt` already *is* one, and it is already what the card
macro, the archive and the `.md` twin read — `post_form.html` relabels the **Summary** box to *What they said* for
this one type instead, the same hard-coded-slug idiom `_card.html` uses for six other types.

Three things the CSS has to undo or lift:

- **`.pl .card-img` is hidden for every list**, so the avatar is switched back on explicitly as a 48px disc. With
  no photo the macro still emits `.card-img-empty`, whose diagonal-hatch placeholder reads as a broken image at that
  size, so it becomes a grey circle carrying **a person outline** (2026-09-18). No photo is the common case — an
  editor writes up a quote long before they have a portrait — so the fallback should look finished, not unfinished.
  It is a `background-image` holding an inline SVG data URI, not markup: the mark is decoration, so there is nothing
  to read out, `_card.html` needs no branch, and the archive at `/testimonials` gets it from the same rule. The one
  compromise is that the stroke colour (`#9aa5b4`) is written **inside** the data URI, where a `var()` cannot reach;
  it is a placeholder tone rather than a brand colour, so it does not follow the palette. If it ever has to, the
  upgrade is a `mask-image` on an `::after` with `background:var(--muted-dark-2)` — marked `ponytail:` in the file.
- **The stars are drawn server-side and clamped** — `[[m.get('rating')|int, 0]|max, 5]|min` — so a 9 or a −3 typed
  into a plain number box can only ever come out as five marks or none. `m.get('rating')` and not `m.rating`: the
  `int` filter raises `UndefinedError` on a missing key rather than returning 0, which is not what its name suggests.
- **`.card>*{position:relative;z-index:1}`** lifts the real children over the `::after` quote watermark. `::after`
  paints after its siblings, and at 390 the card is 289px wide, which is where a long job title ran under the mark.
  `z-index:-1` on the watermark is *not* the fix: `.card` opens no stacking context, so that drops it behind the
  card's own white background and loses it.

### The admin shell

`templates/admin/base.html` is a 248px black sidebar and a grey page canvas, not the old top nav. Three things about it are load-bearing:

- **It uses its own class names** (`.adm-shell`, `.adm-side`, `.adm-nav`, `#adm-toggle`), not `.site-header` / `.site-nav` / `.brand` / `#nav-toggle`. Those live in `site.css` and belong to the public header; restyling them here would repaint every public page, and two `#nav-toggle` checkboxes would fight over the same `:checked ~` rule.
- **One `{% block content %}`, wrapped conditionally.** Jinja refuses the same block name twice in a template even in branches that cannot both run, so the shell opens before the block and closes after it rather than the block appearing in both arms of the `if`.
- **`.admin-main:has(#post-form)` is `height:100vh`**, not `calc(100vh - 66px)`. The editor now owns a grid column rather than sitting under a top bar, so there is no header height to subtract.

**Every date in the admin is IST.** `db.ist()` is registered as a Jinja *filter* in `create_app()` (a date reads better piped than wrapped) and is used by the Posts, Leads, Dashboard and Activity tables; `db.ist_input()` is its twin for `<input type="datetime-local">`. It is a fixed `timezone(timedelta(hours=5, minutes=30))`, **not** `zoneinfo.ZoneInfo("Asia/Kolkata")`: India has never observed daylight saving, so the offset is exactly right for every date there will ever be, and it does not need tzdata, which the slim container image does not ship. 24-hour, because a log is read for precision.

This also closed a standing bug. `post_form.html`'s publish-date box posts a bare wall clock, `2026-09-11T14:00`, and `db.parse_dt()` reads a missing offset as UTC — so an editor in Mumbai typing 2 pm was storing 7.30 pm. The offset is stamped on in `admin_ui._as_ist()`, at that one input, and **not** in `parse_dt()`, which the JSON API shares and where no offset should still mean UTC. `_as_ist()` and `ist_input()` are a pair: the box shows IST and reads back IST, so a stored instant round-trips unchanged. Guarded by `test_the_publish_box_reads_as_ist` and `test_ist_is_five_and_a_half_hours_ahead`. Public output is untouched — `public.py`'s RSS `pubDate` is UTC with a literal `+0000`, which is correct.

**The Activity table pins three of its four columns** (`.aud-table` in `admin.css`) so the What column takes what is left; without that the row grows wider than its card and `.admin table { overflow: hidden }` clips the address off the end rather than wrapping it. A changed field is a `.aud-one` block — its name, then Was and Now in a two-column `.aud-ba` grid — **not** the three-column table this started as: a page's writing is prose, and prose in a 22%/39%/39% table is a column of single words. `<del>` and `<ins>` inside `.aud-ba` are tinted with the existing red and green tokens.

Two breakpoints, not one. At 1000px the pinned widths are released. **At 700px the row stops being a row**: `.aud-table` and its cells go `display:block` and stack into a card reading date, who, what, where, with the header row hidden. No arrangement of four columns keeps the sentence on a 390px screen, and a table that scrolls sideways hides the one column this screen exists to show — `/admin/leads` reaches for `.lead-card` over a table for the same reason.

**The nav icons are one inline sprite.** `admin/base.html` opens with a `<svg hidden>` of sixteen `<symbol id="i-…" viewBox="0 0 24 24">`; each row carries `<svg class="ic"><use href="#i-…"></use></svg>`. The symbols are bare `<path>`/`<rect>` elements — `fill`, `stroke`, `stroke-width` and the line joins are inherited from `.adm-nav .ic` in `admin.css`, which is also how `a.on .ic` recolours one to blue without touching the markup. The wrapper needs `hidden`: a `<svg>` holding only symbols still renders as a 300×150 box otherwise. The eight CONTENT rows are **`post_types` rows, not code**, so a Jinja `ICON` map turns a slug into a symbol name and `ICON.get(t.slug, 'dot')` gives anything an editor adds later the neutral `i-dot` rather than a broken reference. A new nav row needs a new `<symbol>` here — `i-audit` is the seventeenth, and **Activity** sits inside the `admin_user.role == 'admin'` block with Menus, Settings and Users.

**The sidebar's colours come from the dark tokens.** `--muted` (`#5b6675`) is a *light-background* token and lands near 3:1 on `--black`; the group labels, the counts and the resting icons use `--muted-dark-2` (`#7d8794`) instead. The active row is `--black-3` with `box-shadow:inset 3px 0 0 var(--blue)` and a blue icon, not a solid blue fill — fifteen rows of brand colour were louder than the page they lead to. `:focus-visible` on the nav, brand and footer links draws a `--blue-light` outline; there was none before.

**The footer's user block truncates, it does not wrap.** `.adm-me-t b` (the name) and its `span` (the email) are `white-space:nowrap` + `text-overflow:ellipsis`, with the full address in a `title`. That needs `min-width:0` on **both** `.adm-me` and `.adm-me-t`: a flex item defaults to `min-width:auto`, refuses to shrink below its content, and the ellipsis silently never appears. The name itself is the `display_name()` Jinja global (`__init__.py`) — `users.name` when set, otherwise the email's local part with `. _ -` turned to spaces and title-cased. `admin/users.html` calls the same global, so the table and the sidebar cannot disagree.

**`users.name` is written once, at invite time**, by the *Name* field on the Users screen — there is no rename screen and no `POST /admin/users/name`. So an account made by `flask create-admin` (which passes `name=""`) shows the derived name for good, which is the intended outcome rather than a gap: the derivation is right for a `first.last@` address, and anyone who needs a different one is invited with it. Changing an existing name means a `users` row update in Studio.

The invite form is `autocomplete="off"` and its *Temporary password* is `autocomplete="new-password"`: an email field beside a password field is a login form to a password manager, which was filling the signed-in admin's own saved address and password into the invite, ready to create a duplicate account. **`admin/account.html` does the opposite on purpose** — `current-password` on the first field, `new-password` on the other two — because on a real change-password form a manager *should* fill the old one and *should* offer to save the new one. The invite form's blanket `off` was a false positive, not a policy.

**Passwords: `/admin/account` for yourself, `POST /admin/users/<pk>/password` for somebody else.** Both end in `auth.set_password()`, which is one call to `sb().auth.admin.update_user_by_id(id, {"password": …})` and nothing more — proving the old password and re-issuing a session are the caller's business, because the admin resetting a locked-out editor needs neither.

- **`/admin/account`** (`@ui_required()` — *no* role argument, so every signed-in user; it hangs off the sidebar footer rather than the nav because Users and Settings are admin-only and an editor has to be able to reach this). Two calls to `login()` bracket the change, and both are load-bearing. The first **proves the current password by signing in with it** rather than trusting the session cookie: a session says who logged in once, not who is at the keyboard now, and `login()` already is that check. The second, after the change, **replaces the session's tokens** — GoTrue can revoke the refresh token minted under the old password, and without fresh ones `_session_token()` (`auth.py:36-56`) signs the user out on the next refresh, one click after they changed it.
- **`POST /admin/users/<pk>/password`** (`@ui_required("admin")`) takes one field, like the invite form, and refuses your own row: `/admin/account` is where you change yours and it asks for the current one, so a self-reset here would walk around that check for the one account whose session is already open. No `login()` — the admin does not become that user. It sits inside the same `{% if u.id != admin_user.id %}` as *Remove*, in a native `<details>`, so it is hidden on your own row for free and costs no JavaScript.
- `_password_errors(new, confirm=None)` is the shared validator: eight characters minimum (matching the invite form's `minlength`; GoTrue's own floor is six), and a mismatch check that `confirm=None` skips for the admin's one-field form.
- **Neither path ends that user's other sessions** — GoTrue's admin API has no sign-out-everywhere. Marked `# ponytail:` on `set_password()`.

**The admin does not exist outside the office.** `ADMIN_NETWORKS` is a CIDR list, and when it is non-empty a `before_request` on **both** admin blueprints — `admin_ui` (`/admin`) and `admin_api` (`/api/admin/v1`) — answers `404` to any request whose resolved client address is outside it (client, 2026-09-15: staff reach the admin from the office premises only). The public site is untouched: it is a different blueprint and never consulted.

Four things about the shape:

- **It tests `client_ip()`, not `remote_addr`.** Behind Traefik every request has the same `remote_addr`, so a `remote_addr` test would admit everybody or nobody. That makes this guard exactly as good as `TRUSTED_PROXIES` — see the lockout below.
- **A blueprint `before_request`, not a check inside `ui_required()`.** The login form is the one route that takes a password and requires no session, so guarding only the authenticated routes would leave the door that matters open. It also covers every route added later without anyone remembering to.
- **404, not 403.** `/admin` is a well-known path; a refusal saying "not allowed" also says "something is here, keep trying", which from the public internet is an invitation to return with a password list. The API's own `HTTPException` handler turns it into `{"error": "not found"}`, the same answer a missing row gets.
- **Empty means unrestricted**, which is what development and any deploy that has not set it want. This is a `.split(",")` on `""` → `()`, not the `or`-a-default that `TRUSTED_PROXIES` uses, because here "set nothing" genuinely means "restrict nothing".

**It is a layer, not the lock.** The password, the roles and the throttle are all still there and still do their jobs; this only decides who may knock. It also does nothing about somebody already inside the building, which is what the roles are for.

**The lockout to know about before it happens.** If `TRUSTED_PROXIES` stops matching the real proxy — Traefik recreated onto a different address, a tunnel added whose bridge is not in the list — then `client_ip()` returns the *proxy's* address, that address is not in `ADMIN_NETWORKS`, and **every editor is locked out with a 404 and nothing on screen to say why**. Verified deliberately: with `TRUSTED_PROXIES=10.9.9.0/24` and a request through a proxy at `127.0.0.1`, `/admin/login` answers 404 to an office address. The refusal logs both addresses (`admin refused: <resolved> is outside ADMIN_NETWORKS (connection from <peer>)`), so the container log names which of the two went wrong. **The recovery is to clear `ADMIN_NETWORKS` in Dokploy and redeploy**, which restores the admin immediately; fix `TRUSTED_PROXIES`, then set it again.

**Cloudflare should also be told**, once the tunnel is live: a WAF or ingress rule refusing `/admin*` at the edge means the flood never reaches the origin at all. The same complement-not-replacement argument as the login rate limit below — the app-side guard is the one that is in this repo and tested, so it stays either way.

**Failed passwords are counted, and the counter is a sqlite file on tmpfs** (`iopstor/throttle.py`). Three endpoints verify a password and two of them are anonymous, so all three are behind it:

| Door | Key | Refusal |
|---|---|---|
| `POST /admin/login` (`admin_ui.py`) | `ip:<addr>` | the login card re-rendered with a red message naming the wait, `429` + `Retry-After` |
| `POST /api/admin/v1/auth/login` (`admin_api.py`) | `ip:<addr>` | `{"error": "too many attempts"}`, `429` + `Retry-After` |
| `POST /admin/account` (`admin_ui.py`) | `user:<id>` | the message in the page's `errors` list, `429` |

The third is the one that is easy to miss: it re-checks the current password, so a stolen session cookie was an unlimited guessing oracle. It keys on the **user id** rather than the address, because the session already says which account is guessing.

**Keys are never the email typed in.** An email-keyed lock lets anyone shut a named person out of their own site by guessing their password ten times; the IP-keyed version can be evaded by rotating addresses but cannot be turned into a weapon. A correct password calls `clear()`, so two typos and then the right one cost nothing.

**The counter fails open.** Every function swallows `sqlite3.Error` and allows the attempt. A counter that cannot open its file must not be able to lock the owner out of their own site — a throttle that is briefly not throttling is a smaller problem than an admin that cannot log in. It is also skipped entirely under `TESTING`, because the live suite posts to the login route several times inside one test.

**Why `sqlite3` on `/dev/shm`, given the "no SQLite" rule.** The container runs ~30 workers in separate address spaces, so a module-level dict would be thirty independent counters and thirty times the ceiling. `/dev/shm` is tmpfs: RAM, shared by every process in the container, empty again after a redeploy — which is the lifetime this wants. sqlite supplies the cross-process locking, the expiry and an unbounded key space for a fraction of the code a hand-packed `mmap` table needs. `CREATE TABLE IF NOT EXISTS` runs on every connect on purpose: a fresh container has an empty `/dev/shm`, so the file builds itself the first time anyone fails a login. `CLAUDE.md`'s hard rule now carries the matching carve-out. **`# ponytail:` it is per container** — scale to two replicas and each gets its own counter, doubling the effective limit; Redis is the upgrade path.

**The client address is a forwarding header from a peer we named, never from anybody.** `throttle.client_ip()` is the one place it is decided, and every consumer routes through it: both login throttles (`admin_ui.py:94`, `admin_api.py:80`), `post_sessions.ip` (`admin_ui.py:507`) and every audit row (`db.py:110`).

There are **two ways into this app and they put the address in different places**. Through the Cloudflare tunnel the connection is cloudflared and the visitor is in `CF-Connecting-IP`, which the edge sets and strips off anything the client sent. On the LAN it is **Dokploy's own Traefik** — a domain attached in the Dokploy UI puts it in front of this container whether or not anyone configured it — and the visitor is the last `X-Forwarded-For` entry. `remote_addr` is the answer only when nothing is in front at all, which here means development. So the order is: if — and only if — the peer is inside `TRUSTED_PROXIES`, take the first of `CF-Connecting-IP`, `X-Forwarded-For`, `X-Real-IP` that has a value; otherwise `remote_addr`; and `"-"` last, because the key is built with an f-string and a `None` would put every such request in one bucket named `"None"`.

**The gate is the point, not the header list.** A forwarding header is a claim by whoever opened the connection, and it is only evidence when that was a proxy we deployed. Trusting `CF-Connecting-IP` unconditionally — what this did until a LAN port existed — meant any client on a non-Cloudflare path could set it by hand, rotate it freely past `LOGIN_MAX_FAILURES` for unlimited password guesses, and write a chosen string into `audit_log.ip`, which `audit.html` renders to an admin as the authoritative *From* column with nothing marking it unverified.

**`X-Forwarded-For` is read from the right.** A proxy *appends* the peer it saw, so with one trusted hop the last entry is the real connection and everything to its left came from the client. `rsplit(",", 1)[-1]` is what `ProxyFix(x_for=1)` does; the middleware itself still stays out, for the reasons in `design.md` (nothing reads `request.scheme`/`host`, every `redirect()` is relative, and the hop count it wants is a guess).

`TRUSTED_PROXIES` is a comma-separated CIDR list, parsed in `config.py` **at import** so a typo refuses to boot the way a missing `SECRET_KEY` does rather than failing quietly on every login. It is read with `or`, not a `get()` default: compose passes `${TRUSTED_PROXIES:-}` and an empty string has to mean *unset* — read as "trust nothing" it would drop `CF-Connecting-IP` and put every tunnel visitor in cloudflared's bucket. Unset it is `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,::1/128,fc00::/7`, which covers cloudflared, the LAN hop and a dev machine with no configuration at all. **`# ponytail:`** those ranges also contain the LAN *client*, so an insider who chooses to send a header is believed — naming the one subnet the proxy sits on closes it with no code change; and the rightmost-entry rule assumes one hop, so a second trusted proxy in a row would need counting back as many entries as there are hops.

**Measured, 2026-09-15**, against the real WSGI stack on a socket rather than a test request context: from a trusted peer, `CF-Connecting-IP: 9.9.9.9` → `9.9.9.9`; `X-Forwarded-For: 1.2.3.4, 203.0.113.9` → `203.0.113.9` (the spoofed left entry loses); `X-Real-IP` → same; both headers → the Cloudflare one wins. With `TRUSTED_PROXIES=172.18.0.0/16` so the peer is no longer ours, the same two spoofs → `127.0.0.1`, the peer's own address. `TRUSTED_PROXIES=not-a-network` → `ValueError` at import.

**Measured on the deployment, 2026-09-15.** `docker network inspect dokploy-network` puts `dokploy-traefik` at **`10.0.1.7`** on a **`10.0.1.0/24`** overlay, beside `iopstor-backend-nq5xy9-app-1` at `10.0.1.32` and Supabase's Kong at `10.0.1.8`. So the address that started this — every audit row reading `10.0.1.7` — was Traefik, and `10.0.1.0/24` is the value `TRUSTED_PROXIES` should hold: it excludes the office LAN, so no client there can forge a header, and unlike pinning `10.0.1.7/32` it survives a container recreate moving Traefik's address (which would otherwise silently stop `X-Forwarded-For` being read and put every visitor back in one bucket). The container names show plain `docker compose`, not a swarm stack, so the compose `default` network is an ordinary bridge and cloudflared's subnet joins the list when the tunnel goes on.

**`/admin/audit` opens with a shut `<details>` saying where the site thinks you are connecting from** — the value that will be written to the *From* column, the address that actually opened the connection, whether that peer is one of ours, and the raw forwarding headers it sent. `throttle.connection()` builds it, so the screen does not have to know how any of it is worked out, and it is a GET on a route that is already `@ui_required("admin")`: nothing new is exposed, nothing is audited, and `test_every_route_that_can_change_something_is_accounted_for` is untouched. It exists because "is the log recording real visitors" was otherwise a question nobody could answer without a deploy and a guess — and with two ingresses the answer differs by which one you came in on.

Limits are `LOGIN_MAX_FAILURES` (10) and `LOGIN_WINDOW` (900s) in `config.py`, env-readable because a rate limit is exactly the number you tune while under attack — **and they are only tunable because `docker-compose.yml` passes them through**. Compose's `environment:` is an explicit list, so a key `config.py` reads but the `x-app-env` anchor omits is simply absent in the container and the setting quietly takes its default, however plainly the Dokploy screen shows a value. That is how `ADMIN_NETWORKS`, `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW` and `THROTTLE_DB` shipped: set in Dokploy, never received, no log line, no symptom — and in `ADMIN_NETWORKS`'s case the default is *no restriction*, so the office-only admin lock read as off in production. `test_every_setting_the_app_reads_is_passed_into_the_container` walks `config.py` against that anchor and fails until a new key is in both. Cloudflare can also rate-limit `/admin/login` at the edge, which is strictly better where it applies — the flood never reaches the origin — and the two are complements, not alternatives.

**The login screen is a *column* flex, and that is load-bearing.** `.admin-anon` (the class `base.html` puts on `<main>` when nobody is signed in) sets `flex-direction:column` and caps `>*` at `max-width:420px`. The default `row` was a bug: `base.html` renders `get_flashed_messages()` as a **sibling** of the login card, so the moment anything flashed there were two children each asking for `width:100%`, and a row flex split the viewport down the middle — the message became a full-height bar on the left and the card slid right. Any future second child on that screen would have done the same thing, which is why the fix is on the container rather than on the message.

Relatedly, **`login_page()` passes `error=` to the template instead of calling `flash()`**. A refused login is not a success, and `.flash` is the green one; it now renders as `.error` inside the card, above the fields, where the thing it is about lives. Nothing flashes on the anon screen any more.

**`.adm-shell` needs `grid-template-rows:auto 1fr` under 1000px.** Stacked, both rows are auto-sized, and a grid's default `align-content:stretch` grows them to fill `min-height:100vh` — which on a short page (`/admin/account` is the one that exposed it) is a slab of black under the brand bar. Pinning the aside to `auto` and giving `main` the rest fixes it without the aside losing its full height on the desktop layout, where the rule does not apply.

**The settings tabs are CSS, and that is load-bearing.** `settings()` saves `{k: request.form.get(k, "") for k in SETTING_KEYS}`, so **any key missing from the submitted form is blanked**. Rendering only the visible tab would wipe the other three on every save. So all four panes stay in the DOM and a radio + `:checked` sibling rule shows one. The pairing uses explicit ordinal classes (`.t1`/`.p1`), not `:nth-of-type` — the form's hidden CSRF field is an `<input>` too, so type counting put every radio one place out.

The Payments tab shows the provider **read-only**. It comes from the `PAYMENT_PROVIDER` env var through `payments.GATEWAYS`; making it a setting would give the same switch two sources of truth. `currency` and `notify_email` are real settings keys.

**`/admin/menus`** is the screen `NON-TECHNICAL.md` §9 has always promised. It posts flat rows — label, URL, and a level `<select>` — which `menu_items()` rebuilds into the nested `[{label, url, children}]` shape `get_menu()` returns. The level is a **`<select>`, not a checkbox**: an unchecked box posts nothing, so the three `getlist()`s would come back different lengths and every row after the first unticked one would shift a place. `db.set_menu()` is the write side, so every query still lives in `db.py`. SortableJS is loaded by that template alone rather than by `admin/base.html` — it is 45 KB and this is the only screen outside the canvas that drags anything.

**Leads have three states** (`new`, `in_progress`, `handled`) from a whitelist, because `leads.status` is a plain varchar and a toggle would store whatever was posted. No migration.

**Media alt text is only ever edited after upload** (`POST /admin/media/<id>/alt`). It used to be settable only at upload time, so a picture uploaded without it could never be described; since the upload form takes a whole batch, the alt box has come off it entirely — one box above five files could only ever be right about one of them, which is the same reason the editor's inline picker never asked. Image dimensions and a "used on" list are **not** implemented: the first needs two new columns, the second a scan of every post's blocks.

**The media screen works on several files at once, and does it without JavaScript.** `POST /admin/media` reads `request.files.getlist("file")` and tries each file on its own, so one rejected type leaves the rest uploaded and comes back as `Uploaded 3 files. Not added: notes.txt (file type not allowed).` — failing the batch would punish the files that were fine. Deletion is **one route for both buttons**: `POST /admin/media/delete` takes `ids` as a repeated form field, which the grid's tick boxes and the detail panel's single hidden input both post; there is no `/media/<id>/delete` any more. Ids that are not numbers are dropped before the query rather than refused, since the only way to send one is to have edited the form. It stays `@ui_required()` (editor), matching what the single delete always was — this changed how many files one click removes, not who may remove them.

**The selection is a `<form>` of checkboxes, and it works before `admin.js` does.** The tile had to stop being an `<a>` (a checkbox inside an anchor is invalid and the anchor eats the click): it is a `div.m-tile` holding `input.m-pick` and `a.m-open`. With no JavaScript at all a plain click is still a link to `?pick=`, and **the server renders that file's box already ticked** — so one click selects one file, and the panel and the selection are the same act. The box is the chip: no `<label>` wraps it, because a label forwards a second click to its input and every modifier click would then arrive twice and toggle back to where it started. Both visual states are CSS — `.m-tile.on, .m-tile:has(.m-pick:checked)` is **one declaration on purpose** (selected and "the one the panel is showing" are the same thing), and `form:has(.m-pick:checked) .m-bulk button` is what turns the Delete button from grey to red. `:has()` was already load-bearing in `admin.css` (`.role-card`, `.admin-main:has(#post-form)`).

**`initMediaBulk()`** (the sixth entry in `admin.js`'s `DOMContentLoaded` list, and the first thing in that file to run outside the post form) adds only what CSS cannot: **ctrl/cmd-click** to add one file to the selection and **shift-click** to take the run since the last one, from anywhere on the tile rather than only the 17px box. Both call `preventDefault()` — without it the browser navigates away from the selection just made, and ctrl-click opens the tile in a new tab. A plain click is deliberately *not* intercepted; it stays the link, which is what keeps the no-JS path and the alt-text panel reachable. The anchor for a shift run is seeded from whichever box the server rendered checked. Measured in a real Firefox against the real file, by dispatching modifier clicks at the live page: 8/8, including that a plain click is still followed and that ctrl-clicking the box itself does not double-toggle. A "select all" box and a live selected-count are still not there.

**`@ui.errorhandler(413)`.** `MAX_CONTENT_LENGTH` is 20 MB for the *whole request*, so a batch reaches it far more easily than one file did, and Werkzeug's raw 413 page gives an editor no way back. The handler flashes a sentence (the number read from the config, not typed — the template's hint used to say 25 MB) and redirects. **It returns the error untouched for any endpoint but `admin_ui.media`**: `media_upload` answers `admin.js` with JSON, and a 302 there arrives as a 405 HTML body that the fetch's `r.json()` throws on. Measured: the blueprint handler does fire and `request.endpoint` is populated inside it, because URL matching runs before body parsing.

`nav_counts` (not `counts`) carries the sidebar's numbers, because the dashboard view passes its own `counts` and a view's context shadows a context processor's — the leads pill would have been empty on exactly that one page.

`static/admin.js` is the single exception, loaded only by `templates/admin/base.html`. It is plain ES5-ish browser JavaScript — no framework, no bundler, and nothing fetched at runtime: the one third-party file, `static/vendor/sortable.min.js` (SortableJS 1.15.6, MIT, 45 KB), is **vendored, not CDN-loaded**, because the CMS runs on a LAN and an editor without internet must still be able to drag a section. It is **progressive enhancement only**: every part is a no-op when its hook is missing, and the plain form underneath still saves with JavaScript disabled. Five parts (the fifth, `initMediaBulk()`, is the only one that is not about the post form — it is documented with the media screen above):

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

**The stress-test panel (`/admin/stress`, `admin/stress.html`, `iopstor/stress.py`) is fenced to one person, not to a role.** It is an internal load-and-abuse simulator: enter a number of *visitors* and a number of *attackers*, a duration and a target — this instance, or another base URL so development can point traffic at production — press **Run**, and watch throughput, latency (avg / p95 / slowest), a status-code histogram, the 429 count and the no-answer count update live. It exists nowhere for anyone but the email in `STRESS_OWNER` (`admin_ui.py`): the nav row is behind `{% if is_owner %}` (a boolean the context processor sets), and the routes are wrapped in `owner_only`, which layers on `ui_required("admin")` and then `abort(404)`s anyone else — a 404, not a 403, the same "a stranger learns nothing" the office gate uses. It is the **first identity-level gate in the codebase**; every other is network (`ADMIN_NETWORKS`) or role. A single email rather than a new role because it is one operator's tool that can aim real traffic at any host, and because a `VARCHAR(20)` role with no `CHECK` was not worth widening for one person; change the constant to hand it over.

- **Why the load fans out across processes, not just threads.** `start()` validates and clamps, registers the run and spawns one daemon coordinator thread, then returns at once — the POST never blocks a worker for the run. Measured: one CPython process driving `urllib` in threads *loses* throughput as threads rise (GIL + per-request overhead), so the coordinator splits the load across `_nprocs()` generators — a single in-process thread below `PER_PROC` (≈250, keeping small interactive runs spawn-free), otherwise `multiprocessing` processes, one GIL each. `_nprocs()` sizes them off **`os.process_cpu_count()`** (Python 3.13, honours the container's CPU quota — `os.cpu_count()` would report the host's cores and oversubscribe a capped container), capped at `MAX_PROCS`. `_plan()` sets the shape and, crucially, **caps real concurrency at `nprocs × PER_PROC`** — one OS thread per worker, so an uncapped "10000 visitors" would try to *create* ten thousand threads (many seconds, a thrashed box, and a run that then takes ages to tear them down — for no throughput past the cap, measured); over the cap the entered numbers are scaled down proportionally and the run records both `visitors`/`attackers` (requested) and `visitors_run`/`attackers_run` (driven), which the panel shows. Each generator (`_generate()`, module-level so it is picklable) runs its share of `_worker` threads and writes its own row in the `parts` table every 0.5s; the coordinator `_merge_parts()` sums them into the one run row the poll reads. Measured on an 8-core box against a target that scales: one process ~900 req/s and *falling* with more threads; the multi-process path ~1200 req/s and *rising* with more load — the point of the rewrite is that it scales the right way, not that it reaches any particular number. Stdlib only — `urllib.request`, `threading`, `multiprocessing`, `sqlite3` — because `pip install` is denied and no load tool (`ab`, `wrk`, `hey`) is in the image.
- **Why `spawn`, not fork.** `multiprocessing.get_context("spawn")` starts a fresh interpreter that imports `iopstor.stress` (which pulls in `iopstor/__init__` but creates no app — no top-level side effects) rather than copying a gunicorn worker's forked state, sockets and locks. The children are `daemon=True`, so they die with the worker that started them and never orphan; each also self-stops at its own deadline. A worker blocked in a request cannot be interrupted, so once the deadline passes (or Stop is pressed) the coordinator waits only `GRACE` (2s) for a clean drain, then **`terminate()`s the child processes** — SIGTERM takes their threads with it, so a heavy self-test ends within a couple of seconds of its duration instead of dragging on a whole `REQ_TIMEOUT` per stuck request (measured: an 8000→2000 self-test finished in ~6s for a 4s run, was ~18s before the cap and the terminate). The load generator is separate from the 30 workers that *serve* — the Run lands on one worker, which spawns the children; the other 29 keep serving and can still answer the progress poll because the run state is shared (below).
- **Why progress lives in a sqlite file on `/dev/shm`.** The ~30 gunicorn workers *and* the generator processes are all separate address spaces, so a run started in one and polled from another (`GET /admin/stress/progress/<id>`, a GET, so it adds nothing to the audit accounting) and written by many children at once need shared storage. This is throttle.py's trick exactly: tmpfs, wiped on redeploy, which is a load run's whole lifetime. `PRAGMA journal_mode=WAL` so the many child writers do not block the coordinator's read. Two tables: `runs` (the aggregate the poll reads) and `parts` (one row per generator). Nothing here is application data. `STRESS_DB` is a module constant, **not** an env key, specifically so it stays out of `docker-compose.yml`'s `x-app-env` and the container-env test.
- **Why the attackers are non-destructive, and why that is not audited.** They knock on missing paths, fetch missing media keys, guess warranty serials (a read: the block's own ceiling is that a guessed serial leaks a name/email — this probes that), and POST to `/api/v1/leads` **with the honeypot `website` field filled**, so `public.py` accepts and drops it — the full POST path runs but no `leads` row and no audit row lands. Login brute-force is deliberately left out: it would write `login_failed`/`login_blocked` rows into the *target's* Activity and lock out the source IP (the throttle keys on `client_ip()`), and the client requirement is that the log stays clean. Because a run changes no row of ours, `stress_run` and `stress_stop` are entered in `AUDITED` (tests/test_offline.py) as **deliberately not recorded**, the same call preview and canvas make.
- **Ceilings** (`# ponytail:` in `stress.py`): processes × threads lifts throughput by roughly the core count, not without bound — it will not reach 10k/s on a modest box, and the *target* is usually the wall first (a real page render makes 8–11 Supabase calls against a `PGRST_DB_POOL` of 10, so the live site 504s in the low hundreds/s; a clean high number needs a no-DB endpoint like `/healthz`). Real concurrency is capped at `nprocs × PER_PROC` (`_plan()`), so the entered `MAX_VISITORS` (10000) / `MAX_ATTACKERS` (1000) are a *requested* ceiling that is scaled down to what the machine can drive — the panel shows the driven number. The coordinator and children live in whichever worker took the request, so a recycled worker freezes the run at its last flush; the only guard on the target URL is the scheme (no SSRF allow-list — owner-only behind the office-only admin, and dev→prod on the LAN is the point); `MAX_SECONDS` is 300, `MAX_PROCS` 16; and nothing prevents two runs at once (two Run clicks on two workers), which for one owner is their own doubled load. A self-test's generators share the box with the workers they hit, so those figures read heavier than a dev→prod run where the driver has its own cores.

Guarded by `test_run_load_hits_a_real_server_and_the_honeypot_leaves_no_row`, `test_a_multiprocess_run_completes`, `test_nprocs_and_split` and `test_merge_parts_sums_children` (§13).

### 12.1 The document editor

The post form (`templates/admin/post_form.html`) is one screen. A bar across the top: back link, the *saved* status pill, *Edit* / *Preview*, the device widths (Preview only), *View live*, **Save**. Under it, the page column — a borderless title input, the document toolbar and `iframe#canvas` filling whatever height is left — and, on the right, the settings panel: *Publish*, *Web address*, *Summary*, *Featured image*, *Organise* (parent, and a chip picker per taxonomy — the whole section is dropped for a type with neither), the type's *Details* (`field_schema`), then *Search engine overrides* and *Advanced* as collapsed `<details>`. `.admin-main:has(#post-form)` is sized to the viewport and the two columns scroll on their own, so the toolbar never scrolls away; under 1000px the panel stacks beneath the page.

**`menu_order` is not in the form.** A number that decides list order was the one setting no editor could explain, and every list already falls back to newest first. The column stays, and it is still the *primary* sort for `post_list` (`blocks.py`), archives, and the child lists in `render_post()` / the preview — all of which now carry `.order("menu_order").order("published_at", desc=True)`, so a hand-set order still wins and everything else is newest first. It stays writable through `PATCH /posts/<id>` and `cli.py`'s seed, which is what keeps the seeded Services in their intended order; `_form_body()` deliberately omits the key so a browser save leaves whatever is there alone rather than resetting it to `0`.

**Two editors on one page.** The form carries a hidden `updated_at` — the row as it was drawn — and `_save()` hands it to `db.update(..., if_unchanged=…)`, which makes it a filter on the UPDATE (§4). If somebody else saved in between, the write matches no row, nothing is overwritten and nothing is logged. The editor gets a `.notice-amber` banner above the page saying so in a sentence, **not** a row in the field-error list: that list prints the key beside the message and would have put a bare `_` on a non-technical screen. `_rejected()` is the shared re-render both refusals use — it rebuilds the form from `request.form`, `blocks_text` included, so **a refused save loses nothing on screen** — and the conflict branch does one narrow re-read so the hidden field goes back *fresh*. That is deliberate: **warned once, then let through.** Refusing a second time would strand an editor with nowhere to put the work, and there is no draft model to escape into yet. The conflict returns *before* `db.set_post_terms()`, or a refused save would still rewrite the categories. Ceilings: a third save landing between `edit_post`'s read and the UPDATE re-renders an already-stale token, costing one more click; `_save()` only calls `update()` `if changes:`, so a terms-only edit from a stale form is unguarded; and only `posts` is covered — `settings` and `menus` write through `set_settings()`/`set_menu()` and have the same exposure.

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

**A page is a document, not a stack.** Prose lives in `rich_text` blocks; the other nineteen types
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


**Prose is edited by Quill, on the blocks that can hold it without losing anything.** `quill@2.0.3`
is vendored as its published UMD (`dist/quill.js`, 209,274 bytes → `window.Quill`) with
`quill.core.css`, **not** the snow theme: the toolbar is this repo's own, in the parent document.
Both load **inside the canvas iframe** — the `sortable.min.js` precedent, and the opposite of
`supabase.js`, because Quill binds to elements in that document while the socket belongs to the page.
`admin.js` reaches the constructor through `FRAME.contentWindow.Quill`.

Quill is here because word-by-word co-editing needs each paragraph to be a CRDT *text* type, and a
`Y.Text` needs a real editor binding — a plain HTML string is last-writer-wins however it is
transported. **Nothing in this section is collaborative yet**; it is the surface the next PR binds to.

**The gate is per block and measured, not "does it contain a table".** Quill silently drops what it
has no blot for. On this site's own content that was **7 of 24** `rich_text` blocks: `<dl>` on NAS
and Contact Us, `<div>`/`<span>` on About Us, `<table>` on NAS and Testing — and the Home page, which
loses six **classes** and not one tag, so a tag-based check waves it through and the first save strips
the page's styling. **Two of those seven are block types now** — `points` and `definitions`, §6 — which
is the only real cure: the answer to a section Quill cannot hold is usually that it was never prose.
Five refusals are left and all five are deliberate (Contact Us, NAS's spec panel, the About Us founders
grid, two junk tables on a page called *Testing*). So `quillKeeps()` pastes the block into a throwaway Quill in the canvas document,
reads `semantic()` back, and refuses if any tag or class went missing. It is a **no-loss** test rather
than equality: Quill wrapping a bare text node in `<p>` is fine, losing `class="eyebrow"` is not.
`<b>`/`<strong>` and `<i>`/`<em>` are aliased, because `_html_md()` renders them identically
(`test_quills_normalised_tags_make_no_difference_to_the_published_output`) and refusing a block over
that would be refusing it for nothing. A refused block keeps the original `contenteditable`, gets
`data-legacy` on its **section** — never inside a `[data-f]`, which is copied into `MODEL` and
published — and shows a note on hover.

**What a Quill field stores is `getSemanticHTML()` with the `&nbsp;` undone, and both halves are
load-bearing.** `root.innerHTML` always wraps lists in `<ol>` with `<li data-list="bullet">` plus
injected `<span class="ql-ui">`; the public page loads no Quill CSS, so storing it would render every
bulleted list on www.iopstor.com as a numbered one. And `getSemanticHTML()` runs
`replaceAll(" ", "&nbsp;")` over **every** text leaf — read out of the vendored build, not the docs —
so without the undo every space arrives in `posts.blocks` as an entity, and `_html_md()`'s `unescape()`
puts U+00A0 through the `.md` twins and `llms-full.txt` (`test_a_nbsp_from_quill_would_poison_the_markdown_twin`
shows exactly that). The two halves are one expression so they cannot drift into separate functions.

**The toolbar speaks to whichever engine owns the caret.** Half a page can be on each at once, so
every command is `if (!qfmt(...)) exec(...)`: `qfmt()` returns `false` when the caret is not in a Quill
field. `syncBar()` reads `q.getFormat()` there instead of `queryCommandState`. Five controls are
switched **off** in a Quill field rather than inserting something the next keystroke would drop —
picture, table, embed, divider and the `rem` size dropdown — which is the same rule the gate applies,
enforced at insert time: those are precisely the markup Quill has no blot for. Sections that need a
table keep the original editor and keep the buttons. The `/` inserter is hooked from Quill's
`text-change` instead of `bindSlash()`'s `keyup`, because Quill owns the keyboard.

**The page saves itself, and the button publishes.** `initAutosave()` (`admin.js`) writes the whole
document to `POST /admin/posts/<id>/draft` 1.5 s after any change, and the big button copies that draft
into `posts.blocks` — the only moment anything a visitor can see moves. Five things about it are
deliberate:

- **It hangs off `markDirty()`**, the single funnel all thirteen mutation sites already reach, rather
  than off thirteen new calls. `nudgeSave` is a no-op reassigned by `initAutosave()`, the same
  late-binding shape `syncBar()` and `paintPeers()` use, because `markDirty()` can run before there is
  anywhere to save to — and on `/posts/new` there is no row yet, so autosave stays off until the post
  has been created once.
- **It serialises `prune(MODEL)`**, the serialiser the form *submit* uses, not the shallower
  `MODEL.filter(written)` that Preview sends. The draft has to be the same bytes Publish would store,
  or publishing would change the page by itself.
- **The button says `Publish` only when the page's status is `published`**, and `Save` otherwise —
  pressing it on a Draft-status page publishes nothing to anybody. It is server-rendered from
  `p.status` and relabelled by a `change` listener on the status `<select>`, so it does not start
  lying the moment somebody flips the dropdown. The route and the server code are identical either
  way; only the word changes.
- **`.ed-saved` is new UI, not a rename.** Nothing rendered saved-or-unsaved state before this —
  `dirty` had exactly two consumers, the submit reset and the `beforeunload` guard — and with no Save
  to press, the absence would read as "nothing is happening". It ages itself (*Saved just now* →
  *Saved 3 minutes ago*) on a 30 s tick, and hides under the same `max-width:700px` rule as the
  presence roster, because `.ed-bar` never wraps.
- **A successful autosave clears `dirty`**, so the leave-this-page warning now fires only for work
  that genuinely is not on the server — a new post, or the gap between a keystroke and its save.

**Sessions: what the log says now that Save is gone.** Every autosave also carries `was` (the document
as this editor found it) and `now`, which `_record_session()` stores on `post_sessions`; fifteen
minutes after their last change — or on `pagehide`, via `sendBeacon` with `close=1` — that becomes one
`audit_log` row with `action="edit"`, attributed to them. The browser is the only place that can know
which blocks *this* person touched, which is why both halves come from the client rather than being
diffed on the server. Today the editor is single-player so `now` is simply the current document; once
the document is shared this has to become *`was` with only my touched blocks updated*, or one editor's
entry claims everybody's work. `# ponytail:` in `initAutosave()` says so.

There is **no scheduler** — no cron, thirty stateless workers — so the idle timer and the beacon are
optimisations and the real backstop is `db.flush_sessions()` being called by whoever next touches the
page: an autosave, a publish, or opening the editor. A crashed tab still gets its entry.

### 12.2 Preview

The canvas is honest about content but silent about everything around it, and a **draft cannot be
seen any other way**: `db.live()` (`db.py:106-108`) gates every public lookup on
`status='published'` with no bypass, no token and no role check.

**Preview repaints by replacing `#main`, not by reloading the iframe, and that is the difference between "live" and unusable.** It was already the most eagerly re-rendered surface in the editor — `canvasFull()` short-circuits to `renderPreview()`, so every peer keystroke, every `dedupe()` and every structural change reached it. What it did not do was keep the reader's place: `fitPreview()` makes the iframe its own scroll container, and `FRAME.srcdoc = html` navigates it to a new document, so a colleague typing (~6.6 updates a second) snatched the page back to the top roughly that often — even when the new HTML was identical, because nothing compared them.

`base.html` wraps every page in `<main id="main">`, exactly as `canvas.html` does, so the same surgery the edit canvas has always used on one section (`canvasBlock()`'s `node.replaceWith`) works here on the whole body. The document survives, so the scroll offset is never lost rather than saved and restored, there is no blank-then-repaint flash, and `wirePreview()`'s capture-phase listeners — bound to the document — keep working. Measured in a real browser before being relied on: 600px stays 600px across two swaps and the listener still fires, where `srcdoc =` gives 0.

**`pvUp` is what says a previewed page is already up, and it is not optional:** `canvas.html` has a `<main id="main">` of its own, so entering Preview — when the frame still holds the edit canvas — would otherwise graft the previewed body into the canvas document and leave the editor's chrome wrapped around it. First render loads through `srcdoc`, every render after that swaps; `canvasFull()` clears the flag on its way to putting the canvas back.

**One 500 ms beat for every preview repaint, local and remote.** That debounce already existed but was wired only to the parent form's `input`/`change` events and shut inside `initBlocks()`, so a peer's edit went straight to `renderPreview()`. It now sits at module scope and `canvasFull()`'s short-circuit uses it, which coalesces every path at the single funnel they all reach; `setView("preview")` still calls `renderPreview()` directly, so *entering* Preview is instant. This matters because a preview render is a whole page off the database — `post.html` + `base.html`, header, mega-nav, breadcrumbs, footer, JSON-LD, roughly **8-11 Supabase round trips** — against `/admin/canvas`, which touches the database not at all. A peer typing continuously used to cost up to ~13 renders/sec (~140 round trips/sec per previewing browser) plus **~6.6 wasted `/admin/canvas` POSTs a second**, fired by `canvasBlock()` before it could discover that a preview document has no `[data-b]` to patch. It is now ~2 renders/sec and no canvas calls at all.

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

### 12.3 Working at the same time

Two editors on one page see each other, and **they type into the same document**: two people in the same paragraph keep both sets of words, character by character, rather than one of them silently overwriting the other. The rest of this section is in two halves — the shared document first, then the presence layer it is built on.

#### The shared document

**A paragraph is a CRDT text type, not a string.** That is the whole design. A string in a map is last-writer-wins however it is transported, so the document is a `Y.Doc` (Yjs 13.6.32, vendored) whose `blocks` array holds one `Y.Map` per section:

```
ydoc.getArray("blocks")  ->  Y.Map per block
                               type : string
                               data : Y.Map
                                        _id   : uuid, names the section for as long as it exists
                                        _rich : the Quill gate's verdict, stored not recomputed
                                        <prose keys>    : Y.Text      (heading, text, label, …)
                                        <settings keys> : plain value (align, tone, media ids, rows)
                                        cols  : Y.Array of Y.Array of block Y.Map (one level)
```

`_id` and `_rich` live in `data`, so they ride `posts.blocks` and `post_drafts.blocks` with no schema change, and both are listed in `blocks._NON_TEXT_KEYS` — `blocks_text()` walks every string in `data`, so an unlisted `_id` would put a bare uuid into `llms-full.txt`, the `.md` twins' source and admin search. That same set reaches the browser as `EDITOR["scalars"]`, which is how the editor decides what is prose: **a string whose key is not in it becomes a `Y.Text`; everything else stays a value.** One list, two readers, no second opinion.

**`MODEL` is not replaced — it is reconciled.** The editor's thirteen `markDirty()` sites, six canvas paths, `prune()` and the Advanced textarea all keep working on the plain array they always did. Two functions bridge it to the shared document:

| | |
|---|---|
| `markDirty()` → `reconcileOut()` | `MODEL` into Y, matching sections by `_id`, debounced 120 ms |
| `YB.observeDeep` → `reconcileIn()` | Y back into `MODEL`, then the smallest repaint that shows it |

Reconciling rather than rewriting those thirteen sites to speak Yjs is both the smaller change and the safer one: every one of them already performs its own surgical canvas patch, and a diff by `_id` recovers exactly that intent — insert, delete, reorder, set — instead of expressing it twice in two vocabularies. Three things make it correct rather than merely plausible, and each was a live bug before it was a rule:

- **Our own writes carry an origin token** (`YDOC.transact(fn, YORIGIN)`) and `reconcileIn` returns on seeing it. Without that a local insert echoes back through the observer and the section is inserted twice.
- **Attach first, fill second.** Yjs refuses to read a type that is not yet in a document, so `yBlock()` inserts the `Y.Map` into the array *before* populating it. Building a block whole and then inserting it throws (`Add Yjs type to a document before reading data`) the moment a nested column is reached.
- **`reconcileOut` never writes a rich block's `html`.** That key is a `Y.Text` holding a **Quill delta**; `Y.Text.toJSON()` is the plain words and the formatting is not in the string, so pushing `MODEL`'s HTML into it would insert markup as literal text. y-quill owns it end to end. For the same reason `fromY()` takes a rich block's `html` from `MODEL`, which `mountQuill()`'s `text-change` mirror keeps current whoever did the typing.

**`_rich` is decided once, by the elected writer, and stored.** `quillKeeps()` is a pure function of a block's HTML, so two peers agree — until one of them types. If A's editing changed the markup and B loaded afterwards, B could decide differently and build a `Y.Text` where A has a plain string: two shapes for one section, which no amount of merging repairs. It is the kind of fault that passes a two-browser test and fails with the third. So `mountQuill()` **reads** `target._rich` and never works it out; a block with no verdict yet renders as legacy until the writer's document arrives and repaints.

**Quill is bound by `y-quill`'s `QuillBinding`, and binding is a QUEUE rather than a decision taken at mount.** At mount the answer is very often *not yet*, and treating that as *never* fails silently and totally: `canvasFull()`'s `onload` runs `wireDoc()` — which mounts Quill — **before** `initCollab()` has a channel, so `canWrite()` is false for every editor on a page's first paint. The shared text was never created, nothing bound, and from then on typing reached `MODEL` and stopped there, with no throw and no warning, because `reconcileOut` skips a rich block's `html` by design. Found in a stored draft whose `html` read *"Prime Testing  is available only monday to Friday"* beside a shared text that still read *"Prime Test"*. So `shareQuill()` queues onto `WAITING`, and every event that could change the answer drains it: the document arriving, a peer's update, the roster settling, the channel subscribing. Text typed during the gap is not lost — the type is filled from `q.getContents()` when it is finally created.

The seeding order inside that is load-bearing: the constructor ends in `quill.setContents(type.toDelta(), this)`, so binding an *empty* `Y.Text` empties the editor. The type is filled from a Quill that already holds the content (`t.applyDelta(q.getContents().ops)`) and bound afterwards.

**A replaced section's binding is swept, because two bindings on one text is a loop and not a leak.** `canvasBlock()` replaces one section's node without going through `wireDoc()`, so the old binding goes on observing the shared text and feeding deltas into an editor whose DOM is gone — and that editor's own observer writes them back. `bindQuill()` drops any binding whose `quill.root` is no longer `isConnected` before adding a new one. That same `setContents` is what makes coming back from Preview safe: re-binding is the shared truth arriving, so a mirror that went stale repairs itself. Bindings are destroyed at the top of `wireDoc()` — the canvas is replaced wholesale by `srcdoc`, and a binding left alive keeps applying deltas into a dead Quill for the life of the tab.

**`selectionchange` stopped meaning "the person at this keyboard moved their caret",** and two things had to be told. y-quill applies a peer's words by mutating the canvas DOM, which fires it — so `rememberSelection()` now requires the canvas document's own `activeElement` to be inside a `[data-f]` before it records anything, or the editor records a caret it does not have and broadcasts *"I am typing here"* for a field nobody is in. (The iframe keeps its own `activeElement` when focus moves to the toolbar in the parent, so a toolbar click is still a caret in the canvas and the bar stays live.) And `syncBar()` reads the caret with `q.getSelection()`: **`q.getFormat()` with no argument means `getFormat(this.getSelection(true))`**, which focuses the editor and returns `null` when the canvas has no caret — `getFormat` then reads `.index` off that null and throws. It became reachable immediately, not in some corner case: `canvasFull()`'s `onload` runs `wireDoc()` — which binds Quill, and `QuillBinding`'s constructor calls `setContents` — **before** `focusBlock()`, so the first paint of any shared page asked a Quill nobody was in. A Quill field with no caret in it is simply not live.

**Focus wins, and the change applies on blur.** A remote value landing in the field somebody is typing in would replace it mid-word — worse than the editor before any of this, where the loser at least kept typing into their own copy. So `reconcileIn` holds any change that touches the section the caret is in and applies it on `focusout`. One rule, covering all three things that are not a shared text type: a legacy section's `html`, a repeater's rows, and the settings in the panel.

**A draft that could not be stored says so.** `save_draft()` returns `False` when `0010` is not applied, the route passes it back as `"stored": false`, and the editor shows *"Not saved — this site is not set up to keep drafts yet. Tell a developer."* rather than *"Saved just now"*. Tolerating the missing table is right — the editor must run before the migration — but doing it silently is the failure mode `_tolerate_0010`'s own docstring forbids: the editor reports a save, the next reload serves the **published** version back (no draft to load), and the work appears to vanish. Worse for the shared document, because `post_drafts.state` is also where the seed guard above gets its answer: no table means no state means every browser seeds its own copy. The editor's sentence names no table (an admin screen is read by non-technical people); the console names the migration.

**The transport is the channel presence already opened** — base64 in a `broadcast` payload, no new server (`y-websocket` and `y-webrtc` both want one, and gunicorn cannot hold a socket). Three mechanisms, each with a wrong reading:

1. **Deltas, not state.** `doc.on("update")` → broadcast; `Y.applyUpdate(doc, bytes, "remote")` on receipt, and that origin is what stops it being echoed straight back. **That handler is attached before anything in `initShared()` can return**, and the ordering is load-bearing rather than tidy: everything after it has an early exit, and with the line at the end of the function a page with a stored state — every page after its first save — returned before `update` was ever hooked up. Not one keystroke reached anybody, and nothing threw: the editor worked, the draft saved, the peer markers moved, and the words stayed in the browser. `tests/reconcile.mjs` asserts it behaviourally, on that exact path — restore from stored state, edit, expect a delta on the wire — because no source-shaped assertion would have caught a line being in the wrong place.
2. **A newcomer is caught up by a peer, not by the server.** `post_drafts.state` is behind by the save debounce plus whatever is in flight, so a newcomer who loads it and then hears the next delta has Yjs hold that delta as **pending** — its base is missing — and those words never appear. Measured, not assumed: applying a bare delta to a fresh document yields an empty document, silently (`tests/reconcile.mjs`). So **any peer that holds a document** broadcasts `Y.encodeStateAsUpdate(doc)` in full on presence `join` — not only the elected writer, because the writer is whoever has the lowest presence id and that can be the *newcomer*, who has nothing to send. Guarded by `peer.id !== me.id`, because Realtime reports your **own** arrival as a join too; `applyUpdate` is idempotent, so two peers answering costs one extra message.
3. **Coalesce before sending.** `doc.on("update")` fires per transaction and a fast typist is eight to ten a second, against a channel budget counted in events per second. Updates are merged with `Y.mergeUpdates` and sent once per 150 ms tick.

**One elected writer saves; every editor records its own sitting.** The peer whose presence id sorts lowest writes `blocks` + `state` to `POST /admin/posts/<pk>/draft`; the election re-runs whenever the roster moves. **Preview disqualifies you**, and that is not tidiness: Preview replaces the canvas, so there are no Quill instances, and a rich paragraph's HTML is derived from a Quill — a previewing writer would keep saving a draft that is quietly behind. It rides the `where` broadcast rather than presence, which is rationed (below). The *other* half of that request is per person: `was`/`now` are one editor's sitting and **every** peer sends its own, or the activity log would credit the whole room's writing to whoever happened to be elected. So the route tests `if "blocks" in request.form:` — **presence of the field, not truthiness**, because `.get("blocks") or "[]"` reads a missing field as an empty page and would wipe the draft on every peer's autosave.

`sitting()` is what narrows the entry, and it answers two questions: **which sections, and from when.** Quill is the only thing that can tell local typing from a peer's — `text-change` reports source `"user"` for input and the binding object for a delta y-quill just applied — so `touched()` records the sections this person actually worked on. It also **snapshots each one as it was at that first touch**, which is the half that was missing: a baseline taken at page load spans everything a peer did to that section in between, and a real row read `WAS '<p></p>'` → `NOW '<p>Good Hello Afternoon…'` for somebody who had added one word to a colleague's sentence. Both sides of the pair are built together from one ordered list of this person's sections; sending a whole-page `was` beside a narrowed `now` is exactly how the two halves came to describe different documents. Sections nobody here touched are omitted from **both** sides — `_section_rows()` names a row by its section type rather than by its position, so nothing is lost. **This pays off the `# ponytail:` #66 left in `initAutosave()`.**

The snapshot is taken inside `touched()` rather than at the call sites, because the call that matters most is a **deletion**: the section has to be captured while it is still in `MODEL`. And `touched()` is called from the structural mutations (`delBlock`, `moveBlock`, `dupBlock`, `addParagraph`, the `/` inserter) and not only from the two typing handlers — otherwise a section this person deleted, moved, or added without typing into never appears in their entry at all.

**A sitting ends after fifteen minutes idle, and leaving the page is not that.** `pagehide` flushes what is pending but no longer sends `close`; the sitting is closed by the browser's idle timer, or by `flush_sessions()`'s opportunistic backstop when the next person touches the page — which is also what records a tab that was closed and never came back. `db._merge_changes()` folds each visit into the open session, keeping the **earliest `was`** and the **latest `now`** per section by name, so one sitting is one entry however many times somebody reloaded. Before this, a reload wrote the row immediately and twenty minutes' work across three visits became three entries.

**Sections in the diff are paired by `_id`, not by position.** `_blocks_fields()` used to compare the two block-*type* lists and, when they differed, fall back to one page-wide word diff labelled *"The writing on the page"* — losing every other section's field-by-field report. That was a rare corner when one person edited at a time and is the common path once two do, because somebody is always adding a section. `_by_id()` returns sections keyed by name, or `None` when any lacks one or two share one, in which case the positional path still runs for content that predates `_id`.

**Ceiling.** If two people edit one section *alternately* — A, then B, then A again — A's entry still spans B's middle edit. A two-point diff cannot attribute interleaved writing; that needs per-character authorship, which Yjs can carry and which is a much larger change. First-touch removes the page-load-to-first-edit window, which is where essentially all of the observed drift came from.

**The draft is stored unpruned, and validated as a draft.** `prune()` drops an empty paragraph and rebuilds a `columns` block as a fresh object, so a section an editor still has the caret in loses its `_id` and every later one answers to a different name — and a remote edit is then applied to the wrong section. The draft is the live document, empty paragraphs and all; **Publish still prunes**, because that is where "an empty paragraph is the caret waiting for you, not content" is true.

That makes the route's own validation wrong in one specific way, so `validate_blocks(blocks, draft=True)` **checks the shape and not completeness**. A working draft is unfinished by definition: the paragraph the caret is sitting in has no text, and an Image section has no picture until one is chosen (its seed deliberately has no `media_id`). Refusing to *save* somebody's work because they have not finished it is the worst possible moment to enforce a publishing rule — and "required" is a publishing rule, which `apply_post()` enforces anyway as the one full check into `posts.blocks`. What is still refused is a shape that is wrong rather than incomplete: an unknown type, a `hero` or grid nested in a column, a `cols` that is not a list. Pruning used to hide half of this — an empty paragraph never reached the check — and the other half was already a live bug: before this, inserting an Image section and not immediately choosing a picture made every autosave 400 until you did.

**Version stamps are exchanged so an identical document stops tripping the save guard.** After somebody publishes, every other tab still carries the `updated_at` its form was drawn with, so the next Publish trips §12.1's conflict banner over page content that is now the same document. Peers put their stamp on the `where` broadcast and a later one is adopted — **but only when the rest of the form matches**, and that condition is the point. The panel on the right (title, web address, status, summary, SEO) is deliberately not shared, so the guard is still the only thing between two people who both retitled the page; adopting a stamp over a panel that differs would turn a refusal into a silent overwrite.

**Vendored, no build step, and no import map.** `vendor/yjs.mjs` is the esm.sh es2022 bundle with one line changed: its `import __Process$ from "/node/process.mjs"` is an inline stub, because lib0 reads `argv`/`env`/`release`/`stdout` only to decide whether to colour console output, all four behind an is-this-node test that `release: {}` fails. `vendor/y-quill.mjs` is y-quill 1.0.0 with its bare `import * as Y from 'yjs'` rewritten to `./yjs.mjs`. That relative path is why there is no import map: ES modules are identified by resolved URL, so one path means exactly one copy of Yjs, and two copies is a silent `instanceof` failure and broken interop. Both vendored files also have their trailing `//# sourceMappingURL` removed, and so does `quill.js` — we do not ship the `.map`, so it is a guaranteed 404 in every editor's console, and console noise is exactly what hides the next real error (§12.3's own "every state says so once" rule). Each file's header says so, because a re-vendor would otherwise put it back. `post_form.html` publishes `window.IOPY` from a three-line module; `admin.js` stays a classic script. A module script is deferred like `admin.js`, so the global is set before `DOMContentLoaded` runs `initBlocks()`, and its absence is the single-player editor unchanged. `.mjs` serves as `text/javascript` (verified against the running server).

`tests/reconcile.mjs` cuts the shared-document section straight out of `admin.js` and runs it against the real Yjs, so it cannot drift into testing a copy; `test_two_people_in_one_paragraph_keep_both_sets_of_words` runs it and skips when `node` is absent.

#### Presence

**The transport is Supabase Realtime, reached through this app.** Gunicorn runs gthread workers (`-w 30 --threads 8`), so the app cannot hold a WebSocket at all, and putting one behind thirty stateless processes would need a broker to fan out between them. That reason still stands — so the browser does not use a WebSocket. Realtime is Phoenix, Phoenix ships a **longpoll** transport, and longpoll is ordinary request/response HTTP, which a gthread worker proxies exactly the way it proxies a picture. `admin_ui.realtime_longpoll()` forwards `/admin/realtime/v1/longpoll` to Kong; Realtime still does all the fan-out, so the answer is as correct across thirty workers as a direct socket would be. **This is what lets Supabase stay off the tunnel entirely** (§15): the browser talks only to Flask, the same rule that put every picture behind `/media/<key>` (§8). `iopstor/static/vendor/supabase.js` is the pinned UMD build (2.116.0), loaded by `post_form.html` — the **parent** document, not the canvas iframe. That is the opposite of the `sortable.min.js` precedent (`canvas.html`), and deliberately: Sortable binds to elements inside the iframe, while the socket, the roster and the token belong to the page, and only the *markers* are painted into the iframe's DOM from outside.

**Two signals, two transports, and the split is a hard limit on the instance rather than a preference.** `presence.track()` is rationed to roughly **five events a minute per client** here. Sending one per caret move — the obvious design, and the first one built — earned `Client presence rate limit exceeded` from the server on the sixth, and the server then *closed the channel*: the roster emptied and the markers died the moment anybody typed. Measured against the dev Supabase: six tracks 250 ms apart refused; six tracks **three seconds** apart also refused (so it is a budget, not a rate); six tracks fifteen seconds apart all accepted (so it refills at about five a minute); and 160 broadcasts at four a second all delivered with the channel never moving. So **presence carries who is here and is sent exactly once per join**, and **where the caret is goes over `broadcast`**, which is the budget built for it. Positions are held in a map separate from the roster, so a broadcast that arrives before the presence sync is not thrown away, and every peer re-broadcasts its position when somebody joins, because a latecomer has heard nobody's.

**There is no on/off switch any more, and the transport is chosen by handing supabase-js its own LongPoll class.** The library ships a complete longpoll implementation but does not expose it through `createClient` — `_initializeOptions` drops `longPollFallbackMs` — so `join()` fetches it off the socket (`realtime.socketAdapter.socket.getLongPollTransport()`, one level deeper than it looks) and passes it straight back in as `transport`. Three consequences, each verified against the vendored 2.116.0 bundle rather than assumed: the socket then selects its **JSON** encoder by itself, which is required because the default `vsn=2.0.0` binary serializer cannot ride inside a JSON longpoll envelope; the base URL `<origin>/admin` becomes `/admin/realtime/v1/websocket` and LongPoll rewrites that to `/admin/realtime/v1/longpoll`, so no URL is built by hand; and the origin comes from `location.origin`, never from `SITE_URL`, because it has to match the origin the session cookie was set on. **This is minified vendor internals and a bundle upgrade could move it** — if `getLongPollTransport` disappears, the fallback is `vsn:"1.0.0"` plus `replaceTransport()`, which binds the JSON serializer explicitly and arrives at the same place. The only off state left is a post with no id, which has no room to join.

**The proxy answers in the transport's own vocabulary, and that is load-bearing.** Its status switch handles exactly `{200, 204, 403, 410, 500}` and **throws** `unhandled poll status` on anything else, wedging the transport for the life of the tab. So the route refuses with **403** (which LongPoll reads as "stop") rather than `ui_required`'s redirect to the login page, and it collapses every upstream failure — a Kong 401 from a wrong anon key, a 502 while Realtime restarts, an unreachable gateway — to **500**, the one status it knows how to back off from, which then surfaces through our own `CHANNEL_ERROR` path. `ui_required` is also unusable for a second reason: it reads `csrf` out of `request.form`, and a Phoenix POST is a JSON body, so every send would 400. The csrf token rides the query string instead, alongside `eventsPerSecond`. The apikey is pinned server-side, which is **not** about hiding it — the anon key is a browser key by design and is still in `#editor-data`. It means the proxy always presents the key *we* chose: a caller cannot probe Kong's key-auth through it, and a service-role key that leaked somewhere could not be walked in through this route by a signed-in editor.

**A rich paragraph is the one field MODEL cannot read out of the shared document, and that left a hole in Preview.** A `Y.Text` holds a Quill delta; its `toString()` is only the plain words. So `html` has always been mirrored back into MODEL by a mounted Quill's `text-change` (`mountQuill`), and `reconcileIn()` skipped the key on purpose. But Preview has no Quill at all — `canvasFull()` short-circuits to `renderPreview()` and never wires the document — so a colleague's typing reached the shared document, the roster and the markers, and never reached MODEL. MODEL is what Preview renders (`formBody()` sets `blocks` from it) and what Publish submits, so the words were missing from the preview and publishing from there sent the page an edit behind. #68 saw half of this and disqualified a previewing tab from being the elected writer so it could not *save* a stale draft; it could still show one, and Publish was never gated that way.

`mirrorProse()` closes it. When no mounted editor owns the field — `quillOf()` is null, which also correctly counts a field still waiting in the bind queue as owned, since `__quill` is set before the binding is — it converts `yt.toDelta()` with an **offscreen Quill of its own** and writes the result into MODEL. Deliberately not a hand-written delta-to-HTML renderer: the output has to be byte-identical to a mounted editor's or the two paths would disagree about the same paragraph, so it is the same vendored Quill, the same `QUILL_FORMATS` and the same `semantic()`. Measured rather than assumed — a heading, bold/italic/underline/strike, an escaped link, both list kinds, a blockquote and a doubled space came back **identical at 293 characters** in a real browser. That copy of Quill is loaded in the **parent** by `post_form.html` (canvas.html already loads one inside the iframe) and only when there is a room, because the frame in Preview is the previewed page and loads no Quill — which is exactly when the converter is needed. It repaints through `canvasBlock()`, which is right in both views: a preview document has no `[data-b]` to replace, so it falls through to `canvasFull()`, which *is* the render-the-preview path. No `markDirty()`: this is somebody else's edit arriving, not one of ours to stamp and rebroadcast.

**Authorisation mirrors the app's own rule rather than trusting `authenticated`.** Channels are `private: true`, so Realtime checks RLS on `realtime.messages`, which `migrations/0009_realtime_channel_policy.sql` supplies. The policy is not `to authenticated` alone: this GoTrue has signups enabled, so "holds a valid token" is a wider set than "is a CMS editor". It asks `auth.current_user()`'s question — is there a `public.users` row for this token's `sub` — but it **cannot ask it inline**, and that is the trap worth knowing: written as a bare `exists (select 1 from public.users …)` the clause is always FALSE, because the policy runs as `authenticated`, `0002` turned RLS on for `public.users`, and that table has no policies of its own, so the subquery sees an empty table and every editor is refused. (Verified on the running instance: a real admin selecting their own row over PostgREST as `authenticated` gets `[]`.) So the check goes through `public.is_cms_user()`, `SECURITY DEFINER` with `search_path` pinned to `''` and every name schema-qualified, which runs as its owner and therefore bypasses RLS — possible only because `0002` uses `ENABLE` and not `FORCE`. It returns one boolean about the caller and leaks no row, email or role. Plus `topic like 'post:%'` so the grant does not extend to every channel name somebody invents, and `extension in ('broadcast','presence')` because **presence rides `realtime.messages` too**; a broadcast-only policy makes `track()` fail silently and the roster stay empty forever.

**`GET /admin/rt-token`** hands the browser a current access token. It exists because a GoTrue token lasts about an hour and an editing session does not, and the copy the page started with is not refreshed when the server rotates it. Two facts shape the client:

- **`auth._session_token()` refreshes only *after* expiry** — it returns the existing token untouched while it is still valid. So there is no "refresh early" to schedule; the browser reacts to Realtime's `CHANNEL_ERROR` instead, which is the only signal that can be honoured.
- **A finished session does not answer 401.** `ui_required` redirects to the login page before the route body runs, `fetch()` follows it, and the browser gets **200 with HTML**. Verified against a running server: `302 → /admin/login?next=…`, then `200 text/html`. The client tests `r.redirected` and stops rather than retrying forever.

**The client is built around a token *getter*, not a token, and without that presence cannot work at all.** supabase-js re-authorises the socket by itself — on connect, on reconnect and on every heartbeat — and when it does it ignores whatever `realtime.setAuth()` was handed and calls its own `accessToken` callback instead. `SupabaseClient` always installs one (`realtime.accessToken = this._getAccessToken.bind(this)`), and `_getAccessToken()` is `await this._getSessionToken() ?? this.supabaseKey`. This client has no GoTrue session — the token comes from `/admin/rt-token`, not from a sign-in in the page — so that fell through to **the anon key**, which was pushed to the already-joined channel; Realtime re-ran the policy as `anon` against a policy written `to authenticated`, and closed the channel a tenth of a second after it opened. The console read `SUBSCRIBED` then `CLOSED`, the roster stayed empty, and every layer underneath tested green. `_performAuth()` is where it is decided: `this.accessToken ? this._manuallySetToken = false : …`, so the callback's mere existence cancels the manual token. The fix is to pass `accessToken: () => Promise.resolve(token)` to `createClient()` and keep `token` in the closure, which also makes the library's own reconnects use the refreshed token for free. The client is created inside `join()` rather than above it, because a null token at construction lands back on the anon key. Proved by A/B against the live instance: with the getter two peers see each other and hold; without it the first peer is gone before the second arrives.

The token is **never rendered into the page**. `#editor-data`'s `rt` block carries the public Supabase URL, the anon key (a browser key by design — with RLS on and no policies it reads nothing on its own), the room name and the editor's own display identity; the token is fetched at init and lives only in memory. There is no copy at rest in the HTML, in view-source, or in a cached page.

**Markers are attributes, never injected nodes — this is the rule that would otherwise ship a bug.** `bindField()`'s `input` handler copies a `[data-f]`'s `innerHTML` straight into `MODEL`, so any element appended inside an editable field would be **saved into the published page**. So "Asha is typing here" is `setAttribute("data-peer", …)` plus a `::after` in `canvas.css` (`::before` is the empty-field placeholder), and the section edge is `box-shadow: inset` — hover and selection both use `outline`, and an inset shadow adds no layout box, so all three show at once without fighting. An element's own attributes are not part of its `innerHTML`, which is what makes this safe.

**`bars()` is the single repaint point.** Six paths re-render the canvas — `canvasFull`, `canvasBlock`, `canvasInsert`, `moveBlock`, `delBlock` and the Sortable drag — and `bars()` is the only function every one of them reaches, after `renumber()` has finalised `data-b`. `paint()` looks like the obvious hook and is wrong: it misses move, delete and drag. `paintPeers` is declared as a no-op and reassigned by `initCollab()`, the same late-binding `syncBar()` already uses, because `canvasFull()` is async and the iframe document does not exist when `initBlocks()` finishes.

**A peer's position is carried as the section's `_id`, not as `data-b`.** The path is *positional* and `renumber()` rewrites it on every insert, move and delete — so the moment one editor adds a section, their `"2"` is the other's `"3"` and a marker drawn at their path sits on the wrong block. A name resolves wherever the section has since moved to. The structure fingerprint that used to guard this remains as the fallback for a peer that has not sent a name yet (an older tab mid-deploy); with one shared document there is one shape, so it now agrees rather than arbitrating.

**Every state says so once, in the browser console** (`[iopstor] editor presence: …`). The feature used to be off far more often than it was broken, and from the page the two looked identical; the first real setup lost a round trip to exactly that. Now that there is no switch, what remains is: an unsaved post (no room to join), a library that did not load, and the channel's `subscribe` status — which is reported because a missing or wrong RLS policy arrives as `CHANNEL_ERROR` and would otherwise be silent. A working channel says which room it joined.

**The reconnect is capped, and `CLOSED` is not a failure.** The first version retried every two seconds forever, so with the realtime service refusing the socket each open editor fetched `/admin/rt-token` every two seconds for as long as the tab stayed open. It now backs off (2s doubling to 30s) and gives up after five attempts, and a successful `SUBSCRIBED` resets the budget. `CHANNEL_ERROR` and `TIMED_OUT` are the obvious triggers; a `CLOSED` **the client did not ask for** is the third, and it was missing — a server-side hang-up (a restarted realtime container, a changed policy, a limit tripped) ended collaboration for the life of the tab with nothing on screen saying so. A `closing` flag is what separates that from the close `removeChannel()` makes on the way to a retry; without the distinction the retry re-arms itself and the loop cannot end even once the socket recovers, which is exactly what the first version did.

**What the editor gives you no event for:** there is no `blur` on a field, and nothing clears the caret position when focus leaves the iframe for the title or the settings panel. So a position ages itself out after a minute rather than marking a section nobody is in. (The shared document does bind `focusout` on the canvas, but only to release changes that focus-wins held back — it is not a position signal.)

## 13. Tests

```
tests/test_offline.py    always runs — slugify, validate_blocks, render_blocks, JWT matrix, the /media route,
                         the audit diff and its wording, the IST filters, that a trashed post is
                         never live, and that every state-changing route is accounted for
tests/reconcile.mjs      the shared editing document, against the real Yjs -- run by test_offline.py
                         (skipped when node is absent) and standalone with `node tests/reconcile.mjs`.
                         It cuts the shared-document section out of admin.js rather than restating it
tests/conftest.py        app/client fixtures, admin_headers/editor_headers, seeded corpus, cleanup
tests/test_auth.py       JWT matrix, mocked GoTrue login, real bad-password rejection
tests/test_admin_api.py  create/publish visibility, scheduled-post hiding, terms/settings/menus
tests/test_admin_ui.py   browser login and post creation
tests/test_public.py     hierarchical URLs + breadcrumbs, leads, redirects, sitemap/feed/llms, upload, checkout, seed idempotency
```

**`test_throttle_fails_open_and_believes_only_a_proxy_we_named`** covers `client_ip()` end to end: the counter failing open, the header winning from a peer inside `TRUSTED_PROXIES`, the **rightmost** `X-Forwarded-For` entry beating a spoofed one to its left, `CF-Connecting-IP` beating `X-Forwarded-For`, and — the half that is the security property — both of them being *ignored* from a peer outside the list, including after narrowing `TRUSTED_PROXIES` so the private peer no longer qualifies. It was `test_throttle_fails_open_and_reads_cloudflares_header` until the header stopped being read unconditionally.

**The stress engine (`iopstor/stress.py`) is covered offline**: `test_validate_target_*` (scheme-only URL guard), `test_clamp_*`, `test_percentile_is_nearest_rank_in_ms`, `test_progress_store_roundtrips_and_stops` (the `/dev/shm` store on a `tmp_path` file), `test_nprocs_and_split` (the fan-out sizing and even split), `test_plan_caps_real_concurrency` (a huge entered number is scaled down so per-process threads stay ≤ `PER_PROC`), `test_merge_parts_sums_children` (the coordinator's sum of two part rows), and two measured ones: `test_run_load_hits_a_real_server_and_the_honeypot_leaves_no_row` stands up a throwaway `http.server`, runs `stress.start()` at it and asserts requests went, real pages answered 200 and every honeypot lead post was dropped without a row; `test_a_multiprocess_run_completes` forces the fan-out to real spawned processes and asserts both children reported through the `parts` table into a finished run. No Supabase, so they live in `test_offline.py`.

**The testimonial row has four offline tests**, all monkeypatching `blocks._post_list` so no Supabase is needed:
`test_a_rating_is_clamped_to_five_stars_and_absent_when_unset` (9 → five marks, −3 → none, and no rating renders no
`.stars` at all), `test_a_testimonial_card_with_only_a_name_renders_nothing_else` (every other field blank leaves no
empty `<p>` and no stray comma), `test_only_a_testimonial_list_becomes_a_sliding_row` (`pl-rail` and the `hidden`
nav, and a `partner` list getting neither — it asserts the dots box ships **empty**, since the browser builds them),
and `test_a_post_with_no_page_still_reaches_the_md_twin`. What none of them can cover is the drift, hover-pause,
click-drag, the wheel and a real finger: those are measured in a browser (§12 *The sliding row*) and listed as
user-only in the PR, the way `/collab-check` does it.

Everything except `test_offline.py` is marked `live` and skips when `.env` has no Supabase.

---

## 14. Configuration

`SECRET_KEY`, `SITE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `MEDIA_BUCKET`, `PAYMENT_PROVIDER`, `THROTTLE_DB`, `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW`, `TRUSTED_PROXIES`, `ADMIN_NETWORKS`. `FLASK_DEBUG=1` in `.env` gives the dev server the debugger and auto-reload; it must be **absent** in production, and nothing in the Dockerfile guards that.

**Six are required, and the app refuses to boot without them** — `create_app()`'s `REQUIRED`, checked before a blueprint is registered. The four `SUPABASE_*` were always there; `SECRET_KEY` and `SITE_URL` joined them when production became real, and `config.py` dropped their defaults to make the check bite. **Why a refusal rather than a sensible default.** Both used to fail *silently*, which is the expensive way to fail. `SECRET_KEY` fell back to `"dev-only-change-me"`, a string printed in this repo — and `auth.py` accepts a session token as a Bearer fallback when no `Authorization` header is present, so a forged cookie is a way in. `SITE_URL` fell back to `http://localhost:5000`, which does two things at once: every canonical, sitemap `<loc>`, `robots.txt` `Sitemap:` line, RSS guid, JSON-LD `url` and OG image points at localhost, and `SESSION_COOKIE_SECURE` — computed at import from `SITE_URL.startswith("https://")`, not from the request — comes out `False`, so the admin cookie ships over the tunnel without `Secure`. Neither shows up in a smoke test; a deploy that forgets one now stops instead. `test_boot_refuses_without_secret_key_or_site_url` passes empty strings rather than omitting keys, because pipenv loads `.env` and an omitted key would inherit a real value and pass for the wrong reason.

`SUPABASE_JWT_SECRET`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are the same values as `JWT_SECRET`, `ANON_KEY` and `SERVICE_ROLE_KEY` in the Supabase compose environment.

**There is no browser-facing Supabase variable, and that is the point.** The editor's realtime channel comes back through this app (§12.3), so the browser builds its own origin from `location.origin` and never learns where Supabase is. `SUPABASE_PUBLIC_URL` existed for exactly this and was deleted when the proxy landed: one transport, one path, and development exercises the same route production does. Collaboration is no longer switchable by environment — the only off state is a post that has never been saved.

`GUNICORN_CMD_ARGS` is read by gunicorn itself, not by the app: the Dockerfile sets `-w 2 --threads 8 --preload --access-logfile -` and Dokploy's environment raises the worker count (§15). `--access-logfile -` is the only request log there is; the `HEALTHCHECK` adds a `/healthz` line every 30 s, which is not traffic.

Dev gateway: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io` — LAN, self-signed cert on https, so use http until a real certificate exists.

`SUPABASE_URL` needs to be reachable **from the app only**. Nothing a visitor's browser loads points at it
any more (§8), so the gateway can sit on a private network with Flask as the only exposed service. `SITE_URL`
is what the outside world sees, and it is what `seo._abs()` puts in front of a `/media/` path.

Production values, set in the Dokploy Compose service's environment and nowhere else (`.env` and `.env.*` are
both git-ignored, so a `.env.production` on a laptop cannot be committed):

| Key | Production |
|---|---|
| `SITE_URL` | `https://www.iopstor.com` — the tunnel's public hostname, and therefore the Secure flag |
| `SUPABASE_URL` | `http://<kong-service>:8000` — Kong by Docker service name on `dokploy-network`, never a public host |
| `SECRET_KEY` | fresh random, per environment. Never the development one |
| `GUNICORN_CMD_ARGS` | `-w 30 --threads 8 --preload --access-logfile -` (§15) |
| `TUNNEL_TOKEN` | read by the `cloudflared` service in `docker-compose.yml`, not by the app |
| `COMPOSE_PROFILES` | `tunnel` — read by Docker Compose, not by the app; without it `cloudflared` never starts (§15) |
| `FLASK_DEBUG` | **unset** |

The `SUPABASE_SERVICE_ROLE_KEY` bypasses RLS — `0002_enable_rls.sql` enables RLS on every table and defines
no policies at all, on purpose (§10), so the app's security boundary is Flask, not the database. That key
belongs in the deployment's environment and nowhere else: not in the image, not in the repo, not in a
browser.

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

**First-time setup on a Supabase instance** (development; the production order is the runbook below, which has more steps and cares about all of them):

1. Studio → SQL editor: run `migrations/0000_bootstrap.sql`
2. Studio → Storage: create a bucket named `media`. Public or private no longer matters to the app — it uploads and reads with the service-role key (§8), and nothing a visitor loads points at the bucket. The instances built so far use a public one
3. `flask migrate` → `flask seed` → `flask create-admin`

**Workers.** The `app` container runs `gunicorn -b 0.0.0.0:8000 'iopstor:create_app()'` and nothing else — migrations are the stack's separate `migrate` service (below) — and gunicorn takes its worker and thread count from `GUNICORN_CMD_ARGS` — `-w 2 --threads 8 --preload` from the Dockerfile, overridden in Dokploy's environment (production runs `-w 30`). The number is deploy config rather than code because the app is stateless across processes by construction, and it pays to know exactly what that rests on:

- *Per request:* `db._cached()` on `flask.g`, gone at teardown — `admin_counts()`, `tree()`, `seo.site()` and the derived per-id memos. *Per process:* `db._proc_cached()` for `post_types()`, `settings()`, `get_menu()`, `get_media()` and `redirect_for()`, plus `public.py`'s page cache. Neither can go stale between workers, because every write touches the `/dev/shm` epoch file and every read compares it (§4). The workers still share no memory, so a cold page is rendered once per worker rather than once between them (§17).
- *Per process:* one object, the service-role Supabase client in `app.extensions`, built lazily on the first request. It is HTTP plumbing — a thread-safe `httpx` pool — holds no data, and `.table()` builds a fresh query each call.
- *`TRUSTED_PROXIES` is wider than a proxy:* unset, it is every private range, which contains the LAN **client** as well as the LAN proxy — so somebody on the office network can still put an address that is not theirs into the throttle and the *From* column. Narrowing it to the subnet the proxy actually sits on closes it with no code change, and the app logs a warning at every boot while it is unset. It is a default rather than a `REQUIRED` key because refusing to boot would need the operator to know that subnet before they can go and look it up (§12).
- *One hop:* `X-Forwarded-For` is read from the right, which is correct for exactly one trusted proxy. Chain two and the last entry is the inner one, not the visitor; the fix is to count back as many entries as there are hops (§12).
- *Per container:* the login throttle's sqlite file on `/dev/shm` (§8). Two replicas would be two counters.
- Sessions and the CSRF token are the signed cookie; `/admin/canvas` and `/admin/preview` carry everything in the POST body; uploads go to Storage under a `uuid4` key; there are no local files, threads, locks or module-level mutable state. The read-then-write spots — `unique_slug()`, `ensure_term()`, the warranty serial — sit behind `UNIQUE` constraints, so a race costs the loser a 502, never a duplicate row.

`--preload` imports the app once in the master and forks it: a broken import fails once instead of thirty crash-looping workers, and the imported code is shared copy-on-write. It is safe here because the Supabase client is created after the fork, the throttle opens its connection per call, and Python reseeds `random` in every child (`unique_slug()`'s suffix).

Sizing: `create_app()` makes no network call and costs about 0.9 s and 63 MB per worker on its own; a thread costs almost nothing, and every request is a wait on Kong. Measured on the dev box, `-w 30 --threads 8 --preload` boots in a few seconds and holds 472 MB of real memory (PSS, shared pages counted once — the summed RSS reads 1.7 GB, which is the number a per-process view shows). `-w 8 --threads 30` is the same 240 slots at a quarter of that. The ceiling behind either is PostgREST's connection pool — `PGRST_DB_POOL`, 10 by default, with a 10 s acquisition timeout — so check it on the Supabase host (`docker exec supabase-rest env | grep PGRST_DB_POOL`) before going wide.

**Count the cores before the workers.** The production box is 6 cores and 16 GB running Dokploy, Supabase *and* this app, so every PostgREST call is also CPU on the same six cores — `-w 30` is thirty processes competing with Postgres for both CPU and page cache. A 2000-visitor stress run pinned it flat at 100% for the whole run with memory unmoved at 6 GB, which is the CPU-saturation shape, not a memory or pool-wait one. Prefer the `-w 8 --threads 30` shape here, and raise `PGRST_DB_POOL` to match, sized against `max_connections` (`show max_connections;` in Studio) with budget left for GoTrue, Storage, Realtime and Studio. What removes the load rather than redistributing it is the edge cache below. Two **replicas** are a different case from thirty workers, though a smaller one than it used to be: the throttle splits per container, and that is now the whole of it. Migrations are no longer a per-container event — there is one `migrate` service in the stack and every replica of `app` waits on the same run of it — so replicas can start together on a cold database.

**Production (Dokploy + Cloudflare Tunnel).** Production is **one Dokploy Compose service** built from
`docker-compose.yml` at the repo root, holding two containers: `app`, built from the same `Dockerfile`
development uses, and `cloudflared`. Supabase is a separate stack from Dokploy's Supabase template.
`SITE_URL` is `https://www.iopstor.com`.

**Why one compose stack rather than a Dokploy Application plus a separate Compose app for the tunnel.**
Both shapes work, but the split one has to name the app container as the tunnel's origin, and a Dokploy
Application's container name is generated — you read it off the host with `docker ps` and it changes when
the app is recreated, so the tunnel's ingress rule silently points at nothing after a redeploy. Inside a
compose project the service name *is* the DNS name, so the origin is a fixed `http://app:8000` that no
deploy can invalidate. `docker compose up -d` also restarts only what changed, so shipping code rebuilds
`app` and leaves the tunnel connected.

**Migrations, and why Deploy and Rebuild need not be told apart.** `migrate` is a one-shot service built
from the same image as `app`, running `flask migrate`, which `app` waits on with
`depends_on: condition: service_completed_successfully`. It runs once per `docker compose up` rather than
once per container start, which is the distinction that matters: a crash, an OOM kill or a host reboot
brings gunicorn back without touching the schema, and only a deploy touches it. Dokploy's **Deploy** and
**Rebuild** buttons are the same `docker compose up` to Docker — the difference is the `git` pull Dokploy
does before compose runs, and there is no hook in between to hang a migration on. They do not need
separating. New code is a new image, which recreates `migrate` and runs it again; a rebuild of unchanged
source cannot contain a file the ledger has not already seen, so it costs one `SELECT` and prints
`migrations up to date`; and a `migrate` that exited non-zero never satisfies the condition, so a Rebuild
after a failed deploy retries it. `migrate` sits on `dokploy-network` only, carries `restart: "no"` (a
restart policy on a container whose job is to exit is a loop), and disables the inherited `HEALTHCHECK`,
which probes a port it never serves. Both services read one anchored environment block, so the keys
cannot drift apart and migrate a different database than the app reads.

The cost of this shape is the one property the old `CMD` had: `flask migrate` was also the boot-time
proof that `SUPABASE_URL` was right, and `/healthz` is liveness-only partly because of it (§12). A
container restarting while Supabase is unreachable now starts gunicorn and answers 500s instead of
refusing to boot. That is the better failure — it logs, and it recovers by itself when Supabase does —
and the deploy path still proves the configuration, because `migrate` runs before `app` is started.

`app` sits on two networks on purpose: the compose-private `default`, which is how `cloudflared` reaches
it, and the external `dokploy-network`, which is how it reaches Supabase Kong. `cloudflared` is on
`default` only — it has no business reaching Supabase.

**There are two ingresses, and that is the supported shape** (user, 2026-09-15): the Cloudflare tunnel
for the public site, and **Dokploy's own Traefik** for LAN access to the admin. Traefik is in the path
because a domain is attached to service `app` in the Dokploy UI — it needs no `ports:` line and no
Traefik label in this file, which is why it is easy to believe nothing is in front when something is.
`app` still publishes no port, but the reason has changed: it is no longer what makes a header
trustworthy (`TRUSTED_PROXIES` is), it is that Traefik already serves the LAN and a second way in would
be exposure for nothing.

What used to carry this weight was the *absence* of a port: the tunnel being the only way in was the
reason `CF-Connecting-IP` could be trusted from anybody. That is no longer true and no longer the
mechanism — **`TRUSTED_PROXIES` is** (§12). It is therefore the variable to get right on this stack: set
too wide it lets a LAN client claim somebody else's address; set to a network cloudflared is not on it
drops the header and puts every tunnel visitor in one bucket, which is the failure the old shape had.
The required-variable syntax in
the compose file (`${SECRET_KEY:?...}`) is deliberate too: a missing value fails `docker compose config`
with a sentence saying what it wanted, rather than starting a container that refuses to boot for reasons
you then have to read out of a log.

**Deploying before the tunnel exists.** `cloudflared` carries `profiles: [tunnel]`, so `docker compose up`
starts `app` alone until `COMPOSE_PROFILES=tunnel` is in the Dokploy environment — Compose writes that
screen to the project's `.env` and reads the variable from there. `app` has no `profiles:` key, so nothing
about the profile can leave the Python app out. This is also why `TUNNEL_TOKEN` is `${TUNNEL_TOKEN:-}` and
not `:?` like every other variable: interpolation is not profile-aware, so a required marker on a service
that is switched off still fails `docker compose config` for the whole stack, `app` included — which is
exactly the error a first deploy without a tunnel hits.

A **Dokploy domain on service `app`, port 8000** is how that happens — a click, not an edit, because
`app` is already on `dokploy-network` where Traefik can see it. **This is the step that puts Traefik in
the path**, and it leaves no trace in this repo: no `ports:` line, no Traefik label, nothing in
`docker-compose.yml` at all. That is exactly why `10.0.1.7` was a mystery worth measuring rather than
guessing — the file says the tunnel is the only way in, and the file cannot see a domain added in a UI.
`TRUSTED_PROXIES` must contain `dokploy-network`'s subnet for `X-Forwarded-For` to be read; the default
ranges already do, and `10.0.1.0/24` is the tighter value this deployment wants.
On a LAN host with no real name,
`<anything>-<dashed-ip>.sslip.io` resolves to that address (the pattern the dev Supabase already uses) with
the certificate provider left at none. `SITE_URL` must then be *exactly* the URL being browsed, scheme
included: set `https://` while serving plain http and the failure is a login that succeeds and bounces
straight back to `/admin/login`, because `SESSION_COOKIE_SECURE` is derived from `SITE_URL` (§14) and the
cookie is never returned. Every canonical, sitemap `<loc>`, OG url and JSON-LD `url` carries that host too,
so a publicly resolvable temporary domain is a publicly indexable one.

Neither of the two properties that used to lapse in this window does any more, and both were about the
client address. There is still no `CF-Connecting-IP` on a non-Cloudflare path, but there no longer needs
to be: the connection is the visitor, so `remote_addr` is the right answer and each address gets its own
throttle bucket. And the header is no longer spoofable past the limit from an untrusted peer (§12) — the
remaining hole is an insider inside `TRUSTED_PROXIES`, which narrowing it closes.

**`ADMIN_NETWORKS` becomes load-bearing the moment the tunnel is live**, because that is when the site
is reachable by people who are not in the building. Set it to the office range (`192.168.0.0/16` on this
deployment, client 2026-09-15) *before* switching the tunnel on, not after, and confirm from a phone on
mobile data that `/admin/login` answers 404 while `/` still loads. If the admin goes dark for everyone,
the cause is `TRUSTED_PROXIES`, not this (§12): clear `ADMIN_NETWORKS`, redeploy, fix the proxy list,
set it again.

Switching the tunnel on is therefore four things, not five: `TUNNEL_TOKEN`, `COMPOSE_PROFILES=tunnel`,
`SITE_URL` back to `https://www.iopstor.com`, and `TRUSTED_PROXIES` wide enough to include the network
`cloudflared` is on (unset is, since the compose bridge is private). **The Dokploy domain is no longer
deleted** — LAN access is permanent. But `SITE_URL` moving to `https://www.iopstor.com` is not free for
it: `SESSION_COOKIE_SECURE` is derived from `SITE_URL` (§14), so the admin cookie then carries `Secure`
and a browser on a **plain-http** LAN address will never send it back — a login that succeeds and bounces
straight to `/admin/login`, the same failure as setting the scheme wrongly. Public pages over http are
unaffected; only signing in is. So once the tunnel is live the LAN path has to be **https too** — a
Dokploy domain with a certificate — or LAN admins sign in on the public hostname and the bare port stays
for everything else. Decide that before switching `SITE_URL`, not after. Then step 6 below, and
`docker compose ps` must list `cloudflared` beside `app`. Once the tunnel is permanent, deleting the
`profiles:` line and restoring `${TUNNEL_TOKEN:?…}` puts the file back to one shape with nothing to
remember. **Confirm it with the panel at the top of `/admin/audit`** (§12): open it once from the LAN and
once through the tunnel, and both should show a real address.

**Realtime needs a tenant whose name matches the one it looks up, and a fresh self-hosted stack can
get this wrong on its own.** Supabase's Realtime container is multi-tenant even when self-hosted: it
seeds a tenant row at boot and then resolves one per connection. On the dev instance the seeded row
was `external_id = realtime-dev` while the running service asked for `realtime`, so **every** websocket
was refused at the handshake with a bare `403` — `Server: Cowboy`, no body, nothing in the app's own
logs, and the RLS policy never consulted because the connection never got as far as a channel. The
only place it is visible is the Realtime container's log:

```
error_code=TenantNotFound [error] TenantNotFound: Tenant not found: realtime
```

So when presence stays dark and the browser console says `CHANNEL_ERROR`, check that first:
`docker logs --tail 50 <stack>-realtime-1` and `select external_id from _realtime.tenants;`. The two
strings must be equal. Fixing the container's tenant-name environment variable is the durable answer,
because renaming the row alone is undone the next time the stack reseeds.

**The editor's collaboration needs nothing from the tunnel, and that is a deliberate reversal.** An
earlier version of this section told you to add a second Public Hostname rule sending `^/realtime/`
straight to Kong, move `cloudflared` onto `dokploy-network`, and set `SUPABASE_PUBLIC_URL`. **Do none
of that.** The channel is proxied by Flask instead (§12.3), so there is one ingress rule, one exposed
service, and `cloudflared` stays on `default` with no route to Supabase at all. The rule two
paragraphs down — *Studio and Kong never go on it* — now has no exception, which is worth more than
the round trip a direct socket would have saved: routing all of Kong would have published GoTrue's
`/auth/v1/*` including `signup`, which is enabled on these instances and which `throttle.py` does not
sit in front of.

What collaboration **does** need in production is the database half: `0009_realtime_channel_policy.sql`
and `0010` applied, and the realtime container restarted afterwards because it caches authorisation
per tenant. Verify with `curl -i https://www.iopstor.com/rest/v1/` returning the **Flask** 404 page and
not PostgREST (nothing of Supabase is reachable), and, signed in as an editor, the browser's network
tab showing polls to `/admin/realtime/v1/longpoll` — no WebSocket anywhere — with the console
reaching `SUBSCRIBED`.

**The order of first deployment matters, and getting it wrong fails the deploy.** A database without
`0000_bootstrap.sql` in it fails the `migrate` service, which exits 1 with `cli.py`'s message naming both
causes it could be; `app` is then left `Created` and never started, and Dokploy shows a failed deploy.
The stack is down either way — what this buys over the old arrangement, where migrate ran inside `app`'s
`CMD` under `restart: unless-stopped`, is that the reason is stated once, in a container that stays put
to be read, instead of scrolling past every few seconds in a container that keeps being replaced.

0. **Settle how the operator will reach Kong.** From a phone on mobile data, open the dev gateway URL.
   If it answers, the Dokploy host's 80/443 are public and a Traefik domain on Kong would put production
   Supabase on the internet — take 4a. If it times out, the host is LAN-only and 4b is available too.
1. Deploy the **Supabase template** into the production project. Record `ANON_KEY`, `SERVICE_ROLE_KEY`
   and `JWT_SECRET` from its compose environment.
2. Reach Studio the way step 0 chose → SQL editor → run `migrations/0000_bootstrap.sql` **once**.
3. Studio → Storage → create the bucket `media`.
4. **Size PostgREST before the app exists.** `-w 30 --threads 8` is 240 concurrent request slots in front
   of `PGRST_DB_POOL`, which the template ships at **10** with a 10-second acquisition timeout — so a
   burst does not queue politely, it 504s. Read it
   (`docker exec <supabase-rest-container> env | grep PGRST_DB_POOL`), raise it in the Supabase stack's
   compose environment in Dokploy — that is where it lives — and redeploy that service. Size it against
   Postgres `max_connections` (`show max_connections;` in Studio), remembering GoTrue, Storage, Realtime
   and Studio draw from the same budget: PostgREST must not be able to exhaust it alone. Then read Kong's
   service name (`docker ps --format '{{.Names}}' | grep kong`) and confirm it is on `dokploy-network`;
   that name is the app's `SUPABASE_URL`. For the operator's own access:
   - **4a — no domain, no published port on Kong.** SSH-forward to the container:
     `ssh -L 8000:$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <kong-container>):8000 <host>`,
     then `http://127.0.0.1:8000` serves Studio and the CLI both. The `docker inspect` stays inside the
     command because the overlay address changes whenever the container is recreated.
   - **4b — a Dokploy domain on Kong**, the development pattern. Only private because the host is.
5. Dokploy → **Compose** service → GitHub `primesukh/iopstor`, branch `main`, file `docker-compose.yml`.
   Set the environment from §14's table plus `TUNNEL_TOKEN` and `COMPOSE_PROFILES=tunnel` — without the
   second one `cloudflared` is not in the stack at all (above). Give the stack at least 1 GB: thirty
   `--preload` workers measure at 472 MB of real memory, and an OOM kill at boot is indistinguishable
   from a failed build in the log. Auto-deploy on push to `main` is a choice to make here, not a default —
   with it on, merging a PR redeploys production. Two settings on that screen decide whether this shape
   works at all, and both fail quietly rather than loudly, so check them before the first deploy: the
   stack must run as **plain Docker Compose, not `docker stack deploy`** (Swarm ignores `build:`,
   `restart:` and `depends_on`, so there is no image to run), and **service-name randomisation /
   isolated deployment must be off** (it suffixes service and network names, and then `http://app:8000`
   resolves to nothing and the tunnel answers 502). After deploying, `docker compose ps` should list a
   service named literally `app` **and one named `migrate`**. Migrate then applies `0001`–`0011`, and
   gunicorn starts. `migrate` showing `Exited (0)` beside a running `app` is the healthy steady state, not
   a half-failed deploy — it is a one-shot, and `app` would not be up if it had ended any other way.
6. Cloudflare Zero Trust → the tunnel that token belongs to → public hostname `www.iopstor.com` →
   `http://app:8000`. Send the apex to www with a redirect rule, which needs a **proxied** DNS record on
   the apex to fire at all.
7. Content, from a machine with the step 4 forward open and `SUPABASE_URL=http://127.0.0.1:8000`:
   `flask seed` → `flask create-admin EMAIL PASSWORD` → `flask import-media website_assets` → `flask seed`
   again, so the seeded pages pick their pictures up by filename. This runs from the developer's clone,
   not the container: `website_assets` is in `.dockerignore` and is not in the image. `create_app()` needs
   `SECRET_KEY` and `SITE_URL` here too, which the development `.env` supplies — `cli.py` never reads
   `SITE_URL`, so its development value is harmless.
8. Check `/healthz`, `/`, `/sitemap.xml` (every `<loc>` must read `https://www.iopstor.com`),
   `/robots.txt`, and sign in at `/admin` — the session cookie must carry `Secure`.

Two rules rather than steps: **the tunnel is the only *public* ingress** — the LAN port is deliberate and
stays, but nothing else joins them — and **Studio and Kong never go on either** — Flask is the only exposed
service, which is the whole reason `/media/<key>` exists (§8). A third way in would be a third answer to
"where is the visitor's address", so anything added here belongs in `TRUSTED_PROXIES` and in §12. Worth adding
once the site is live: a Cloudflare rate-limit on `/admin/login`, which §12 argues is a complement to the
sqlite throttle rather than a replacement, since the flood never reaches the origin.

**Turn on the edge cache for public HTML** (asked for 2026-09-16, when 2000 simulated visitors saturated the
box). The origin now sends `Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=300` on
public pages (§8), but **Cloudflare does not cache HTML without a Cache Rule**, so the header alone does
nothing. Add one: eligible for cache, respect the origin TTL, **excluding `/admin/*` and `/api/*`**. It works
only because anonymous pages carry no `Set-Cookie` (§7); do not undo that. The cost is the one
NON-TECHNICAL.md's *Quick answers* names: the origin drops a published page from its own cache instantly (the
epoch, §4), but the edge serves the old one for up to `EDGE_TTL`, and a scheduled `published_at` falling due
lags the same way. Nothing purges on publish — a Cloudflare purge call in the publish path is the fix if a
minute is ever too long. Without this rule the app is still far faster than it was, but the traffic still
arrives at the box; this is what stops it arriving at all.

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
| New block | `BLOCKS` entry + `EDITOR` names/seed/order (+ widgets/items/labels/choices for new keys) + `templates/blocks/<type>.html` + a `blocks_md()` branch (or `MD_SKIP`) + a `site.css` rule group; `/new-block` in `.claude/skills/` is the checklist |
| New taxonomy | A `taxonomies` row + the type's `taxonomies` array |
| Schema change | A new `migrations/NNNN_*.sql`, then `flask migrate`, then the code. A seeded `post_types` or `settings` row that already exists needs the migration to `UPDATE` it — the seed only inserts |
| New payment provider | A `PaymentGateway` subclass in `payments.py` + `PAYMENT_PROVIDER` |
| Theme change | `static/site.css` (admin extras in `static/admin.css`) |

---

## 17. Known ceilings

Marked in code with `# ponytail:` comments.

- **A failed audit write is swallowed** (`db._audit()`). The content write has already succeeded by the time it runs, so raising would show the editor an error for a save that did happen — and it is what lets the app run against a database where `0008` has not been applied yet. The cost is that the log can have a gap the log cannot report; the warning goes to `current_app.logger`. Watch those warnings.
- **`audit_log` grows without bound.** No retention job, no archiving. A post save stores the whole old `blocks` array and the whole new one, so a large page costs roughly 50 KB twice over. Point the diff at a revisions table, or trim by age, if it ever gets heavy.
- **The word diff is bounded at `DIFF_MAX` (2000 words a side).** Past that the two texts print plain with a note, because diffing two novels fifty rows to a page is real CPU on every load. Per-section diffing bounds the common case but does not retire the guard: one `rich_text` block can hold a whole page, and the types-differ branch still runs one page-wide diff. An unchanged run longer than `2 * CONTEXT` words collapses to its two ends (`.aud-gap`), so the marks are not buried in text nobody touched.
- **A save that changes the sections *and* a setting reports only the sections — for pages that predate `_id`.** When neither side can be keyed by name, `_blocks_fields()` falls back to comparing the two block-type lists and, when they differ, emits `_structural()` plus one page-wide word diff, never reaching `_data_rows()`. Anything edited since #68 takes the paired-by-name path instead and does not have this problem. Upgrade for the archive, if it ever matters: `difflib.SequenceMatcher` on the two type lists.
- **An entry cannot attribute interleaved editing.** A section's before/after is taken from the moment this person first touched it, so if a colleague edits the same section *between* two of their own edits, that colleague's words sit inside their entry. Real attribution needs per-character authorship — Yjs can carry it; the diff cannot.
- **A hard-deleted post loses its type on the screen** and falls back to "page or post" — `_post_context()` resolves the type from the row. Production never hard-deletes a post (deleting trashes it), so this only shows for rows the test cleanup removes.
- **A restore is not pre-checked against what it references.** Putting back a version whose featured image or parent page has since been deleted fails on the foreign key and surfaces through `_pg_error` as a 502 page rather than a sentence.
- **`/admin/audit` pages with offset/limit** like every other admin list. Deep pages get slower; keyset pagination if that day comes.
- **The sliding row is hard-coded to one content type.** `render_blocks()` sets `rail = pt_slug == "testimonial"`; nothing else can ask for it. A "Sliding row" checkbox on the `post_list` block is the upgrade, and it is deliberately not built yet — a field costs validation, a seed entry, a label, an `EDITOR["widgets"]` line and a test, and exactly one type wants this.
- **`site.js` has no error boundary and no feature detection.** It is 45 lines against `scrollTo`, pointer events and `matchMedia`, all of which every browser the client's visitors use has had for years; if any of it throws, the row silently stays a plain native scroller, which is the state the page is served in anyway. That is the whole reason the controls ship `hidden` and the script unhides them.

Shared editing (§12.3), all of them named in `admin.js`:

- **A section added, removed or moved by somebody else repaints the whole canvas**, which costs the local caret. Typing never comes through that path — y-quill applies a peer's words straight into Quill — so the common case is unaffected. Dispatching a structural delta to `canvasInsert` / `delBlock` / `moveBlock` by `_id` is the upgrade if it proves annoying in real use.
- **A repeater rides as one value.** The rows of a `faq`, `cards`, `stats` or `spec_table` block are a plain array in the `Y.Map`, not a nested CRDT, so two people editing two *different rows of one block* still lose a side — and an FAQ answer is a paragraph by any honest reading. Focus-wins stops it happening under a caret; per-row ids and a nested `Y.Array` is the upgrade. **This is the largest remaining gap in "both sets of words survive".**
- **A move is a delete and a fresh insert.** `Y.Array` has no move and one `Y.Map` cannot be integrated twice, so a peer typing into a section as somebody else moves it loses that sentence. y-utility's move, or a position CRDT, is the upgrade.
- **The writer's tab can die between an edit and its save.** The loss is bounded by the 1.5 s debounce, and the next writer's first save closes it. A **backgrounded** writer is the sharper version — browsers throttle timers in hidden tabs — and a `visibilitychange` hand-off is the upgrade.
- **Preview does not refresh the head, header, nav or footer between full renders.** It swaps `#main` to keep the reader's place (§12.2), so a Settings or Menus change made in another tab shows on the next Edit/Preview switch, which reloads the whole document. The page editor cannot change either of those, which is why this is a ceiling and not a bug.
- **A peer's prose arriving while nothing is mounted costs one conversion, not a stale page.** Preview replaces the canvas, so there are no Quill instances to derive a rich paragraph's HTML from, and MODEL used to sit at whatever it held when Edit was left — which Preview renders and Publish submits. `mirrorProse()` now converts the shared delta with an offscreen Quill of its own (§12.3) whenever no mounted editor owns the field, so both are current. What remains is narrow: a batch that carries a structural change *and* prose applies `fromY()` and returns, so that batch's prose waits for the next one — seconds, in practice, and nothing durable is at risk because the words are in `post_drafts.state` throughout.
- **Two editors opening in the same instant can still double-seed, and the repair is visible rather than silent.** Seeding waits for the roster to say nobody else is here (4 s backstop for a peer that never answers), so the normal case cannot collide — but two loads milliseconds apart both see an empty roster. `dedupe()` runs after every peer update and deletes a second copy of an `_id` it already has, saying so in the console. This was not theoretical: with no stored state it happened on **every** load, because the seed guard did not exist and every browser built its own document.

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
- A section effect plays once as the page loads, not when the reader scrolls to it, so on a long page it has finished before they arrive. Deliberate: the scroll-timeline version left a section in the first viewport part-way through its own animation, which showed a *wrong figure* under the hero — see §12.
- The counting figure needs `@property` (Chrome 85+, Safari 16.4+, Firefox 128+) for `--cv` to interpolate at all. Below that floor a counted figure reads `0`; untick *Count up from zero* for it. The floor is older than the `:has()` the mega panel already depends on, so nothing that can open the menu is caught by it.
- A page whose **first** section is a `hero` or a `columns` writes its own opening, so `post.html` draws no page head for it. That is what lets the Contact screen put its H1 beside the form — and it means a page an editor starts with a Columns section shows no title until they type one into it.
- `--w` is one measure per section, so a hero's headline and its paragraph (820px and 720px by default) take the same custom width. Per-element widths would need a key per element, which no editor has asked for.
- A custom width is pixels only — no `%`, `rem` or `vw`. The three named steps cover the proportional cases, and `section_style()` stays a digits-only check rather than a unit parser.
- `.cta` and table cells keep their own explicit `text-align`, so a centred section does not restyle a CTA band or a spec table's columns. `align_box` likewise only moves a section narrower than the page; a full-width one has nowhere to go.
- `public.media_file()` reads the whole file into memory before answering — `MAX_CONTENT_LENGTH` caps an upload at 20 MB, so the worst case is bounded. Stream it through httpx if big PDFs ever land.
- No server-side cache in front of Storage: a cold client costs one LAN round trip per file. The immutable year plus the ETag mean repeat views cost nothing, and `gunicorn --threads 8` keeps a page's images off each other's way; put a CDN or a disk cache in front if that stops being enough.
- `DummyGateway` moves no money.
- `apply_migration()` checks the ledger and inserts without a lock. Within one stack that no longer
  matters — `migrate` is a single one-shot service, so however many replicas of `app` there are, only one
  process runs migrations. What is still unguarded is two *stacks* against one database, which is not a
  shape this project has and would need a second Dokploy service pointed at the same Supabase. If it ever
  does, `perform pg_advisory_xact_lock(hashtext('apply_migration'))` at the top of that function is the
  fix, and note that `cli.py`'s "already exists" hint would point at `repair_schema_migrations.sql`, which
  is the wrong advice for a race.
- The container runs as root — no `USER` in the Dockerfile. Nothing needs it: the only writes are Storage
  uploads and `/dev/shm`.
- `/healthz` is liveness-only and touches nothing, so **nothing polls Supabase's health**. It used to run a
  PostgREST query, which made the 30-second `HEALTHCHECK` a dependency check: one Supabase restart marked a
  healthy container unhealthy, and the restart re-ran `flask migrate`, which needs Supabase too. Monitoring
  Supabase itself is a job for something outside the container. **The probe itself is `bash`'s `/dev/tcp`,
  not python**: `python -c "import urllib.request"` measured 115 ms of CPU a run (a bare interpreter is
  31 ms — the import is the rest), and one of those every 30 s drew evenly spaced ~45 % spikes on an
  otherwise idle container's Dokploy graph. The bash form is 4.4 ms and still does a real GET and a real
  status check; a socket-only probe was rejected because gunicorn's listen backlog accepts TCP with every
  worker wedged. It must be **exec form with `bash` named** — the shell form runs `/bin/sh`, which is dash
  and has no `/dev/tcp` — and it is the one place the image is relied on to carry `bash`, `grep` and
  `head`. All three are Debian-essential and were confirmed present in `python:3.13-slim`
  (`docker run --rm python:3.13-slim bash -c 'which bash grep head'`); re-check it if the base image
  ever changes, because the failure mode is a container that reports itself unhealthy forever.
- **Seven blocks are not on the new editing surface**, and on this content they are the Home page,
  NAS, Contact Us and About Us. They keep the original `contenteditable`, which also means the next
  PR's co-editing will not reach them. The long-term fix is not a bigger Quill: that markup is layout
  smuggled into prose (a spec table, a definition list, a founders grid) and belongs in block types.
- **Quill normalises on load, so the first save of a Quill block rewrites it** even if nobody typed —
  attribute order, whitespace — and the Activity diff reports it. Once per block, harmless, and the
  gate guarantees no tag or class moves.
- **The working draft is shared but not merged yet.** Two editors autosaving one page still overwrite
  each other every second or two, because the draft is one row and nothing reconciles two copies of the
  document — presence tells them somebody else is there, and that is all. The shared document is the
  next PR; until then autosave is best understood as per-editor crash recovery.
- **A session on a page nobody ever reopens stays pending.** With no scheduler, stale sessions are
  closed by whoever next touches the page; if nobody ever does, the `post_sessions` row sits there and
  its `audit_log` entry is never written. The row is not lost and a sweep command could close it, but
  there is none. Marked `# ponytail:` in `db.flush_sessions()`.
- **The session diff is whole-document.** Correct while only one person can edit at a time, and wrong
  the moment the document is shared — one editor's entry would claim everybody's work. Named in
  `initAutosave()` as the thing the shared-document PR has to narrow.
- **Presence is advisory, and its *where* is best-effort.** `data-b` is positional, so a structure fingerprint hides the
  section markers whenever two editors' block lists differ rather than drawing them on the wrong block (§12.3). A
  caret position also ages out after a minute, because the editor raises no event when focus leaves a field. The
  roster itself is always correct. All of this goes away when the document becomes genuinely shared.
- **Nothing tests the channel end to end.** The offline suite covers the room naming, the colour's stability across
  workers, and the proxy's own edges — that it refuses without a session or the csrf, pins the apikey, and turns a
  status the browser cannot read into one it can. The transport selection, the RLS policy and the token refresh are
  proved by hand with two browsers. A mock here would test the mock.
- **One worker thread per open editor, and a request rate that tracks messages rather than time.** Idle, that is one
  poll per editor every 10 s (Phoenix's window). Busy, a poll returns the instant a message arrives and is re-issued
  at once, so each message costs its sender a POST and every peer a returning poll plus a fresh one — two people
  typing is several requests a second. Concurrency stays at one thread per editor (8 of 240 slots at `-w 30
  --threads 8`), so the pressure is the request count, not the slots. It scales with editors, which nothing else in
  the app does. A websocket would cost far less and needs gevent or a broker to fan out across the thirty
  processes (§12.3).
- **Successful polls are filtered out of the access log** (`_QuietPolls` in `__init__.py`, installed on `werkzeug`
  and `gunicorn.access`). Left in, they drown every other line, and each one writes the query string — apikey and
  the Phoenix session `token`, a live credential — into a file that gets copied and kept. Non-2xx still prints, so
  a refusal or a failure is still visible; drop the filter to watch the transport itself.
- **The transport is selected through minified vendor internals.** `realtime.socketAdapter.socket.getLongPollTransport()`
  is not part of supabase-js's public API, so a bundle upgrade can move it and collaboration would break quietly.
  The fallback is written down in §12.3; check it when bumping `vendor/supabase.js`.
- **The conflict guard covers `posts` only.** `settings` and `menus` write through `set_settings()` /
  `set_menu()`, which are not keyed by `id`, so two people on the Settings or Menus screen still overwrite
  each other silently. Same shape, same fix (§4), not yet done.
- Thirty workers is where `media_file()` reading a whole object into memory stops being theoretical: 240
  request slots against a 20 MB `MAX_CONTENT_LENGTH` is a 4.8 GB worst case. Streaming through httpx is the
  upgrade named above; what the worker count changes is that it is now a number to watch, not an argument.
- The caches are **per worker process**, so thirty workers each render a cold page once rather than once between them, and each holds its own copy (a 26 KB page × `PAGE_MAX` 512 is the ceiling per worker). A shared cache would fix both and would also be another service to run on a box that is already short of cores. `CACHE_TTL` (30 s) and `PAGE_TTL` (30 s) are backstops only — the epoch file is what actually invalidates — so a write that somehow skipped `bump_epoch()` would still self-correct within half a minute.
- **Any write invalidates everything**, not just the pages it affects: the epoch is one stamp, so changing a lead's status drops every cached page. Writes are rare next to reads and the miss path is now 3–5 round trips, so this is deliberate; per-table stamps are the upgrade if an import ever makes it hurt.
- **Edge caching is opt-in and lags a publish.** The origin never does (the epoch drops the entry at once), but a Cloudflare Cache Rule serves for `EDGE_TTL` (60 s), and nothing purges it on publish — a `published_at` falling due lags the same way. A purge call on publish is the fix if a minute is ever too long.
- The redirect `hits` counter is now approximate in a second way: the row comes from the per-worker cache, so within one cache generation every visit writes back the same number. Nothing reads the column; a `bump_redirect(id)` RPC makes it exact.
- PostgREST calls wait `db.PGRST_TIMEOUT` (15 s), down from the library's 120 s default. Two minutes was longer than gunicorn's own 30 s worker timeout, so a merely-slow Supabase parked eight threads per worker until the worker was killed mid-request — a slow database read as a dead site. 15 s is far longer than any query here (the widest is the sitemap's 5000 rows) and safely inside that timeout, so overload now sheds load instead of swallowing the pool. It is a constant, not an env key, for the reason `STRESS_DB` is. It rides on `ClientOptions(postgrest_client_timeout=…)`, which the library marks deprecated but still passes on every client it builds (the warning predates this and fires on the default too); `ClientOptions(httpx_client=…)` is where it goes when that is finally removed.
- A redirect's `hits` is a read-then-write, so parallel visits lose counts. Nothing reads the column; a `bump_redirect(id)` SQL function called via `.rpc()` makes it exact if it is ever reported on.
- FAQPage JSON-LD is not wired up (§9).
- The stress-test run (§12) is bounded but coarse: it fans out across `_nprocs()` processes (× threads), lifting throughput ~core-count (measured ~900 req/s one process and *falling* with more threads, vs ~1200 rising, on an 8-core box against a scalable target) — not any fixed number, not 10k/s on modest hardware. Real concurrency is capped at `nprocs × PER_PROC` so a huge entered number is scaled down (the panel shows the driven count); the coordinator terminates the child processes `GRACE` seconds after the deadline/Stop rather than waiting a `REQ_TIMEOUT` per stuck request, so even a heavy self-test ends within ~2s of its duration. The coordinator and children live in whichever worker took the request, so a recycled worker freezes the run at its last `/dev/shm` flush; the only target-URL guard is the scheme (no SSRF allow-list — owner-only behind the office-only admin); nothing prevents two runs at once (one owner, their own doubled load); and a self-test's generators share the box with the workers they hit. What it surfaces first is the target's PostgREST pool, not the driver (§15 step 4).

Run `/ponytail-debt` to harvest the current ledger from source.

---

## 18. Working on it with an agent (`.claude/`)

`CLAUDE.md` at the repo root is the rulebook Claude Code loads every session; `.claude/` is what makes the rules cheap to follow.

| Path | What it does |
|---|---|
| `.claude/docs/design.md` | The architecture map — what exists, where, and the dated decision log. Updated in every PR that changes the shape of the system (the third doc, beside this one and NON-TECHNICAL.md) |
| `.claude/docs/requirements.md` | The client brief verbatim, the dated client decisions, and the status of each brief item |
| `.claude/skills/*/SKILL.md` | Slash-command procedures: `/pr`, `/docs`, `/new-block`, `/migration`, `/theme-check`, `/after-merge`, `/collab-check`. Each is a checklist of a thing that has gone wrong before |
| `.claude/settings.json` | Permission rules. The **deny** list is the hard rules made mechanical: no `flask migrate`/`seed`/`import-media`/`create-admin`, no `pip install`, no push to `main`, no hand edits to the generated `requirements*.txt`, `Pipfile.lock` or `.env`; `git merge` and `graphify update` sit on the **ask** list, so they prompt rather than run. `includeCoAuthoredBy: false` keeps the agent out of git authorship |
| `.claude/hooks/session-start.sh` | Runs at session start: branch, dirty files, last 12 commits, and how many commits behind `HEAD` the knowledge graph is |

The knowledge graph (`graphify-out/`, gitignored) has two halves. Its code nodes are re-extracted by git hooks (`graphify hook install`: `post-commit`, `post-checkout`) after every commit and branch switch, with no LLM. Its prose nodes and community labels come from the LLM pass, which runs **only when the user explicitly asks for `/graphify`** — no merge, pull or `/after-merge` triggers it, so the prose half may sit several merges behind. `/after-merge` still audits `.claude/` against the merged diff, so the written map never drifts more than one PR behind the code; anything that drifted is reported and carried by the next PR touching that area.
