-- Give Realtime the tenant it actually looks up. Hand-run, once, per Supabase stack.

-- NOT a migration step: no four-digit prefix, so `flask migrate` never sees it. It repairs the
-- Supabase stack rather than our schema, it is needed once per instance and only on some of them,
-- and `flask migrate` gates the app container -- a file that fails here would be an outage rather
-- than a warning. `repair_schema_migrations.sql` is the same shape.
--
-- THE FAULT, measured on production 2026-09-21. The editor never reaches SUBSCRIBED and the console
-- repeats `channel error: connection lost`. From inside the app container:
--
--     GET <SUPABASE_URL>/realtime/v1/longpoll?vsn=2.0.0&apikey=...  ->  200 {"status":403}
--     docker logs <stack>-realtime-1
--     error_code=TenantNotFound [error] TenantNotFound: Tenant not found: realtime
--
-- Realtime is multi-tenant even when self-hosted. `SEED_SELF_HOST=true` creates a tenant called
-- `realtime-dev` at boot, while the running service resolves `realtime` per connection -- so every
-- connection is refused before a channel is ever joined, the RLS policy in 0009 is never consulted,
-- and the app's own logs said nothing until `realtime_longpoll()` learned to warn (TECHNICAL 12.3).
--
-- THE FIX IS A SECOND ROW, NOT A RENAME, and that is the part worth reading. The development stack
-- has both `realtime-dev` and `realtime` and has worked for weeks; its realtime container's
-- environment is byte-identical to production's (`APP_NAME=realtime`, `SEED_SELF_HOST=true`), which
-- is how we know the env var TECHNICAL 15 recommended was never what fixed it. A second row also
-- survives what a rename would not: `SEED_SELF_HOST` recreates `realtime-dev` whenever it is absent,
-- so renaming it away simply brings it back and leaves the same two names unmatched.
--
-- The row is COPIED rather than written out, so nothing here has to know this image's column list --
-- and `jwt_secret` is encrypted with the container's `DB_ENC_KEY`, which differs per stack, so a
-- hand-written secret would be wrong in a way that only shows up as another silent refusal.
--
-- RUN IT AS supabase_admin, NOT postgres. `_realtime` is owned by supabase_admin -- the role the
-- realtime container itself connects as -- and `postgres` is not a member of it on these images, so
-- the block gets `42501: permission denied for table tenants` on the insert and nothing else says why
-- (confirmed 2026-09-21). Studio's SQL editor runs as postgres too, so this one goes through psql:
--
--     docker exec -i <stack>-db-1 psql -U supabase_admin -d postgres < repair_realtime_tenant.sql
--
-- Safe to run twice. Restart the realtime container afterwards -- it caches authorisation per tenant:
--     docker restart <stack>-realtime-1

do $$
declare
    want text := 'realtime';       -- what the service asks for; the name in the TenantNotFound line
    have text := 'realtime-dev';   -- what SEED_SELF_HOST created
begin
    if exists (select 1 from _realtime.tenants where external_id = want) then
        raise notice 'tenant % already exists; nothing to do', want;
        return;
    end if;
    if not exists (select 1 from _realtime.tenants where external_id = have) then
        raise exception 'no % tenant to copy from -- check `select external_id from _realtime.tenants`', have;
    end if;

    create temp table _t on commit drop as select * from _realtime.tenants where external_id = have;
    update _t set id = gen_random_uuid(), external_id = want, name = want;
    insert into _realtime.tenants select * from _t;

    -- Broadcast and presence need no extension row, but postgres_changes would, and a tenant that
    -- has one on this instance should have it under both names rather than differ by which is used.
    create temp table _e on commit drop as select * from _realtime.extensions where tenant_external_id = have;
    update _e set id = gen_random_uuid(), tenant_external_id = want;
    insert into _realtime.extensions select * from _e;

    raise notice 'tenant % created from %', want, have;
end $$;

-- Check: both names present, and the container log quiet after a restart.
select external_id, name from _realtime.tenants order by external_id;
