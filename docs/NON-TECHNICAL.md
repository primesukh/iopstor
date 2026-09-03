# IOPSTOR Website — Plain-English Guide

For everyone who edits the website: marketing, sales, HR and management. No coding needed.

---

## 1. What this system is

It is the IOPSTOR website plus its own control panel — the same idea as WordPress, built specifically for IOPSTOR.

There are two halves:

| Half | Who uses it | Where |
|---|---|---|
| **The public website** | Customers, prospects, Google, AI crawlers | `https://<your-domain>/` |
| **The admin panel** | IOPSTOR staff | `https://<your-domain>/admin` |

Anything you change in the admin panel appears on the public website immediately. You never need a developer to publish a page, add a case study, or change the phone number in the footer.

---

## 2. Logging in

1. Go to `/admin`.
2. Enter the email and password you were given.
3. You land on the dashboard, which shows counts of your content and recent enquiries.

**Two kinds of account:**

- **Editor** — can create and edit content, upload images, and read enquiries. This is the right level for most people.
- **Admin** — everything an editor can do, plus deleting content, changing site settings, and creating other user accounts.

If you can log in but see "Forbidden", your login exists but has not been given a role yet — ask an admin.

---

## 3. The kinds of content you can create

Content is organised into **types**. Each type has its own list in the admin sidebar and its own address pattern on the website.

| Type | What it is for | Web address |
|---|---|---|
| **Pages** | Standalone pages: Home, About Us, Careers, Contact Us | `/about-us` |
| **Blog** | News and articles | `/blog/my-article` |
| **Services** | The service catalogue. Nests two levels deep: *Storage* → *NAS* | `/services/storage/nas` |
| **Case Studies** | Customer stories | `/case-studies/lks` |
| **Events** | Trade shows, launches, collaborations | `/events/broadcast-2018` |
| **Technology Partners** | Partner companies and their logos | `/partners/seagate` |
| **Datasheets** | Downloadable PDFs | `/datasheets/flash-array` |
| **Products** | Items that can be paid for online | `/products/starter-array` |

The site ships pre-loaded with the real IOPSTOR service catalogue (Storage, Hyper Converged Media, Cloud, AI, Software Based), all seven case studies (LKS, SCM, FM, DCSL, SSC, ATPL, KLPL), and the two 2018 events.

Some types ask for a few extra details. A Case Study asks for Client, Challenge, Solution and Results. An Event asks for start date, end date and location. A Datasheet asks you to attach the PDF. These extra boxes appear automatically on the form — just fill in what applies.

---

## 4. Building a page out of blocks

A page is not one big text box. It is a **stack of blocks**, each one a full-width band down the page. You choose the blocks and the order; the design is applied for you, so every page looks consistent and works on phones.

The available blocks:

| Block | What the visitor sees |
|---|---|
| **Hero** | The big banner at the top: headline, sub-headline, optional image and button |
| **Rich text** | A normal paragraph area for prose |
| **Image** | One picture with a caption |
| **Gallery** | A grid of pictures |
| **Cards** | A row of boxes, each with a title, short text, icon and link |
| **CTA** | A "call to action" strip: a line of text and a button |
| **FAQ** | Question-and-answer list |
| **Stats** | Big numbers with labels — "5 PB / in a single rack" |
| **Testimonial** | A customer quote with their name, role and company |
| **Spec table** | A two-column table of specifications |
| **Post list** | Automatically pulls in the latest Services, Case Studies or Blog posts. You do not maintain this by hand — new items appear on their own |
| **Contact form** | An enquiry form. Choose *contact*, *quote* or *career* |
| **Embed HTML** | For dropping in code from another service, like a map or a video |

**Rule of thumb:** if a page starts with a Hero block, the Hero supplies the page's main headline. Otherwise the page title is shown at the top.

> **Today's limitation.** The drag-and-drop builder is phase 2. Right now blocks are entered in the admin as a structured text field, with a reference panel listing every block and the fields it needs. The blocks themselves and how they look on the site are already finished — only the editing experience is due to be upgraded.

---

## 5. Draft, published and scheduled

Every piece of content has a **status**:

- **Draft** — only you can see it. Nobody on the internet can reach it, even with the direct link.
- **Published** — live on the website.
- **Scheduled** — set the publish date to a future date and time. The page stays hidden and appears by itself when that moment arrives. Nobody has to press anything.

---

## 6. Pictures and files

The **Media** section is the shared library for every image, logo and PDF.

1. Go to Media and upload the file.
2. Give it **alt text** — a short description of what is in the picture. This is what a blind visitor's screen reader reads out, and it is one of the things Google looks at. Please do not skip it.
3. The file is then selectable anywhere the site asks for an image.

---

## 7. Enquiries from the website

Every contact form, quote request and job application on the site lands in **Leads** in the admin panel — nothing is emailed into a black hole.

Each enquiry can be marked **New**, **In progress** or **Done**, so sales can work through the list and see what has been handled. The form also carries a hidden anti-spam trap that catches most automated junk before it reaches you.

---

## 8. Menus, settings and redirects

**Settings** holds the things that appear everywhere: site name, tagline, logo, contact email and phone, address, social links, and the Google Analytics ID.

**Menus** control the header and footer navigation. The header menu supports one level of drop-down, which is how *Services* and *Company* expand.

**Redirects** send an old address to a new one. If a page moves — or you are bringing across links from the old website — add a redirect so the old link keeps working and nobody hits a "not found" page. This protects the search rankings you have already earned.

---

## 9. Being found: search engines and AI

This was an explicit requirement, so it is built in rather than bolted on. Every page is delivered to Google and to AI crawlers fully formed, with no waiting for scripts to run.

The site publishes automatically, with no work from you:

- `/sitemap.xml` — the list of every public page, for search engines
- `/robots.txt` — the rules for crawlers
- `/feed.xml` — an RSS feed of the blog
- `/llms.txt` and `/llms-full.txt` — a clean, plain-text version of the whole site, written for AI assistants to read

Each page also carries its title, description, social-sharing preview and machine-readable labelling (a Case Study is labelled an Article, a Service a Service, an Event an Event) so that search results and shared links look right.

**What you can control per page:** the SEO title, the description, and a "hide from search engines" switch for pages you would rather keep out of Google.

---

## 10. Payments

Products can carry a price and a checkout button. The payment step is currently a **placeholder** — it walks through the full flow and records the order, but no money moves. Connecting a real provider such as Razorpay or Stripe is a configuration change, not a rebuild.

---

## 11. Where the project stands

**Done:** the content system, the public website with its theme, the admin panel, search-engine and AI output, enquiry capture, media library, users and roles, and the payment placeholder.

**Still to come:** the drag-and-drop page builder (phase 2) and a live payment provider.

---

## 12. Quick answers

**I changed something and the website looks the same.** Check the status is *Published* and the publish date is not in the future. Then refresh with Ctrl+F5.

**A page gives "not found".** Its address is built from its slug and its type. A Service named *NAS* filed under *Storage* lives at `/services/storage/nas`, not `/services/nas`. Check the parent is set correctly.

**I need a new kind of content — say, Job Openings.** No development work is needed. An admin can add a new content type through the admin panel, and it gets its own list, its own form and its own web addresses.

**Someone left the company.** An admin should delete their user account. This removes both their login and their access.

**I deleted something by mistake.** Deletion is permanent. Set things to *Draft* instead when you only want them off the site.

---

*Technical companion: [TECHNICAL.md](TECHNICAL.md).*
