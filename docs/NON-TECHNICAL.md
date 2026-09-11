# IOPSTOR Website — Plain-English Guide

For everyone who edits the website: marketing, sales, HR and management. No coding needed.

---

## 1. What this system is

It is the IOPSTOR website plus its own control panel — the same idea as WordPress, built specifically for IOPSTOR.

There are two halves:

| Half | Who uses it | Where |
|---|---|---|
| **The public website** | Customers, prospects, Google, AI crawlers | `https://www.iopstor.com/` |
| **The admin panel** | IOPSTOR staff | `https://www.iopstor.com/admin` |

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

**Finding your way around.** Everything lives in the black bar down the left. Every line has a small picture beside it so you can find the one you want without reading down the list. *Content* lists every kind of page with how many of each there are; *Site* holds Media, Leads, Warranty and — if you are an administrator — Settings and Users. The page you are on is marked with a blue stripe down its left edge, and a blue number next to **Leads** means new enquiries are waiting. On a narrow screen the bar collapses to a single line with a ☰ button.

At the bottom of that bar it says who is signed in — your name, and your email address underneath it. A long email address is shortened with a "…"; hover over it to see the whole thing. The name comes from the **Name** box that was filled in when the account was created, on the Users screen. If it was left empty — which it is for the very first administrator, created from the command line — the system makes a sensible one out of the email address instead, so `sukhpreet.saluja@…` shows as *Sukhpreet Saluja*. There is no screen for changing it afterwards; ask whoever runs the database if a name needs correcting.

**Changing your password.** Click **Password** at the bottom of the black bar. You need your current password, then the new one twice — at least 8 characters. Everyone can do this, editors included. You stay signed in afterwards.

**Too many wrong passwords locks the door for a while.** After ten wrong attempts the login page stops accepting tries from that internet connection and says how long to wait — fifteen minutes by default. It clears itself; nobody has to unlock anything, and an administrator cannot let you back in early. It counts by internet connection, not by account, so nobody can lock *you* out by guessing at your email address, and being locked out on one device does not stop you signing in from another. The same limit applies to the **Password** screen if you keep getting your current password wrong.

**If someone forgets their password**, an administrator can hand them a new one: **Users**, then *Set a password* under that person's name. Type one, press *Set*, and tell them what it is so they can change it themselves. There is no "forgot my password" email — this website's Supabase does not send mail. Your own row has no *Set a password*; use the **Password** screen for yourself, which is the one that checks you know the old one.

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
| **Technology Partners** | Partner companies and their logos | *(no page of its own — see below)* |
| **Datasheets** | Downloadable PDFs | `/datasheets/flash-array` |
| **Products** | Items that can be paid for online | `/products/starter-array` |

The site ships pre-loaded with the real IOPSTOR service catalogue (Storage, Hyper Converged Media, Cloud, AI, Software Based), all seven case studies (LKS, SCM, FM, DCSL, SSC, ATPL, KLPL), and the two 2018 events.

Some types ask for a few extra details. A Case Study asks for Client, Challenge, Solution and Results. An Event asks for start date, end date and location. A Datasheet asks you to attach the PDF. These extra boxes appear automatically on the form — just fill in what applies.

**Specifications, on a Product, is a list of rows.** A *Label* box and a *Value* box for each line — "CPU", "Xeon 4 core" — with **+ Add row** underneath, and ✕ to remove one. The ↑ and ↓ arrows put them in the order you want them read, and that is the order the table shows on the website. It used to be a box of computer code, where one wrong bracket made the whole table disappear from the live page without telling you. That cannot happen now.

**The listing page for each type now looks like the thing it is listing**, and you do not have to set any of it up:

