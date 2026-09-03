-- 0002_enable_rls: lock every app table away from Supabase's PostgREST / anon key.
-- The Flask app calls PostgREST with the service_role key (BYPASSRLS); with no policies defined,
-- the anon / authenticated keys get nothing from these tables (drafts, leads stay private).
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE taxonomies ENABLE ROW LEVEL SECURITY;
ALTER TABLE terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE media ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE menus ENABLE ROW LEVEL SECURITY;
ALTER TABLE redirects ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
