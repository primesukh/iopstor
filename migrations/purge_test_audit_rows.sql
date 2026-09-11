-- Hand-run in Studio's SQL editor. NOT a migration -- no four-digit prefix, so `flask migrate`
-- never touches it (test_only_numbered_files_are_migrations guards that).
--
-- Why this exists: audit_log is append-only by trigger, which is the point of it, so nothing the
-- app or a test fixture does can take a row out again. Before db._audit() learned to sit out of
-- TESTING, a run of the live suite against the development Supabase left its zz-test writes in the
-- Activity screen permanently. This is how you take them out.
--
-- Safe to run twice. Nothing to run later. It is the only sanctioned way to delete from this table:
-- if you find yourself reaching for it for any reason other than test rows, stop -- the whole value
-- of the table is that nobody can quietly edit their own history out of it.

-- 1. LOOK FIRST. Decide what is yours and what is the suite's.
SELECT id, at, action, table_name, label, user_email FROM public.audit_log ORDER BY id;

-- 2. Lift the guard.
ALTER TABLE public.audit_log DISABLE TRIGGER audit_log_no_change;

-- 3a. Everything the suite names after itself: its users, its posts, its terms, its redirects, its
--     media, and the leads it submits (the address is inside the recorded change).
DELETE FROM public.audit_log
 WHERE user_email LIKE '%@zz-test.local'
    OR label LIKE 'zz-test%'
    OR label LIKE '/zz-test%'
    OR changes -> 'email' ->> 1 LIKE '%@zz-test.local';

-- 3b. The rest of a run is harder to name: tests/test_auth.py signs in with invented addresses like
--     a@b.c, which look like a real person getting their password wrong. Read the SELECT above,
--     find the minute the run happened in, and uncomment this with that window.
-- DELETE FROM public.audit_log
--  WHERE at >= '2026-09-11T05:03:00Z' AND at < '2026-09-11T05:04:00Z';

-- 4. PUT THE GUARD BACK. Do not skip this -- without it the table is editable by anything holding
--    the service-role key, which is the app itself.
ALTER TABLE public.audit_log ENABLE TRIGGER audit_log_no_change;

-- 5. Check.
SELECT count(*) AS remaining FROM public.audit_log;
