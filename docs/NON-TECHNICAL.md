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

**The admin panel only opens from the office.** This is deliberate: the website itself is on the internet
for everybody, but the part where content is written is reachable from inside the premises only, so a
password that goes astray is worth nothing to somebody outside. Working from home or on mobile data, you
will not be able to reach it — and you will not get a "not allowed" message either. The page simply does
not exist from out there, which is the point: anybody scanning the internet for a login form finds
nothing to try passwords against.

1. On the office network, go to `/admin`.
2. Enter the email and password you were given.
3. You land on the dashboard, which shows counts of your content and recent enquiries.

**Two kinds of account:**

- **Editor** — can create and edit content, upload images, and read enquiries. This is the right level for most people.
- **Admin** — everything an editor can do, plus deleting content, changing site settings, and creating other user accounts.

If you can log in but see "Forbidden", your login exists but has not been given a role yet — ask an admin.

If the login page itself says the page cannot be found, you are almost certainly not on the office
network — check that first, before assuming the site is down. The public website answering normally while
`/admin` does not is exactly what this is supposed to look like from outside. If you *are* in the office
and everybody is getting that, it is a settings problem rather than something you did; tell whoever looks
after the server, and they have a note about what to check.

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
| **Testimonials** | What a customer said about you | *(no page of its own — see below)* |
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

**Testimonials are added like anything else.** Open **Testimonials** in the sidebar, click **Add new**, and fill in
as much or as little as you have:

- **Title** — the person's name. This is the only thing you must fill in.
- **What they said** — the quote itself, in their words. This is the box that would say *Summary* on any other kind
  of content; on a testimonial it is the quote, so it says so.
- **Featured image** — their photo. It is shown as a small round portrait. Leave it out and the circle shows a
  simple person outline instead, which is what most of them will have — so a testimonial with no photo still looks
  finished rather than unfinished.
- **Job title** and **Company** — either, both or neither. If you fill in only one, only that one shows, with no
  stray comma left behind.
- **Stars out of 5** — type a whole number from 1 to 5. Leave it empty and the card simply has no stars, and closes
  up the space they would have taken. If you type something silly like 9, the card shows five, not nine.

Set the testimonial to **Published** and it appears on the home page straight away. Nothing else to arrange: the
row shows the newest twelve, and it grows as you add to it. If you ever want more or fewer than twelve, that is the
**Limit** box on the section itself — open the home page, click the testimonials section and change the number.

**They have no pages of their own**, for the same reason partners do not — a quote is something shown on our pages,
not somewhere a visitor goes. The admin list shows *"no page of its own"* where the web address usually goes. All of
them together are at `/testimonials` if you ever want to link to the full set.

**On the home page they slide.** The row drifts sideways on its own, one card at a time, and:

- **it stops the moment somebody points at it**, so nobody ever loses their place mid-sentence;
- the **‹ and › buttons** step it one card, and the **dots** underneath jump straight to a position;
- a visitor can also just **scroll it with the mouse wheel, drag it, or swipe it on a phone**;
- for anyone whose computer is set to reduce motion, it **does not drift at all** — the buttons still work.

You will see the cards in the page editor too, but they will not drift there and there are no arrows: things moving
around while you are trying to write is unhelpful, so the editor shows them still.

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
| **Definitions** | Terms down one side, what each one means down the other — like the ZFS list on the NAS page |
| **Key points** | A heading, a short intro and a dashed list of points, with an optional button — the shape used down one side of the home page |
| **Post list** | Automatically pulls in the latest Services, Case Studies or Blog posts. You do not maintain this by hand — new items appear on their own |
| **Contact form** | An enquiry form. Choose *contact*, *quote* or *career* |
| **Embed HTML** | For dropping in code from another service, like a map or a video |

**Rule of thumb:** if a page starts with a Hero, the Hero supplies the page's main headline. Otherwise the page title is shown at the top, above whatever you have written. **Blog articles and case studies are the exception**, and always show their own title, date and categories at the top whatever you put first — a Hero on one of those is a banner further down the page, not the headline.

**The panel on the right** holds everything about the page that is not the page:

| Group | What it is for |
|---|---|
| **Publish** | Draft or published, and the date (see §5). The small grey or green label in the top bar shows what is *saved* — it changes when you press Save, not before. |
| **Web address** | Made from the title automatically. If another page of the same kind already uses that address, three random letters are added so yours still works — `testing-shc` — and the note under the box tells you so. **Edit** if you really need to change it; it asks first, because changing it breaks existing links. A handful of words — `admin`, `api`, `media`, `static`, `healthz` — belong to the website itself and cannot be used; if you pick one, Save says so and asks for another. Only where the word would be the *start* of the address: a blog post called "Admin" is fine, because blog posts sit under `/blog/`. |
| **Summary** | A sentence or two. Shown in lists, and under the page in Google results. |
| **Featured image** | The picture used in lists and when the page is shared, and — unless the page starts with a **Hero** section — the big picture at the top of the page itself. A Hero draws its own picture, so on a page that has one this box only feeds the list card and the shared link, and the box says so right above it whenever that is the case. (On a blog article or a case study the title, date and categories still show; it is only the picture the Hero replaces.) **Choose file** uploads on the spot. Tick **Show the title on this picture** just underneath and the picture moves behind the page's title instead — full width, darkened, white text, the way a Hero section looks. |
| **Organise** | The parent page (for services) and any categories or tags — see below. It only appears for types that have one or the other. Nothing here asks you to number your pages — lists show the newest first on their own. |
| **Details** | The extra boxes some kinds of content have — a case study's client, an event's dates, a datasheet's PDF. Leave one blank and nothing at all shows for it on the page; there is no empty space left behind. Where a type has long boxes (Challenge, Solution, Results), **Where the long details go** decides where they land on the page — see below. |
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
| **↶ ↷** | Undo and redo — **Ctrl+Z** and **Ctrl+Shift+Z** (⌘ on a Mac; Ctrl+Y also redoes on Windows). They step back the last thing *you* did anywhere on the page, not just your typing: a section you deleted, moved, copied or added, and anything you changed in a section's **⚙** settings. They go grey when there is nothing left to undo. If somebody else is editing the same page, undo never touches their work. |
| **Normal text ▾** | Sets the size of the line: **H1** down to **H6**, or back to *Normal text*. H2 is the normal way to start a section, H3 for something under it, and so on down. |
| **Size ▾** | Makes ordinary writing bigger or smaller — *Small*, *Normal*, *Large*, *Larger*, *Huge*. **Select some words and only those words change.** With nothing selected it sets the size for what you type next, the way **B** and *I* do — it no longer resizes the line you happen to be standing in. *Normal* puts it back. Adjusting twice works: pick *Large*, then *Larger*, and the same words change again. It is greyed out on a heading, because a heading's size is set by its H-level instead — and turning a line into a heading drops any size you had set on it, so the heading comes out the size a heading should be. |
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

