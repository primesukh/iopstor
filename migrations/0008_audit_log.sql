-- Who did what, when, and what it was before.
--
-- The CMS could not answer any of those. updated_at says a post changed; author_id says who first
-- created it. Nothing recorded who edited it, what they changed it from, who deleted the page that
-- is now missing, who changed a setting, or who signed in. With more than one editor that gap is
-- the difference between a record and a guess.
--
-- One table, written by db._audit() from inside db.insert()/update()/delete(), so a new write path
-- is logged without anybody remembering to log it. changes is {field: [before, after]} for every
-- field that actually changed -- which is what lets the admin screen show a post's old and new
-- version side by side, and lets Restore write the old values back.
--
-- Three deliberate departures from the other tables in this schema, each with a reason:
--
-- 1. text, not varchar(n). A title longer than the limit would fail the audit INSERT, and that
--    INSERT is deliberately swallowed (the content write has already succeeded; failing the request
--    afterwards would confuse the editor without undoing anything). A silently missing entry is the
--    one failure an audit log must not have, so no string here has a length to trip over.
--
-- 2. bigint generated always as identity, not SERIAL. This table grows per action rather than per
--    page, and `generated always` additionally refuses an INSERT that supplies its own id.
--
-- 3. No foreign key to users. The log has to outlive the row it names, so the actor's address is
--    copied in as text: delete the user and the record of what they did still names them.
--
-- Append-only is enforced by Postgres, not by the app declining to offer a delete -- the app holds
-- the service-role key and could otherwise rewrite its own evidence.
--
-- Safe to run twice. Nothing to run later.
--
-- One consequence on the development database: the live tests write audit rows that their cleanup
-- fixture then cannot remove. To purge them by hand, in the SQL editor:
--     ALTER TABLE public.audit_log DISABLE TRIGGER audit_log_no_change;
--     DELETE FROM public.audit_log WHERE ...;
--     ALTER TABLE public.audit_log ENABLE TRIGGER audit_log_no_change;

CREATE TABLE IF NOT EXISTS public.audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at          TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    user_id     UUID,                        -- no FK: the log outlives the user row
    user_email  TEXT DEFAULT '' NOT NULL,    -- copied, so a removed user is still named
    ip          TEXT DEFAULT '' NOT NULL,
    action      TEXT NOT NULL,               -- create | update | delete | restore | login | logout | login_failed
    table_name  TEXT DEFAULT '' NOT NULL,
    row_id      TEXT DEFAULT '' NOT NULL,    -- text: posts are ints, users uuids, settings keys
    label       TEXT DEFAULT '' NOT NULL,    -- the human name of the row at the time
    changes     JSONB DEFAULT '{}' NOT NULL  -- {field: [before, after]}
);

-- The screen lists newest first, which is the primary key backwards -- no index needed for that.
-- This one is for the "everything one person did" filter, the only other query there is.
CREATE INDEX IF NOT EXISTS ix_audit_log_user_id ON public.audit_log (user_id, id DESC);

CREATE OR REPLACE FUNCTION public.audit_log_immutable() RETURNS trigger
    LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END $$;

CREATE OR REPLACE TRIGGER audit_log_no_change
    BEFORE UPDATE OR DELETE ON public.audit_log
    FOR EACH ROW EXECUTE FUNCTION public.audit_log_immutable();

-- No policies, like every other table here: the service-role key bypasses RLS, the anon key must
-- see nothing. An audit log readable with the public key would be the worst of the eleven.
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
