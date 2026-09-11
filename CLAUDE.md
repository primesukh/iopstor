# IOPSTOR CMS — project instructions

WordPress + Elementor-Pro-style CMS in Python Flask for IOPSTOR (software-defined storage / cloud / HCI vendor).
Built and in use: the content system, the public site in the client's design (one stylesheet, `iopstor/static/site.css`, no JS), the browser admin at `/admin` with a document editor (a post opens as a blank page with the caret in it, `/` inserts a designed section, the page renders live through `render_blocks()` in an iframe, previews at 1440/834/390 — `docs/TECHNICAL.md` §12.1), SEO + AI output including a `.md` twin of every page, leads, a warranty register with a public serial check. Still open: a live payment provider (`DummyGateway` stands in).
Client requirements and dated client decisions: `.claude/docs/requirements.md`. Architecture spec (the map): `.claude/docs/design.md`.
Living documentation: `docs/TECHNICAL.md` (developers) and `docs/NON-TECHNICAL.md` (editors) — **both are updated with every feature**, and so is `design.md`.

## Stack

Python 3.13, Flask 3.1, **supabase-py 2.x** (PostgREST data access, Auth, Storage — all through the Kong gateway), PyJWT, gunicorn, pytest.
No SQLAlchemy, no direct Postgres connection, no ORM: rows are plain dicts.
Package manager: **pipenv** (`Pipfile` + `Pipfile.lock`, venv in `.venv/`). `requirements.txt` / `requirements-dev.txt` are generated
from the lock (`pipenv requirements > requirements.txt`, `pipenv requirements --dev-only > requirements-dev.txt`) and are what Docker installs. Regenerate both after any Pipfile change.
**Installing a new package: `pipenv install <pkg>` (or `pipenv install --dev <pkg>`) — never `pip install`** (denied in `.claude/settings.json`). Then regenerate both
`requirements.txt` and `requirements-dev.txt` from the lock in the same change; never hand-edit them (also denied). Docker only ever reads those two files.

Platform: self-hosted **Supabase** reached only via its Kong gateway (`SUPABASE_URL`) with the service-role key — PostgREST for data,
GoTrue for admin logins, Storage bucket `media` for uploads — and self-hosted **Dokploy** (Dockerfile + gunicorn).
Content is edited in the browser admin at `/admin` (login with a Supabase Auth account that has a `users` row); Supabase Studio works too.

## Layout

```
iopstor/__init__.py      create_app(), /healthz (liveness only, no DB call), blueprint + CLI registration, Jinja globals rupees()/media_url/media_alt/media_download; refuses to start without SECRET_KEY, SITE_URL or any SUPABASE_* key
iopstor/config.py        env → constants (module, no class)
iopstor/db.py            supabase-py clients + query helpers: table(), one(), rows(), insert(), update(), delete(), live(), select_posts(), tree(),
                         _audit()/audit_event() (every write is logged from inside the three write helpers), ist()/ist_input(),
                         with_paths()/ancestors()/hydrate() (hierarchical URLs, has_pages), unique_slug(), ensure_term(), paginate(), admin_counts(), post_types()/settings() caches
iopstor/auth.py          login/refresh/logout via GoTrue, verify_jwt() (local HS256), require_role(), create_auth_user()
iopstor/storage.py       save_upload()/delete_media() → Supabase Storage bucket + media table; public_path() (= media.url), fetch() (the bytes back)
iopstor/blocks.py        BLOCKS + EDITOR + LAYOUTS + NEVER_NESTED, validate_blocks(), section_class()/section_style(), render_blocks(), blocks_text(), blocks_md()
iopstor/seo.py           site(), build_meta(), jsonld(), md_url()
iopstor/payments.py      PaymentGateway, DummyGateway, GATEWAYS
iopstor/throttle.py      failed-password counter shared by every worker (sqlite on tmpfs); client_ip() reads CF-Connecting-IP
iopstor/admin_api.py     /api/admin/v1 (JWT-protected REST; apply_post() is the single validation path)
iopstor/admin_ui.py      browser admin at /admin: session login, post form + POST /admin/canvas + /admin/preview, media, leads, warranty, menus, settings, users, /audit (the activity log + restore)
iopstor/public.py        catch-all resolver (+ .md twins, /checkout), archives, /media/<key> file proxy, sitemap/robots/llms/feed, /api/v1 public read API, leads, checkout
iopstor/cli.py           flask migrate | seed | import-media | create-admin
iopstor/templates/       base.html post.html archive.html 404.html checkout.html _card.html (the one card macro), blocks/<type>.html (18, each a full-width <section>), admin/*.html
iopstor/static/site.css  the whole public theme: tokens at the top, header + mega panel + footer, .cards/.card/.btn/.section, layout group (.al-* .w-* .t-*), one rule-group per block
iopstor/static/admin.css admin-only rules layered on site.css; canvas.css = editor chrome inside the iframe; admin.js = the editor (plain JS, no build); vendor/sortable.min.js
docker-compose.yml       production only: `app` (this Dockerfile) + `cloudflared` as one Dokploy Compose service; `app` has no ports and no Traefik labels, so the tunnel is the only ingress
migrations/              0000_bootstrap.sql (run once by hand in Studio) + NNNN_name.sql applied by `flask migrate`; repair_schema_migrations.sql is a hand-run repair, not a step
tests/                   pytest: test_offline.py always; the rest are marked live and skip without the Supabase in .env
docs/                    TECHNICAL.md + NON-TECHNICAL.md — the two docs every change keeps current
.claude/                 docs/ (design.md, requirements.md), skills/ (the procedures below), hooks/session-start.sh, settings.json (enforced rules)
website_assets/          the client's mock (mock-website.html), pictures, partner logos — tracked; loaded into Supabase with `flask import-media`
graphify-out/            the knowledge graph — gitignored; code nodes rebuilt by git hooks per commit, prose + labels only when the user asks for /graphify
```