- **Hero** — the big opening band. *Small label above the heading* is the short blue line above the headline ("The Storage Specialist"). There is a **second button** now, which draws as an outline next to the main one. And **Full-width band, picture behind the words** — the tick that used to be called *Dark background* — turns the hero into the full-width band used on About Us, where the picture you choose becomes a faded backdrop *behind* the words instead of sitting beside them. It was renamed because it decides the **shape** of the hero, not its colour: **the colour is the section's own Background setting**, in the same **⚙** panel, and it now works on a hero where it used to do nothing at all. So a full-width hero can be black (leave Background alone), light grey or blue, and a hero with the picture beside the words can be any of those too. Whichever you pick, the headline, the small label and the buttons switch to light or dark text to suit it — you do not have to do anything about that. A hero you have never set a Background on keeps the band it has always had, and the dropdown shows you which one that is — so a full-width hero opens on *Dark*. Choose **Page background** and you get the full-width band on white, which is a shape the site did not have before. The faded picture stays faded — it sits at about a fifth of its strength so the words stay readable — so on a light grey or blue band expect a pale ghost of it rather than the photograph. Two newer controls decide how the picture behaves. **Where the picture goes** offers *Beside the words* (how every hero looks today, and what you get if you leave it alone), *Above the words* and *Below the words* — the two stacked choices put the picture across the full width, which suits a wide photograph better than a narrow column does. **Hold the picture still** stops the picture drifting gently up and down and stops the soft glow behind it pulsing; it still slides into place as the page loads, and if you have given the hero several pictures they still take turns. **Hide the glow behind the picture** is a separate tick that removes the faint blue halo altogether — the two are not the same thing, and holding the picture still only stops that halo *pulsing*, it does not take it away. The halo is very faint and mostly sits behind the picture, so expect a small change rather than an obvious one. Neither control does anything on a hero with the full-width band ticked, because there the picture is the backdrop rather than something sitting next to the words.
  A hero can also hold **more than one picture**. Under *Pictures that take turns*, add a row per picture; from two rows up they fade from one to the next on their own, about four and a half seconds each, with small bars underneath showing which one is up. That is what the home page does with the three appliances. One picture, or none, behaves exactly as before — and a visitor whose device is set to reduce motion simply sees the first picture, still.
- **Automatic list** — the section that lists your pages and keeps itself up to date. *Header link text* and *Header link* put a link like "All services →" on the right of the section's heading. The cards style themselves to suit what they are listing: services show a number and their sub-services, products show the product picture, case studies show their industry and solution, blog posts show the date. You do not choose that; it follows the content type. In the card style, a service card lists **four** sub-services and then says "+3 more" rather than all of them — every card in a row is as tall as the tallest, so one long list used to leave the cards beside it half empty. The full list is on the Services page, where each one is a button you can click. **Items per row** decides how many sit side by side. Leave it on *As many as fit the width* and the row simply fills up, which is how every list behaved before. Choose **Even rows** and the system works the number out from how many there are: it uses **as few lines as it can**, and makes those lines as equal as the number allows — fourteen partners become two rows of seven instead of a row of eight and a row of six, and fifteen become a row of eight and a row of seven rather than three rows of five. If you add or remove one it works it out again on its own. When a number will not split evenly, only the last line is short — a short last line is preferred to a whole extra line. You can also just pick a number from 2 to 8. On a phone the list always wraps to fit the screen, whatever you choose here. **List style** chooses between the two shapes an automatic list has. Leave it on *Automatic* and a list of services opens as a stack — one service per line, and pointing at a line or tapping it slides that one open to show its description and all of its sub-services, closing whichever was open before. They all start closed, so the section is a tidy list of five lines until somebody points at one. Every other kind of list stays a row of cards. *Cards* and *Accordion* force one shape or the other, whatever is being listed. The stack shows **all** of a service's sub-services, not four and a count, because only one is open at a time so there is room for them. **Colour when open** decides what the opened line looks like — *Black* as the design draws it, or *Blue*, or *Light grey*. The closed lines stay white whichever you pick.
- **People** is new, and it is the pair of name cards on **About Us** — a round picture, a name in bold and a job title under it, side by side. Each person is three boxes under the section's **⚙**: *Name*, *Role* and *Image*. Leave the picture empty and you get the soft hatched circle the page has always shown, so you can put the names up today and add photographs later. **+ Add item** puts another person in, the arrows reorder them and **✕** takes one out. You can also type straight over a name or a job title on the page itself. The cards share the width evenly, so two sit side by side in a column and four across a full-width page; on a phone they stack. Until now these two cards were part of the words around them and could not be edited as cards at all — see *Quick answers*.
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
paragraph at a time. To do a whole section at once, open its **⚙** and use the first two boxes:

| Box | What it moves |
|---|---|
| **Align the content** | Everything inside the section — the heading, the writing, the button, the picture, the caption — lines up left, centre or right together. |
| **Align the section** | The section's own block. Only some sections are narrower than the page (writing, an enquiry form); those can sit on the left, in the middle, or over on the right. A section that already fills the width has nowhere to go, so nothing changes. |

Both start on **Default**, which is how the design lays that section out on its own. Set one, and the
page redraws as you choose it. A coloured CTA band stays centred and a specification table stays
left, whatever you pick — those two are designed that way on purpose.

**How wide a section is.** Also in the same **⚙** panel:

| Width | What you get |
|---|---|
| **Default** | How the design lays that section out on its own — writing stops at a comfortable reading width rather than stretching across the whole screen. |
| **Wide** | The section's contents fill the page column, edge to edge of the white area. |
| **Full width** | The section breaks out of the page column entirely and runs the full width of the browser window. Good for a picture or a coloured band. |
| **A number** | Type an exact width in pixels in the small box next to it — 950, say. The dropdown then reads *Custom*. Empty the box to go back. |

Set a width and an alignment together and they work as you would expect: a section narrowed to 700
and set to *Align the section: Centre* sits as a neat centred column.

**The colour behind a section.** The **Background** box in the same panel. **Page background** is
the plain white the page is built on, and is how every section starts; **Light grey** is the soft
band the design alternates down a page to separate one part from the next; **Dark** and **Blue**
are the full-width coloured bands. A section that is already a coloured band by design — the blue
*Call to action*, the black *Numbers* strip — keeps its own colour unless you pick one here.

**Too much space above and below a section.** The **Spacing** box, last in the panel:

| Spacing | What you get |
|---|---|
| **Default** | The generous air the design gives every section. This is how every section starts, and nothing already published has changed. |
| **Medium** | About half the usual. |
| **Small** | About a quarter — useful for a Divider, which otherwise sits in a lot of white for one thin line. |
| **None** | No air at all above or below. The section sits directly against its neighbours. |

Two things worth knowing. **Each section only controls its own space**, and the gap you see between
two sections is both of theirs added together — so to really close up around a Divider, set it on
the Divider *and* on the sections either side of it. Setting only the Divider halves the gap;
setting all three closes it. And there is deliberately no setting **bigger** than Default: to add
space, drop in a **Spacer** section instead, which you can drag, copy and delete like anything
else. A Spacer has no Spacing box of its own, because its **Height** already is its spacing.

**Giving a section a bit of movement as the page opens.** Two sections can be given an effect: **Numbers**
(the strip of big figures) and your own writing. Open the section's **⚙** and you will find an
**Effect** box under the width:

