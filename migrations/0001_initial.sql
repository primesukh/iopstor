-- 0001_initial: all IOPSTOR tables (applied through apply_migration; see 0000_bootstrap.sql).

CREATE TABLE menus (
	id SERIAL NOT NULL, 
	slug VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	items JSONB DEFAULT '[]' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE post_types (
	id SERIAL NOT NULL, 
	slug VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	url_prefix VARCHAR(100) DEFAULT '' NOT NULL, 
	hierarchical BOOLEAN DEFAULT false NOT NULL, 
	field_schema JSONB DEFAULT '[]' NOT NULL, 
	taxonomies JSONB DEFAULT '[]' NOT NULL, 
	jsonld_type VARCHAR(40), 
	in_sitemap BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE redirects (
	id SERIAL NOT NULL, 
	from_path VARCHAR(500) NOT NULL, 
	to_url VARCHAR(1000) NOT NULL, 
	code SMALLINT DEFAULT '301' NOT NULL, 
	hits INTEGER DEFAULT '0' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (from_path)
);

CREATE TABLE settings (
	key VARCHAR(100) NOT NULL, 
	value JSONB NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE taxonomies (
	id SERIAL NOT NULL, 
	slug VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE users (
	id UUID NOT NULL, 
	email VARCHAR(300) NOT NULL, 
	name VARCHAR(200) DEFAULT '' NOT NULL, 
	role VARCHAR(20) DEFAULT 'editor' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE media (
	id SERIAL NOT NULL, 
	key VARCHAR(300) NOT NULL, 
	url VARCHAR(600) NOT NULL, 
	filename VARCHAR(300) NOT NULL, 
	mime VARCHAR(100) NOT NULL, 
	size INTEGER DEFAULT '0' NOT NULL, 
	alt VARCHAR(300) DEFAULT '' NOT NULL, 
	uploaded_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (key), 
	FOREIGN KEY(uploaded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE terms (
	id SERIAL NOT NULL, 
	taxonomy_id INTEGER NOT NULL, 
	slug VARCHAR(200) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT DEFAULT '' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (taxonomy_id, slug), 
	FOREIGN KEY(taxonomy_id) REFERENCES taxonomies (id) ON DELETE CASCADE
);

CREATE TABLE posts (
	id SERIAL NOT NULL, 
	post_type_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	slug VARCHAR(200) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	excerpt TEXT DEFAULT '' NOT NULL, 
	blocks JSONB DEFAULT '[]' NOT NULL, 
	meta JSONB DEFAULT '{}' NOT NULL, 
	seo JSONB DEFAULT '{}' NOT NULL, 
	status VARCHAR(20) DEFAULT 'draft' NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	featured_media_id INTEGER, 
	author_id UUID, 
	menu_order INTEGER DEFAULT '0' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (post_type_id, slug), 
	FOREIGN KEY(post_type_id) REFERENCES post_types (id), 
	FOREIGN KEY(parent_id) REFERENCES posts (id) ON DELETE SET NULL, 
	FOREIGN KEY(featured_media_id) REFERENCES media (id) ON DELETE SET NULL, 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_posts_type_status_published ON posts (post_type_id, status, published_at);

CREATE TABLE leads (
	id SERIAL NOT NULL, 
	kind VARCHAR(20) DEFAULT 'contact' NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	email VARCHAR(300) NOT NULL, 
	phone VARCHAR(50) DEFAULT '' NOT NULL, 
	company VARCHAR(200) DEFAULT '' NOT NULL, 
	message TEXT DEFAULT '' NOT NULL, 
	post_id INTEGER, 
	data JSONB DEFAULT '{}' NOT NULL, 
	status VARCHAR(20) DEFAULT 'new' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id) ON DELETE SET NULL
);

CREATE INDEX ix_leads_status_created ON leads (status, created_at);

CREATE TABLE post_terms (
	post_id INTEGER NOT NULL, 
	term_id INTEGER NOT NULL, 
	PRIMARY KEY (post_id, term_id), 
	FOREIGN KEY(post_id) REFERENCES posts (id) ON DELETE CASCADE, 
	FOREIGN KEY(term_id) REFERENCES terms (id) ON DELETE CASCADE
);

CREATE TABLE payments (
	id SERIAL NOT NULL, 
	provider VARCHAR(30) NOT NULL, 
	provider_ref VARCHAR(200), 
	post_id INTEGER, 
	lead_id INTEGER, 
	amount NUMERIC(12, 2) NOT NULL, 
	currency VARCHAR(3) DEFAULT 'INR' NOT NULL, 
	status VARCHAR(20) DEFAULT 'created' NOT NULL, 
	raw JSONB DEFAULT '{}' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id) ON DELETE SET NULL, 
	FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE SET NULL
);

CREATE INDEX ix_payments_provider_ref ON payments (provider, provider_ref);

-- keep updated_at current on UPDATE (moddatetime extension, enabled in 0000_bootstrap)
CREATE TRIGGER users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER post_types_updated_at BEFORE UPDATE ON post_types FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER taxonomies_updated_at BEFORE UPDATE ON taxonomies FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER terms_updated_at BEFORE UPDATE ON terms FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER media_updated_at BEFORE UPDATE ON media FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER posts_updated_at BEFORE UPDATE ON posts FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER menus_updated_at BEFORE UPDATE ON menus FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER redirects_updated_at BEFORE UPDATE ON redirects FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
CREATE TRIGGER payments_updated_at BEFORE UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);
