---
name: after-merge
description: Use when the user says a PR was merged, or asks to "sync", "pull main", "refresh .claude", "clean up branches" — the post-merge housekeeping for this repo.
---

# After a merge: pull, then bring `.claude/` back in line by hand

Merging is the user's act. Everything after it is yours, on `main`, without a single push.

## Steps

1. **Pull and prune**
   ```bash
   git checkout main && PREV=$(git rev-parse HEAD) && git pull --ff-only   # PREV = main before the pull, for the audit diff
   git fetch -p && git branch -d <merged-branch>     # or /clean_gone for every [gone] branch
   ```

2. **Bring `.claude/` back in line, by hand.** This is the whole job — nothing rebuilds it for you. A sentence that was true last week is the failure mode, and the diff is the only thing that proves it either way, so read what landed — `git diff --stat "$PREV"..HEAD` and `git log --oneline "$PREV"..HEAD` — then open every file the table points at and check the sentence describing the changed thing still describes it:

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

3. **Nothing drifted?** Say which files you read and stop.
   **Something drifted?** `git checkout -b chore/claude-sync-<date>`, make the edits, `/pr`. Never commit to `main`.

4. **Per-machine facts** learned on the way (a CLI that appeared, a tool that stopped working) go to Claude's memory directory, not to the repo.

## Do not

- Run `/graphify . --update`, `/graphify` or `graphify label`. The graph is queried, never rebuilt from here — its code half follows the git hooks on its own, and its prose half is deliberately left where it is (`CLAUDE.md` rule 1).
- Touch the database.
- Push anything from `main`.
- Rewrite `design.md` from scratch; it is refreshed, section by section, against the diff.