| Effect | What the visitor sees |
|---|---|
| **None** | Nothing moves. This is how every section starts. |
| **Fades in as the page loads** | The section drifts up into place as the page opens, instead of just being there. |
| **Gradient across the big text** | The headings — or, in a Numbers section, the big figures — are painted in the brand blue rather than plain black or white. |
| **Highlighter sweep behind the headings** | A blue bar draws itself under the heading, left to right, like a marker pen, as the page opens. |

A **Numbers** section has one more box, a tick called **Count up from zero**. Tick it and every figure
in the strip climbs as the page opens — 0 to 300 for *300+*, 0 to 25 for *25+ yrs*. Only
the number moves: words you put around it stay where they are, so *Up to 5 PB* keeps its "Up to" and
its "PB" still and only the 5 climbs. A figure with no number in it, like *Always on*, simply sits there.

**Setting an effect on one figure instead of the whole strip.** Under **Items** in a Numbers section,
each row now has its own **Effect** box and its own **Count up from zero** tick, next to the value and
the label. Leave them alone and that figure does whatever the whole section is set to; set them and
that one figure wins. So you can have one figure counting up in brand blue and the three beside it
sitting still.

**Pictures, links and settings.** Some things are not words on the page — which picture a section uses, where a button goes, how many posts a list shows. Those live on the section itself: hover it, click the **⚙** on its little dark toolbar, and a small panel opens over that section with exactly its own options — **Align the content**, **Align the section**, **Background**, **Width**, **Spacing**, **Effect** where the section has one, the picture, the button link, how many posts to list, and **+ Add** / ✕ for rows in a Cards, FAQ, Numbers or Specification section. Rows always come last in that panel, so the settings above them are never buried under a long list. Any picture field there has a **Choose file** button that uploads on the spot. The page updates as you type. Close it with **Esc**, the ✕, another press of ⚙, or by clicking anywhere else.

**The writing area has been rebuilt**, and for most sections you will not notice — the same toolbar,
the same buttons, the same typing. It is what lets two people write in the same paragraph at once
(*Seeing who else is on the page*, below).

A few sections are left on the old writing area because they contain layout the new one cannot hold —
the ones with a table or a side-by-side panel. On this site that is **Contact Us** and part of
**NAS**. Hover such a section and it says so. You can still
edit them exactly as before; they are the sections that will not get shared editing when it arrives.

In a section on the **new** writing area, five buttons are switched off: **picture**, **table**,
**embed**, the **divider**, and the **text size** dropdown. Those build the very layout that would
push the section back onto the old area, so they are offered where they work rather than failing
quietly. Everything else — bold, italic, headings, bullets, numbering, quotes, links, alignment and
colour — behaves exactly as it did.

One thing you may notice once per section: the first time you save a section on the new writing area,
**Activity** may record a change even if you only fixed a typo. The new area tidies the invisible
markup as it loads. Nothing you can see on the page changes, and it only happens once.

**The page now saves itself, and the button puts it on the website.** As you type, a small line at the top right says **Saved just now** — you no longer have to remember to save, and you cannot lose an afternoon's work to a closed laptop or a browser crash. What is saved is *not* on the website yet: it is your work in progress, and only you and the other editors can see it.

The blue button at the top right is what puts it on the site. It says **Publish** on a page that is live, and **Save** on one that is not — because pressing it on a page nobody can see does not publish anything to anybody.

**These are two different things, and they are easy to mix up.** *Status* (in the right-hand panel: Draft, Published, Scheduled) decides **who is allowed to see the page at all** — see §5. **Publish** decides **which version** those people see. A page whose status is Draft is invisible to the public whatever you press; a page that is live keeps showing the last published version until you press the button again.

While you have changes that have not been published, an amber note sits above the page saying so, with a **Throw them away** link that puts the page back to the version on the site. That link only discards the unpublished work — it never touches what visitors can see.

If something required is missing, the page comes back with the problem listed at the top and your work still in place.

**Preview keeps up with your colleague too, without losing your place.** If somebody else is writing while you are looking at Preview, their words appear there as they type — they used to show only when you switched back to Edit, which also meant pressing Publish from Preview could put the page live without their last paragraph. And if you have scrolled halfway down a long page to look at something, it stays where you put it while they type; it used to jump back to the top every second or so.

**Seeing who else is on the page.** This works everywhere now, the live site included — it used to be switched on only on the practice site, because of how the site connects to its database, and there is nothing to turn on any more. If a colleague has the same page open, their initials appear in a coloured circle at the top right, beside the blue button. Click into a section and they see a coloured line down the edge of it and a small label saying you are typing there — and you see the same for them. It is a nudge, not a lock: nothing stops two people typing in the same paragraph, it just means you can see that you are about to.

**You are writing in the same document.** What you type appears on their screen and theirs appears on yours, within about a second. You can both be in the **same paragraph**, in the same sentence, and both sets of words are kept — nobody's typing replaces anybody else's, the way it works in Google Docs. Add a section, remove one, change a picture, and it turns up on their screen too.

**Activity still says who did what.** Everybody's writing is on one screen now, but the log is not one entry for the room: each person gets their own line listing only the sections *they* changed (§11).

**The sections that cannot do this yet, and what happens instead.** Two kinds:

- The few sections still on the old writing area — on this site **NAS**'s specification table and **Contact Us** — say so when you hover them. Two of you can still type in one of those, and it will not scramble under your fingers: while you are typing, nothing moves, and their version arrives when you click away. But only one of the two versions survives, so it is worth agreeing who has it.
- Inside a **Cards**, **FAQ**, **Numbers**, **Specification**, **Definitions**, **Key points** or **People** section, the rows are shared as a group rather than row by row. Two people in two different rows of the *same* section will lose one side. Two people in two different sections are fine. Everything *outside* the rows — the heading, the small label above it, the intro — is shared word by word like any other writing.

Two smaller things you may notice. The circles vanish on a narrow phone screen, because the bar at the top is already full — the coloured lines on the sections still show. And if somebody else adds or removes a section while you are typing, the page redraws and your cursor goes back to the top; your words are not affected.

**If somebody else published the same page.** Two people can open the same page at once, and there was a time when the second person to save quietly wiped out the first person's work — with both of them told it had saved. That no longer happens. If a colleague published while you were writing, your press of the button stops and an amber note appears above the page:

> Somebody else saved this page while you were writing. Nothing of yours has been lost — it is all still on this screen. Save again to replace their version, or open the page in another tab to see what changed first.

Everything you typed is exactly where you left it. You are warned once: press the button a second time and your version goes through, replacing theirs. Their version is not lost either — it is in **Activity** (§11), where it can be put back. If you would rather keep their work, open the page in a second browser tab first to see what they changed, then copy across whatever you still need.

> **Advanced.** At the very bottom of the right-hand panel, *Advanced* shows the page's sections as raw data. It is there for developers; you never need to open it.


### Checking how it looks

In the bar at the top of the screen are two buttons: **Edit** and **Preview**.

**Preview** shows the page exactly as a visitor gets it — with the site header and menu, the
breadcrumb trail, the featured image, the footer, and none of the editing marks. Nothing is
published by doing this, and it works on a page that has never been published, which is the point:
you can check a draft before anyone else sees it. The preview keeps up as you type.

