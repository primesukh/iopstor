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

## 4. Writing a page

**Open a page and start typing.** Under **Content** you get a blank white page with the cursor already in it and a toolbar across the top — the same as Word or Google Docs. You do not have to choose anything, set anything up, or understand anything first. Type.

Most pages are exactly that: words. When you want something fancier than words — a row of boxes, a strip of big numbers, a coloured band with a button — you drop one in without leaving the keyboard. Those are called **sections**, and the design is applied for you, so they always look right and work on phones.

The sections available:

| Section | What the visitor sees |
|---|---|
| **Hero** | The big banner at the top: headline, sub-headline, optional image and button |
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

**Rule of thumb:** if a page starts with a Hero, the Hero supplies the page's main headline. Otherwise the page title is shown at the top, above whatever you have written.

### Writing

**Just type.** The page opens with the cursor in it. Everything you write goes down the page the way it does in a Word document — press Enter for a new paragraph and keep going.

**The toolbar** across the top works the way you would expect:

| | |
|---|---|
| **↶ ↷** | Undo and redo |
| **Normal text ▾** | Turn a line into a *Heading*, *Sub-heading* or *Small heading*. (There is no “Heading 1” on purpose — the page title at the top is already the main heading, and having two confuses Google.) |
| **B** *I* <u>U</u> **S** | Bold, italic, underline and strikethrough |
| **Tx** | Strips all formatting off the selected words |
| **• 1.** | Bulleted and numbered lists |
| **❝ —** | A pull quote, and a dividing line |
| **🔗 🖼 ▦ </>** | A link; a picture; a table; or code embedded from another service like YouTube or Google Maps |
| **⇤ ↔ ⇥** and the two colour squares | Alignment, text colour and highlight |

**The buttons light up to show what is switched on.** Put the cursor in a line and the toolbar
follows it: if that line is a quote, **❝** is highlighted; if it is centred, **↔** is highlighted;
bold, italic, underline and strikethrough do the same. **Clicking a highlighted button switches it
back off** — that is how you take a paragraph back out of a quote, or move centred text back to the
left.

**Pasting from Word or Google Docs works properly.** Draft wherever you like, copy the whole thing, paste it in — your headings stay headings and your bullets stay bullets. Word's own invisible junk is dropped on the way in, so nothing strange leaks into the site.

**Pictures go in the flow.** Press **🖼**, choose a file, and it uploads and lands where the cursor was. You are then offered a box to describe the picture for blind visitors — worth thirty seconds, and good for Google too.

### Adding a section

**Press `/` on an empty line.** A short list appears under the cursor. Type a few letters to narrow it — “num” finds Numbers, “quo” finds Customer quote — and press Enter. The section drops in right there, already filled with stand-in wording, and the cursor lands on a fresh line underneath so you can carry on writing.

You can also use **+ Section** on the toolbar, which opens the same list with a description of each one. The same menu has *“Start from a layout…”* if you would rather begin from a ready-made Product, Service or Landing page and replace the wording.

### Changing a section

Click any wording inside a section and type over it — headline, button label, a question in the FAQ, a number in the numbers strip. Hover a section and a small dark toolbar appears in its top-right corner:

| Button | What it does |
|---|---|
| **⠿** | Hold and drag to move the whole section up or down the page |
| **↑ ↓** | Move it one place up or down, if you prefer buttons to dragging |
| **⧉** | Make a copy of the section, just below |
| **⚙** | Open its settings on the right — pictures, links, and the choices that are not words on the page |
| **✕** | Remove the section (it asks first) |

Ordinary paragraphs deliberately have no toolbar hovering over them. They are just writing.

**Pictures, links and settings.** Some things are not words on the page — which picture a section uses, where a button goes, how many posts a list shows. Those live in the **Section settings** panel on the right, which fills in when you click a section. Any picture field there has a **Choose file** button that uploads on the spot.

Nothing is saved until you press **Save**. If you try to leave with unsaved changes, your browser will warn you. If something required is missing, the page comes back with the problem listed at the top and your work still in place.

> **The other two tabs.** Above the page there are three tabs. **Visual** is the one described above and the one to use. **Form** is the older view — the same content as a list of labelled boxes — which some people find quicker for bulk typing. **Advanced** shows the raw data for developers; you never need to open it.


### Checking how it looks

Above the page are two buttons: **Edit** and **Preview**.

**Preview** shows the page exactly as a visitor gets it — with the site header and menu, the
breadcrumb trail, the featured image, the footer, and none of the editing marks. Nothing is
published by doing this, and it works on a page that has never been published, which is the point:
you can check a draft before anyone else sees it. The preview keeps up as you type.

**Desktop / Tablet / Phone** redraw the preview at those screen sizes, so you can check a page
works on a phone before publishing rather than after.

Underneath, two small cards show **how the page will look in a Google result** and **when someone
shares the link** on WhatsApp or LinkedIn — the title, the web address, the description and the
picture. They also tell you if your title or description is too long and will be cut short. If the
share card says *No image*, set a Featured image on the right.

Links in the preview open in a new tab rather than taking you away from it, and the contact form
does not send anything.

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

**You do not have to go to Media first.** Anywhere a page asks for a picture — a Hero image, an Image or Gallery block, the Featured image in the sidebar — there is a **Choose file** button right there. Pick a file and it uploads straight away, gets used on the spot, and joins the Media library so you can reuse it elsewhere. A small thumbnail next to it shows what is currently selected. Uploads made this way have no alt text yet, so add it in the Media section afterwards for anything important.

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

**Still to come:** a live payment provider.

---

## 12. Quick answers

**I changed something and the website looks the same.** Check the status is *Published* and the publish date is not in the future. Then refresh with Ctrl+F5.

**Can I change a page's web address?** The address is made from the title automatically, and the box is locked so it cannot be changed by accident — an address that changes breaks every link and bookmark pointing at the old one, and search engines drop the page. If you genuinely need to change it, the small **Edit** button beside the box unlocks it and warns you first.

**A page gives "not found".** Its address is built from its slug and its type. A Service named *NAS* filed under *Storage* lives at `/services/storage/nas`, not `/services/nas`. Check the parent is set correctly.

**I need a new kind of content — say, Job Openings.** No development work is needed. An admin can add a new content type through the admin panel, and it gets its own list, its own form and its own web addresses.

**Someone left the company.** An admin should delete their user account. This removes both their login and their access.

**I deleted something by mistake.** Deletion is permanent. Set things to *Draft* instead when you only want them off the site.

---

*Technical companion: [TECHNICAL.md](TECHNICAL.md).*