## Commands

```
pipenv install --dev                        # install (pipenv auto-loads .env)
pipenv run dev                              # dev server with debugger + auto-reload (= flask run --debug); FLASK_DEBUG=1 in .env does the same for `flask run`
pipenv run flask migrate                    # USER ONLY: apply unapplied migrations/*.sql through Supabase (after 0000_bootstrap.sql was run once in Studio)
pipenv run flask seed                       # USER ONLY: idempotent site-map seed (post types, pages, menus, settings); --reset-content also overwrites the seed pages' blocks
pipenv run flask import-media DIR           # USER ONLY: bulk-load a folder of images/PDFs into the media library (--dry-run to list)
pipenv run flask create-admin EMAIL PASS    # USER ONLY: Supabase Auth user + CMS admin row
pipenv run pytest                           # offline tests always; live tests against the Supabase in .env
```

The user's own dev server is usually already running on port 5000 — if you need to run a server yourself to test something, use a different port (e.g. `pipenv run flask run -p 5001`), never 5000.

## Skills (`.claude/skills/`)

The procedures this repo repeats, as slash commands. Load the one that fits before starting; each is a checklist that has been wrong before.

| Skill | Use it when |
|---|---|
| `/pr` | work is ready to push — pre-flight, commit style, PR body, the stop |
| `/docs` | a change is code-complete — which of the three docs it touches, in what voice |
| `/new-block` | adding or reshaping a section type — the eleven places a block lives |
| `/migration` | the schema or a seeded row must change — write the `.sql`, never run it |
| `/theme-check` | anything in `site.css`, a block template, `_card.html`, `admin.js` — screenshots at three widths |
| `/after-merge` | the user says a PR is merged — pull, prune branches, audit `.claude/` (no graph rebuild) |

## Workflow (non-negotiable)

**0. Check recent git history before planning or implementing anything.**
The session-start hook prints the branch, dirty files, the last 12 commits and how stale the graph is. Still run `git log -p` / `git show` on anything that looks related before touching a new feature or an existing one — recent commits often already cover, half-cover, or conflict with the task. Do this before graphify/grep in step 1.

**1. Explore with graphify first, then grep.**
Before answering an architecture question or touching an unfamiliar area, read `.claude/docs/design.md` and query the knowledge graph at `graphify-out/graph.json`:

```
graphify query "<question>"          # BFS traversal, broad context
graphify path "AuthModule" "db.py"   # shortest path between two concepts
graphify explain "apply_post"        # plain-language explanation of one node
```

