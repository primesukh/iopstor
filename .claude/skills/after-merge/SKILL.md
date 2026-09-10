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

2. **Refresh the graph — two commands, and the code half is free.** Do not expect the git hooks to have done it: `post-checkout` fired when you switched to `main`, but a fast-forward `git pull` fires no hook, so after step 1 the graph is still the *old* `main`. The halves update **independently**, so run them in this order, on `main` only (`git branch --show-current` must print `main`):

   ```bash
   graphify update .        # code nodes. Pure AST, no LLM, no subagents, seconds. Always run this.
   ```
   ```
   /graphify --update       # doc nodes + community labels. Subagents, costs tokens. Ask first.
   ```

   `graphify update .` is the whole of the merge for a code-only PR, and it is what the report's
   `Built from commit` line follows — check it equals `git rev-parse --short HEAD` afterwards. It also
   backs the curated graph up into a dated folder under `graphify-out/` before writing, so a bad
   rebuild is recoverable.

   The second command is the only moment the LLM pass ever runs, and it is the one to be careful with.
   Two things to expect. Community labelling is a manual step in the skill (a 2–5 word name per
   community). And the first `--update` after a graphify upgrade re-extracts **every** prose file,
   because the cache is keyed on the extraction prompt — 54 files and ~400k subagent tokens the first
   time. **Say what it will cost and let the user decide** rather than firing it off: a merge whose
   prose did not change does not need it at all, and the doc nodes being one merge stale is a much
   smaller problem than the tokens. Unrefreshed files stay unstamped in the manifest, so they re-queue
   on the next update instead of being silently marked done.

   **Never pass a subdirectory to either command.** `graphify update ./docs` or `/graphify ./docs --update`
   re-roots the manifest at that path, so every tracked file outside it reads as *deleted* and its nodes
   are pruned — 88 files here, the whole code half, on 2026-09-10. The path is always `.`. To limit the
   expensive half to a few files, run `--update` from the root and filter the semantic file list, never
   the scan root.

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
