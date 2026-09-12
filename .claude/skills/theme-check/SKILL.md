---
name: theme-check
description: Use when a change touches site.css, admin.css, canvas.css, a block template, base.html, _card.html or admin.js — or when asked to "check how it looks", "screenshot the site", "compare with the mock", "does it fit on a phone".
---

# Look at it before you say it works

The public site ships no JavaScript and the theme is one stylesheet, so a CSS change is invisible to pytest. The check is a screenshot at the three widths the editor's Preview uses — 1440, 834, 390 — read back with the Read tool, against the client's mock.

No browser extension is connected on this machine. Firefox headless works; Playwright's Chrome does not produce files. Every command below is on the `settings.json` allow list as written — keep them one per Bash call, no loops, no `&&` chains, or they prompt.

## Run

1. **A server on a spare port** — the user's own is on 5000, never touch it. Run with the Bash tool's `run_in_background`, and stop it with TaskStop when done:
   ```bash
   pipenv run flask run -p 5001
   ```
2. **Confirm it is up** (`{"ok": true}`):
   ```bash
   curl -s http://localhost:5001/healthz
   ```
3. **One shot per page per width.** Firefox needs its own profile directory, and `--window-size` sets the viewport. Repeat the command for each width (1440, 834, 390) and each page from the table below:
   ```bash
   mkdir -p /tmp/claude-1000/shots /tmp/claude-1000/ffprofile
   firefox --headless --profile /tmp/claude-1000/ffprofile --window-size=1440,2400 --screenshot /tmp/claude-1000/shots/home-1440.png http://localhost:5001/
   ```
4. **The mock at the same width**, for the comparison:
   ```bash
   firefox --headless --profile /tmp/claude-1000/ffprofile --window-size=1440,2400 --screenshot /tmp/claude-1000/shots/mock-1440.png file:///home/sukhpreetsaluja/Documents/coding-stuff/iopstor/website_assets/mock-website.html
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

## Shooting an admin screen (no login, no database write)

The table above used to say this needed a logged-in session. It does not. Render the page through
Flask with a stand-in user and screenshot the saved HTML as a `file://` page:

```python
app = create_app({...})                       # TESTING=True, SITE_URL=http://localhost:5001
with app.test_request_context("/admin/posts/7"):
    g.user = {"id": "...", "email": "zz@zz-test.local", "name": "", "role": "admin"}
    html = render_template("admin/post_form.html", **ctx)   # patch db.settings/get_menu/post_types
```

Then rewrite `/static/` to `file:///…/iopstor/static/` (or inject `<base href="http://localhost:5001/">`
so `/media/*` resolves too) and shoot it. **Nothing is written to the database** — unlike
`tests/conftest.py`'s `make_user()`, which inserts a real row.

Two extras this unlocks: inject a `<script>` at the end to put the page into a state the server does
not render on its own (a peer roster, an open burger menu, an error banner), and shoot the **canvas**
document separately by rendering `render_blocks(blocks, edit=True)` into `admin/canvas.html` — that
is the only way to see the editor chrome, which lives inside an iframe.

## What to look for

- **Horizontal overflow at 390**: a right edge cut off, or a band that stops short of the viewport while content runs past it. Usually a grid track pinned with `grid-column` or a min-content word — see TECHNICAL.md §12 for both fixes.
- **A width set with `max-width` instead of `--w-def`** — the section ignores the editor's Width control.
- **Fonts**: Manrope / IBM Plex Sans come from Google Fonts; offline they fall back and the screenshot lies about measure. Say so if the box has no internet.
- **Reduced motion**: the hero rotator parks on the first picture under `prefers-reduced-motion`; a screenshot with the second picture showing is fine, one with none is not.
- **The mock is the reference, the client's decisions win over it**: white header, logo in colour, price on the Buy button, and since 2026-09-12 **the brand blue is `#4273b8` while the mock is still `#008cf7`** — every side-by-side now shows two blues, and that is the decision, not a regression (`.claude/docs/requirements.md`). The logo picture in the header is the client's own file and still carries the old blue until they send a new one.

## Report

Name the file you looked at and the width, then what matched and what did not — never "looks good" without the screenshot behind it.