The graph gives the shape: which modules connect, which communities a symbol bridges, where the god nodes are (`table()`, `require_role()`, `render_blocks()`, `one()`, `apply_post()`). *Then* grep and read the actual files to confirm the detail — the graph is the map, the source is the territory. Never skip straight to grep on a question the graph can answer, and never trust the graph alone for a claim you are about to write down.

**The code half of the graph maintains itself; the prose half is refreshed only when the user asks.** Git hooks installed by `graphify hook install` (`.git/hooks/post-commit`, `post-checkout`) re-extract changed code files in the background after every commit and branch switch (not after a `git pull`) — no LLM, a few seconds, log in `~/.cache/graphify-rebuild.log` — so the code nodes follow whatever branch is checked out. `.sql` files contribute nothing until `tree_sitter_sql` is installed beside graphify. The doc nodes (`CLAUDE.md`, `docs/*.md`, `.claude/docs/*.md`) and the community labels come from the LLM pass, and **that runs only when the user explicitly asks for it** — not from `/after-merge`, not on a branch, never unasked, because it costs real tokens on a shape that may still change. So the prose half can be many merges old: query it for the shape, then confirm every detail against source.

**2. Every feature goes on its own branch and PR. Never merge without being told.**

```
git checkout -b <type>/<short-name>    # feat/, fix/, docs/, chore/
# ... work, commit ...
/pr                                    # pre-flight, push, open the PR — then stop
```

Open the PR and **stop there**. Do not merge, do not squash, do not push to `main` — even when tests pass and the work is obviously finished (`git merge` and `git push origin main` are denied). Merging happens only when the user explicitly says so, on that specific PR — then `gh pr merge N --merge` (a merge commit, the remote branch kept, as every PR so far), and `/after-merge`. `gh` is installed and authenticated; `/pr` has the commands, including the REST call that replaces the silently-failing `gh pr edit`.

**Never mention Claude or Anthropic anywhere in git authorship** — no `Co-Authored-By: Claude ...` trailer, no `noreply@anthropic.com`, no "Generated with Claude Code" line, in commit messages or PR bodies/authors. Commits and PRs are authored as the user only (`includeCoAuthoredBy: false` in `settings.json` handles the trailer; the PR body is on you).

**3. Every feature updates all three docs, in the same PR.**
`docs/TECHNICAL.md` for developers (modules, schema, endpoints, contracts, ceilings), `docs/NON-TECHNICAL.md` for editors (what it does, in plain English, no jargon), and `.claude/docs/design.md` for the next agent (what exists and why, compressed; a dated row in its decision log for anything surprising). `/docs` says which sections. A feature is not finished until all three reflect it. If a change genuinely affects only some audiences, say so in the PR body rather than silently skipping the rest.

**4. `.claude/` is refreshed with every PR merge — mandatory, and the whole point of `/after-merge`.**
The PR itself carries the `design.md` change (rule 3). After the user merges, `/after-merge` on `main`: pull, then audit every written doc against the merged diff — **no graphify command runs, and the audit is not optional because of it** — layout in this file, `design.md` sections, `requirements.md` decisions, the skill whose procedure turned out incomplete, `settings.json` allow/deny for commands that prompted or must never run. Drift is reported to the user and folded into the next PR that touches the same area — no separate sync PR, and never a commit straight to `main`. A `design.md` row the merged PR should have carried (rule 3) is a miss to name, not a PR to open. Per-machine facts (which CLI is installed, how screenshots work) belong in Claude's memory, not in the repo.

So the full order is: branch → work → three docs → `/pr` → **stop** → (user merges) → `/after-merge`.

## Hard rules

- **Never write to the database, run migrations, or deploy anything without the user's explicit permission.** Reading data (via `db.py` helpers, Studio, or the Supabase MCP) is always fine. Never run `flask migrate`, `flask seed`, `flask import-media`, `flask create-admin`, or any other command that changes the database yourself (all four are denied in `settings.json`) — write the `.sql` file and hand it to the user so they can read it and apply it manually (Studio SQL editor or `flask migrate` on their own machine). `/migration` is the procedure.
- **Migrations are plain `.sql` files in `migrations/`, one per schema edit**, named `NNNN_short_name.sql` (zero-padded, applied in name order,
  tracked in `schema_migrations`; only a four-digit-prefixed name is a step). `0000_bootstrap.sql` is pasted once into Studio's SQL editor; it creates `apply_migration(name, sql)`
  (SECURITY DEFINER, executable by service_role only) which `flask migrate` calls per file over Kong — each file runs in one transaction.
  Workflow for a schema change: write the `ALTER`/`CREATE` SQL as a new file → tell the user it's ready for them to apply → update the code so it tolerates the column not existing yet → commit.
  **The seed only inserts** (`_get_or_create()`): a change to a seeded `post_types` row (field_schema, has_pages) or a setting needs a migration that `UPDATE`s the existing row as well.
