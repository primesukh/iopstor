---
name: after-merge
description: Use when the user says a PR was merged, or asks to "sync", "pull main", "refresh .claude", "clean up branches" — the post-merge housekeeping for this repo.
---

# After a merge: pull, audit `.claude/`

Merging is the user's act. Everything after it is yours, on `main`, without a single push.

The graph is **not** refreshed here — no `/graphify`, no `graphify update` (user, 2026-09-11). The audit is, and it is mandatory: every `.claude/` and `docs/` file the merged diff made untrue is found and named as drift for the next PR that touches that area — found here, never committed here. Dropping the graph step does not make this step optional — it is now the whole point of the skill.

## Steps

1. **Pull and prune**
   ```bash
   git checkout main && PREV=$(git rev-parse HEAD) && git pull --ff-only   # PREV = main before the pull, for the audit diff
   git fetch -p && git branch -d <merged-branch>     # or /clean_gone for every [gone] branch
   ```

2. **Audit the written docs against what landed — mandatory, every merge, no exceptions.** Read the diff first and check *every* file below against it: `CLAUDE.md`, `.claude/docs/design.md`, `.claude/docs/requirements.md`, the six skills, `settings.json`, and `docs/TECHNICAL.md` + `docs/NON-TECHNICAL.md` if the merged PR left either behind (rule 3 says it should not have — if it did, that is the miss to name).

   ```bash
   git diff --stat "$PREV"..HEAD && git log --oneline "$PREV"..HEAD
   ```

   Then for each kind of change:

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
   | anything the merged PR changed for developers or editors and did not write down | `docs/TECHNICAL.md` / `docs/NON-TECHNICAL.md` — a rule-3 miss on that PR; fix it in the next PR that touches the area and name it |

   Also read the merged PR body's **Decisions worth reviewing** — those rows belong in §14.

3. **Nothing drifted?** Say so and stop.
   **Something drifted?** Say what drifted and where it belongs, and carry it in the next PR that touches that area. Do not open a PR of your own for it, and never commit to `main`. Rows the merged PR should have carried are a rule-3 miss on the last PR — name it as that.

4. **Per-machine facts** learned on the way (a CLI that appeared, a tool that stopped working) go to Claude's memory directory, not to the repo.

## Do not

- Run `/graphify`, `graphify update` or `graphify label` — on a branch **or** on `main`, and least of all here (user, 2026-09-11). The graph's code half keeps itself current through the git hooks; its prose half is refreshed only when the user asks for `/graphify`, so expect the session hook's "N commits behind" to read non-zero after a pull until the next commit or branch switch, and expect the prose nodes to be several merges old. Query the graph for the shape, confirm the detail against source.
- Touch the database.
- Push anything from `main`.
- Rewrite `design.md` from scratch; it is refreshed, section by section, against the diff.