**Desktop / Tablet / Phone**, which appear next to them in Preview, redraw the page at those screen sizes, so you can check a page
works on a phone before publishing rather than after.

**Search & social** is the fourth button in that same row, and it swaps the page for two small
cards: **how the page will look in a Google result** and **when someone shares the link** on
WhatsApp or LinkedIn — the title, the web address, the description and the picture. They also tell
you if your title or description is too long and will be cut short. If the share card says
*No image*, set a Featured image in the panel on the right. Both keep up as you type, the same way
the page does. (These cards used to sit underneath the page, so you had to scroll past the whole
thing including the footer to reach them; they have their own button now, and Preview shows only
the page.)

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

1. Go to Media and press **Browse**. You can pick **as many files as you like in one go** — hold Ctrl (⌘ on a Mac) as you click them, or drag a box round the lot — and press **Upload** once. Everything together has to fit in 20 MB, so a big batch of photographs may need splitting into two or three goes; if it is too much the site says so and nothing is lost.
2. Give each one **alt text** — a short description of what is in the picture. This is what a blind visitor's screen reader reads out, and it is one of the things Google looks at. Click the file in the grid and the box is on the right. Please do not skip it.
3. The file is then selectable anywhere the site asks for an image.

If one file in a batch is a kind the site does not take — a Word document, say — the others still go up. The message at the top tells you how many arrived and names the one that did not.

**Choosing files, and deleting several at a time.** Click a file — anywhere on it, not just the little box in its corner — and it is selected: it turns blue, and its details open in the panel on the right. To choose more than one:

- **Ctrl-click** (**⌘-click** on a Mac) a second, third, fourth file to add each one to what you have already chosen. Ctrl-click one again to take it back out.
- **Shift-click** to take everything between the last file you clicked and this one, in one go — the quick way to select a whole row or a whole screenful.
- A plain click on its own starts again with just that file.
- The tick boxes still work on their own if you prefer them, and they are what you use on a phone or tablet, where there is no Ctrl key.

Then press **Delete selected** underneath the grid. It stays grey until you have chosen something, turns red once you have, and asks you to confirm before anything goes. You can still delete one file at a time from the panel on the right, exactly as before. Deleting is permanent: anything on the site using that picture will lose it, and it does not come back from Activity.

One thing this costs: Ctrl-clicking a file no longer opens it in a new browser tab, because Ctrl-click now means "add this one to the selection".

**Putting a PDF on a page.** Press `/` on an empty line and choose **PDF**. The section drops in; hover it, press **⚙**, and pick the PDF from the list — or press **Choose file** to upload one on the spot. Only PDFs are offered there, so you cannot pick a photo by mistake. Visitors then read it without leaving the page — scrolling, zooming and printing with their browser's own controls — and there is a **Download the PDF** button under it, which saves the file to their computer under the name it was uploaded with. That button is also how people on a phone read it: phone browsers usually will not show a PDF inside a page, so they download it and open it from there. Give the section a heading by typing straight onto the page above the viewer.

**The website hands out the pictures itself.** Every picture and PDF is now delivered by the website
rather than by the storage system behind it, so the file store can be shut away where only the website
can reach it. You will not notice a difference while working — files are uploaded, picked and shown
exactly as before — but two things follow from it. The **Public address** shown beside a selected file
in Media is the address on the website itself, safe to paste into an email or another page. And a
picture you have already used stays in the visitor's browser for a long time, so the site feels quicker
on a second visit; if you ever replace a picture, upload it as a new file rather than expecting an old
address to change.

**You do not have to go to Media first.** Anywhere a page asks for a picture — a Hero image, an Image or Gallery section, the Featured image in the panel on the right — there is a **Choose file** button right there. Pick a file and it uploads straight away, gets used on the spot, and joins the Media library so you can reuse it elsewhere. A small thumbnail next to it shows what is currently selected. No upload anywhere on the site asks for alt text at the moment it happens — one box above a batch of five could only ever describe one of them — so add it in the Media section afterwards for anything important.

---

**Adding a very large number of files.** A batch at a time covers most of it, but forty partner logos is still several trips to the 20 MB limit. Put the folder somewhere on the server and ask a developer to run `flask import-media <folder>` — everything lands in Media exactly as if you had uploaded it, with a first draft of the alt text taken from each filename. It skips anything already there, so it is safe to run twice.

---

## 7. Enquiries from the website

Everything sent through a form on the site arrives under **Leads**, with the person's name, company, email, phone and message — and, for a quote request, what they said they were interested in and how many users.

Each enquiry has three states, and the tabs across the top follow them:

- **New** — nobody has picked it up yet.
- **In progress** — you are dealing with it.
- **Done** — finished.

Change the dropdown on the right of an enquiry and it moves to that tab. The blue number beside **Leads** in the sidebar counts the new ones.

**Junk enquiries.** Every form on the site carries a hidden trap that automated spam programs fill in
and a real visitor never sees — anything that fills it is quietly thrown away and never reaches this
screen. That is the only thing standing between the form and **Leads** at the moment: there is no
picture puzzle to solve, and no limit on how many times the form can be sent. That is the right trade
while the site is new and no junk has arrived; if junk does start turning up, say so and it can be shut
off before it ever reaches the website, with nothing changing on your side. One other quiet limit: a
message longer than about two pages of typed text is shortened before it is saved, so nobody can fill
the site up by sending a book. No real enquiry comes anywhere near that length.

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

**About the logo.** Whichever picture you choose, the logo is given the same amount of room in the
header and at the bottom of every page, and it is fitted **whole** into that room — nothing is ever
cut off, whatever shape the file is. The one thing that matters is how the file is exported: blank
margins around the wordmark are now counted as part of the picture, so a file saved with a lot of
empty space around the logo will look small. **Trim it before uploading** and it fills the space
properly. A wide, letterbox-shaped logo with little margin is what the space is cut for.

**Menus** has its own screen now. Each row is one link: a label, where it goes, and whether it sits at the top level or drops down under the item above it. Drag the handle on the left to reorder, **+ Add item** for a new one, **✕** to remove one. Save writes the whole menu at once. One level of drop-down is all the site shows.

**Menus** control the header and footer navigation. The header menu supports one level of drop-down, which is how *Company* expands.

**The Services menu builds itself.** Hovering *Services* in the header opens a wide panel with one column per top-level service and **every** sub-service listed underneath it, each with a small picture beside its name. Nothing has to be pointed at to be read. You do not edit that panel anywhere — it is your Services pages. Change a service's **title** and the panel's wording changes; add a sub-service under a service and it appears in that column; publishing or unpublishing one adds or removes it. The name at the top of a column is still a link to that service's own page, and along the bottom are *All services* and *Not sure which fits? Request a quote*. It holds however many services you have — the columns simply get narrower, and on a narrow screen the menu becomes a list you tap open one group at a time. The same list fills the *Services* column in the footer.

