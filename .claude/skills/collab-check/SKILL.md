---
name: collab-check
description: Use when a change touches the editor's shared document, presence, autosave, the working draft, the realtime proxy or Preview — admin.js's shared-document section, initCollab(), mirrorProse(), renderPreview(), /admin/posts/<id>/draft, /admin/realtime/v1/longpoll, post_drafts, post_sessions — or when asked "does collaboration still work", "check the editor with two people", "why is nobody seeing anybody".
---

# What can be proved here, and what only two browsers can

Six PRs (#65, #67, #68, #72, #73, #74) each rebuilt this sequence by hand. The offline suite covers the room name, the colour's stability across workers, the proxy's own edges and the reconcile harness; **nothing tests the channel end to end**, and a mock there would test the mock. So the check has five layers you can run, and a sixth that is handed to the user.

## 1. The document — `node tests/reconcile.mjs`

It cuts the shared-document section straight out of `admin.js` and drives it against the real Yjs, so it cannot drift into testing a copy; pytest runs it too and skips without node. Expect `all passed`. **Add a case for the path you changed**: #68 added the pending-update trap (a bare delta with no base yields an empty document, silently), #73 the peer-prose-into-`MODEL` path, #74's scroll test lives in a browser because `renderPreview()` is outside the slice. A change inside a closure the slice cannot reach (`sitting()`, `touched()` inside `initAutosave()`) gets a source assertion on its shape, as #69's did.

## 2. The modules — a served scratch page in a real browser

Anything that `import`s (`yjs.mjs`, `y-quill.mjs`, `quill.js` in the parent) is proved over http, never `file://` — `/theme-check` has the server and the kill-by-port. Worth re-proving whenever the vendored files or the binding change, with the numbers the PRs got: two Quills on one `Y.Doc` converge word for word and `<strong>` survives the merge (#68, 8/8); the offscreen converter's HTML is byte-identical to a mounted editor's — 293 characters across a heading, the five inline marks, an escaped link, both list kinds and a blockquote (#73); a `#main` swap holds `scrollY` at 600 where `srcdoc` gives 0 (#74). A peer's delta must arrive with a source that is never `"user"`; the per-person audit depends on it.

## 3. The channel — from node, then through the proxy

- **Against Supabase directly**, `node --experimental-websocket`, with the realtime `logger` on: the server's own refusals (`Client presence rate limit exceeded`, `Unauthorized: … Channel topic`) appear nowhere else — the client callback only ever says `CLOSED`. Run **at least 45 s** (the first harness exited in under a second and hid a close at t+0.1 s and the re-auth at the 30 s heartbeat), A/B the broken and the fixed variant in one script, two peers in one process. The vendored bundle is `var supabase=(function…)`, so load it with `vm.runInThisContext`; mint an HS256 token for a real `users` id with `SUPABASE_JWT_SECRET`. The exact recipe is in Claude's memory.
- **Through the proxy**, with the Flask test client and a session (#72): `GET /admin/realtime/v1/longpoll` answers `410` plus a token, `phx_join` is accepted, `phx_reply {"status":"ok"}` polls back, and the `vsn=2.0.0` ndjson batch the real client sends goes through. Without a session or with a wrong csrf it is `403`, never a redirect.

## 4. The server — two tabs against the dev server, log open

Every realtime request lands on `/admin/realtime/v1/longpoll` and there is no WebSocket anywhere. Successful polls are filtered out of the access log by `_QuietPolls` (`__init__.py`) — drop the filter to watch the transport; refusals and failures still print. While a colleague types with Preview open: about **two `POST /admin/preview` pairs a second and zero `POST /admin/canvas`** (#74). Drafts save alongside.

## 5. The data — read-only

`post_drafts.state` disagreeing with `post_drafts.blocks` is how #68's silent bind failure was found — the draft's `html` held words the `Y.Text` did not. `post_sessions.changes` is where an activity entry's `was`/`now` per section can be read before it becomes a row (#69). Read them with `db.rows()` from a `pipenv run python` one-liner; never write.

## 6. What only two browsers can prove — hand it over under **Tests → Not verified**

Two browsers, two accounts, one page:
- both type in one paragraph — both sets of words survive; a legacy section (NAS's table, Contact Us, About Us) does not change under your caret, and their version arrives on blur
- a colleague's paragraph shows in Preview; **Publish from Preview** publishes it
- scroll a long page halfway in Preview, the colleague types — the words appear and the page does not move
- A adds one word to B's sentence — A's Activity entry names only A's word; A deletes a section without typing, reloads, types again — **one** entry fifteen minutes later
- **nobody sees anybody**: `0009` not applied (`CHANNEL_ERROR`, single-player fallback, retries 2→30 s); the realtime container caching authorisation (restart it after a policy change); or the tenant-name trap (TECHNICAL §15) — a bare `403` on every join

## Migrations this depends on

`0009` (channel policy) and `0010` (drafts, sessions). An unapplied `0010` is reported now — "could not be stored" in the editor, the file named in the console — but the rule is still: applied before judging, or one missing table shows up as three unrelated symptoms (a save that says saved, a reload that loses the work, a document with every section twice). In production the deploy's `migrate` service applies both; the realtime restart is by hand.
