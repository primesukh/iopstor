---
name: docs
description: Use when a change is code-complete and the documentation has not caught up — before opening a PR, after a feature or fix lands on the branch, or when asked to "update the docs", "document this", "write it up".
---

# Three docs, three readers

A feature is not finished until all three say so, in the same PR. `TECHNICAL.md` and `NON-TECHNICAL.md` are the project's living documentation; `.claude/docs/design.md` is the map the next agent reads before touching anything.

| Doc | Reader | Voice |
|---|---|---|
| `docs/TECHNICAL.md` | The next developer | The mechanism **and the trap**: what it does, why the obvious alternative was wrong, what breaks if you move it. Names functions, templates, tests. Section numbers are stable — add inside the right §, do not renumber |
| `docs/NON-TECHNICAL.md` | Marketing, sales, HR, management | Plain English, no identifiers, no jargon. What they can now do, where the button is, what they will see. Every visible behaviour change also gets a line in *Quick answers* (the last section, phrased as the question an editor would ask) and *Where the project stands* if it moves the status |
| `.claude/docs/design.md` | The next agent | What exists and why, compressed. Update the section that describes the changed area, and add a dated row to §14 for any decision that would surprise someone |

## Where a change goes

| Change | TECHNICAL.md | NON-TECHNICAL.md | design.md |
|---|---|---|---|
| New block type | §6 (count + shape), §16 table | §4 *Adding a section* list | §5 |
| Schema / migration | §3 table, §10 | only if editors see a new field | §3, §2 (migrations line) |
| Admin screen or control | §8 `/admin` routes, §12 admin shell / §12.1 editor | the screen's own § + Quick answers | §10, §7 admin row |
| The editor itself — `admin.js`, the canvas, Quill, the shared document, presence, autosave | §12.1, §12.3 *Working at the same time*, §17 for any new ceiling | §4 *Writing* and *Seeing who else is on the page* + Quick answers | §10 editor paragraph, §15 |
| Preview | §12.2 | §4 *Checking how it looks* | §10 Preview paragraph |
| Activity wording, or what is and is not recorded | §8 `/admin/audit`; §4 if a write path changed | §11 *Activity* | §10 Activity paragraph |
| A test, a harness, a suite rule | §13 | — | §13 |
| Public URL / endpoint | §5 or §8 | §10 if it is about being found | §7 |
| Theme | §12 (the decision, the CSS rule that carries it) | only if a visitor notices | §9 if it is a rule an agent could undo |
| CLI command | §2 module map, §15 | — | §2, §11 |
| A `# ponytail:` ceiling | §17 | — | §15 if an agent will trip on it |
| Client decision | — | *Where the project stands*, if it moves the status | `requirements.md` decisions table (dated), the ask quoted |
| Workflow / tooling / `.claude/` | §18 | — | §16 + `CLAUDE.md` |
| Deployment / hosting / env key | §14 (the key and what breaks without it), §15 (the runbook step) | *Where the project stands* only if the address or the live/practice split changes | §1 platform table, §14 row + `CLAUDE.md` Env keys |

**NON-TECHNICAL.md's sections are referred to by name here, not by number, on purpose:** its two closing sections are *Where the project stands* and *Quick answers*, and inserting a screen's section ahead of them renumbers both (audit log, 2026-09-11). TECHNICAL.md and design.md numbers *are* stable — add inside the right §, never renumber. If you do move a NON-TECHNICAL heading, `grep -rn "NON-TECHNICAL" .claude/ docs/ CLAUDE.md` and fix what points at it.

**An applied migration's header comment is never rewritten, even once it is false.** `0009` still says the browsers talk to Supabase without Flask in the middle; PR #72 made that untrue and left the file alone — an applied file is history. The supersession is a dated `design.md` §14 row that names the file.

A change can match several rows; apply every row that matches. A client decision about the header is a dated `requirements.md` row **and** a `design.md` §9 rule an agent could undo **and** a TECHNICAL.md §12 paragraph.

## How to write the TECHNICAL.md entry

1. Say what it does in one sentence.
2. Say where it lives — the function, template, CSS group, migration.
3. Say why it is shaped that way — the alternative that was tried or considered, and what went wrong with it. This is the part the next developer cannot get from the code.
4. Name the test that guards it.
5. Keep existing prose; extend it. Delete only what is now false.

## How to write the NON-TECHNICAL.md entry

- Start from what the editor sees on the screen or the site, not from the feature name.
- Use the admin's own labels in bold (**Save**, **Warranty**, *Details*).
- If it changed something they might notice and worry about, add a Quick answer: "*The X looks different.* It now …".
- Never mention a file, a function, a table, JSON or a migration.

## Check before `/pr`

```bash
grep -n "<the feature's word>" docs/TECHNICAL.md docs/NON-TECHNICAL.md .claude/docs/design.md
```

Each file should hit, or the PR body must say which audience is unaffected and why.

If `/after-merge` reported drift in this area, this PR carries it: fix it here and list it in the PR body's **Docs** section as drift, by file (PRs #65, #66, #67 did). Do not open a PR of its own for it.