**Choosing the little picture beside a service.** Each service has an **Icon** box in the right-hand panel of the page editor. Leave it empty and the site picks a sensible picture for that service on its own, which is what every service does today. To change one, type one of these names into the box: `nas`, `das`, `sas`, `aws`, `proxmox`, `vmware`, `daas`, `staas`, `vps`, `lxc`, `serverless`, `s3`, `draas`, `ai`, `sql`, `tally`, `sap`, `dot`. Anything else in the box is ignored rather than showing an empty square.

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

- `/sitemap` — the list of every public page, for search engines
- `/robots.txt` — the rules for crawlers
- `/feed` — an RSS feed of the site's news: **blog posts, case studies, events and datasheets**, newest first
- `/llms.txt` and `/llms-full.txt` — a clean, plain-text version of the whole site, written for AI assistants to read
- **a plain-text version of every single page** — add `.md` to any address and you get that page's words with no design around them. `/about-us` becomes `/about-us.md`, `/services/storage/nas` becomes `/services/storage/nas.md`, and the home page is `/index.md`. Section headings, lists, tables and specification rows all survive; only the styling is dropped

**`/sitemap` and `/feed` are now proper pages.** Click *Sitemap* or *RSS* in the footer and you get a
designed page in the site's own style — the sitemap lists every page grouped by what it is, and the
feed shows recent items as cards you can click. The raw versions machines read are still there at
`/sitemap.xml` and `/feed.xml`, and each page links to its own, but you never need to look at those.

The other three keep their `.txt` endings on purpose: those are fixed names that search engines and
AI tools look for by name, and renaming them would quietly stop them being found at all.

One small consequence: **you can no longer name a page "Feed" or "Sitemap"**, because the site
itself now answers on those two addresses. Nothing you have is affected — we checked, and no page
uses either name.

### What appears in the RSS feed, and what never will

The feed is the site's news. A **blog post, case study, event or datasheet** goes into it the moment
you publish it. A **service, technology partner or testimonial never does**, however often you edit
one — those are the catalogue, not news, and a feed that announced them would cry wolf. The home page
and the other standing pages stay out for the same reason. If you need that changed, it is a small
job for whoever looks after the site; there is no setting for it on your screens.

Each entry carries the headline, the date, the picture and the tags, and a short summary underneath.
**That summary is the Excerpt you wrote**, or the page's own opening words if you left the Excerpt
empty — and for a case study, its **Challenge**. If a post has none of those filled in, the entry is
just a headline with nothing under it, which is worth knowing: filling in the Excerpt is what makes
the entry read well wherever it is picked up.

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

Every line is a sentence. *Sukhpreet Saluja — published the blog post **Prime ABGB***. *Priya Sharma — added the picture or file **hero.png***. Beside it sits the date and time in Indian time and the internet address the person was working from.

**The address in the last column is the visitor's own, not the machinery's.** There are two ways to reach
this site — over the internet, and from inside the office network — and until now the second one recorded
the address of the equipment in between rather than the person. Both now record the person. The site also
refuses to take somebody's word for it: an address is only believed when it was passed on by our own
equipment, so nobody can sign a wrong address into the record.

**Where the site thinks you are connecting from** sits just above the filters, folded shut. Open it and it
tells you the address that will be written against anything you do, where the connection reached the site
from, and whether that was our own equipment. It is there for when an address in the log looks wrong — open
it, and it says what the site is actually seeing. Nothing on it is a setting; it only reports.

**Pages now produce two kinds of line, and the difference is worth knowing.** *Worked on the blog post **Prime ABGB*** is one person's sitting at that page — it appears about fifteen minutes after they stop, and lists the sections **they** changed. *Published the blog post **Prime ABGB*** is the moment that work went on the website. Before the editor started saving itself, those were the same act and got one line; they are not the same act any more.

**A sitting is not interrupted by leaving the page.** Reload, go and look at Media, come back and carry on — it is all one line, covering everything you changed. Only fifteen minutes of genuine quiet ends a sitting and writes it up.

**A line covers your own work, and starts from the moment you touched each section.** If a colleague writes a paragraph while you have the page open and you then add a sentence to it, your line shows your sentence, not theirs. One thing it cannot untangle: if the two of you take turns in the *same* section — you, then them, then you again — their words in the middle will sit inside your line, because a before-and-after picture cannot say who typed which word. Sections you removed, added or moved are listed too, whether or not you typed in them.

Two consequences. There is **one line per person per sitting**, not one per keystroke — an afternoon of editing is a line, not a hundred. And typing that is never published leaves no line of its own content; if somebody throws unpublished changes away, that *act* is recorded (*threw away unpublished changes to…*) even though the words are not.

Each kind of thing is called what you call it. A page says **page**, a service says **service**, a datasheet says **datasheet** — not the name the database uses for them. So it covers, and says so in plain words: every page, blog post, service, case study, event, technology partner, datasheet and product; pictures and files added, renamed or removed; enquiries arriving and being moved along; warranty records; settings; menus; people added, changed or removed; **passwords changed**, both your own and one an administrator sets for somebody else; signing in, signing out, wrong passwords, and being locked out after too many of them.

Nothing can be edited away afterwards — not by you, not by an administrator, not by anybody. That is the point of it.

### Seeing what changed

**Show what changed** opens the detail: one block per thing that moved, with what it **was** and what it is **now** side by side.

For a page, you get one line per thing that actually moved, and each one says **which section it was in** — *Hero section*, *Numbers section*, *Column 2, Picture section*. Nothing else is shown, so a change in a long page is one or two short lines rather than the whole page printed twice.

If you changed the writing, that line shows the writing, in plain words rather than the code behind it, and **the part that changed is marked** — what you removed struck through in red, what you added highlighted in green. A single word altered in a long page is visible at a glance, and a long stretch nobody touched is shortened to its two ends so the marked part is not buried.

If you changed something the words cannot show — a picture, a link, a tick box, an effect — the line names the setting and both values in the words you chose them by: *"Numbers section, row 2 — Effect · was None · now Gradient across the big text"*. Inside a row of a repeating list, it tells you which row.

And if a section was added, removed or moved, that is a sentence: *"Added Cards"*, *"Moved the sections around"*. A save that only made a word bold says *"Formatting changed"* — never "nothing changed", because something did.

### What it does not record

Looking at things. Opening a page to read it, or viewing the Leads screen, leaves no line — on a normal day that would be about fifty lines of looking for every line of doing, and the change you came to find would be buried underneath them. Only things that actually changed, plus signing in and out.

### Putting something back

Under that detail is **Restore** — one button for the whole entry, at the bottom, whatever number of lines the detail has. It puts **the whole thing** back as it was before that change, not just the line you happen to be looking at: for a page, that is the entire page. The restore itself appears in Activity as a new line, so the record stays complete. It works for anything that was changed — a page, a setting, a menu, a picture's description — and for a page that was deleted.

It does not work for things that were properly removed: a person whose account was deleted, a picture deleted from the library, a category that was removed. Those lines still show you everything the record held, so you can see what was there and re-enter it, but the system will not recreate them behind your back and leave you with something half-working.

### Finding one thing

The three boxes at the top narrow the list: a particular person, a particular kind of action, or a particular kind of thing. They are drop-downs of ordinary words — pick **Pages and other content** to see only content changes, **Setting** for settings. Leave them alone to see everything.

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