- **Supabase is the only backend, reached only through Kong with the supabase library.** No `DATABASE_URL`, no psycopg, no SQLite **as an application data store**.
  The one exception is `throttle.py`: a failed-password counter in a `sqlite3` file on tmpfs (`/dev/shm`), which is shared memory for the ~30 gunicorn workers
  and is wiped by every redeploy. It holds no application data, nothing reads it but the throttle, and losing it costs nothing. Local development and tests
  point at the same self-hosted Supabase; the app refuses to start without `SECRET_KEY`, `SITE_URL`, `SUPABASE_URL`, both keys and the JWT secret.
- Every query goes through `iopstor/db.py`; use `db.select_posts()` (embeds `post_type`, `featured_media`, `terms`) and `db.hydrate()`/`db.with_paths()` so posts carry `path`.
  Never call `.delete()` without a filter (PostgREST would wipe the table).
- Content types (`post_types`) and taxonomies are **rows**, not code. Adding "Jobs" = a seed entry or an admin API call, not a table.
- Per-type fields live in `posts.meta` (JSON) described by `post_types.field_schema` (types: text, textarea, number, date, url, media, json, kv). Page content lives in `posts.blocks` (ordered `[{type, data}]`; a `columns` block nests one level).
- `iopstor/blocks.py` `BLOCKS` is the only place to add a block type; `/new-block` lists the other ten places it must also appear (`EDITOR` names/seed/order, the template wrapped in `<section class="section{{ cls }}"{{ sty }}{{ fe() }}><div class="wrap">…`, a `blocks_md()` branch, a `site.css` rule group, three offline tests). `hero` is the only block that renders its own `<h1>`, and `post.html` skips the page head when a post starts with a hero or a columns block. Unknown types are rejected on save. Anything an editor types that would land in a class or style attribute goes through a whitelist (`section_class()`, `col_widths()`) or is a checkbox.
- Theme changes go in `static/site.css` (shared by the public site, `body.admin` and the editor canvas; admin extras in `static/admin.css`, canvas chrome in `canvas.css`); no CSS framework, no build step, no JS on the public site. The client's mock in `website_assets/mock-website.html` is the design reference, and the client's later decisions in `requirements.md` override it (white header, price on the Buy button). Verify with `/theme-check`. Public forms post plain HTML to `/api/v1/leads` and get redirected back with `?sent=1`.
- Public queries go through `db.live(q)` (`status='published' AND published_at <= now()`; a future `published_at` = scheduled). A `has_pages=false` type gets `path=None` from `with_paths()`, and that one value removes its detail page, sitemap entry, `.md` twin and card link. `status='trash'` is a deleted post — the row is kept so it can be restored, and `live()` excludes it for free.
- **Every write is audited.** `db.insert()/update()/delete()` write an `audit_log` row themselves, so a new write path is logged without being asked; `_audit()` is silent outside a request context, which is what keeps `flask seed` out of it. Never write to `audit_log` through `insert()` (it recurses), and never add a route-level audit call for something the helpers already cover. A change that touches **no table of ours** — a GoTrue password, a login, a lockout — is invisible to `db.py` and needs an explicit `db.audit_event()`; `test_every_route_that_can_change_something_is_accounted_for` walks `url_map` and fails until a new non-GET route is written down as logged or deliberately not.
- URL scheme: pages at `/<slug>` (slug `home` = `/`), others at `/<url_prefix>/<slug>`, hierarchical types at `/<prefix>/<parent>/<slug>`,
  term archives at `/<taxonomy>/<term>`, `/<prefix>/<slug>/checkout` for a product with a price, and every resolvable URL + `.md` as its Markdown twin. `checkout` and `index` are reserved slugs. Slugs are unique per post type.
