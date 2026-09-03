-- 0000_bootstrap: run this ONCE by hand in Supabase Studio → SQL editor (as the postgres role).
-- It is the only SQL that is not applied by `flask migrate`. Everything after it goes through the
-- apply_migration() function below, which the app calls over Kong (/rest/v1/rpc/apply_migration)
-- with the service-role key. anon / authenticated cannot execute it.

create table if not exists public.schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
);
alter table public.schema_migrations enable row level security;

create or replace function public.apply_migration(name text, sql text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    if exists (select 1 from public.schema_migrations where filename = name) then
        return false;
    end if;
    execute sql;                                           -- whole file, one transaction
    insert into public.schema_migrations (filename) values (name);
    perform pg_notify('pgrst', 'reload schema');           -- let PostgREST see new tables at once
    return true;
end
$$;

revoke all on function public.apply_migration(text, text) from public, anon, authenticated;
grant execute on function public.apply_migration(text, text) to service_role;

-- updated_at maintenance for every table that has the column (used by 0001)
create extension if not exists moddatetime with schema extensions;
