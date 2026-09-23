---
name: theme-check
description: Use when a change touches site.css, admin.css, canvas.css, a block template, base.html, _card.html or admin.js — or when asked to "check how it looks", "screenshot the site", "compare with the mock", "does it fit on a phone", "prove nothing changed".
---

# Look at it before you say it works

The public site ships one small script (`static/site.js`, the sliding testimonial row) and the theme is one stylesheet, so a CSS change is invisible to pytest. The check is a screenshot at the three widths the editor's Preview uses — 1440, 834, 390 — read back with the Read tool, against the client's mock. Which browsers exist on this machine, at what version, is a per-machine fact kept in Claude's memory; the procedure below holds for any of them.

No browser extension is connected. Firefox headless is the default. Every command under *Run* is on the `settings.json` allow list as written — keep them one per Bash call, no loops, no `&&` chains, or they prompt. `ss` is allowed too; `python3 -m http.server` and `kill` in the two sections after the page table are not, and prompt once each.

## Run

1. **A server on a spare port** — the user's own is on 5000, never touch it. Run with the Bash tool's `run_in_background`, and stop it with TaskStop when done:
   ```bash
   pipenv run flask run -p 5001 --debug
   ```
   **`--debug`, or a template edited after the server started is served from the old cache** (2026-09-19). `.env`'s `FLASK_DEBUG=1` does not reach this invocation, so without the flag Jinja never re-reads a template: the stylesheet changes, the markup does not, and the shot shows a rule applying to a class that is not in the HTML — which reads as a specificity problem and is not one. `grep` the served page for what you added (`curl -s localhost:5001/<path> | grep -c '<your class>'`) before shooting; the log tells you too, since a debug server prints "Debugger is active".
   **Port 5001 is not reliably free.** A stale server from an earlier session serves *old* code, yours fails to bind with "Address already in use" in its log rather than on stdout, and the shot shows the unchanged page — a correct change looks unapplied (2026-09-11). `ss -ltnp | grep 500` first; pick 5002+ if something is there, and read the server log before trusting a shot.
2. **Confirm it is up** (`{"ok": true}`):
   ```bash
   curl -s http://localhost:5001/healthz
   ```
   A long-lived dev server serves *new* templates against an *old* Jinja environment — filters and globals are registered once in `create_app()` — so a template using a filter added since the server started raises `No filter named …`, which reads exactly like a missing registration. Restart the server; do not edit `__init__.py`.
3. **One shot per page per width.** Firefox needs its own profile directory and **the directory must already exist** (otherwise Firefox hangs forever and writes nothing). `--window-size` sets the viewport **and clips the capture**: a 1440x2400 window of the ~5800px home page is the top only, and a footer change is simply absent from a shot that looks fine. Set the height well above the page and crop the band you want:
   ```bash
   mkdir -p /tmp/claude-1000/shots /tmp/claude-1000/ffprofile
   firefox --headless --profile /tmp/claude-1000/ffprofile --window-size=1440,9000 --screenshot /tmp/claude-1000/shots/home-1440.png http://localhost:5001/
   ```
   **Every picture on a public page is `loading="lazy"`, and a lazy image does not hold up `load` — so `--screenshot` can fire before any of them paints and the shot comes back with the layout right and every picture missing** (2026-09-21, the partner strip: correct row heights, fourteen blank cells, and the server log showing all fourteen fetched with a 200). It reads as a broken image path and is not one. Strip the attribute from a saved page before shooting it (`s.replace(' loading="lazy"', '')`), or shoot a page whose pictures are all above the fold and accept the risk.
   `390,14000` at phone width. `convert shot.png -trim -format "%wx%h\n" info:` gives the real content height; `convert shot.png -crop WxH+0+Y +repage band.png` cuts out the band to read.
4. **The mock at the same width**, for the comparison:
   ```bash
   firefox --headless --profile /tmp/claude-1000/ffprofile --window-size=1440,9000 --screenshot /tmp/claude-1000/shots/mock-1440.png file:///home/sukhpreetsaluja/Documents/coding-stuff/iopstor/website_assets/mock-website.html
   ```
5. Read each PNG. `convert` (ImageMagick) exists for cropping or a side-by-side montage; Python PIL does not. Stop the server; the profile directory can stay.

## Which pages

A change can hit several rows; screenshot every row that matches.

| Change | Pages |
|---|---|
| tokens, header, footer, `.btn`, `.card` | `/`, `/services`, `/blog`, one product |
| a block's rule group | a page holding it on its own **and inside a Columns section** |
| archive shapes (`pl-*`) | `/services`, `/products`, `/events`, `/datasheets`, `/case-studies`, `/partners` |
| `post.html`, `_card.html` | one post of every type that renders differently: service, product (+ `/checkout`), blog, datasheet |
| mega panel / mobile sheet | `/` at 1440 (hover cannot be captured — see *A hover state*) and 390 |
| anything that opens on `:hover` | `/` at 1440 **and** the cascade check in *A hover state* — a screenshot only ever shows the unhovered page |
| `admin.css`, `canvas.css`, `admin.js` | **an admin screen CAN be shot without logging in** — see below; do that rather than describing a check for the user |
| a block type that replaces markup that was `rich_text` | the page **before and after in one document** — see below — on the page and in its column |

