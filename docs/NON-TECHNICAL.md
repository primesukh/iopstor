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

**Open a page and start typing.** The screen *is* the page: a big title box at the top, a toolbar under it, and a blank white page with the cursor already in it — the same as Word or Google Docs. Everything that is not the page itself — whether it is live, its web address, the picture used when it is shared — sits in the panel on the right, and **Save** is in the bar at the top. You do not have to choose anything, set anything up, or understand anything first. Type.

Most pages are exactly that: words. When you want something fancier than words — a row of boxes, a strip of big numbers, a coloured band with a button — you drop one in without leaving the keyboard. Those are called **sections**, and the design is applied for you, so they always look right and work on phones.

The sections available:

| Section | What the visitor sees |
|---|---|
| **Hero** | The big banner at the top: headline, sub-headline, optional image and button |
| **Image** | One picture with a caption |
| **Gallery** | A grid of pictures |
| **PDF** | A PDF shown right on the page, with the reader's own page and zoom controls, and a button to open it full-size |
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

**The panel on the right** holds everything about the page that is not the page:

| Group | What it is for |
|---|---|
| **Publish** | Draft or published, and the date (see §5). The small grey or green label in the top bar shows what is *saved* — it changes when you press Save, not before. |
| **Web address** | Made from the title automatically. If another page of the same kind already uses that address, three random letters are added so yours still works — `testing-shc` — and the note under the box tells you so. **Edit** if you really need to change it; it asks first, because changing it breaks existing links. |
| **Summary** | A sentence or two. Shown in lists, and under the page in Google results. |
| **Featured image** | The picture used in lists and when the page is shared. **Choose file** uploads on the spot. |
| **Organise** | The parent page (for services) and any categories or tags — see below. It only appears for types that have one or the other. Nothing here asks you to number your pages — lists show the newest first on their own. |
| **Details** | The extra boxes some kinds of content have — a case study's client, an event's dates, a datasheet's PDF. |
| **Search engine overrides**, **Advanced** | Closed by default. Leave them closed unless you know why you are opening them. |
| **Delete** | At the very bottom, for administrators. It asks first. |

### Categories and tags

Under **Organise** there is a search box for each one — *Category*, *Tags*, whatever the kind of content
uses. Start typing and the ones that already exist drop down; click one and it becomes a small chip
above the box. Add as many as you like, and click the **×** on a chip to take it off again.

If nothing matches what you typed, the last line of the list offers **Create “…”**. Pick it and the chip
appears in a different colour — that is the one that does not exist yet. It is created when you press
**Save**, and from then on it is an ordinary category or tag that everybody can pick for other posts.
Nothing is created if you walk away without saving.

You do not need to worry about making the same tag twice. Typing *All-Flash* when *all flash* already
exists offers you the one that is there rather than a second copy of it, whatever the spacing or capitals.

### Writing

**Just type.** The page opens with the cursor in it. Everything you write goes down the page the way it does in a Word document — press Enter for a new paragraph and keep going.

**The toolbar** across the top works the way you would expect:

| | |
|---|---|
| **↶ ↷** | Undo and redo |
| **Normal text ▾** | Sets the size of the line: **H1** down to **H6**, or back to *Normal text*. H2 is the normal way to start a section, H3 for something under it, and so on down. |
| **Size ▾** | Makes ordinary writing bigger or smaller — *Small*, *Normal*, *Large*, *Larger*, *Huge*. Select some words to resize just those, or click anywhere in a line to resize the whole line. *Normal* puts it back. It is greyed out on a heading, because a heading's size is set by its H-level instead — and turning a line into a heading drops any size you had set on it, so the heading comes out the size a heading should be. |
| **B** *I* <u>U</u> **S** | Bold, italic, underline and strikethrough |
| **Tx** | Strips all formatting off the selected words |
| **• 1.** | Bulleted and numbered lists |
| **❝ —** | A pull quote, and a dividing line |
| **🔗 🖼 ▦ </>** | A link; a picture; a table; or code embedded from another service like YouTube or Google Maps. Each one opens a proper box to fill in, not a bare browser pop-up |
| **⇤ ↔ ⇥** and the two colour squares | Alignment, text colour and highlight |

**The buttons light up to show what is switched on.** Put the cursor in a line and the toolbar
follows it: if that line is a quote, **❝** is highlighted; if it is centred, **↔** is highlighted;
bold, italic, underline and strikethrough do the same. **Clicking a highlighted button switches it
back off** — that is how you take a paragraph back out of a quote, or move centred text back to the
left.

