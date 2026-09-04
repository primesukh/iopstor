# IOPSTOR CMS — architecture spec (current state, 2026-09-03)

Decisions and commands: `CLAUDE.md` (repo root). Client brief: `requirements.md`. This file describes what is built.

## 1. Stack and platform

| Piece | Choice |
|---|---|
| App | Flask 3.1, Jinja, one CSS file, no JS framework, no build step |
| Data / auth / files | Self-hosted **Supabase**, reached **only through its Kong gateway** with `supabase-py` 2.x and the service-role key: PostgREST for rows, GoTrue for logins, Storage for uploads. No direct Postgres connection, no ORM; rows are dicts. |
| Tokens | PyJWT verifies Supabase access tokens locally (HS256 with `SUPABASE_JWT_SECRET`) |
| Packaging | pipenv (`Pipfile`, `Pipfile.lock`, in-project `.venv/`); `requirements*.txt` generated from the lock for Docker |
| Deploy | Dokploy → Dockerfile (python:3.13-slim, `pip install -r requirements.txt`, `flask migrate && gunicorn`) |
| Tests | pytest; `tests/test_offline.py` always, the rest against the Supabase in `.env` (skip without it) |

Rejected on the way (user decisions): SQLAlchemy + psycopg over `DATABASE_URL`, Alembic, Flask-Admin, uv. See git history.

## 2. Layout

```
Pipfile Pipfile.lock requirements.txt requirements-dev.txt pytest.ini .env.example Dockerfile .dockerignore CLAUDE.md
iopstor/__init__.py      create_app(): config, refuses to start without SUPABASE_*, blueprints, JSON/HTML 404, /healthz, CLI
iopstor/config.py        os.environ → constants
iopstor/db.py            supabase-py clients (service role, throwaway anon), query helpers, live(), select_posts(), with_paths()/ancestors(),
                         unique_slug(), paginate(), per-request caches for post_types()/settings()/hierarchy index
iopstor/auth.py          GoTrue login/refresh/logout, verify_jwt, current_user (bearer or session), require_role, create/delete auth user
iopstor/storage.py       save_upload()/delete_media() → Storage bucket + media table
iopstor/blocks.py        BLOCKS registry, validate_blocks(), render_blocks(), blocks_text()
iopstor/seo.py           site(), build_meta(post), jsonld(post, crumbs)
iopstor/payments.py      PaymentGateway, DummyGateway, GATEWAYS
iopstor/admin_api.py     /api/admin/v1 JSON API; apply_post() is the one validation path for posts
iopstor/admin_ui.py      /admin browser admin: session login, CSRF, forms that reuse apply_post()
iopstor/public.py        catch-all resolver, sitemap/robots/llms/feed, /api/v1 public read API, leads, checkout, 404 page
iopstor/cli.py           flask migrate | seed [--reset-content] | create-admin
iopstor/static/          site.css (public theme + variables), admin.css (admin-only rules on top of site.css)
iopstor/templates/       base.html post.html archive.html 404.html blocks/<type>.html admin/*.html
migrations/              0000_bootstrap.sql (run once in Studio) 0001_initial.sql 0002_enable_rls.sql
tests/                   conftest.py test_offline.py test_auth.py test_admin_api.py test_admin_ui.py test_public.py
```

## 3. Tables (see `migrations/0001_initial.sql`)

| Table | Purpose / notable columns |
|---|---|
| `post_types` | content types as rows: `slug, name, url_prefix ("" = top-level pages), hierarchical, field_schema [{key,label,type,required}], taxonomies [slugs], jsonld_type, in_sitemap` |
| `posts` | everything editable: `post_type_id, parent_id, slug, title, excerpt, blocks [{type,data}], meta {}, seo {title,description,canonical,robots,og_image}, status draft/published, published_at (future = scheduled), featured_media_id, author_id, menu_order`; unique `(post_type_id, slug)` |
| `taxonomies`, `terms`, `post_terms` | generic classification; `post_terms` is a junction with composite PK so PostgREST can embed `terms(*)` |
| `media` | `key` (bucket path), `url` (public URL), `filename, mime, size, alt, uploaded_by` |
| `users` | `id` = GoTrue user id, `email, name, role editor/admin` — the row is what grants CMS access |
| `leads` | contact / quote / career submissions: `kind, name, email, phone, company, message, post_id, data {}, status new/handled` |
| `settings` | `key` → JSON `value` (site_name, tagline, logo_url, default_og_image, social_links, ga_id, contact_email, contact_phone, address, robots_extra) |
| `menus` | `slug` (header/footer) → `items [{label, url, children}]` |
| `redirects` | `from_path → to_url`, `code`, `hits` |
| `payments` | `provider, provider_ref, post_id, lead_id, amount, currency, status created/paid/failed, raw` |
| `schema_migrations` | applied migration filenames (created by the bootstrap) |

All NOT NULL columns carry DB defaults; `updated_at` is maintained by `moddatetime` triggers. RLS is enabled everywhere (0002) so anon/authenticated keys see nothing; service_role bypasses.