**The brand colours are the company's own now.** Every blue on the site — buttons, the small labels above headings, the blue band at the bottom of a product page, the tab icon — is the blue taken from the IOPSTOR logo itself, so the logo and the button beside it are the same colour. Headings and body text moved to the dark grey from the *STOR* half of the logo, a little softer than the near-black they were. None of that needs anything from you.

**One thing does need you.** The logo picture on the site is still the old file, drawn in the old brighter blue — it is a picture, not something the site colours in. The new one is ready: go to **Media**, upload `iopstor-logo-2026.png`, then **Settings → Site identity → Logo url** and point it at the new file. The header and the footer both pick it up.

One oddity worth knowing, so nobody reports it as a fault: the printed brand sheet names a slightly different blue from the one on the site. The site uses the blue that is actually inside the logo artwork, on purpose, so the two always match.

**One more thing changed behind the scenes** and needs nothing from you: pictures and PDFs are now
delivered by the website itself instead of by the file store behind it, so that store can be closed off
from the internet entirely. Nothing about uploading or choosing a file changes.

**The website now has its real address**, `https://www.iopstor.com`, and you sign in to edit it at
`https://www.iopstor.com/admin`. Nothing about writing a page changes — same screens, same buttons.

There are now **two separate copies** of the site: the live one at that address, and a practice one used
while the site was being built. They do not share anything. A page written on the practice site does not
appear on the live one, and vice versa — so anything the live site needs is written on the live site.
Your sign-in is per site too: the password you use on one is not the password on the other.

**Pages now save themselves.** The blue button at the top right has become **Publish** — the separate,
deliberate step that puts your work on the website. Everything you type is saved by itself within a
couple of seconds, so a crashed browser or a closed laptop no longer costs you an afternoon, and nothing
you are still working on can reach a visitor by accident. **Activity** follows the same split: one line
per person per sitting saying what they changed, and a separate line for the moment it went live.

Two people can now write on one page at the same time and keep both sets of words, in the same
paragraph, the way Google Docs does (§4).

**Still to come:** a live payment provider.

---

## 15. Quick answers

**I cannot change the background of the About Us hero — is it hardcoded?** It is not, and now you can.
That black band is an ordinary **Hero** section: click it, open its **⚙**, and **Background** offers
*Light grey*, *Dark* and *Blue* beside the page's own white. That dropdown has been in the panel all
along but did nothing on a hero, which is what made the band look built-in. Nothing on any page
changed when this was fixed — every hero keeps exactly the band it had until somebody picks
something else.

**I cannot edit the two founders on About Us, and I cannot put them on another page.** You can now. Those two name cards used to be part of the paragraph above them rather than a section of their own, which is why clicking a name only let you retype it and there was no way to add a third person or a photograph. They are a **People** section now: open the section's **⚙** and each person has *Name*, *Role* and *Image*, **+ Add item** puts another one in, and you can drop a People section on any page from **+ Section** or by pressing `/`. The page looks exactly as it did. One thing to know: this only takes effect on About Us once your developer has applied the change to the live content — until then the page still shows the old, uneditable pair.

**Can I put a photograph of each person in?** Yes — *Image* on each row picks one from the media library, and it is shown as a circle. Leave it empty and you get the soft hatched circle the design draws, which is what the page has shown until now.

**The RSS feed never updates.** Check what you published. Until now the feed listed **blog posts
only**, and the site has exactly one of those — so a week of publishing case studies, testimonials
and pages left it sitting on the same single entry, which looked broken and was not. It now carries
blog posts, case studies, events and datasheets, so publishing any of those shows up in it within a
minute or two. Services, partners and testimonials are still deliberately left out.

**Clicking RSS downloads a file instead of showing me anything.** It used to. Now *RSS* and *Sitemap*
in the footer both open a proper page in the site's own design. If you follow the small link on either
page you reach the raw version machines read, and your browser will show that as code — that is
normal and is what it is for.

**An entry in the feed has a headline but nothing under it.** That post has no **Excerpt**, no words
on the page and — if it is a case study — no **Challenge** filled in, so there is nothing to put
there. Write an Excerpt and it will read properly. Nothing is broken; there is simply nothing to show.

**The services on the home page look different.** They do. The row of five cards is now a stack: one
service per line, and pointing at a line — or tapping it on a phone — slides that one open to show its
description and all of its sub-services, closing whichever was open before. They all start closed,
so what you see on arriving is a tidy list of five lines. Nothing had to be re-typed and nothing was lost: it is the same five services, from the
same Services pages, and the *All services →* link is still on the right of the heading. Inside an open line
the sub-service buttons and the *All Storage*-style link have no arrow after them — the small arrow beside
the count, which points down when a line is shut and up when it is open, is the only one. If you prefer
the cards back, open the section's **⚙** and set **List style** to *Cards*.

**The Services menu looks different.** It does. Instead of a list of the five group names that you
had to point at one by one, it now opens as five columns with every service on show at once, each
with a small picture beside its name. Nothing was re-typed — it is the same Services pages, and the
column headings still lead to the group's own page. If a service should have a different picture,
there is an **Icon** box on its page; section 9 lists the names it takes.

**Is there a practice version of the site?** Yes — the one used while the site was being built. It is a
completely separate copy: content does not travel between the two in either direction, so a page you want
customers to see has to be written on the live site at `https://www.iopstor.com/admin`. If you are ever
unsure which one you are looking at, check the address at the top of the browser.

**Is the contact form protected from spam?** Partly, and deliberately so for now. A hidden trap catches
automated spam programs, and anything caught is thrown away before it reaches **Leads** — but there is
no picture puzzle and nothing stopping the same form being sent over and over. While the site is still
being built and no junk has come through, that is the right balance: a puzzle on a quote form costs real
enquiries. Tell whoever looks after the site the moment junk starts arriving and it can be blocked
without you noticing any difference.

**The trail of links at the top of a page is squashed against the menu bar.** It isn't any more. On
pages that open with a big banner section the trail — *Home / Case Studies / …* — was sitting almost
touching the menu bar above it, while on every other page it had a comfortable gap. Both now have the
same gap. Nothing to change on your side; it applies to every page on the site.

**Can I move the Hero's picture, or stop it moving about?** Yes, both. Open the Hero section's
settings (the ⚙ on the section) and you will find **Where the picture goes** — beside the words,
above them, or below them — **Hold the picture still**, which stops the gentle drifting and stops
the faint blue halo pulsing, and **Hide the glow behind the picture**, which removes that halo
completely. The picture still slides into place as the page loads either way, and
several pictures still take turns. Leaving both alone keeps every hero exactly as it is now.

**Challenge, Solution and Results are in the wrong place on the page.** They used to come out
above everything you had written, which on a case study meant above the opening Hero. They are
boxes in the panel rather than sections on the page, so you cannot drag them — instead, under
**Details**, **Where the long details go** lets you pick: at the top, after the short details
(where they have always been), after any one of your sections by name, or at the very end. If you
delete the section you picked, they fall back to where they were before, so nothing ever
disappears.

