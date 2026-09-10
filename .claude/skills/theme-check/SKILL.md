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
| mega panel / mobile sheet | `/` at 1440, forced open (below), and 390 |
| `admin.css`, `canvas.css`, `admin.js` | needs a logged-in session; screenshot what is public, and describe the admin check the user should do |

## Hover-only UI, forced open

Headless Firefox cannot move a pointer, but it does not have to: fetch the page, give it a `<base>`
so `/static/site.css` still resolves, and append a stylesheet that pins the state you want. That is
how the mega panel is checked — the default state, a *non-first* group, and an over-tall pane all
render without a mouse.

```python
import urllib.request
h = urllib.request.urlopen('http://localhost:5001/').read().decode()
h = h.replace('<head>', '<head><base href="http://localhost:5001/">', 1)
h = h.replace('</head>', '<style>.nav-mega>.mega{display:block!important}</style></head>', 1)
open('/tmp/claude-1000/shots/panel.html', 'w').write(h)
```

Then shoot the `file://` copy. To stand in for `:hover` on the *n*-th group, add `!important`
overrides for the pane you want shown and the row you want tinted (the real rules out-specify a
plain class selector, so `!important` is what makes the stand-in win). Add `min-height` to a pane to
prove a tall one does not spread the group list.

**This proves layout, never hover itself.** The screenshot cannot tell you the pointer survives the
trip from the link to the pane — say so, and ask the user to click it.

## What to look for

- **Horizontal overflow at 390**: a right edge cut off, or a band that stops short of the viewport while content runs past it. Usually a grid track pinned with `grid-column` or a min-content word — see TECHNICAL.md §12 for both fixes.
- **A width set with `max-width` instead of `--w-def`** — the section ignores the editor's Width control.
- **Fonts**: Manrope / IBM Plex Sans come from Google Fonts; offline they fall back and the screenshot lies about measure. Say so if the box has no internet.
- **Reduced motion**: the hero rotator parks on the first picture under `prefers-reduced-motion`; a screenshot with the second picture showing is fine, one with none is not.
- **The mock is the reference, the client's decisions win over it**: white header, logo in colour, price on the Buy button (`.claude/docs/requirements.md`).

## Report

Name the file you looked at and the width, then what matched and what did not — never "looks good" without the screenshot behind it.