## Proving a change is a no-op: before and after in ONE document

Two headless renders of the *identical* page differ by ~150k pixels here — a webfont race, each run re-fetching Google Fonts and sometimes painting first — so `compare -metric AE` between a before-run and an after-run proves nothing. Render both versions into **one** HTML file and screenshot it once: `render_blocks()` for each version of the block (or `git show main:iopstor/static/site.css` beside the working stylesheet), stacked under sticky black labels, with `<base href="http://localhost:5001/">` and a `<link>` to `site.css`. One render, one font state, so any difference is real. That is what caught a `max-width` on a `<section>` losing its page gutter that a cross-run diff had buried in noise (2026-09-15, `points`). The same `<base>` trick swaps another branch's stylesheet in, to prove whether a visual change is a regression or the design.

## A page whose rows are not in the state you need yet

A migration written and deliberately **not** applied, a Featured image nobody has set, a setting no live page
uses — the page you have to photograph does not exist in the database, and you may not put it there. Render it
instead: fetch the real row read-only, patch the field **in memory**, render through Flask, and shoot the file.

```python
post = db.hydrate(db.one(db.live(db.select_posts()).eq("slug", slug)))
post["blocks"] = []                                   # what the unapplied migration will do
with app.test_request_context("/" + post["path"].lstrip("/")):
    html = render_template("post.html", post=post, children=[], siblings=False,
                           crumbs=crumbs_for(post), meta=seo.build_meta(post), jsonld=seo.jsonld(post, crumbs_for(post)))
html = html.replace("<head>", '<head><base href="http://localhost:5001/">', 1)
```

Nothing is written. Used on three consecutive PRs (2026-09-19) — the post-migration case-study layout, four hero
arrangements, and the details-placement setting — which is why it is written down. The same shape renders an admin
screen (below) and a block through `render_blocks()`.

**An entrance animation makes the shot come back BLANK, and it does not look like a timing problem.** `rise` and
`heroin` are `both`-filled and start at `opacity:0`, and `--screenshot` fires on `load`, so frame 0 is an empty
white band and it reads as a broken change or a stylesheet that 404'd. Add
`<style>.hero-text,.hero-media{animation-delay:-2s!important}</style>` to hold the end frame. It does not disturb a
`getComputedStyle(...).animationName` probe in the same page, so one render can carry both.

## Anything that `import`s is served, never `file://`

ES modules do not load from `file://` in Firefox, and the page renders its pre-script state with **no error in the shot** — it looks exactly like the script threw. A scratch page that loads `vendor/yjs.mjs`, `vendor/y-quill.mjs` or `vendor/quill.js` is served from the scratchpad — `python3 -m http.server 8137` in that directory, in the background — and shot at `http://127.0.0.1:8137/x.html`. Stop it **by port, never `pkill -f <pattern>`**: `-f` matches the whole command line, which includes the pattern in the very shell running the `pkill`, so it kills that shell (exit 144) and any edit in the same call is silently lost — seen twice on 2026-09-15.

```bash
PID=$(ss -lptnH 'sport = :8137' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$PID" ] && kill "$PID"
```

## A hover state, and the transition it starts

**`matchMedia('(hover:hover)').matches` is `false` in headless Firefox here** (measured 2026-09-21), so anything inside `@media(hover:hover)` is not even parsed into the run, and `:hover` cannot be forced from script. A screenshot of a page with a hover-driven panel or accordion always shows the unhovered state, and that is not a finding.

To check what a real pointer gets, stand a class in for `:hover` in a **copy** of the stylesheet and let the browser resolve the same cascade — a media query adds no specificity, so the answer is the real one:

```python
css = css.replace("@media(hover:hover){", "@media all{").replace(".acc-row:hover", ".acc-row.hv")
h   = h.replace('<link rel="stylesheet" href="/static/site.css">', "", 1)   # <- or the reading is worthless
h   = h.replace("</head>", "<style>\n" + css + "\n</style></head>", 1)
```

Two traps, both of which produced a confident wrong reading before they were understood:

- **Remove the real `<link>`.** Leave it and its own unmodified `:not(:has(… :hover))` guards keep answering "nothing is hovered", so the rule you are testing is overruled by the file you are testing.
- **Read the custom property, not the resolved value.** Sampled synchronously after forcing layout, a property that is mid-transition still reports its **start** frame — `grid-template-rows` read `0px` on a row that had just been told to open, which looks exactly like a rule that did not apply. `getComputedStyle(el).getPropertyValue('--rows')` gives the answer the cascade actually produced.

