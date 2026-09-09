---
name: pr
description: Use when work on a branch is ready to leave this machine — committing, pushing, opening or updating the pull request — or when asked to "open a PR", "push this", "ship it", "update the PR body".
---

# Open the PR, then stop

The PR is the hand-off. It is opened by you and merged by the user, never by you. `gh` is installed and authenticated as `primesukh`.

## Pre-flight (every line must be true before `git push`)

- On a `feat/ | fix/ | docs/ | chore/` branch, not `main`: `git branch --show-current`
- `pipenv run pytest -q` was run in this session. Record the count. A failure that also fails on `main` is reported as such **after checking** (`git stash; git checkout main; pytest <test>; git checkout -; git stash pop`), never assumed.
- `/docs` is done: `docs/TECHNICAL.md`, `docs/NON-TECHNICAL.md`, `.claude/docs/design.md` — or the body says which audience is genuinely unaffected and why.
- A new `migrations/NNNN_*.sql` exists → it was **not** applied by you, and the body has a **Needs applying** section naming it.
- `Pipfile` changed → `requirements.txt` and `requirements-dev.txt` were regenerated from the lock.
- Theme or admin change → `/theme-check` screenshots were looked at.
- Nothing staged from `.env`, `website_assets/`, `graphify-out/`: `git status --short`.
- No Claude or Anthropic authorship anywhere: `git log origin/main..HEAD --format=%B | grep -iE 'claude|anthropic'` prints nothing. (`settings.json` sets `includeCoAuthoredBy: false`; check anyway.)

## Commit style

`type(scope): a sentence in plain words about what changed for whom`, as the history does — `fix(theme): the services list stacks on a phone instead of running off it`, `feat(admin): a warranty register, and a serial-number check for visitors`. Body: the why, the trap avoided, the decision the reviewer should question. One commit per coherent change; do not squash a migration into the code that reads it unless they cannot be separated.

## Push and open

```bash
git push -u origin "$(git branch --show-current)"
gh pr create --title "<the commit's sentence>" --body-file /tmp/claude-1000/pr-body.md
```

Never `--web`. Write the body to a file first (heredoc), then pass it — a body with backticks and tables does not survive `--body "..."`.

`git push` and both `gh` calls prompt for permission; that is deliberate — they are the only outward-facing commands in the repo.

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
- Each non-obvious choice as one bullet: what, and why the alternative lost.

## Needs applying            (only if a migration or a seed change is in the PR)
`migrations/NNNN_name.sql` — **not applied**; apply before the branch is used. Say what happens to the app before it is applied (the code tolerates the gap, or does not).

## Tests
`N passed` (+ any pre-existing failure, verified on main). What was checked by hand, on which port.

## Docs
Which sections of TECHNICAL.md, NON-TECHNICAL.md and .claude/docs/design.md changed — or which audience is unaffected and why.
```

## Then stop

Report the PR URL, the test line, and anything that needs applying. Do not merge, do not `git merge`, do not push `main`, do not rebase onto `main` unasked. When the user says it is merged, `/after-merge`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Opening the PR before the docs | `/docs` first; the PR body's Docs section is written from what was actually changed |
| "Tests fail but not because of me" | Prove it on `main` before writing that sentence |
| Running `flask migrate` to "make the tests pass" | Denied by `settings.json`, and it is the one hard rule. Hand the file over |
| Editing the PR with `gh pr edit` | Prints a GraphQL error and changes nothing; use the `gh api` PATCH |
