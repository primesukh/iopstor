-- Let CMS editors join a page's realtime channel, and nobody else.

-- Two people editing the same page could not see each other. The next step is presence -- who has
-- this page open, which section they are in -- carried over Supabase Realtime on a private channel
-- named post:<id>, so the browsers talk to each other without Flask in the middle (gunicorn runs
-- sync workers and cannot hold a websocket; see design.md).
--
-- A private channel is authorised by RLS on realtime.messages. That table already has RLS enabled
-- and, on this instance, ZERO policies -- so today it denies everything that does not bypass RLS,
-- and presence simply cannot work. This file is what turns it on; it is not a hardening extra.
--
-- The policy deliberately does NOT stop at `to authenticated`. This GoTrue has signups enabled, so
-- "holds a valid token" is a wider set than "is a CMS editor". The app's own rule is one line --
-- auth.current_user() returns the public.users row for the token's sub, and no row means 403 -- so
-- the policy mirrors exactly that with an EXISTS. The topic filter keeps the grant to page channels
-- rather than every channel name somebody can invent.
--
-- THREE THINGS THAT LOOK LIKE MISTAKES AND ARE NOT:
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

drop policy if exists "cms editors read page channels" on realtime.messages;
create policy "cms editors read page channels" on realtime.messages
    for select to authenticated
    using (
        extension in ('broadcast', 'presence')
        and topic like 'post:%'
        and exists (select 1 from public.users u where u.id = auth.uid())
    );

drop policy if exists "cms editors write page channels" on realtime.messages;
create policy "cms editors write page channels" on realtime.messages
    for insert to authenticated
    with check (
        extension in ('broadcast', 'presence')
        and topic like 'post:%'
        and exists (select 1 from public.users u where u.id = auth.uid())
    );