- **Products** (`/products`) shows the price and a **Buy** button on each card. The button only appears once you have filled in *Price* on that product — leave it blank and the card simply ends at the description, which is the right thing when a price is on request. **Prices are always in rupees** and print the way you would read one — `₹ 12,50,000`, not `₹ 1,250,000`. There is no currency box to fill in any more. Type the number only; the ₹ and the commas are added for you.
- **A product's own page** leads with its title, its summary, the *Request a quote* and *Buy* buttons, and the **Featured image beside them** — so choose one, and it appears. **The price is printed on the Buy button itself** — *Buy · ₹ 10,000* — rather than sitting in a box of its own further down the page, so a visitor sees what it costs at the moment they decide to buy it. Leave *Price* blank and the button disappears, exactly as on the listing card. Under that come the other details you filled in, then the specifications table.
- **Services** (`/services`) is one wide row per group, with every sub-service beside it as a button a visitor can click straight through to.
- **Events** (`/events`) is a list with the year and month on a black tile at the left of each row.
- **Datasheets** (`/datasheets`) is a list of rows with a PDF mark and a **Download** button.

**Technology Partners have no pages.** A partner is a logo shown on other pages, so there is nothing
to read on a page of its own: the logos in the strip are not clickable, and there is no
`/partners/micron` address. You still add, edit and remove partners exactly as before — upload the
logo, give it a name — and the admin list shows *"no page of its own"* where the web address usually
goes. They appear wherever an Automatic list of Technology Partners is placed.

**A blog article reads top to bottom**: the title, the date under it, the picture, a line, then what you wrote. The picture is shown **at the size you uploaded it** — never stretched, never cropped — and is only made smaller if it is wider than the page. You do not arrange any of that: write the article, choose a *Featured image*, and it lays itself out. Every other kind of page still puts its picture beside the words.

A service page with no sub-services of its own now ends with **"Other &lt;group&gt; services"** — the rest of its group, so a visitor reading about NAS can step sideways to DAS or SAS.

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
| **PDF** | A PDF shown right on the page, with the reader's own page and zoom controls, and a button to download it |
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

A few sections gained settings worth knowing about, all under the section's own **⚙**:

- **Hero** — the big opening band. *Small label above the heading* is the short blue line above the headline ("The Storage Specialist"). There is a **second button** now, which draws as an outline next to the main one. And **Dark background** turns the hero into the full-width black band used on About Us — in that mode the picture you choose becomes a faded backdrop *behind* the words instead of sitting beside them.
  A hero can also hold **more than one picture**. Under *Pictures that take turns*, add a row per picture; from two rows up they fade from one to the next on their own, about four and a half seconds each, with small bars underneath showing which one is up. That is what the home page does with the three appliances. One picture, or none, behaves exactly as before — and a visitor whose device is set to reduce motion simply sees the first picture, still.
- **Automatic list** — the section that lists your pages and keeps itself up to date. *Header link text* and *Header link* put a link like "All services →" on the right of the section's heading. The cards style themselves to suit what they are listing: services show a number and their sub-services, products show the product picture, case studies show their industry and solution, blog posts show the date. You do not choose that; it follows the content type. A service card lists **four** sub-services and then says "+3 more" rather than all of them — every card in a row is as tall as the tallest, so one long list used to leave the cards beside it half empty. The full list is on the Services page, where each one is a button you can click.
- **Customer quote** also has a **Dark background** tick, for a quote on a dark card. On its own a quote sits on a soft grey card; **put two side by side in a Columns section and the cards fall away** — the words go italic on the page's own background, which is how the home page runs them. Give the Columns section a *Heading* (“What our clients say”) and it sits above the pair.
- **Contact form** — *Form type* also picks how the form looks. **quote** sits on the soft grey panel and asks two extra questions — what the visitor is interested in, and how many users — which arrive with the enquiry under **Leads**. **career** is the same grey panel, used on Careers, without those two questions. **contact** is the plain white card. Whatever you type in *Heading* sits inside the panel, at the top of the form.

Two of the sections are not writing at all, and they are there for laying a page out:

- **Spacer** is a gap and nothing else. Drop one between two sections when they sit too close
  together, then open its **⚙** and pick a **Height** — *Small*, *Medium*, *Large* or
  *Extra large*. On the page a visitor sees only white space; in the editor it shows as a faint
  dashed strip so you can find it, move it or take it out again.
