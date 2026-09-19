# IOPSTOR — client requirements (brief verbatim from 2026-09-03; decisions and status to 2026-09-15)

The brief is kept word for word. Everything under **Decisions** is dated and appended to, never rewritten; a later line overrides an earlier one. What the brief asked for versus what exists is in **Status against the brief** at the end.

## Services

- Storage
    - NAS
    - DAS
    - SAS
    - AWS Integration (DR)
- Hyper Converge Media
    - Proxmox
    - VMware
- Cloud
    - Desktop as a Service
    - Storage as a Service
    - VPS
    - Linux Containers
    - Serverless
    - S3 Bucket Solutions
    - Disaster Recovery as a Service (DRAAS)
- AI
    - On-prem AI Servers
- Software Based
    - SQL Server
    - Tally
    - SAP

## Website Content

- Case Studies
    - LKS - Finance (Virtualization)
    - SCM - Education (Big Data)
    - FM - Post Production (Media)
    - DCSL - Services (Private Cloud)
    - SSC - Distribution (Private Cloud)
    - ATPL - Travel (HCI)
    - KLPL - Logistic (Private Cloud)
- Blogs
- Technology Partners
- Company
    - About Us
    - Events
        - Broadcast 2018
        - Seagate Collaboration December 2018
    - Careers
    - Contact Us
- Datasheet
- Products (with payment gateway — placeholder for now)

## Competition

- Netweb Technologies - https://www.netwebindia.com/index.php
- ESDS - https://www.esds.co.in/

## Software Prerequisites

- Content Management System like Wordpress (+ Elementor Pro style page building)
- Easy to use admin panel for non technical persons
- We need to make it easier for AI to scrape data
- We also need the website to be SEO compatible
- Backend structure first; UI is a later phase

## Company blurb (About Us seed)

IOPStor specializes in Software define storage and solves productivity problems is SMB and large enterprises faced on regular basis.

With our unique convergence of hardware, software, and storage expertise, we bring you IOPStor flash and all-flash storage arrays, offering enterprise reliability and performance at a value unheard of in storage.

Unify your business-critical applications with a IOPStor storage array that fits the performance and capacity requirements of your application. IOPStor unifies block and file storage, grows to nearly 5PB in a rack, is available in hybrid and all-flash configurations, and uses the Block storage file system to guarantee data stays pristine and safe.

With the need of Storage growing and with a opportunity to server a un-served market of customized storage IOPStor was founded by Gulbirr Bhatia Prime ABGB and Noshir Dalal who both have a cumulative experience in the IT space for the more than 50 years

## Assets received

