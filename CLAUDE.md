# IOPSTOR CMS — project instructions

WordPress + Elementor-Pro-style CMS in Python Flask for IOPSTOR (software-defined storage / cloud / HCI vendor).
Phase 1 = backend + a basic theme: one stylesheet (`iopstor/static/site.css`), block templates rendered as full-width sections, a browser admin at `/admin`. The drag-and-drop page builder is still to come (blocks are edited as JSON in the admin).
Client requirements: `.claude/docs/requirements.md`. Architecture spec: `.claude/docs/design.md`.
Living documentation: `docs/TECHNICAL.md` (developers) and `docs/NON-TECHNICAL.md` (editors) — **both are updated with every feature**.

## Stack

Python 3.13, Flask 3.1, **supabase-py 2.x** (PostgREST data access, Auth, Storage — all through the Kong gateway), PyJWT, gunicorn, pytest.
No SQLAlchemy, no direct Postgres connection, no ORM: rows are plain dicts.
Package manager: **pipenv** (`Pipfile` + `Pipfile.lock`, venv in `.venv/`). `requirements.txt` / `requirements-dev.txt` are generated
from the lock (`pipenv requirements > requirements.txt`, `pipenv requirements --dev-only`) and are what Docker installs. Regenerate both after any Pipfile change.

Platform: self-hosted **Supabase** reached only via its Kong gateway (`SUPABASE_URL`) with the service-role key — PostgREST for data,
GoTrue for admin logins, Storage bucket `media` for uploads — and self-hosted **Dokploy** (Dockerfile + gunicorn).
Content is edited in the browser admin at `/admin` (login with a Supabase Auth account that has a `users` row); Supabase Studio works too.

## Layout

```
iopstor/__init__.py      create_app(), /healthz, blueprint + CLI registration; refuses to start without the SUPABASE_* keys
iopstor/config.py        env → constants (module, no class)
iopstor/db.py            supabase-py clients + query helpers: table(), one(), insert(), update(), live(), select_posts(),
                         with_paths()/ancestors() (hierarchical URLs), unique_slug(), paginate(), post_types()/settings() caches
iopstor/auth.py          login/refresh/logout via GoTrue, verify_jwt() (local HS256), require_role(), create_auth_user()
iopstor/storage.py       save_upload()/delete_media() → Supabase Storage bucket + media table
iopstor/blocks.py        BLOCKS registry, validate_blocks(), render_blocks(), blocks_text()
iopstor/seo.py           site(), build_meta(), jsonld()
iopstor/payments.py      PaymentGateway, DummyGateway, GATEWAYS
iopstor/admin_api.py     /api/admin/v1 (JWT-protected REST; apply_post() is the single validation path)
iopstor/admin_ui.py      browser admin at /admin: session login (Supabase email/password), post forms per type, media, leads, settings, users
iopstor/public.py        catch-all page resolver, sitemap/robots/llms/feed, /api/v1 public read API, leads, checkout
iopstor/cli.py           flask migrate | seed | create-admin
iopstor/templates/       base.html (header/nav/footer), post.html, archive.html, 404.html, blocks/<type>.html (each a full-width <section>), admin/*.html
iopstor/static/site.css  the whole public theme: CSS variables at the top, header/footer, .cards/.card/.btn/.section, one rule-group per block
iopstor/static/admin.css admin-only rules (tables, forms, pills) layered on site.css so /admin shares the theme
migrations/              0000_bootstrap.sql (run once by hand in Studio) + NNNN_name.sql applied by `flask migrate` through the apply_migration RPC
tests/                   pytest: test_offline.py always; the rest run against the Supabase in .env and skip without it
docs/                    TECHNICAL.md + NON-TECHNICAL.md — the two docs every change keeps current
```

## Commands

```
pipenv install --dev                        # install (pipenv auto-loads .env)
pipenv run dev                              # dev server with debugger + auto-reload (= flask run --debug); FLASK_DEBUG=1 in .env does the same for `flask run`
pipenv run flask migrate                    # apply unapplied migrations/*.sql through Supabase (after 0000_bootstrap.sql was run once in Studio)
pipenv run flask seed                       # idempotent site-map seed (post types, pages, menus, settings); --reset-content also overwrites the seed pages' blocks
pipenv run flask create-admin EMAIL PASS    # Supabase Auth user + CMS admin row
pipenv run pytest
```

## Workflow (non-negotiable)

**1. Explore with graphify first, then grep.**
Before answering an architecture question or touching an unfamiliar area, query the knowledge graph — it is already built at `graphify-out/graph.json`:

```
graphify query "<question>"          # BFS traversal, broad context
graphify path "AuthModule" "db.py"   # shortest path between two concepts
graphify explain "apply_post"        # plain-language explanation of one node
```

The graph gives the shape: which modules connect, which communities a symbol bridges, where the god nodes are (`table()`, `require_role()`, `one()`, `apply_post()`, `render_blocks()`). *Then* grep and read the actual files to confirm the detail — the graph is the map, the source is the territory. Never skip straight to grep on a question the graph can answer, and never trust the graph alone for a claim you are about to write down.

**Never rebuild the graph during feature work.** The graph is refreshed at merge time only — see rule 2. A branch may be abandoned or reworked, so indexing it mid-flight burns tokens on a shape that may never reach `main`. Query a slightly stale graph, then confirm against source; that is what step 1 is for.

