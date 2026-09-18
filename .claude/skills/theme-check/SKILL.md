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
   pipenv run flask run -p 5001
   ```
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
| mega panel / mobile sheet | `/` at 1440 (hover cannot be captured — check the markup) and 390 |
| `admin.css`, `canvas.css`, `admin.js` | **an admin screen CAN be shot without logging in** — see below; do that rather than describing a check for the user |
| a block type that replaces markup that was `rich_text` | the page **before and after in one document** — see below — on the page and in its column |

## Proving a change is a no-op: before and after in ONE document

Two headless renders of the *identical* page differ by ~150k pixels here — a webfont race, each run re-fetching Google Fonts and sometimes painting first — so `compare -metric AE` between a before-run and an after-run proves nothing. Render both versions into **one** HTML file and screenshot it once: `render_blocks()` for each version of the block (or `git show main:iopstor/static/site.css` beside the working stylesheet), stacked under sticky black labels, with `<base href="http://localhost:5001/">` and a `<link>` to `site.css`. One render, one font state, so any difference is real. That is what caught a `max-width` on a `<section>` losing its page gutter that a cross-run diff had buried in noise (2026-09-15, `points`). The same `<base>` trick swaps another branch's stylesheet in, to prove whether a visual change is a regression or the design.

## Anything that `import`s is served, never `file://`

ES modules do not load from `file://` in Firefox, and the page renders its pre-script state with **no error in the shot** — it looks exactly like the script threw. A scratch page that loads `vendor/yjs.mjs`, `vendor/y-quill.mjs` or `vendor/quill.js` is served from the scratchpad — `python3 -m http.server 8137` in that directory, in the background — and shot at `http://127.0.0.1:8137/x.html`. Stop it **by port, never `pkill -f <pattern>`**: `-f` matches the whole command line, which includes the pattern in the very shell running the `pkill`, so it kills that shell (exit 144) and any edit in the same call is silently lost — seen twice on 2026-09-15.

```bash
PID=$(ss -lptnH 'sport = :8137' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$PID" ] && kill "$PID"
```

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
- **The mock is the reference, the client's decisions win over it** (`.claude/docs/requirements.md`): white header with the logo in colour (2026-09-08); price on the Buy button (2026-09-09); the Contact page's quote form on the Careers grey panel, not the mock's black card (2026-09-10); footer socials as an icon row under the logo (2026-09-11); and **the brand blue is `#3573b9` while the mock is still `#008cf7`** (2026-09-18; it was `#4273b8` from 2026-09-12). Note the client's brand sheet prints `#1F6DB2` — the site deliberately uses the blue inside the logo artwork instead, so do not "correct" it — every side-by-side shows two blues, and that is the decision, not a regression. The header logo file is the client's own; the 2026-09 artwork is in `website_assets/iopstor-logo-2026.png` and is the site's logo once an administrator uploads it in Media and points Settings at it.

## Report

Name the file you looked at and the width, then what matched and what did not — never "looks good" without the screenshot behind it, and never a "no change" claim from two separate runs.