- **Every picture and PDF is served by the app**, at `/media/<bucket key>` (`public.media_file()`), never straight from the Storage gateway: Supabase is LAN-only and Flask is the only exposed service. `media.url` stores that path (`storage.public_path()`), which is why every reader — the `media_url`/`media_download` Jinja globals, `featured_media.url`, `seo._image()`, `blocks._media()`, the admin JSON — needs no special case. `media` is a reserved first URL segment.
- SEO output (meta, canonical, Open Graph, JSON-LD, sitemap, robots, llms.txt, llms-full.txt, `.md` twins, RSS) is server-rendered from `seo.py` + `public.py`; keep it there. `_indexable()` is the one gate for sitemap, llms and twins.
- Auth: admin API expects `Authorization: Bearer <Supabase JWT>`; the browser admin keeps the tokens in the signed session cookie and refreshes on expiry. Both verify locally with `SUPABASE_JWT_SECRET` (HS256). `users.id` = GoTrue `sub`. Browser POSTs carry a `csrf` field checked by `ui_required`.
  Roles: `editor` < `admin`. A GoTrue login without a `users` row gets 403.
- Payments: only `PaymentGateway` subclasses in `payments.py`; `PAYMENT_PROVIDER` env selects one. `dummy` is the placeholder.
- Ponytail mode is on for this repo: fewest files, stdlib first, mark deliberate ceilings with `# ponytail:` comments (38 in source; `/ponytail-debt` lists them). Non-trivial logic gets one small pytest test in `tests/test_offline.py` when it can run without Supabase.

## Env keys (`.env.example`)

`SECRET_KEY, SITE_URL, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, MEDIA_BUCKET, PAYMENT_PROVIDER, THROTTLE_DB, LOGIN_MAX_FAILURES, LOGIN_WINDOW`
**`SECRET_KEY` and `SITE_URL` have no defaults and sit in `create_app()`'s `REQUIRED`** beside the four `SUPABASE_*` — the app refuses to boot without them, because both used to fail silently: a signing key printed in this repo, and localhost canonicals plus a session cookie with no `Secure` flag.
Development also sets `FLASK_APP=iopstor` and `FLASK_DEBUG=1`. `GUNICORN_CMD_ARGS` is container-only and gunicorn reads it itself — `-w 2 --threads 8 --preload --access-logfile -` from the Dockerfile, raised in Dokploy, never in code.
Production: `SITE_URL=https://www.iopstor.com`, `SUPABASE_URL=http://<kong-service>:8000` (Kong's internal Docker name on `dokploy-network`), `GUNICORN_CMD_ARGS=-w 30 --threads 8 --preload --access-logfile -`, `TUNNEL_TOKEN` for the cloudflared container, and **no `FLASK_DEBUG`**. Set in Dokploy's environment only; `.env` and `.env.*` are both git-ignored. Runbook: `docs/TECHNICAL.md` §15.
Dev Supabase: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io` (LAN, self-signed cert on https → use http until a real cert exists).
`SUPABASE_JWT_SECRET`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` are the same values as `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY` in the Supabase compose env.
The `media` bucket is created in Supabase Studio; public or private no longer matters, since the app uploads and reads it with the service-role key and nothing a visitor loads points at it. RLS is enabled on all app tables (`migrations/0002_enable_rls.sql`; a new table repeats the line) so the anon key
cannot read drafts or leads; the app's service-role key bypasses RLS.

## First-time setup on a Supabase instance (development)

Production is a different and longer order — Supabase template, `PGRST_DB_POOL`, the Compose service, the tunnel, then content. It lives in `docs/TECHNICAL.md` §15 and is not repeated here.

1. Studio → SQL editor: paste and run `migrations/0000_bootstrap.sql`.
2. Studio → Storage: create a bucket named `media` (the instances so far are public; the app does not require it).
3. `pipenv run flask migrate` → `pipenv run flask seed` → `pipenv run flask create-admin EMAIL PASSWORD` → `pipenv run flask import-media website_assets` → `pipenv run flask seed` again so the pages pick up the pictures by filename.
4. If `flask migrate` stops on `relation "…" already exists`, the schema was built by hand: paste `migrations/repair_schema_migrations.sql` into Studio once and re-run.
