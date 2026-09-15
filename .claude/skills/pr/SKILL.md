---
name: pr
description: Use when work on a branch is ready to leave this machine — committing, pushing, opening or updating the pull request — or when asked to "open a PR", "push this", "ship it", "update the PR body".
---

# Open the PR, then stop

The PR is the hand-off. It is opened by you and merged by the user, never by you. `gh` is installed and authenticated as `primesukh`.

## Pre-flight (every line must be true before `git push`)

- On a `feat/ | fix/ | docs/ | chore/` branch, not `main`: `git branch --show-current`
- `pipenv run pytest -q` was run in this session. Record the count. Two live tests, `test_browser_admin_login_and_create_post` and `test_upload_checkout_seed`, have failed on the seeded dev database since 2026-09-10 and are named as the standing pair. Any other failure — and those two whenever the change touches `iopstor/` — is reported as pre-existing only **after checking on `main`** (`git stash; git checkout main; pytest <test>; git checkout -; git stash pop`), never assumed. `node tests/reconcile.mjs` runs inside the offline suite when node is present; run it on its own too when `admin.js`'s shared-document section changed (`/collab-check`).
- `/docs` is done: `docs/TECHNICAL.md`, `docs/NON-TECHNICAL.md`, `.claude/docs/design.md` — or the body says which audience is genuinely unaffected and why.
- A new `migrations/NNNN_*.sql` exists → it was **not** applied by you, and the body has a **Needs applying** section naming it.
- `Pipfile` changed → `requirements.txt` and `requirements-dev.txt` were regenerated from the lock.
- Theme or admin change → `/theme-check` screenshots were looked at.
- Nothing staged from `.env` or `graphify-out/`: `git status --short`. (`website_assets/` is tracked since 2026-09-10 — staging it is normal now.)
- No Claude or Anthropic authorship anywhere: `git log origin/main..HEAD --format=%B | grep -iE 'co-authored-by|anthropic|generated with'` prints nothing. (`settings.json` sets `includeCoAuthoredBy: false`; check anyway.) The rule is about *authorship* — a trailer, an email, a "generated with" line — not about naming `CLAUDE.md` or `.claude/` in a body, which 34 lines on `main` already do; the old grep for the bare word flagged every one of them.

## Commit style

`type(scope): a sentence in plain words about what changed for whom`, as the history does — `fix(theme): the services list stacks on a phone instead of running off it`, `feat(admin): a warranty register, and a serial-number check for visitors`. Body: the why, the trap avoided, the decision the reviewer should question, and the measurement with its number ("measured in a real browser: 600px held across two swaps, `srcdoc` gave 0"). Scopes the history uses: `admin`, `theme`, `blocks`, `db`, `auth`, `media`, `seo`, `deploy`, `migration`, `tests`, and `claude`/`agent` for `.claude/` itself; `docs(<scope>)` for a docs-only commit. One commit per coherent change; do not squash a migration into the code that reads it unless they cannot be separated.

A change that turned out wrong once it was seen in the browser is **reverted, not fixed forward**: `git revert` with a body saying what was seen and why the first judgement was off, and the doc rows the original added come out with it. Three on 2026-09-10 — one had been judged against a stylesheet with an unbalanced brace, one did not hold against the dark footer, one put a header on the wrong side of the wire.

## Push and open

```bash
git push -u origin "$(git branch --show-current)"
gh pr create --title "<the commit's sentence>" --body-file /tmp/claude-1000/pr-body.md
```

Never `--web`. Write the body to a file first (heredoc), then pass it — a body with backticks and tables does not survive `--body "..."`.

`git push` and both `gh` calls prompt for permission; that is deliberate — they are the only outward-facing commands in the repo.

**A PR stacked on another PR.** When the work builds on a branch that is still open (its entry point is markup the parent rewrites, say), cut from that branch and open with `--base <parent-branch>` so the diff shows only your commits. Two things then follow, and both have bitten:

- **`gh pr merge` does not retarget the children.** `--merge` keeps the head branch, and GitHub only auto-retargets when the base branch is *deleted* — so after the parent merges, the child's base still points at a branch that is now in `main`, and merging it lands the work **on that branch, not on `main`**. Retarget first: `gh api -X PATCH repos/primesukh/iopstor/pulls/N -f base=main`, then confirm the diff shrank to the child's own commits before merging.
- Merge bottom-up, one at a time, and re-read `mergeable` after each: a parent landing can turn a clean child `CONFLICTING/DIRTY`.

Updating a body later: `gh pr edit N --body-file` does not work on this machine — it prints a Projects-classic GraphQL error and leaves the body unchanged. Use the REST call:

```bash
gh api -X PATCH repos/primesukh/iopstor/pulls/N -F body=@/tmp/claude-1000/pr-body.md
```

## PR body

```markdown
## What
What a reader of the site or the admin gets. Tables for URL/behaviour maps.

## How
The mechanism, one paragraph per moving part, naming the function or template a reviewer opens.

## Decisions worth reviewing
- Each non-obvious choice as one bullet: what, and why the alternative lost. A measurement belongs in its row: the number, and where it was taken.
- What was deliberately **not** built, so the reviewer does not ask for it as an oversight.

## Needs applying            (only if a migration or a seed change is in the PR)
`migrations/NNNN_name.sql` — **not applied**; apply before the branch is used. Say what happens to the app before it is applied (the code tolerates the gap, or does not).

## Tests
`N passed` (+ the standing pair, verified on main when iopstor/ changed). New tests by name and what each pins.
What was checked by hand, on which port, with the number that was measured.
**Not verified, and why** — a two-browser check, a Docker daemon this machine cannot reach — as its own line, so the reviewer knows what to try before merging.

## Docs
Which sections of TECHNICAL.md, NON-TECHNICAL.md and .claude/docs/design.md changed — or which audience is unaffected and why.
Drift carried from the last /after-merge, listed by file, as drift.
```

## Then stop

Report the PR URL, the test line, and anything that needs applying. Do not merge, do not `git merge`, do not push `main`, do not rebase onto `main` unasked. When the user says "merge it" on this PR: `gh pr merge N --merge` (merge commit, remote branch kept), then `/after-merge`. When the user says they merged it themselves: `/after-merge`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Opening the PR before the docs | `/docs` first; the PR body's Docs section is written from what was actually changed |
| "Tests fail but not because of me" | Prove it on `main` before writing that sentence |
| Running `flask migrate` to "make the tests pass" | Denied by `settings.json`, and it is the one hard rule. Hand the file over |
| Editing the PR with `gh pr edit` | Prints a GraphQL error and changes nothing; use the `gh api` PATCH |
| "Looks right" from one headless screenshot | Two runs of one page differ by ~150k pixels; before and after go in one document (`/theme-check`) |
| A Tests section with no "not verified" line | Every collaboration PR needed two browsers it did not have; say what the reviewer must try |