**I chose a Featured image and it is not on the page.** Look at whether the page starts with a **Hero**
section. A Hero draws its own picture, so on a page that has one the picture you chose under
**Featured image** is used for the list card and the shared link but not on the page itself — put the
picture in the Hero section's own **Image** box instead, or remove the Hero and the page will show
yours. Case studies and events no longer start with a Hero unless you add one, so there the picture
usually shows straight away.

**My logo looks cut off in the header.** It isn't any more — the logo is shown whole, whatever
shape it is. One thing worth knowing when you upload a new one: **trim the empty space around it
first.** The logo is sized by its height, so if the file has wide blank margins baked in, those
margins are measured as part of the logo and the wordmark comes out smaller than it should. A file
cropped tight to the artwork always looks right.

**The Case Studies, Services, Partners and Products pages used to have a black banner at the
top.** They don't any more — every section's page now opens the same light way Blog always did,
which is what the rest of the site looks like. The row of figures on the home page (*17+ satisfied
customers* and the rest) sits on the page now too, instead of on a black strip.

**There is still a dark band on the home page — how do I change it?** That one is a setting on the
section, not part of the design, so it is yours: open the home page, click the **⚙** on the *Case
studies* section, and change **Tone** from *Dark* to *Grey* or *White*. The same applies to any
section anywhere — including that row of figures, which you can put back on black the same way if
you ever want to. There is one other dark block, on the NAS page.

**The Industry and Solution pages look plain, not like the rest of the site.** They don't any
more. Clicking a category chip — *Finance*, *Logistics*, *HCI* — now gives you a page built the same
way **Case Studies** is: the dark banner at the top, the cards with their pictures and labels, and a
row of the other industries along the top so you can move between them without going back. The trail
at the top also leads somewhere now: it says *Home / Case Studies / Finance*, and **Case Studies**
takes you to the full list. It used to say *Industry*, which was not a page and went nowhere.

**I deleted a section by mistake — can I get it back?** Yes. Press **↶** in the toolbar, or
**Ctrl+Z** (**⌘Z** on a Mac). It brings back the section with its writing and its settings. The same
works for a section you moved, copied or added, and for anything you changed under **⚙** — press it
again to keep stepping back, and **↷** / **Ctrl+Shift+Z** to go forward again. Two things worth
knowing: it only undoes **your own** changes, so it can never wipe out what a colleague is typing on
the same page; and it is for the page you have open right now — once you have left the page, use
**Activity** in the sidebar instead, which keeps a record of every saved change and can restore one.

**Can I put the title on top of a picture, like the big banner sections?** Yes. Choose a
**Featured image** in the panel on the right, then tick **Show the title on this picture** just
below it. The page's title, date and categories then sit on that picture across the full width of
the screen, darkened so the words stay readable — the same look a Hero section gives you, without
adding one. Untick it and everything goes back. With no picture chosen the tick does nothing, so
choose the picture first.

**I added a Hero and the title, date and categories disappeared.** They do not any more, on a blog
article or a case study: those two always show their own title, date and categories at the top, and a
Hero you add becomes a banner below them. If the banner repeats the title word for word, change the
Hero's own heading — the page is showing you both because you have written both. On every other kind
of page a Hero at the very top is still the headline, and the page title is not repeated above it.

**Case study pages look different.** They now read the way a blog post does — the title, the date, the
picture across the full width, a line, then the writing. Before, a case study opened with an empty Hero
section that hid the summary, the industry and solution labels, and the picture, which is why those never
appeared. Nothing you wrote was lost.

**The Client box is not in a grey panel any more.** That was asked for: the extra details — a case
study's client, an event's dates, a datasheet's PDF — now read as ordinary page content instead of
sitting in a highlighted box. The wording and the labels are exactly the same, and the same change
applies everywhere those details show, not only on case studies.

**A dropdown in a section's settings used to snap shut before I could choose.** Fixed
(2026-09-19). The editor redraws the section as you change its settings, and it was doing that a
moment after you merely *opened* a menu — the redraw pulled the menu shut under you. It now
redraws only once you have actually chosen something. If you still see it, tell whoever looks
after the site: it means the page is running an older copy of the editor and needs a reload.

**Save says a word "is part of the website's own address".** A few words are used by the system itself
— `admin`, `api`, `media`, `static`, `healthz` — so a page cannot take one as its address: it would
never open, because the website would go looking for its own admin panel instead. Pick another word;
nothing else about the page is lost, only the address box needs changing.

**Will visitors see a page the moment I press Publish?** Yes, if it is set to **Published** — there is
nothing to rebuild and no waiting. A **Draft** stays invisible, and a scheduled page appears by itself at
the date you set. One thing to know now that the site keeps a short-term copy of each page to stay fast
under heavy traffic: the website itself throws that copy away the instant you publish, so your own check
shows the new page straight away. If the speed service in front of the site has been switched on, a visitor
who happens to be served from it may see the previous version for up to a minute before it catches up. It
catches up by itself; there is nothing to press. The same applies to a page you scheduled — it can appear
up to a minute after the time you set.

**The site got faster. Did something change about my pages?** No — nothing about writing or publishing is
different, and no page looks any different. The website simply remembers each finished page for a short
while instead of rebuilding it for every single visitor, which is what lets it stay quick when thousands
of people arrive at once. It forgets what it remembered the moment anybody saves or publishes anything.

**The Save button says Publish now. What happened?** The page saves itself as you type, so there is
nothing left for a Save button to do — the line at the top right tells you it is saved. The blue button
is now the separate step that puts your work on the website. It still says **Save** on a page that is not
live, because pressing it there publishes nothing to anybody.

**I typed something and it is not on the site.** Your work is saved, but saving and publishing are two
different things now. Look for the amber note above the page — *changes on this page have not been
published yet* — and press the blue button. See §4.

**Is my work safe if my browser crashes?** Yes. Everything you type is saved by itself within a couple of
seconds, and it is waiting for you when you open the page again. What crashing costs you is at most the
last sentence.

**Activity has a line saying I "worked on" a page and another saying somebody "published" it. Why two?**
Because they are two different things now. *Worked on* is one person's sitting at the page, written up
about fifteen minutes after they stop, listing the sections they changed. *Published* is the moment that
work went on the website. See §11.

**Can two of us edit the same page at the same time?** Yes, properly. You see each other — initials at
the top right, a coloured line down the section the other person is in — and you write in the same
document: what they type appears on your screen, and you can both be in the same paragraph without
either of you losing a word. A few sections are still one-at-a-time and say so when you hover them, and
the rows inside a Cards, FAQ, Numbers, Specification, Definitions or Key points section are shared as a group rather than one by
one. See *Seeing who else is on the page* in §4.

**Their initials never appear, even though we are both on the page.** Say so to whoever looks after the
server. There is nothing to switch on and nothing you can have done wrong — and the website now keeps a
note of the reason each time it happens, so it can be looked up rather than guessed at. Everything else
on the page carries on working while this is off: your own writing, saving and publishing are unaffected;
you simply will not see each other's typing until it is fixed.

**Where did the Instagram link in the footer go?** It is still there, as an icon. The social links used to
appear as web addresses in the *Contact* column at the bottom of the page; they now sit under the logo as a
row of icons instead, so you can add all of your profiles without that column turning into a list of web
addresses. Add the rest under **Settings → Contact details → Social links**, one address per line.

