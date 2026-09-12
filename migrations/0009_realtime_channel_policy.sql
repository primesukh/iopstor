-- Let CMS editors join a page's realtime channel, and nobody else.

-- Two people editing the same page could not see each other. Presence -- who has this page open,
-- which section they are in -- is carried over Supabase Realtime on a private channel named
-- post:<id>, so the browsers talk to each other without Flask in the middle (gunicorn runs sync
-- workers and cannot hold a websocket; see design.md).
--
-- A private channel is authorised by RLS on realtime.messages. That table already has RLS enabled
-- and, on this instance, ZERO policies -- so today it denies everything that does not bypass RLS,
-- and presence simply cannot work. This file is what turns it on; it is not a hardening extra.
--
-- The policy deliberately does NOT stop at `to authenticated`. This GoTrue has signups enabled, so
-- "holds a valid token" is a wider set than "is a CMS editor". The app's own rule is one line --
-- auth.current_user() returns the public.users row for the token's sub, and no row means 403 -- so
-- the policy asks exactly that question.
--
-- IT HAS TO ASK IT THROUGH A SECURITY DEFINER FUNCTION, AND THAT IS THE WHOLE TRICK HERE.
-- The obvious `exists (select 1 from public.users where id = auth.uid())` written inline is always
-- FALSE: the policy runs as the authenticated role, 0002 turned RLS on for public.users, and that
-- table has no policies of its own -- so the subquery sees an empty table and every editor is
-- refused. Verified against the running instance: a real admin selecting their own row over
-- PostgREST as `authenticated` gets []. The function below runs as its owner instead, which
-- bypasses RLS because 0002 uses ENABLE and not FORCE, and it returns one boolean about the caller
-- and nothing else -- no row, no email, no role.
--
-- THREE MORE THINGS THAT LOOK LIKE MISTAKES AND ARE NOT:
--   1. No `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` line. /migration step 4 asks for one on every
--      new table; realtime.messages is not our table and RLS is already on. Nothing to add.
--   2. `extension in ('broadcast','presence')` -- presence rides realtime.messages too. A
--      broadcast-only policy makes channel.track() fail silently and the roster stays empty forever.
--   3. The `topic` COLUMN, not realtime.topic(). The helper function only exists on newer Realtime
--      builds; the column exists on all of them.
--
-- Depends on 0001 for public.users. Safe to run twice. Nothing to run later.
-- Before it is applied the app is unaffected: subscribe() returns CHANNEL_ERROR and the editor stays
-- single-player, which is the same state as SUPABASE_PUBLIC_URL being unset.
-- After changing it, restart the realtime container: it caches authorisation per tenant.

-- search_path is pinned and every name below is schema-qualified: a SECURITY DEFINER function that
-- resolves names through the caller's search_path is how privilege escalation gets in.
create or replace function public.is_cms_user()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.users where id = (select auth.uid()));
$$;

revoke all on function public.is_cms_user() from public;
grant execute on function public.is_cms_user() to authenticated;

drop policy if exists "cms editors read page channels" on realtime.messages;
create policy "cms editors read page channels" on realtime.messages
    for select to authenticated
    using (
        extension in ('broadcast', 'presence')
        and topic like 'post:%'
        and public.is_cms_user()
    );

drop policy if exists "cms editors write page channels" on realtime.messages;
create policy "cms editors write page channels" on realtime.messages
    for insert to authenticated
    with check (
        extension in ('broadcast', 'presence')
        and topic like 'post:%'
        and public.is_cms_user()
    );