- **Divider** is one thin line straight across the page. It has no settings of its own, because the
  boxes every section already has do the job: set **Width** to a number like *400* and the line gets
  shorter, and **Align the section** puts that shorter line on the left, in the middle or on the
  right. It is the same line as the **—** button on the writing toolbar — that one draws a line
  *inside* a piece of writing, this one draws a line *between* two sections.

Both can go inside a **Columns** section as well, where the spacer's height is exactly the gap you
asked for.

One section is worth calling out: **Warranty check**. Drop it on a page and visitors get a box where they type the serial number of their unit and see straight away whether it is still in warranty. What it shows comes from the **Warranty** screen — see section 8 below.

### Putting things side by side

Most sections run the full width of the page. When you want two, three or four things **next to each other** — a description beside a picture, three features in a row, a bit of text beside an enquiry form — add a **Columns** section.

It arrives as two columns with a line of writing in each. From there:

- **Type in a column** exactly as you type on the page.
- **Put a section in a column.** An empty column shows a dashed box saying *“Type here, or press / for a section”*. Click it, press `/`, and pick what you want. In a column that already has something in it, the same line appears above and below what is there when you hover — click the one where you want the new section to land. Numbers, Cards, a Customer quote, a Contact form — almost anything can go in a column. Unlike on the page itself, you do not get a blank line under it afterwards; a column is somewhere you place things, so it stays exactly as tight as what you put in it. (Hero and Columns cannot: a Hero is the page's big opening band, and columns inside columns get impossible to work with.)
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
| **⚙** | Open its settings, right over the section — alignment, width, pictures, links, and the choices that are not words on the page |
| **✕** | Remove the section (it asks first) |

A section of your own writing has the same toolbar — hover it and it appears in the corner, so a block of writing can be moved, copied, aligned or widened like any other section.

**Lining a section up: left, centre or right.** The **⇤ ↔ ⇥** buttons on the top toolbar centre one
paragraph at a time. To do a whole section at once, open its **⚙** and use the two boxes at the top:

| Box | What it moves |
|---|---|
| **Align the content** | Everything inside the section — the heading, the writing, the button, the picture, the caption — lines up left, centre or right together. |
| **Align the section** | The section's own block. Only some sections are narrower than the page (writing, an enquiry form); those can sit on the left, in the middle, or over on the right. A section that already fills the width has nowhere to go, so nothing changes. |

Both start on **Default**, which is how the design lays that section out on its own. Set one, and the
page redraws as you choose it. A coloured CTA band stays centred and a specification table stays
left, whatever you pick — those two are designed that way on purpose.

**How wide a section is.** The third box in the same **⚙** panel:

| Width | What you get |
|---|---|
| **Default** | How the design lays that section out on its own — writing stops at a comfortable reading width rather than stretching across the whole screen. |
| **Wide** | The section's contents fill the page column, edge to edge of the white area. |
| **Full width** | The section breaks out of the page column entirely and runs the full width of the browser window. Good for a picture or a coloured band. |
| **A number** | Type an exact width in pixels in the small box next to it — 950, say. The dropdown then reads *Custom*. Empty the box to go back. |

Set a width and an alignment together and they work as you would expect: a section narrowed to 700
and set to *Align the section: Centre* sits as a neat centred column.

**Making a section move as the reader scrolls to it.** Two sections can be given an effect: **Numbers**
(the strip of big figures) and your own writing. Open the section's **⚙** and you will find an
**Effect** box under the width:

| Effect | What the visitor sees |
|---|---|
| **None** | Nothing moves. This is how every section starts. |
| **Fades in as you scroll to it** | The section drifts up into place as it comes onto the screen, instead of just being there. |
| **Gradient across the big text** | The headings — or, in a Numbers section, the big figures — are painted in the brand blue rather than plain black or white. |
| **Highlighter sweep behind the headings** | A blue bar draws itself under the heading, left to right, like a marker pen, as you scroll to it. |

A **Numbers** section has one more box, a tick called **Count up from zero**. Tick it and every figure
in the strip counts up as the reader arrives at it — 0 to 300 for *300+*, 0 to 25 for *25+ yrs*. Only
the number moves: words you put around it stay where they are, so *Up to 5 PB* keeps its "Up to" and
its "PB" still and only the 5 climbs. A figure with no number in it, like *Always on*, simply sits there.

**Setting an effect on one figure instead of the whole strip.** Under **Items** in a Numbers section,
each row now has its own **Effect** box and its own **Count up from zero** tick, next to the value and
the label. Leave them alone and that figure does whatever the whole section is set to; set them and
that one figure wins. So you can have one figure counting up in brand blue and the three beside it
sitting still.

**Pictures, links and settings.** Some things are not words on the page — which picture a section uses, where a button goes, how many posts a list shows. Those live on the section itself: hover it, click the **⚙** on its little dark toolbar, and a small panel opens over that section with exactly its own options — **Align the content**, **Align the section**, **Width**, **Effect** where the section has one, the picture, the button link, how many posts to list, and **+ Add** / ✕ for rows in a Cards, FAQ, Numbers or Specification section. Rows always come last in that panel, so the settings above them are never buried under a long list. Any picture field there has a **Choose file** button that uploads on the spot. The page updates as you type. Close it with **Esc**, the ✕, another press of ⚙, or by clicking anywhere else.

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
- **Deleted** — gone from the website and from your lists, but see section 12: an administrator can still bring it back.

The publish date is in **Indian time**, and so is every date and time shown anywhere in the admin panel. They used to be shown in London's winter time, five and a half hours behind, without saying so.

---

## 6. Pictures and files

The **Media** section is the shared library for every image, logo and PDF.

1. Go to Media and upload the file.
2. Give it **alt text** — a short description of what is in the picture. This is what a blind visitor's screen reader reads out, and it is one of the things Google looks at. Please do not skip it.
3. The file is then selectable anywhere the site asks for an image.

**Putting a PDF on a page.** Press `/` on an empty line and choose **PDF**. The section drops in; hover it, press **⚙**, and pick the PDF from the list — or press **Choose file** to upload one on the spot. Only PDFs are offered there, so you cannot pick a photo by mistake. Visitors then read it without leaving the page — scrolling, zooming and printing with their browser's own controls — and there is a **Download the PDF** button under it, which saves the file to their computer under the name it was uploaded with. That button is also how people on a phone read it: phone browsers usually will not show a PDF inside a page, so they download it and open it from there. Give the section a heading by typing straight onto the page above the viewer.

**The website hands out the pictures itself.** Every picture and PDF is now delivered by the website
rather than by the storage system behind it, so the file store can be shut away where only the website
can reach it. You will not notice a difference while working — files are uploaded, picked and shown
exactly as before — but two things follow from it. The **Public address** shown beside a selected file
in Media is the address on the website itself, safe to paste into an email or another page. And a
picture you have already used stays in the visitor's browser for a long time, so the site feels quicker
on a second visit; if you ever replace a picture, upload it as a new file rather than expecting an old
address to change.

**You do not have to go to Media first.** Anywhere a page asks for a picture — a Hero image, an Image or Gallery section, the Featured image in the panel on the right — there is a **Choose file** button right there. Pick a file and it uploads straight away, gets used on the spot, and joins the Media library so you can reuse it elsewhere. A small thumbnail next to it shows what is currently selected. Uploads made this way have no alt text yet, so add it in the Media section afterwards for anything important.

---

**Adding a lot of files at once.** Uploading forty partner logos one at a time through this screen is nobody's idea of a good afternoon. Put the folder somewhere on the server and ask a developer to run `flask import-media <folder>` — everything lands in Media exactly as if you had uploaded it, with a first draft of the alt text taken from each filename. It skips anything already there, so it is safe to run twice.

---

## 7. Enquiries from the website

Everything sent through a form on the site arrives under **Leads**, with the person's name, company, email, phone and message — and, for a quote request, what they said they were interested in and how many users.

Each enquiry has three states, and the tabs across the top follow them:

- **New** — nobody has picked it up yet.
- **In progress** — you are dealing with it.
- **Done** — finished.

Change the dropdown on the right of an enquiry and it moves to that tab. The blue number beside **Leads** in the sidebar counts the new ones.

## 8. Warranty records

**Warranty** in the admin panel is the register of every unit you have sold and how long it is covered for. It is what the *Warranty check* box on the website reads from — put that section on a page (press `/` and pick **Warranty check**) and customers can look their own unit up instead of emailing to ask.

**Adding a record.** Fill in the form at the bottom of the Warranty screen:

| Field | What to put in it |
|---|---|
| Serial number | Exactly as it is printed on the unit. Letters, numbers and symbols are all fine. Capitals do not matter — a customer typing it in lower case will still find it. |
| Customer name | The company or person who bought it. |
| Registered email | Whoever should be contacted about it. Optional. |
| Purchase date | When they bought it. Optional. |
| Warranty expiry | The date cover runs out. **Required** — this is what decides "in warranty" or "expired". It cannot be earlier than the purchase date; if it is, the record is not saved and you are told which two dates disagree. |
| AMC status | Yes or No, for an annual maintenance contract. |
| Remarks | A note to yourself. See below. |

**If something is wrong, the message appears on the field.** Put an expiry date earlier than the purchase date and the browser stops you the moment you press the button, with its own little message next to the date box — the same way it tells you a required field is empty. Nothing is sent and nothing is lost. Leave the purchase date empty and no such check applies: any expiry date is allowed.

A serial number already on file is the one thing the browser cannot know by itself, so that check happens when you press the button — the message comes back on the serial number box, and everything you typed is still exactly where it was. Fix that one thing and press the button again; you never have to find the record and type it out a second time. Your search and your place in the list survive too.

**Editing one.** Press **Edit** on any row: the record loads into the form, you change what you need and press **Save changes**. **Search** finds a record by serial number, customer name or email. Only an admin can delete a record.

**Remarks are private unless you say otherwise.** Anything you type in Remarks is an internal note that the customer never sees — unless you tick **"Show these remarks to the customer"**, which puts it on their warranty result. Use the tick for something helpful ("PSU replaced under RMA, October 2025") and leave it clear for anything internal.

**You never set "expired" yourself.** The status is worked out from the expiry date every time someone looks, so a record can never be out of date. A warranty expiring today still counts as in warranty.

**One thing to know.** The serial number is the only thing a visitor has to type, and the result shows the customer's name and registered email along with the dates. That was a deliberate choice — it keeps the check to one box — but it does mean anyone who knows a serial number can see who owns that unit. Everything except Remarks is public in that sense.

---

## 9. Menus, settings and redirects

**Settings** holds the things that appear everywhere: site name, tagline, logo, contact email and phone, address, social links, and the Google Analytics ID.

**About the logo.** Whichever picture you choose, the logo appears at the same size in the header and
at the bottom of every page — the site does not shrink or stretch it to suit the file. It fills that
space, which means blank margins inside your picture are trimmed off rather than counted as part of
the logo: you no longer have to crop a file perfectly for it to look right. The one thing to avoid is
artwork that is as tall as it is wide with the design running right to the edges, because the top and
bottom of a picture like that will be cut off. A wide, letterbox-shaped logo is what the space is cut
for.

**Menus** has its own screen now. Each row is one link: a label, where it goes, and whether it sits at the top level or drops down under the item above it. Drag the handle on the left to reorder, **+ Add item** for a new one, **✕** to remove one. Save writes the whole menu at once. One level of drop-down is all the site shows.

**Menus** control the header and footer navigation. The header menu supports one level of drop-down, which is how *Company* expands.

**The Services menu builds itself.** Hovering *Services* in the header opens a wide panel: your top-level services down the left, and whichever one you are pointing at expands on the right with its summary and its sub-services. You do not edit that panel anywhere — it is your Services pages. Change a service's **title** and the panel's wording changes; change its **Summary** (the box in the right-hand panel of the page editor) and the sentence under the name changes; add a sub-service under a service and it appears as a new tile. Publishing or unpublishing a service adds or removes it. The panel stays on whichever service you are pointing at while you move across to click one of its sub-services, and it holds however many services you have. The same list fills the *Services* column in the footer.

Two things follow from that. A service with no Summary shows its name and its sub-services but no sentence, so it is worth writing one. And the panel has room for eight top-level services; a ninth would not get its own tab.

**The contact details in Settings are used in three places** — the footer address block, the phone and email links, and the search-engine data. They are filled in from the company flyers: Prime ABGB, Simlim Square, and the +91 98219 09800 number.

**Social links.** The box under *Contact details* takes the web address of each of your social profiles,
**one per line** — paste the whole address, the way it appears in the browser. They show at the bottom of
every page as a row of small icons under the logo. LinkedIn, X, YouTube, Instagram and Facebook each get
their own icon; a profile on anything else still appears as a link, labelled with its website name instead
of an icon. They open in a new tab, so a visitor who clicks one does not lose the page they were reading. Remove a line and it disappears from the site. The same list is what tells Google which social
accounts belong to the company, so it is worth keeping complete.

**Settings** is split into tabs — Site identity, Contact details, SEO & analytics and Payments. Moving between them changes nothing until you press **Save settings**, and saving stores every tab, not just the one you are looking at.

**Redirects** send an old address to a new one. If a page moves — or you are bringing across links from the old website — add a redirect so the old link keeps working and nobody hits a "not found" page. This protects the search rankings you have already earned.

---

## 10. Being found: search engines and AI

This was an explicit requirement, so it is built in rather than bolted on. Every page is delivered to Google and to AI crawlers fully formed, with no waiting for scripts to run.

The site publishes automatically, with no work from you:

- `/sitemap.xml` — the list of every public page, for search engines
- `/robots.txt` — the rules for crawlers
- `/feed.xml` — an RSS feed of the blog
- `/llms.txt` and `/llms-full.txt` — a clean, plain-text version of the whole site, written for AI assistants to read
- **a plain-text version of every single page** — add `.md` to any address and you get that page's words with no design around them. `/about-us` becomes `/about-us.md`, `/services/storage/nas` becomes `/services/storage/nas.md`, and the home page is `/index.md`. Section headings, lists, tables and specification rows all survive; only the styling is dropped

### Why the `.md` versions matter

Assistants like ChatGPT, Claude, Perplexity and Google's AI answers read pages before they answer a
question. Handing them the words directly, instead of a page they have to pick apart, makes it far
more likely they quote IOPSTOR correctly — and cite us — when someone asks about NAS, ZFS or
hyper-converged storage. It is the same idea as a sitemap, but for AI rather than for Google.

You do not have to do anything. Every page you publish gets its version the moment it goes live, and
it updates itself the moment you edit the page — there is no separate file to keep in step, and
nothing to remember. Listing pages get one too: `/blog.md` and `/services.md` are the lists of what
is in them.

The one exception is deliberate: a page you have switched **"hide from search engines"** on, or a
draft, has no plain-text version either. Hidden means hidden from AI as well.

Each page also carries its title, description, social-sharing preview and machine-readable labelling (a Case Study is labelled an Article, a Service a Service, an Event an Event) so that search results and shared links look right.

**What you can control per page:** the SEO title, the description, and a "hide from search engines" switch for pages you would rather keep out of Google.

---

## 11. Activity: who did what

**Activity**, at the bottom of the sidebar, is the record of everything anybody has done in the admin panel — and it is only visible to administrators.

Every line says the same four things: **when** (in Indian time), **who**, **what**, and the internet address they were working from. It covers far more than pages: a setting changed, a menu rearranged, a picture removed, an enquiry marked done, somebody signing in or out, and somebody typing the wrong password. Nothing is left out and nothing can be edited away afterwards — not by you, not by an administrator, not by anybody. That is the point of it.

Where something was changed rather than merely created, the line says so — *2 things changed* — and clicking that opens a small table with one row per thing that moved: the name of what changed, what it **was**, and what it is **now**. For a page, that includes the writing itself, so you can read the old version of a paragraph beside the new one.

### Putting something back

Under that table is **Restore this version**. It puts the old values back exactly as they were, and the restore itself appears in Activity as a new line, so the record stays complete. It works for anything that was changed — a page, a setting, a menu, a picture's description — and for a page that was deleted.

It does not work for things that were properly removed: a person whose account was deleted, a picture deleted from the library, a category that was removed. Those lines still show you everything the record held, so you can see what was there and re-enter it, but the system will not recreate them behind your back and leave you with something half-working.

### Finding one thing

The three boxes at the top narrow the list: a particular person, a particular kind of action, or a kind of thing — type `posts` to see only page changes, `settings` for settings. Leave them alone to see everything.

---

## 12. If you delete a page by mistake

Deleting a page still warns you that it cannot be undone, and you should carry on treating it that way — it disappears from the website immediately and from your lists, and anybody visiting its address gets a "page not found".

But it is not actually thrown away. An administrator can find it by going to any content list, opening the status dropdown in the filter bar, choosing **trash**, and pressing **Filter**. Deleted pages appear there with a **Restore** button beside each one.

A restored page comes back as a **Draft**, not live — it has been off the website for a while, so somebody should look at it before visitors do. Everything else survives the round trip: its web address, its categories and tags, any pages filed underneath it, and any enquiries that came in about it. Press **Published** when you are happy with it and it is back exactly where it was.

Its web address stays reserved while it is in the trash, so a new page cannot quietly take it.

---

## 13. Payments

Products can carry a price and a checkout button. The payment step is currently a **placeholder** — it walks through the full flow and records the order, but no money moves. Connecting a real provider such as Razorpay or Stripe is a configuration change, not a rebuild.

---

## 14. Where the project stands

**Done:** the content system, the public website with its theme, the admin panel, search-engine and AI output, enquiry capture, the warranty register and its public check, media library, users and roles, the payment placeholder, and the Activity record with its trash and restore.

**Two things changed across every page** and need nothing from you: the bar at the top of the site is
now **white with black text**, with the IOPSTOR logo in its own blue-and-black rather than knocked out
to white — the footer stays dark, and the logo is still white down there. And the little icon that
shows in a browser tab (the "favicon") is now the IOPSTOR mark at every size a phone or a bookmark
asks for.

**One more thing changed behind the scenes** and needs nothing from you: pictures and PDFs are now
delivered by the website itself instead of by the file store behind it, so that store can be closed off
from the internet entirely. Nothing about uploading or choosing a file changes.

**The website now has its real address**, `https://www.iopstor.com`, and you sign in to edit it at
`https://www.iopstor.com/admin`. Nothing about writing a page changes — same screens, same buttons.

There are now **two separate copies** of the site: the live one at that address, and a practice one used
while the site was being built. They do not share anything. A page written on the practice site does not
appear on the live one, and vice versa — so anything the live site needs is written on the live site.
Your sign-in is per site too: the password you use on one is not the password on the other.

**Still to come:** a live payment provider.

---

## 15. Quick answers

**Is there a practice version of the site?** Yes — the one used while the site was being built. It is a
completely separate copy: content does not travel between the two in either direction, so a page you want
customers to see has to be written on the live site at `https://www.iopstor.com/admin`. If you are ever
unsure which one you are looking at, check the address at the top of the browser.

**Will visitors see a page the moment I press Save?** Yes, if it is set to **Published** — the live site
is served straight from what you save, with no waiting and nothing to rebuild. A **Draft** stays invisible,
and a scheduled page appears by itself at the date you set.

**Where did the Instagram link in the footer go?** It is still there, as an icon. The social links used to
appear as web addresses in the *Contact* column at the bottom of the page; they now sit under the logo as a
row of icons instead, so you can add all of your profiles without that column turning into a list of web
addresses. Add the rest under **Settings → Contact details → Social links**, one address per line.

**The quote form on Contact Us is no longer black.** That is deliberate. It now sits on the same soft grey panel as the *Apply* form on Careers, at the client's request. Nothing else about it changed — it still asks what the visitor is interested in and how many users, and the enquiry still arrives under **Leads** as a quote request.

**A long web address or code runs off the edge of the page.** It no longer does — a word too long to
fit now breaks and carries on on the next line, in the editor and on the live site, instead of
pushing the page sideways.

**Who changed this page?** Open **Activity** in the sidebar (administrators only) and type `posts` in
the third box. Every change to every page is there with the person's name, the date and time, and what
the page said before and after.

**I deleted a page by mistake.** It is not gone. Ask an administrator: they open the list the page was
in, set the status filter to **trash**, and press **Restore**. It comes back as a draft with its address,
its categories and anything filed under it intact, ready to be published again. See section 12.

**The times in the admin panel have changed.** They are now Indian time, and every screen says IST after
the time so there is no doubt. They were previously five and a half hours behind without saying so, which
also meant a publish date you typed was acted on five and a half hours late. Both are now correct.

**Somebody has been trying to sign in as me.** Wrong passwords are recorded. An administrator can open
**Activity**, choose *login failed* in the middle box, and see every attempt with the email that was
typed, the time, and where it came from.

**The Services list ran off the side of my phone.** It no longer does. On a narrow screen each service
group now reads down the page — the number, the group name, its description, then its services as
full-width buttons you can tap. On a laptop it is unchanged: the words on the left, the services in a
column on the right.


**Are the pictures on the site still working?** Yes. They are now handed out by the website itself
instead of by the file store behind it, which is a change nobody sees: the same pictures, at the same
places, a little faster on a repeat visit.

**I ticked Count up from zero and my figure is not counting.** It needs a number in it to count —
*Always on* has nothing to climb to, so it just sits there. A figure written with a comma, like
*1,200 TB*, also stays still: the counter cannot draw the comma, and a figure that ended up reading
*1200 TB* would not be the one you typed. Write it as *1200 TB* and it counts.

**Do the effects work in my browser?** Yes, in any current one. On the newest browsers an effect
waits until you scroll down to that section and then plays, which is the nicest version. On an older
one — Firefox before version 144, say — it plays once as the page loads instead. Either way you see
it. If you have asked your computer to reduce motion, nothing animates at all and every figure and
heading simply sits there in full, which is deliberate.

**How do I put a bit more space between two sections?** Press `/` on an empty line and pick
**Spacer**, then set its **Height** under the **⚙**. Four sizes, from a small nudge to a big
breath. Adding empty lines used to be the only way; this is the tidy one, and it survives being
dragged around like any other section.

**How do I draw a line between two sections?** Press `/` and pick **Divider**. For a line inside a
paragraph of writing instead, use the **—** button on the writing toolbar. They draw the same line.

**I changed something and the website looks the same.** Check the status is *Published* and the publish date is not in the future. Then refresh with Ctrl+F5.

**Can I change a page's web address?** The address is made from the title automatically, and the box is locked so it cannot be changed by accident — an address that changes breaks every link and bookmark pointing at the old one, and search engines drop the page. If you genuinely need to change it, the small **Edit** button beside the box unlocks it and warns you first.

**Two pages with the same name.** Two pages cannot share an address, but you are never stopped from writing one. Give a second page the same title as an existing one and it quietly gets three random letters on the end — *“testing” is already used, so this page is at “testing-shc”* — and the note under the box says exactly that. If you would rather choose the address yourself, press **Edit** and type one. There the rule is stricter: type an address another page already has and the note turns red, offers you a free one, and Save will not go through until you change it.

**A page gives "not found".** Its address is built from its slug and its type. A Service named *NAS* filed under *Storage* lives at `/services/storage/nas`, not `/services/nas`. Check the parent is set correctly.

**I need a new kind of content — say, Job Openings.** No development work is needed. An admin can add a new content type through the admin panel, and it gets its own list, its own form and its own web addresses.

**A customer says their serial number is not found.** Check the record exists under **Warranty** — search for part of the serial rather than all of it. Capitals and stray spaces do not matter, but a wrong character does. If it is genuinely missing, add it and they can check again straight away.

**Someone left the company.** An admin should delete their user account. This removes both their login and their access.

**I deleted something by mistake.** Deletion is permanent. Set things to *Draft* instead when you only want them off the site.

---

*Technical companion: [TECHNICAL.md](TECHNICAL.md).*