**The quote form on Contact Us is no longer black.** That is deliberate. It now sits on the same soft grey panel as the *Apply* form on Careers, at the client's request. Nothing else about it changed — it still asks what the visitor is interested in and how many users, and the enquiry still arrives under **Leads** as a quote request.

**Technology Partners is not in the top menu any more.** That is deliberate, at the client's request. The page itself has not gone anywhere — it is still at `/technology-partners`, still listed for search engines, and still linked from the bottom of every page. If you ever want it back in the top menu, add it under **Menus → Header** the way you would any other link.

**The technology partner logos are in colour now.** They used to be grey, and only turned colourful when you pointed at one. The client asked for them in colour all the time, so that is deliberate — on the home page and on the Technology Partners page alike. Pointing at a logo now makes it grow a little, smoothly, and settle back when you move away. Nothing about adding, editing or removing a partner changed: upload the logo under **Media**, pick it on the partner, and it appears in the row.

**A long web address or code runs off the edge of the page.** It no longer does — a word too long to
fit now breaks and carries on on the next line, in the editor and on the live site, instead of
pushing the page sideways.

**Who changed this page?** Open **Activity** in the sidebar (administrators only) and choose **Pages and
other content** in the third box. Every change to every page is there with the person's name, the date
and time, and — under **Show what changed** — which section and which setting moved, with the old value
beside the new one.

**The detail under a page edit used to show the whole page twice.** It does not any more. It now shows
one short line per thing that actually changed, each naming the section it was in and, for a setting, both
values in the words you picked them by — *Numbers section, row 2 — Effect · was None · now Gradient across
the big text*.

**I deleted a page by mistake.** It is not gone. Ask an administrator: they open the list the page was
in, set the status filter to **trash**, and press **Restore**. It comes back as a draft with its address,
its categories and anything filed under it intact, ready to be published again. See section 12.

**The times in the admin panel have changed.** They are now Indian time, and every screen says IST after
the time so there is no doubt. They were previously five and a half hours behind without saying so, which
also meant a publish date you typed was acted on five and a half hours late. Both are now correct.

**I cannot reach /admin from home.** That is intended — the admin panel opens from the office network
only, so nobody outside can even find the login form, let alone try passwords at it. The public website
works normally from anywhere. There is no setting on your side to change; content has to be written from
the premises.

**Somebody has been trying to sign in as me.** Wrong passwords are recorded. An administrator can open
**Activity**, choose *login failed* in the middle box, and see every attempt with the email that was
typed, the time, and where it came from. If somebody gets it wrong enough times in a row **that address**
is locked for a while, and that is recorded too, as *login blocked*. The lock is on where the attempts are
coming from, never on the account, so nobody can shut you out of your own site by guessing at your password.

**The addresses in Activity have changed — and there is a new folded line above the filters.** The last
column used to show the address of the equipment between you and the site whenever you were working from
inside the office, so several people could appear as the same address. It now shows the person, whichever
way they reached the site. **Where the site thinks you are connecting from**, just above the filters,
opens to say what address will be recorded against what you do and where your connection came from — for
when an address in the log looks wrong. It only reports; there is nothing to set.

**Does it record password changes?** Yes — both changing your own and an administrator setting a new
one for somebody else. It records *that* the password was changed and whose it was. The password
itself is never written down anywhere you or anybody else can read it.

**Why does one line say "the website" instead of a name?** Because nobody was signed in: it is an
enquiry somebody sent through a form on the public site, or a payment coming back from the payment
provider. Choose *The website (nobody signed in)* in the first box to see only those.

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

**Do the effects work in my browser?** Yes, in every one, and they all do the same thing: the effect
plays once as the page opens. A section far down a long page will therefore have finished before you
scroll to it. If you have asked your computer to reduce motion, nothing animates at all and every
figure and heading simply sits there in full, which is deliberate.

**There is too much space around my Divider.** That is the design's usual spacing, and every
section has it. Open the Divider's **⚙** and set **Spacing** to *Small* or *None* — then do the
same on the section above it and the one below, because the gap you see is all three added
together. Setting only the Divider halves it; setting all three closes it up.

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

**I added a partner and the logo strip went from two lines to three.** Fixed — it now uses as few lines as it can. Fifteen partners are a line of eight and a line of seven, where before they were three lines of five, and the marks stay the small, quiet size they are meant to be. You do not have to do anything: it works the arrangement out again every time a partner is added or removed. The one thing that can still look wrong is a single logo, and that is the picture rather than the strip — see the next answer.

**One partner's logo comes out much smaller than all the others.** It is almost always the wrong version of that company's logo. A logo strip gives every mark the same *height*, so a **wide** logo — the symbol and the company name side by side, which is what all the others are — fills its space, while a **tall** one — the symbol with the name underneath it — has to shrink to fit that height and ends up a third of the width, with a name too small to read. Big brands publish both; ask for the wide one (it is usually called the *horizontal* logo) and upload that instead. Making the picture file bigger does not help — the shape is what matters, not how many pixels it has.

**Do my product photos all have to be the same shape?** No. Each card gives the picture a fixed amount of room and centres it there, so a tall photo and a wide one still produce two cards that line up — same size, titles level, the line under the picture in the same place. Upload whatever the manufacturer sent.

**On my phone the menu was one huge list, and the partner logos were enormous.** Both fixed, and neither needs anything from you. Tapping the menu button now shows just six rows — *Services*, *Case Studies*, *Blog*, *Company*, *Datasheets*, *Products* — and the whole menu fits on one screen. The ones with a small arrow open when you tap them: *Services* opens into its groups, and tapping a group (*Cloud*, say) opens that group's pages. Tap again to close. And the technology partner logos are three to a row instead of two, so they read as a row of partners rather than a wall. On a computer both look exactly as they did before.

**On my phone the page slid sideways, and the quote cards had an empty gap under the name.** Both fixed, and neither needed anything from you. The page no longer drifts left and right when you scroll it on a phone — that was the big picture at the top of the home page sliding in from the side and pushing everything over. And a short quote no longer leaves a block of empty white under the person's name: the photo and name now sit on the bottom edge of the card, however long or short the quote is. The buttons either side of the testimonials are also bigger on a phone, so they are easier to hit with a thumb.

**The home page testimonials look different, and they move.** The two quotes that used to sit side by side are now
**Testimonials** in the sidebar, and the home page shows every published one in a row that slides. The two that were
there before are already in the list — nothing was lost. Add a third and it appears in the row on its own.

**A testimonial I added is not on the home page.** Check it is set to **Published** rather than *Draft*, and that
*Publish date* is not in the future. If it still does not show, it is almost certainly the website remembering the
old version of the page for a minute — wait a minute and reload.

**On a testimonial, where does the quote go?** In the big box marked **What they said**. On every other kind of
content that box is called *Summary*; on a testimonial it is the quote itself.

**The sliding row is annoying me while I am editing.** It does not slide in the page editor — only on the live
website. If it is moving, you are looking at the site rather than the editor.

---

*Technical companion: [TECHNICAL.md](TECHNICAL.md).*