**Whether a transition is running at all** is `el.getAnimations().map(a => a.transitionProperty)`, synchronously after the state change and a forced reflow. That is the only way to prove a value delivered through `var()` still animates, which is worth proving whenever the open/closed look is carried by custom properties rather than written per selector.

## A moving thing, at a chosen moment

A plain headless screenshot fires at an arbitrary point in an animation and usually catches frame 0. Save the page locally with `<base href="http://localhost:5001/">` injected and `<style>SELECTOR{animation-delay:-1.2s!important}</style>` before `</head>`, then shoot the file: a negative delay past the duration on a `both`-filled animation holds its end frame, a partial one holds a mid frame — the only deterministic way to verify an animated state. Firefox 140 has `@property` but not scroll-driven animations, so anything scroll-triggered renders as its fallback there and only a Chromium binary shows it (which one exists is in memory). Neither browser is the client's: a Firefox-only bug (no `var()` interpolation in a keyframe, 2026-09-10) is real, and a Chromium screenshot hides it.

## Shooting an admin screen (no login, no database write)

Render the page through Flask with a stand-in user and screenshot the saved HTML as a `file://` page:

```python
app = create_app({...})                       # TESTING=True, SITE_URL=http://localhost:5001
with app.test_request_context("/admin/posts/7"):
    g.user = {"id": "...", "email": "zz@zz-test.local", "name": "", "role": "admin"}
    html = render_template("admin/post_form.html", **ctx)   # patch db.settings/get_menu/post_types
```

Then rewrite `/static/` to `file:///…/iopstor/static/` (or inject `<base href="http://localhost:5001/">`
so `/media/*` resolves too), **strip the `<script>` tags** — `admin.js` opens the realtime channel and fetches `/admin/canvas`, and headless waits on both — and shoot it. **Nothing is written to the database**, unlike `tests/conftest.py`'s `make_user()`, which inserts a real row. To see the `<1000px` burger-open state, add `checked` to the `#adm-toggle` input in the saved HTML (`:checked` is pure CSS).

Two extras this unlocks: inject a `<script>` at the end to put the page into a state the server does
not render on its own (a peer roster, an open burger menu, an error banner), and shoot the **canvas**
document separately by rendering `render_blocks(blocks, edit=True)` into `admin/canvas.html` — that
is the only way to see the editor chrome, which lives inside an iframe.

## What to look for

- **Horizontal overflow at 390**: a right edge cut off, or a band that stops short of the viewport while content runs past it. Usually a grid track pinned with `grid-column` or a min-content word — see TECHNICAL.md §12 for both fixes.
- **A width set with `max-width` instead of `--w-def`** — the section ignores the editor's Width control. And a `max-width` on the `<section>` itself rather than an inner element loses the page gutter (`/new-block` step 4).
- **A rule that "just isn't applying"**: check brace balance before editing the rule — one orphan `}` on 2026-09-10 silently dropped the hero's padding while pytest stayed green (`test_stylesheets_are_balanced` guards it now) — and read `getComputedStyle` rather than the source.
- **Fonts**: Manrope / IBM Plex Sans come from Google Fonts; offline they fall back and the screenshot lies about measure. Say so if the box has no internet.
- **Reduced motion**: the hero rotator parks on the first picture under `prefers-reduced-motion`; a screenshot with the second picture showing is fine, one with none is not.
- **The mock is the reference, the client's decisions win over it** (`.claude/docs/requirements.md`): white header with the logo in colour (2026-09-08); price on the Buy button (2026-09-09); the Contact page's quote form on the Careers grey panel, not the mock's black card (2026-09-10); footer socials as an icon row under the logo (2026-09-11); the archive heads are light where the mock draws four of them on `#0a0d12` (2026-09-21); the home page's "What we do" section is the client's own design option 1a — an accordion of service groups, not the mock's deck of cards (2026-09-21); **no `→` after any link, tile or pill** where the mock draws fifteen (2026-09-23 — the chevrons that show a state stay); and **the brand blue is `#3573b9` while the mock is still `#008cf7`** (2026-09-18; it was `#4273b8` from 2026-09-12). Note the client's brand sheet prints `#1F6DB2` — the site deliberately uses the blue inside the logo artwork instead, so do not "correct" it — every side-by-side shows two blues, and that is the decision, not a regression. The header logo file is the client's own; the 2026-09 artwork is in `website_assets/iopstor-logo-2026.png` and is the site's logo once an administrator uploads it in Media and points Settings at it.

## Report

Name the file you looked at and the width, then what matched and what did not — never "looks good" without the screenshot behind it, and never a "no change" claim from two separate runs.