**2. Every feature goes on its own branch and PR. Never merge without being told.**

```
git checkout -b <type>/<short-name>    # feat/, fix/, docs/, chore/
# ... work, commit ...
git push -u origin <branch>            # then open the PR
```

Open the PR and **stop there**. Do not merge, do not squash, do not push to `main` — even when tests pass and the work is obviously finished. Merging happens only when the user explicitly says so, on that specific PR. `gh` is not installed on this machine; PRs go through the GitHub API using the existing git credential.

**Rebuild the graph as the last step of a merge, and only then:**

```
git checkout main && git pull        # after the PR is merged
/graphify . --update                 # re-extract only new/changed files
```

So the full order is: branch → work → both docs → push → open PR → **stop**. Then, once the user says merge: merge → pull `main` → `/graphify . --update`. The graph therefore always describes what is on `main`, never a half-finished branch.

**3. Every feature updates both docs, in the same PR.**
`docs/TECHNICAL.md` for developers (modules, schema, endpoints, contracts, ceilings) and `docs/NON-TECHNICAL.md` for editors (what it does, in plain English, no jargon). A feature is not finished until both reflect it. If a change genuinely affects only one audience, say so in the PR body rather than silently skipping the other.

## Hard rules

- **Migrations are plain `.sql` files in `migrations/`, one per schema edit**, named `NNNN_short_name.sql` (zero-padded, applied in name order,
  tracked in `schema_migrations`). `0000_bootstrap.sql` is pasted once into Studio's SQL editor; it creates `apply_migration(name, sql)`
  (SECURITY DEFINER, executable by service_role only) which `flask migrate` calls per file over Kong — each file runs in one transaction.
  Workflow for a schema change: write the `ALTER`/`CREATE` SQL as a new file → `flask migrate` → update the code that reads/writes those columns → commit.
- **Supabase is the only backend, reached only through Kong with the supabase library.** No `DATABASE_URL`, no psycopg, no SQLite. Local development and tests
  point at the same self-hosted Supabase; the app refuses to start without `SUPABASE_URL`, both keys and the JWT secret.
- Every query goes through `iopstor/db.py`; use `db.select_posts()` (embeds `post_type`, `featured_media`, `terms`) and `db.hydrate()`/`db.with_paths()` so posts carry `path`.
  Never call `.delete()` without a filter (PostgREST would wipe the table).
- Content types (`post_types`) and taxonomies are **rows**, not code. Adding "Jobs" = a seed entry or an admin API call, not a table.
- Per-type fields live in `posts.meta` (JSON) described by `post_types.field_schema`. Page content lives in `posts.blocks` (ordered `[{type, data}]`).
- `iopstor/blocks.py` `BLOCKS` is the only place to add a block type; add `templates/blocks/<type>.html` alongside (wrap it in `<section class="section"><div class="wrap">…`; `hero` is the only block that renders its own `<h1>`, and `post.html` skips the page title when a post starts with a hero). Unknown types are rejected on save.
- Theme changes go in `static/site.css` (public and admin share it; admin extras in `static/admin.css`); no CSS framework, no build step. Public forms post plain HTML to `/api/v1/leads` and get redirected back with `?sent=1`.
- Public queries go through `db.live(q)` (`status='published' AND published_at <= now()`; a future `published_at` = scheduled).
- URL scheme: pages at `/<slug>` (slug `home` = `/`), others at `/<url_prefix>/<slug>`, hierarchical types at `/<prefix>/<parent>/<slug>`,
  term archives at `/<taxonomy>/<term>`. Slugs are unique per post type.
- SEO output (meta, canonical, Open Graph, JSON-LD, sitemap, robots, llms.txt, RSS) is server-rendered from `seo.py` + `public.py`; keep it there.
- Auth: admin API expects `Authorization: Bearer <Supabase JWT>`; the browser admin keeps the tokens in the signed session cookie and refreshes on expiry. Both verify locally with `SUPABASE_JWT_SECRET` (HS256). `users.id` = GoTrue `sub`. Browser POSTs carry a `csrf` field checked by `ui_required`.
  Roles: `editor` < `admin`. A GoTrue login without a `users` row gets 403.
- Payments: only `PaymentGateway` subclasses in `payments.py`; `PAYMENT_PROVIDER` env selects one. `dummy` is the placeholder.
- Ponytail mode is on for this repo: fewest files, stdlib first, mark deliberate ceilings with `# ponytail:` comments. Non-trivial logic gets one small pytest test.

## Env keys (`.env.example`)

`SECRET_KEY, SITE_URL, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, MEDIA_BUCKET, PAYMENT_PROVIDER`.
Dev Supabase: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io` (LAN, self-signed cert on https → use http until a real cert exists).
`SUPABASE_JWT_SECRET`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` are the same values as `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY` in the Supabase compose env.
The `media` bucket must be created **public** in Supabase Studio. RLS is enabled on all app tables (`migrations/0002_enable_rls.sql`) so the anon key
cannot read drafts or leads; the app's service-role key bypasses RLS.

## First-time setup on a Supabase instance

1. Studio → SQL editor: paste and run `migrations/0000_bootstrap.sql`.
2. Studio → Storage: create a **public** bucket named `media`.
3. `pipenv run flask migrate` → `pipenv run flask seed` → `pipenv run flask create-admin EMAIL PASSWORD`.
