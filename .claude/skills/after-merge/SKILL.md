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

2. **Refresh the graph's prose half** — the only moment the LLM pass ever runs. The code half already rebuilt itself: the `post-checkout` hook fired on step 1 (`~/.cache/graphify-rebuild.log`), and `grep 'Built from commit' graphify-out/GRAPH_REPORT.md` should already name `HEAD`. Now, on `main` only (`git branch --show-current` must print `main`), invoke the skill so the docs that changed in the merged PRs and the community labels are re-extracted:
   ```
   /graphify . --update
   ```
   If the report says the community set changed since labelling, that pass also refreshes the names. Confirm the report's commit line equals `git rev-parse --short HEAD` afterwards.

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
