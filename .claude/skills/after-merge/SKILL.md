---
name: after-merge
description: Use when the user says a PR was merged, or asks to "sync", "pull main", "rebuild the graph", "refresh .claude", "clean up branches" — the post-merge housekeeping for this repo.
---

# After a merge: pull, refresh the map, audit `.claude/`

Merging is the user's act. Everything after it is yours, on `main`, without a single push.

## Steps

1. **Pull and prune**
   ```bash
   git checkout main && PREV=$(git rev-parse HEAD) && git pull --ff-only   # PREV = main before the pull, for the audit diff
   git fetch -p && git branch -d <merged-branch>     # or /clean_gone for every [gone] branch
   ```

2. **Refresh the graph** — the only moment the LLM pass ever runs. Do not expect the git hooks to have done it: `post-checkout` fired when you switched to `main`, but a fast-forward `git pull` fires no hook, so after step 1 the graph is still the *old* `main`. On `main` only (`git branch --show-current` must print `main`), invoke the skill; it re-extracts every file changed since the last manifest — code with the AST (free) and prose with subagents — and re-labels the communities:
   ```
   /graphify . --update
   ```
   Two things to expect. Community labelling is a manual step in the skill (a 2–5 word name per community). And the first `--update` after a graphify upgrade re-extracts **every** prose file, because the cache is keyed on the extraction prompt — 54 files and ~400k subagent tokens the first time; run it anyway, on `main`, it is what the rule is for. The skill's report has **no** `Built from commit` line — only graphify's code-only rebuild writes that stamp, and the session hook reads it — so finish with
   ```bash
   PYTHONHASHSEED=0 graphify update .
   ```
   which re-stamps the report at `HEAD` and keeps every prose node (1390 before and after on 2026-09-09). Then confirm the stamp equals `git rev-parse --short HEAD`.
   When you write the extraction subagents' prompts, tell each one to mint nodes **only under its own file's ID stem** and to refer to other files' entities by edge, never by node — a chunk that re-emits another file's IDs creates stubs with the wrong source file, and the next re-extraction of the real file loses to them.

3. **Audit `.claude/` against what landed**: `git diff --stat "$PREV"..HEAD` and `git log --oneline "$PREV"..HEAD`, then for each kind of change:

   | Landed | Refresh |
   |---|---|
   | new module, template, static file, migration, CLI command | `CLAUDE.md` layout tree; `design.md` §2 (and §3 for a migration, §11 for a CLI command) |
   | new or reshaped block | `design.md` §5; `/new-block` if a step turned out to be missing or wrong |
   | new route, URL, endpoint | `design.md` §7 |
   | theme rule an agent could undo | `design.md` §9 |
   | admin screen or editor behaviour | `design.md` §10 |
   | a decision with a why | `design.md` §14 row, dated; a client decision → `requirements.md` table |
   | a procedure that was repeated or got a step wrong | the skill that owns it, or a new one if none does |
   | a command that prompted for permission more than once | `settings.json` `allow` |
   | a command that must never run unasked | `settings.json` `deny` |
   | a rule in `CLAUDE.md` that the PR had to work around | the rule |

   Also read the merged PR body's **Decisions worth reviewing** — those rows belong in §14.

4. **Nothing drifted?** Say so, with the graph commit line, and stop.
   **Something drifted?** `git checkout -b chore/claude-sync-<date>`, make the edits, `/pr`. Never commit to `main`.

5. **Per-machine facts** learned on the way (a CLI that appeared, a tool that stopped working) go to Claude's memory directory, not to the repo.

## Do not

- Run `/graphify` or `graphify label` on a branch (`CLAUDE.md` rule 1). The git hooks' code-only rebuild is not that.
- Touch the database.
- Push anything from `main`.
- Rewrite `design.md` from scratch; it is refreshed, section by section, against the diff.