In `website_assets/` (tracked in git since 2026-09-10 — the client's files, loaded into the media library with `flask import-media website_assets`, which runs from a clone because the folder is in `.dockerignore` and never reaches the image):

- `mock-website.html` — the visual design the theme is built from. It is the reference for every theme question; `/theme-check` compares against it.
- Pictures: `Untitled-4.png` (home hero), `banner-homepage-96tb.png` (ZFS section, IOPStor Edge), `DSC_0305n.png` (IOPStor Classic), `background1.jpg` (About backdrop), `Feature.jpg`, `Services.jpg`, `Untitled-3.png`, `iopstor-logo-white.png`, `iopstor_logo-png1.png` (site logo).
- `partners/` — fourteen technology-partner logos, one per seeded partner post.

## Decisions taken with the client

| Date | Decision |
|---|---|
| 2026-09-03 | Self-hosted via Dokploy (Docker) |
| 2026-09-03 | Self-hosted Supabase, accessed **only through its Kong gateway with the Supabase Python library** (PostgREST for data, GoTrue for logins, Storage for uploads). No separate database, no direct Postgres connection. Dev gateway: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io` (http until a real certificate exists) |
| 2026-09-03 | pipenv for dependencies, plus a generated `requirements.txt` |
| 2026-09-03 | Database migrations are plain `.sql` files, one per schema edit |
| 2026-09-03 | A basic themed public site and a browser admin (`/admin`) are wanted in phase 1 after all; the drag-and-drop page builder was deferred to phase 2 |
| 2026-09-03 | Local development runs `flask run --debug` (auto-reload) |
| 2026-09-04 | Phase 2 came early: the admin is a **document editor** — a post opens as a blank page you type into, `/` inserts a designed section, sections drag, columns hold sections, and the page previews live at desktop / tablet / phone widths |
| 2026-09-04 | The agent never writes to the shared dev database: migrations and seeds are written as files and applied by the client's developer by hand |
| 2026-09-07 | **Warranty register**: staff record serial number, customer, email, purchase and expiry dates, AMC and remarks under `/admin/warranty`; the public site gets a *Warranty check* section where a customer types a serial and sees the record. **The whole record, name and email included, is shown to anyone who has the serial** — the client's choice, to keep the check to one box. Remarks stay private unless ticked public |
| 2026-09-07 | The public theme follows the client's mock (`website_assets/mock-website.html`): palette, Manrope + IBM Plex Sans, mega menu for services, animated hero, dark case-study band |
| 2026-09-07 | The client's photographs and partner logos are bulk-loaded with `flask import-media` and wired into the seeded pages by filename |
| 2026-09-10 | The Supabase gateway is **not reachable from a visitor's browser** — it stays on the LAN and only the Flask app is exposed. The app serves every picture and PDF itself at `/media/<bucket key>`, fetching the bytes from Storage server-side. This overrides the 2026-09-03 line's implication that a browser loads uploads straight from Storage |
| 2026-09-08 | The **header is white with black text and the logo in its own colours**, not the mock's black; the footer stays dark. The favicon is the IOPSTOR mark at every size |
| 2026-09-09 | **Technology partners have no pages of their own** — a partner is a logo on somebody else's page; `/partners` stays as the logo wall |
| 2026-09-09 | **Prices are rupees only**; the currency choice is gone from products and settings. The price shows on the Buy button, not as a detail tile. Specifications are typed as label/value rows and keep their order |
| 2026-09-09 | **Every page has a Markdown twin** (`/about-us.md`, `/index.md`, …) for AI crawlers, linked from `<head>` and from `llms.txt`; `llms-full.txt` is real Markdown. Nothing is generated to disk |
| 2026-09-09 | The payment provider stays a placeholder until the client names one |
| 2026-09-10 | **A Numbers or Rich text section can carry an effect** — fade in, gradient, highlighter sweep — and a Numbers section can count its figures up from zero. Each figure can override the band it sits in |
| 2026-09-11 | **An audit log that is the source of truth for everything every user does** — which post was created, edited or deleted, which setting was changed, who signed in and who got a password wrong, each with the date and time in **IST**. Administrators only. An edit records the old and the new version and can be **restored**. **A deleted post is never really deleted**: it moves to a trash an administrator can restore it from, while the delete button goes on warning that it cannot be undone |
| 2026-09-11 | **The Activity screen is for non-technical readers.** No column name, no table name, no raw JSON, no status code on it — a row has to be readable aloud by somebody who has never seen the database. "Restore", not "Put it back the way it was" |
| 2026-09-11 | **Everything means everything**: a password change (the editor's own and one an administrator sets for somebody else), a user created or deleted, media uploaded, renamed or removed, leads and their status, warranty records, settings, menus, and every content type by its own name — page, blog post, service, case study, event, technology partner, datasheet, product |
| 2026-09-11 | **The test suite must not appear in the log.** Live tests run against the development Supabase, and their rows were reaching the client's Activity screen |
| 2026-09-11 | **A page edit has to say what was changed**, not print the page twice — which section, which setting, and what it became, in the words the editor picked it by |
| 2026-09-10 | **The production stack**: a Dokploy project holding one Compose service — the app and a Cloudflare Tunnel container side by side — with the database from Dokploy's Supabase template, the code pulled from GitHub (`primesukh/iopstor`), and the environment set in Dokploy. The site is public at **`https://www.iopstor.com`** through the tunnel, which is the **only** way in: Supabase and its Studio stay unreachable from the internet, and the app itself has no public port. Thirty gunicorn workers. Production and development are separate databases with separate logins and no content passing between them |
| 2026-09-18 | **The brand sheet arrived**: *IOP / Electric Blue* and *STOR / Deep Charcoal `#2E3133`*, with the logo artwork. Two calls follow from it (user, 2026-09-18). **The blue is `#3573B9` — the fill actually inside the artwork — not the `#1F6DB2` printed on the sheet**, which is a visibly more saturated blue; the artwork wins so the logo and the buttons beside it match, and this supersedes the `#4273b8` row below. **The charcoal is type, not surface**: it becomes the heading and body colour, while the dark bands, the footer and the admin sidebar stay near-black — a charcoal band would put the sidebar's labels at 3.6:1 and the brand blue on it at 2.43:1. The logo file itself replaces the one carrying the old blue |
| 2026-09-12 | **The brand blue is `#4273b8`**, not the mock's `#008cf7`. The darker hover, the pale tint and the lighter shade used on the black bands are all re-derived from it, and the favicon's bar changes with them. The logo file the client uploaded still carries the old blue and needs replacing |
| 2026-09-10 | **The Contact Us quote form sits on the Careers grey panel**, not the mock's black card. Colour only: it still asks what the visitor is interested in and how many users, and still files a `quote` lead |
| 2026-09-12 | **Two people must be able to edit one page at the same time without destroying each other's work.** The question that started it: *"what if multiple people are editing the same page?"* |
| 2026-09-13 | **Not last-writer-wins, and not a lock: both sets of changes are kept.** *"just like google docs it saves both of the changes combine i want that kind of experience"* — which ruled out an interim design where the loser's autosave simply paused |
| 2026-09-14 | **Down to the word, inside one paragraph.** *"two persons editing the same para doesn't make the last one editing the winner it would update word for word just like google docs collaboration"* — this is what made a text CRDT, and therefore a real editor under it, a prerequisite rather than a later stage |
| 2026-09-14 | **The activity log records what each person changed, per sitting, closed after fifteen minutes of inactivity.** *"when there is no activity for 15 mins by that user keep that audit what changes they had made as we want the audits of the user what they have changed in the blogs"*. Refined 2026-09-15: leaving the page — a reload, a trip to another screen — does **not** end a sitting; only the fifteen minutes do |
| 2026-09-14 | **The button says `Publish` when the page is live and `Save` when it is not**, and the right-hand panel (title, web address, status, summary, SEO) does **not** save itself — it moves only when the button is pressed |
| 2026-09-15 | **A section the shared editor cannot hold should become a section type, not a bigger editor.** Home's panel and NAS's feature list became `points` and `definitions`; Contact Us keeps the old editor until its details can be read from Settings instead of frozen into the page; NAS's specification table and the About Us founders grid stay as they are |
| 2026-09-15 | **Collaboration must reach Supabase through the Flask app, not through the tunnel.** *"our database is not directly exposed to the WAN its only accessable to the flask server so we need to route the webhooks for collaborative work as well just like images that we do"* — the documented plan had been to route `^/realtime/` from the Cloudflare tunnel straight to Kong; that is abandoned. The editor's channel is proxied by the app at `/admin/realtime/v1/longpoll`, exactly as every picture is proxied at `/media/<key>`, so Flask stays the only exposed service. Two decisions taken with it: `SUPABASE_PUBLIC_URL` is **deleted** rather than kept as a switch ("one path, dev exercises production"), and collaboration goes **live on deploy** rather than staying off — which makes applying `0009` and `0010` to the production database a prerequisite of the deploy, not a follow-up |
| 2026-09-15 | **Migrations run on a deploy, never on a restart or a rebuild.** *"run migrations on a redeploy, but only on deploy and not on rebuild"* — `flask migrate` became a one-shot `migrate` service in the compose stack that the app waits on, so a crash or a host reboot never touches the schema, a rebuild of unchanged code finds nothing to apply, and a failed migration states its reason once in a container that stays put. The trade, agreed before it was built: an app container restarting during a Supabase outage now serves errors until Supabase is back, instead of refusing to boot |
| 2026-09-15 | **Preview follows a colleague's typing without moving the reader.** *"preview should live update just like editor"* — a colleague's paragraph shows in Preview as it does in Edit, the page does not jump when it arrives, and Publish never sends the page an edit behind. Of three refresh rates offered, **two renders a second** was chosen |
| 2026-09-15 | **The admin panel is reachable from the office network only; the public site stays open to everyone.** *"i want the /admin pages to be only accessable from the lan only which is this ip http://iopstor-192-168-5-8.sslip.io/ and only normal webpages would be accessable from anywhere/cloudflare tunnel"* and *"so we have have security layer for admin access as employee can only access from the office premises itself"* — `ADMIN_NETWORKS=192.168.0.0/16` (the user chose the wider `192.168.0.0/16` over the server's own `192.168.5.0/24`, so staff on another office subnet are not locked out). Enforced as a **404** on both `/admin` and `/api/admin/v1`, login form and token endpoint included — the user chose the silent 404 over a friendlier "office network only" 403, so a scanner learns nothing. A layer in front of the password, not a replacement for it |
| 2026-09-15 | **The real visitor address, not the equipment in between, in the activity log and the login throttle.** *"we want the actual real ips of the user in audit logs and rate limits as well instead of 10.0.1.7"* — `10.0.1.7` turned out to be `dokploy-traefik`; a forwarding header is now believed only from a peer inside `TRUSTED_PROXIES` (`10.0.1.0/24` on this deployment) |
| 2026-09-15 | **No admin or private-API address may appear in the sitemap, the RSS feed or llms.txt.** *"sitemap, rss, llms.txt should never include admin pages/api"* — enforced in `_indexable()` and refused at save (`db.RESERVED_SEGMENTS`). Two calls taken with it: the **public** `/api/v1` stays advertised in llms.txt (read-only published content, which is what llms.txt is for), and `robots.txt` **stopped** disallowing `/admin` — it was the only public statement that an admin exists, and protects nothing now that `/admin` 404s outside the office |
| 2026-09-16 | **The technology-partner logos show in full colour, and grow when you point at one** — not the mock's greyed, faded strip. The mock (and the theme after it) ran the row at `grayscale(1)` and `opacity:.7`, with colour returning only under the pointer; the client asked for the marks as their own files carry them. A first pass lifted the tile 2px, the movement the site's cards make; the client asked for something bigger and smoother, so the mark now grows to 1.14x over .3s on an ease-out curve |
| 2026-09-16 | **The partner logos must sit in equal rows, and stay equal as partners are added** — fourteen were laid out 8 + 6. *"all line should have same number of partners"*, and *"this setting should be configurable from the edit page"*, so it is a control on the Automatic list section (**Items per row** → *Even rows*) rather than a number fixed in the theme |
| 2026-09-16 | **Technology Partners comes out of the header menu** — *"from header remove technology partners"*. The page is not deleted: it stays at `/technology-partners`, stays in the sitemap and stays linked from the footer; only the top-navigation entry goes |
| 2026-09-18 | **The phone menu opens with everything collapsed, and the partner logos are too big on it** — *"by default in mobile header/burger icon all categories should be closed and can be opened by tapping on it"*, then *"close services company etc as well"* for the top level, and *"when in mobile, the technology partners become too big"*, both with screenshots. Neither is a design change on desktop: the menu's expanded-by-default list and the two-across logo wall were only ever the phone fallback |
| 2026-09-16 | **The home page's testimonials become a sliding row, and testimonials become content staff can add** — *"in home page under testimonials section we need something like this … which would be auto scrolling and they can control with mouse as well"*, and *"and ability to add testimonials directly"*, with three reference themes attached. Four decisions taken from the ask: **layout** — a centred eyebrow + heading with the cards in a row beneath, the shape of two of the three references, rather than the third's heading-and-button beside the row; **controls** — arrows, dots and click-drag were chosen over the CSS-only alternative (drift + pause on hover + wheel/swipe) with the cost stated plainly, which makes this **the first first-party JavaScript the public site has ever carried**; **card fields** — job title, company, photo and a star rating, *"everything would be optional to fill and if empty and it would adjust automatically"*, so every one of them renders nothing at all when blank; **the two existing quotes** move into the new type and the home section is swapped by the migration, so the page works the moment it is applied |
| 2026-09-19 | **A case-study page reads like a blog post** — reported as *"in case studies page why there's no featured image shown?"* with a screenshot of a page that was a breadcrumb, a CLIENT box and a bare title over half a screen of white. Asked what the page should be, the answer was *"make the page just like blog posts"*: title, date, the main picture full width at its own size, a rule, then the writing. The picture was invisible for two reasons at once — none was set on any case study, and the page would not have shown one if it were, because a page that starts with a Hero section draws its own title and picture and the rest of the head is skipped. Case studies and events no longer start with one |
| 2026-09-19 | **A field left blank shows nothing at all, and the ones that do show are not highlighted** — *"make if the client name is empty dont show the client and also dont highlight the client keep the same design"*. Clearing a box used to leave the grey band and an empty white card behind it; now the whole strip disappears when there is nothing in it. And the short fields — a case study's Client, an event's dates, a datasheet's PDF — are plain label-and-value page content rather than cards on a grey band. Applies to every content type that shows short fields, not just case studies |

## Status against the brief

| Brief item | State |
|---|---|
| Services tree (5 groups, 17 services) | Seeded as a hierarchical type at `/services/<group>/<service>`, in the mega menu and the services archive |
| Case studies (7) | Seeded with industry/solution terms; dark case-study band on the home page |
| Blogs | `post` type at `/blog`, article layout, RSS feed |
| Technology partners | 14 seeded with logos; logo wall at `/partners`, no detail pages |
| About Us, Careers, Contact Us | Pages with the design's founders block, career form (`contact_form kind=career`), quote form and contact list |
| Events (2) | `event` type at `/events` with date tile |
| Datasheet | `datasheet` type with a PDF field, `pdf` block reads it in the browser, Download button |
| Products with payment gateway | `product` type, checkout page, `DummyGateway` placeholder; **live provider still open** |
| WordPress-like CMS + Elementor-style building | Content types as rows, per-type fields, document editor with sections, columns, alignment/width/tone per section |
| Easy admin for non-technical staff | Sidebar admin, plain-English section picker, live preview, `docs/NON-TECHNICAL.md`; two people can write in one page — one paragraph, even — at the same time and keep both sets of words, and Activity says what each of them changed |
| Easy for AI to scrape | `llms.txt`, `llms-full.txt`, `.md` twin of every page, `/api/v1` read API |
| SEO compatible | Server-rendered meta, canonical, Open Graph, JSON-LD per type, sitemap, robots, redirects; FAQPage JSON-LD not yet wired |
| Backend first, UI later | Both delivered; UI followed the client's mock |
