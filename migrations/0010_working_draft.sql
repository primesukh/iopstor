-- A page keeps its unpublished edits beside it, and the log still says who changed what.

-- Until now Save wrote posts.blocks, and if the page was published that was instantly live. The
-- editor is about to start saving by itself every second or two, which would put a half-typed
-- sentence on the website. So the work in progress goes somewhere that is never public, and
-- Publish is the deliberate act that moves it across. posts.blocks stays exactly what it is --
-- the published content -- and every public reader (render_blocks, the .md twins, llms-full.txt,
-- the sitemap, the feed, the JSON API) goes on reading it with no change at all.
--
-- TWO TABLES, AND BOTH ARE BESIDE posts RATHER THAN COLUMNS ON IT. That is the decision this file
-- exists to record, because columns look obviously simpler and are wrong four times over:
--
--   1. db.select_posts() selects "*", and db.tree() uses it with NO limit on every public page
--      view (the header's services panel). A draft-blocks column would put a second copy of every
--      service page's content into every request on the site.
--   2. public.public_post() does dict(post) and pops only author_id, so a draft column would be
--      served to the world through /api/v1/posts -- unreviewed content, published by accident.
--   3. db._diff() excludes only created_at, updated_at and serial_key, so every save would write
--      both halves of the draft into audit_log.changes, which has no retention job.
--   4. posts has a moddatetime trigger on updated_at, and that column is the save-conflict token
--      (0001 + the if_unchanged guard). An autosave touching posts would bump it and invalidate
--      every other editor's open form every couple of seconds.
--
-- Safe to run twice. Nothing to run later.
--
-- Before this file is applied the app behaves exactly as it does today: db.get_draft() swallows
-- PostgREST's "relation does not exist" and returns None, the editor loads posts.blocks, and no
-- editing session is ever opened.

-- The work in progress. One row per page, and it only exists while there is something unpublished.
CREATE TABLE IF NOT EXISTS public.post_drafts (
    post_id          INTEGER PRIMARY KEY REFERENCES public.posts(id) ON DELETE CASCADE,
    blocks           JSONB DEFAULT '[]'::jsonb NOT NULL,
    -- ponytail: base64 of the CRDT document, ~33% bigger than the bytes. TEXT and not BYTEA on
    -- purpose: PostgREST hands bytea back as a \x hex string and supabase-py JSON-encodes it, so a
    -- real bytea would mean encoding and decoding on both sides to arrive where base64 already is.
    -- Empty until the shared-document PR; the column is here so that PR needs no migration.
    state            TEXT  DEFAULT '' NOT NULL,
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_by       UUID,                       -- no FK: informational, and it outlives the user row
    updated_by_email TEXT DEFAULT '' NOT NULL
);

-- One open editing session per person per page, and it is what keeps the audit log honest.
--
-- audit_log records a row from inside db.insert/update/delete, so today every Save is logged with
-- its before and after. Autosave cannot be logged that way -- audit_log has no retention job and
-- stores the whole blocks array on both sides of every write, so a row every second or two per
-- editor would grow without bound. Instead each editor accumulates what THEY changed here, and
-- fifteen minutes after their last change (or when they close the tab, or when the page is
-- published) it is flushed to one audit_log row attributed to them.
--
-- ip is copied onto the row because the flush usually runs inside somebody else's request: there is
-- no scheduler here, so stale sessions are closed opportunistically by whoever next touches the
-- page. Taking the ip from that request would record the wrong person's address.
CREATE TABLE IF NOT EXISTS public.post_sessions (
    post_id     INTEGER NOT NULL REFERENCES public.posts(id) ON DELETE CASCADE,
    user_id     UUID    NOT NULL,
    user_email  TEXT DEFAULT '' NOT NULL,    -- copied, so a removed user is still named
    ip          TEXT DEFAULT '' NOT NULL,
    changes     JSONB DEFAULT '{}' NOT NULL, -- {field: [was, now]}, the shape audit_log.changes uses
    started_at  TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (post_id, user_id)
);

-- The only query there is besides "this page's sessions": find the stale ones to close.
CREATE INDEX IF NOT EXISTS ix_post_sessions_updated_at ON public.post_sessions (updated_at);

-- keep updated_at current on UPDATE (moddatetime extension, enabled in 0000_bootstrap), the same
-- way 0001 does for every other table. On post_drafts it is also the autosave's version token.
CREATE OR REPLACE TRIGGER post_drafts_updated_at BEFORE UPDATE ON public.post_drafts
    FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE OR REPLACE TRIGGER post_sessions_updated_at BEFORE UPDATE ON public.post_sessions
    FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);

-- No policies, like every other table here: the service-role key bypasses RLS and the anon key must
-- see nothing. A draft readable with the public key would be the unpublished-content leak this
-- whole file exists to prevent.
ALTER TABLE public.post_drafts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.post_sessions ENABLE ROW LEVEL SECURITY;
