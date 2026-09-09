---
name: migration
description: Use when a change needs the database schema or seeded rows to change — a new table, column, constraint, index, a field_schema or settings row that already exists — or when asked to "add a column", "write a migration", "change the post type's fields".
---

# Write the file, hand it over, never run it

The dev Supabase is shared and live. You write `migrations/NNNN_short_name.sql`; the user applies it (Studio SQL editor or `flask migrate` on their machine). `settings.json` denies `flask migrate|seed|create-admin|import-media` from you, and the rule stands even where the deny does not reach.

**Load `supabase:supabase-postgres-best-practices` before writing SQL.**

## Steps

1. **Number it**: `ls migrations | grep -E '^[0-9]{4}_' | tail -1` → next number, zero-padded. Only `[0-9][0-9][0-9][0-9]_*.sql` is a step (`MIGRATION_GLOB`); a non-numbered file is a hand-run script, never executed by `flask migrate` (`test_only_numbered_files_are_migrations`).
2. **Header comment** the way `0005` and `0006` do (no filename prefix): the need in a sentence, what the file changes and why a re-seed could not, whether it is safe to run twice, and any line the user must run *later* (a `VALIDATE CONSTRAINT`, a follow-up) — or "nothing to run later".
3. **One schema edit per file.** Idempotent where Postgres allows it (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`). NOT NULL columns carry a `DEFAULT`. `updated_at` uses the `moddatetime` trigger the way `0001` does.
4. **New table** → end with `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` and define no policies (the service-role key bypasses; the anon key must see nothing).
5. **Constraint on a table with rows** → add it `NOT VALID` (`0004`), and put the `ALTER TABLE … VALIDATE CONSTRAINT …;` line in the comment for the user.
6. **Index for the query you are about to write**, not for one you imagine.
7. **Seeded rows**: `cli.py`'s `_get_or_create()` **only inserts** — an edit to `POST_TYPES` (`field_schema`, `has_pages`), `TAXONOMIES` or `SETTINGS` never reaches a row that already exists. Change the seed *and* write the migration that `UPDATE`s the existing row (`0005`, `0006` are the pattern), so a fresh database and the dev database end up the same. The commonest migration here changes **no column at all** — it restates a type's whole `field_schema` array (order = the order of the boxes in the form).
   - **`posts.meta` has no per-key default.** A field that "defaults to 12" is a `default` key in its descriptor (the form pre-fills it; nothing validates descriptor keys, so it is additive) *plus* a backfill `UPDATE posts … SET meta = meta || '{…}' WHERE NOT (meta ? 'key')`.
   - **A backfill on a seeded post loses to the next `flask seed --reset-content`**, which overwrites `meta` wholesale — put the same value into the seed's post data (`cli.py` `_post(..., meta=…)`) too.
8. **Code tolerates the gap.** The app must run against a database where the file is not applied yet. New column: read it with `.get(col, default)` (`with_paths()` reads `has_pages` that way); do not `SELECT` it by name in a list that a missing column would 400. New `field_schema` field: the form, `post.html`, `_card.html` and `_md_fields()` iterate descriptors generically, so before the migration the box simply is not there — say so in the hand-over, and check that any new code reading `meta.get('key')` is inert when the key is absent.
9. **Docs** — `/docs`: TECHNICAL.md §3 (table, or the per-type-data paragraph for a `field_schema` change) and §10 only if the workflow gained a wrinkle; NON-TECHNICAL.md whenever an editor sees a new box or a new line on the site; `.claude/docs/design.md` in every place that names the migration range — §0 status, §2 tree, §3 heading — plus the §3 table or types paragraph.
10. **Tell the user**, in the reply and in the PR's **Needs applying** section: the file name, what it does, what the app does before it is applied.

## Never

- `pipenv run flask migrate`, `flask seed`, `flask create-admin`, `flask import-media`, or any `db.insert/update/delete` outside a test — not to "check it works", not on a throwaway table.
- `ALTER` inside `0000_bootstrap.sql` or an already-applied file. A mistake in an applied migration is a new migration.
- A `.delete()` without a filter anywhere in code; PostgREST reads it as the whole table.

## When the ledger and the database disagree

`flask migrate` stopping on `relation "…" already exists` means the schema was built by hand and `schema_migrations` never heard about it. That is what `migrations/repair_schema_migrations.sql` is for — hand-run, safe twice. Point the user at it; do not write a second repair.