**Migrations.** One `.sql` file per schema edit, applied in name order by `flask migrate`, which calls the `apply_migration(name, sql)` RPC (SECURITY DEFINER, executable by service_role only, runs the file + records it + reloads PostgREST's schema cache in one transaction). `0000_bootstrap.sql` creates that function and must be pasted into Studio once.

## 4. Posts as dicts

`db.select_posts()` embeds `post_type:post_types(*)`, `featured_media:media(*)`, `terms(*, taxonomy:taxonomies(*))`. `db.with_paths()` / `db.hydrate()` add `path` using a per-request index of `{id: slug, parent_id, title}` per hierarchical type. `db.live(q)` = `status=published AND published_at <= now`. Term filtering uses `post_terms!inner(term_id)` + `.eq("post_terms.term_id", id)`.

## 5. Blocks

`BLOCKS = {type: (required, optional)}`: hero, rich_text, image, gallery, cards, cta, faq, stats, testimonial, embed_html, post_list (post_type, heading, term, limit, top_level), spec_table, contact_form. Each has `templates/blocks/<type>.html` rendered as a full-width `<section class="section"><div class="wrap">`; `hero` renders the page `<h1>` and `post.html` omits its own title when a post starts with a hero. `validate_blocks` rejects unknown types / missing required fields; `blocks_text` flattens text in a fixed field order (JSONB does not keep key order) for `llms-full.txt` and the public API `text` field.

## 6. Auth

- Admin API: `Authorization: Bearer <access token>`; `POST /api/admin/v1/auth/login|refresh|logout`, `GET /auth/me`. 401 bad credentials, 403 GoTrue user without a `users` row.
- Browser admin: same login through a form; `access_token` + `refresh_token` live in the signed session cookie (SameSite=Lax, Secure when SITE_URL is https); `auth._session_token()` refreshes silently on expiry. Every POST carries a per-session `csrf` field checked by `ui_required`. `next` redirects only accept relative same-origin paths.
- Roles: editor (create/edit content, media, leads) < admin (delete posts, post types, settings, users, redirects).
- Login sign-in uses a throwaway anon client (never the service-role client: supabase-py would swap its storage bearer).

## 7. URLs (public)

| Type | URL |
|---|---|
| page | `/<slug>`; slug `home` = `/` (`/home` → 301 `/`) |
| post (blog) | `/blog/<slug>`, archive `/blog` |
| service (hierarchical) | `/services/<group>/<slug>`, `/services/<group>`, archive `/services` (top level only) |
| case_study / event / partner / datasheet / product | `/<prefix>/<slug>`, archive `/<prefix>` |
| term archive | `/<taxonomy>/<term>` e.g. `/industry/finance` |
| crawler files | `/sitemap.xml`, `/robots.txt`, `/llms.txt`, `/llms-full.txt`, `/feed.xml` |
| public JSON | `/api/v1/post-types`, `/posts?type=&term=&page=`, `/posts/<type>/<slug>` (includes `text`), `/taxonomies/<slug>/terms`, `/menus/<slug>`, `/settings`, `POST /leads`, `POST /payments/checkout`, `POST /payments/webhook/<provider>` |

Resolver order: trailing slash → 301; `redirects` table; post type by first segment; page slug; taxonomy/term; 404 (HTML page, JSON under `/api/`). `POST /api/v1/leads` from an HTML form (non-JSON) redirects back to `back?sent=1`; the `website` field is a honeypot.

## 8. SEO

`seo.build_meta` → title (`seo.title` or `"<title> | <site>"`), description (excerpt fallback), canonical, robots, OG/Twitter image. `seo.jsonld` → Organization + WebSite on the home page, BreadcrumbList elsewhere, then per `post_types.jsonld_type`: BlogPosting/Article, Product (offers from meta price/currency/sku), Service, Event; FAQPage when a page has a faq block. Scheduled posts and drafts never render publicly.

## 9. Theme

`static/site.css`: CSS variables (`--navy`, `--accent`, widths) at the top; sticky navy header with hover dropdowns and a checkbox-driven mobile menu; `.cards/.card`, `.btn`, `.section/.wrap`; one rule group per block; footer with tagline, footer menu, contact + social links. `static/admin.css` adds tables, forms, pills and the login card on top of it, so the admin looks like the site. Logo = settings `logo_url` (falls back to the site name).

## 10. Admin UI (`/admin`)

Dashboard (counts per type, new leads) → per-type lists (search, status filter) → post form: title, slug, excerpt, meta fields generated from `field_schema` (text/textarea/number/date/url/media/json), blocks in a visual editor (canvas / form / JSON tabs) with a block reference panel, SEO overrides, status, publish date, parent (hierarchical), menu order, featured image, taxonomy checkboxes, delete (admin). Media (upload/delete), Leads (mark handled), Settings and Users (admin). The visual page editor replaced the JSON block editor; the JSON textarea remains the escape hatch and the only field that POSTs.

## 11. Seed

`flask seed` is idempotent: 8 post types with field schemas, taxonomies (industry, solution, category, tag), the services tree (5 groups, 17 services), 7 case studies with industry/solution terms, 2 events, pages (home with hero/service cards/stats/case studies/CTA, about, careers, contact, technology partners), settings defaults, header/footer menus. `--reset-content` overwrites the blocks/excerpt/meta of those seed-defined posts only.

## 12. Payments

`PaymentGateway` interface + `DummyGateway` (`redirect_url = /api/v1/payments/dummy/<id>`; webhook body `{payment_id, status}`). `POST /api/v1/payments/checkout {product_id, email, name}` creates a lead + payment row. A real provider = subclass with signature verification, registered in `GATEWAYS`, selected by `PAYMENT_PROVIDER`.

## 13. Known ceilings (`# ponytail:` comments)

HS256-only JWT verification; hierarchy index assumes < 2000 posts per hierarchical type; single sitemap < 5000 URLs; honeypot-only spam control on forms; raw HTML in `rich_text`/`embed_html` trusted (staff-only authors); blocks edited as JSON.
