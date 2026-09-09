-- Repair: tell schema_migrations what this database already has.
--
-- Symptom
--     $ flask migrate
--     Error: 0001_initial.sql: relation "menus" already exists
--
-- Cause: the schema was built by running these files by hand in the SQL editor, before anything was
-- writing to the ledger. Every table is there; the row that says so is not, so migrate() starts from
-- the beginning again and the first CREATE TABLE collides with the table it already made.
--
-- This is NOT a migration -- it is a repair, run by hand like 0000_bootstrap.sql, and `flask migrate`
-- ignores it because its name does not start with four digits. Paste it into Supabase Studio's SQL
-- editor and run it, then run `flask migrate` again.
--
-- Each file is recorded only if the thing that file makes is actually present, so this is safe on a
-- database in any state and safe to run twice. A file that was never applied stays unrecorded and
-- `flask migrate` will apply it normally.

insert into public.schema_migrations (filename)
select f
from (values
    -- the initial schema: keyed on a table only it creates
    ('0001_initial.sql',
     to_regclass('public.posts') is not null),

    -- row-level security: keyed on the flag itself, not on the table, because the table can exist
    -- with RLS still off -- which is exactly the state this file is meant to fix
    ('0002_enable_rls.sql',
     exists (select 1 from pg_class
             where relname = 'posts' and relnamespace = 'public'::regnamespace and relrowsecurity)),

    ('0003_warranty.sql',
     to_regclass('public.warranties') is not null),

    -- 0004 adds a constraint and no column, so the constraint is the only trace of it
    ('0004_warranty_date_check.sql',
     exists (select 1 from pg_constraint where conname = 'warranties_expiry_after_purchase'))
) as t(f, already_here)
where already_here
on conflict (filename) do nothing;

-- what the ledger says now
select filename, applied_at from public.schema_migrations order by filename;
