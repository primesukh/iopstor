# IOPSTOR — client requirements (verbatim, 2026-09-03)

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

## Decisions taken with the client (2026-09-03)

- Self-hosted via Dokploy (Docker)
- Self-hosted Supabase, accessed **only through its Kong gateway with the Supabase Python library** (PostgREST for data, GoTrue for logins,
  Storage for uploads). No separate database, no direct Postgres connection. Dev gateway: `http://developmentserver-supabase-9f7088-111-125-233-170.sslip.io`
- pipenv for dependencies, plus a generated `requirements.txt`
- Database migrations are plain `.sql` files, one per schema edit
- A basic themed public site and a browser admin (`/admin`) were wanted in phase 1 after all; the drag-and-drop page builder remains phase 2
- Local development runs `flask run --debug` (auto-reload)