**A word on H1.** It is in the list, but reach for **H2** to open a section. The page title at the
top of the page is already the page's H1, so adding another one inside your writing gives the page
two — and that is one of the things Google reads to work out what a page is about. H2, H3, H4 and
below are yours to use freely.

**If the toolbar goes grey, it is waiting for you.** It fades and the line underneath reads *“Click
in the page to start editing”* whenever the cursor is not in text it can format — after you have
been working somewhere else on the screen, or when the cursor is in a headline or a button label,
which are a fixed size on purpose. Click into a paragraph and the toolbar comes straight back. It is
deliberately switched off rather than pretending: a button that looked available but did nothing was
the old, more confusing behaviour. This now covers **every** button that needs the cursor, the four
on the right included — so you can never fill in a picture or a table box and find nothing arrives.

**Pasting from Word or Google Docs works properly.** Draft wherever you like, copy the whole thing, paste it in — your headings stay headings and your bullets stay bullets. Word's own invisible junk is dropped on the way in, so nothing strange leaks into the site.

**Links.** Select the words you want to link and press **🔗**. A box asks for the web address, shows the words you selected so you can correct them, and offers **Open in a new tab**. You can type a plain address like `iopstor.com/nas` and the `https://` is added for you; `/about` links to another page on this site, and `mailto:` or `tel:` addresses work too. Put the cursor inside a link you already made and press **🔗** again: everything is filled in ready to change, and there is a **Remove link** button that takes the link off without deleting the words.

**Pictures go in the flow.** Press **🖼**. Pick a picture you have already uploaded from the list, or press **Choose file** to upload a new one on the spot — either way there is a thumbnail so you can see what you have chosen. Write the **alt text** in the same box (a short description for blind visitors — worth thirty seconds, and good for Google too), then press **Insert** and it lands where the cursor was.

**Tables.** Press **▦** and drag across the little grid, the way you would in Word — the squares light up and the label underneath reads the size, then click to drop the table in. For anything bigger than the grid shows, type the numbers into the **Rows** and **Columns** boxes instead. Leave **First row is a header** ticked and the top row comes out shaded and bold. Then just click into a cell and type.

**Making a column wider or narrower.** Put the pointer on the line between two columns — it turns into a left-right arrow — and drag. The column either side gives up what the other one gains, so the table stays the same width overall, and the proportions hold when the page is viewed on a phone. Tables you have never dragged carry on sizing themselves to fit their contents.

**Embedded code.** Press **</>** for a video, a map, a booking calendar or anything else another service gives you a snippet for. Copy the "embed" code from that service, paste it into the box — a proper big box, so you can actually read it — and press **Insert**.

### Adding a section

**Press `/` on an empty line.** A short list appears under the cursor. Type a few letters to narrow it — “num” finds Numbers, “quo” finds Customer quote — and press Enter. The section drops in right there, already filled with stand-in wording, and the cursor lands on a fresh line underneath so you can carry on writing.

You can also use **+ Section** on the toolbar, which opens the same list with a description of each one. The same menu has *“Start from a layout…”* if you would rather begin from a ready-made Product, Service or Landing page and replace the wording.

### Putting things side by side

Most sections run the full width of the page. When you want two, three or four things **next to each other** — a description beside a picture, three features in a row, a bit of text beside an enquiry form — add a **Columns** section.

It arrives as two columns with a line of writing in each. From there:

- **Type in a column** exactly as you type on the page.
- **Put a section in a column.** An empty column shows a dashed box saying *“Type here, or press / for a section”*. Click it, press `/`, and pick what you want. In a column that already has something in it, the same line appears above and below what is there when you hover — click the one where you want the new section to land. Numbers, Cards, a Customer quote, a Contact form — almost anything can go in a column. (Hero and Columns cannot: a Hero is the page's big opening band, and columns inside columns get impossible to work with.)
- **Move things in and out.** Drag a section by its **⠿** handle into a column, out of it, or across to the next one. The **↑ ↓** buttons move a section within the column it is already in.
- **Add or remove a column.** Hover the Columns section, click **⚙**, and use **+ Add column** and the **✕** next to each one. It asks before removing a column that still has something in it.

**How wide each column is.** By default they share the space equally. To split it yourself, put numbers in the **Column widths** box in the same **⚙** panel — one per column, separated by slashes:

| You type | You get |
|---|---|
| *(blank)* | Equal columns |
| `50/25/25` | A wide first column and two narrower ones |
| `1/2` | A second column twice the width of the first |
| `33/33/33` | Equal thirds |

The numbers are proportions, so `50/25/25` and `2/1/1` do the same thing. If the numbers do not match the number of columns, or you type something that is not a number, the columns simply go back to equal — nothing breaks.

On a phone, columns always stack one under the other, however you set the widths. You can check this with **Preview → Phone**.

### Changing a section

Click any wording inside a section and type over it — headline, button label, a question in the FAQ, a number in the numbers strip. Hover a section and a small dark toolbar appears in its top-right corner:

| Button | What it does |
|---|---|
| **⠿** | Hold and drag to move the whole section up or down the page |
| **↑ ↓** | Move it one place up or down, if you prefer buttons to dragging |
| **⧉** | Make a copy of the section, just below |
| **⚙** | Open its settings, right over the section — pictures, links, how wide each column is, and the choices that are not words on the page |
| **✕** | Remove the section (it asks first) |

Ordinary paragraphs deliberately have no toolbar hovering over them. They are just writing.

**Pictures, links and settings.** Some things are not words on the page — which picture a section uses, where a button goes, how many posts a list shows. Those live on the section itself: hover it, click the **⚙** on its little dark toolbar, and a small panel opens over that section with exactly its own options — the picture, the button link, how many posts to list, and **+ Add** / ✕ for rows in a Cards, FAQ, Numbers or Specification section. Any picture field there has a **Choose file** button that uploads on the spot. The page updates as you type. Close it with **Esc**, the ✕, another press of ⚙, or by clicking anywhere else.

Nothing is saved until you press **Save**. If you try to leave with unsaved changes, your browser will warn you. If something required is missing, the page comes back with the problem listed at the top and your work still in place.

> **Advanced.** At the very bottom of the right-hand panel, *Advanced* shows the page's sections as raw data. It is there for developers; you never need to open it.


### Checking how it looks

In the bar at the top of the screen are two buttons: **Edit** and **Preview**.

**Preview** shows the page exactly as a visitor gets it — with the site header and menu, the
breadcrumb trail, the featured image, the footer, and none of the editing marks. Nothing is
published by doing this, and it works on a page that has never been published, which is the point:
you can check a draft before anyone else sees it. The preview keeps up as you type.

**Desktop / Tablet / Phone**, which appear next to them in Preview, redraw the page at those screen sizes, so you can check a page
works on a phone before publishing rather than after.

The preview fills the screen; scroll down under it for two small cards that show **how the page will look in a Google result** and **when someone
shares the link** on WhatsApp or LinkedIn — the title, the web address, the description and the
picture. They also tell you if your title or description is too long and will be cut short. If the
share card says *No image*, set a Featured image in the panel on the right.

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

**Putting a PDF on a page.** Press `/` on an empty line and choose **PDF**. The section drops in; hover it, press **⚙**, and pick the PDF from the list — or press **Choose file** to upload one on the spot. Only PDFs are offered there, so you cannot pick a photo by mistake. Visitors then read it without leaving the page — scrolling, zooming and printing with their browser's own controls — and there is an **Open the PDF** button under it for phones and for anyone who wants to download it. Give the section a heading by typing straight onto the page above the viewer.

**You do not have to go to Media first.** Anywhere a page asks for a picture — a Hero image, an Image or Gallery section, the Featured image in the panel on the right — there is a **Choose file** button right there. Pick a file and it uploads straight away, gets used on the spot, and joins the Media library so you can reuse it elsewhere. A small thumbnail next to it shows what is currently selected. Uploads made this way have no alt text yet, so add it in the Media section afterwards for anything important.

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

**Two pages with the same name.** Two pages cannot share an address, but you are never stopped from writing one. Give a second page the same title as an existing one and it quietly gets three random letters on the end — *“testing” is already used, so this page is at “testing-shc”* — and the note under the box says exactly that. If you would rather choose the address yourself, press **Edit** and type one. There the rule is stricter: type an address another page already has and the note turns red, offers you a free one, and Save will not go through until you change it.

**A page gives "not found".** Its address is built from its slug and its type. A Service named *NAS* filed under *Storage* lives at `/services/storage/nas`, not `/services/nas`. Check the parent is set correctly.

**I need a new kind of content — say, Job Openings.** No development work is needed. An admin can add a new content type through the admin panel, and it gets its own list, its own form and its own web addresses.

**Someone left the company.** An admin should delete their user account. This removes both their login and their access.

**I deleted something by mistake.** Deletion is permanent. Set things to *Draft* instead when you only want them off the site.

---

*Technical companion: [TECHNICAL.md](TECHNICAL.md).*
