# IOPSTOR — client requirements (brief verbatim from 2026-09-03; decisions and status to 2026-09-09)

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

In `website_assets/` (untracked in git — the client's files, loaded into the media library with `flask import-media website_assets`):

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
| Easy admin for non-technical staff | Sidebar admin, plain-English section picker, live preview, `docs/NON-TECHNICAL.md` |
| Easy for AI to scrape | `llms.txt`, `llms-full.txt`, `.md` twin of every page, `/api/v1` read API |
| SEO compatible | Server-rendered meta, canonical, Open Graph, JSON-LD per type, sitemap, robots, redirects; FAQPage JSON-LD not yet wired |
| Backend first, UI later | Both delivered; UI followed the client's mock |
