-- 0003_warranty: warranty records, looked up by serial number from the public Warranty check section.

CREATE TABLE warranties (
	id SERIAL NOT NULL, 
	serial VARCHAR(100) NOT NULL, 
	-- the lookup key: generated, so a customer typing "iop-2024-a7x91" finds "IOP-2024-A7X91", and two
	-- records can never claim the same serial in different cases. Serials may contain % and _, which
	-- are wildcards to PostgREST's ilike, so the public lookup is an exact match on this column.
	serial_key VARCHAR(100) GENERATED ALWAYS AS (upper(btrim(serial))) STORED, 
	customer_name VARCHAR(200) NOT NULL, 
	email VARCHAR(300) DEFAULT '' NOT NULL, 
	purchase_date DATE, 
	expiry_date DATE NOT NULL, 
	amc BOOLEAN DEFAULT false NOT NULL, 
	remarks TEXT DEFAULT '' NOT NULL, 
	remarks_public BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (serial_key)
);

-- no status column: "in warranty" is expiry_date vs today, worked out at render time so it is never stale
CREATE INDEX ix_warranties_expiry ON warranties (expiry_date);

CREATE TRIGGER warranties_updated_at BEFORE UPDATE ON warranties FOR EACH ROW EXECUTE FUNCTION extensions.moddatetime(updated_at);

-- as everywhere else: RLS on with no policies, so only the app's service-role key (BYPASSRLS) sees it
ALTER TABLE warranties ENABLE ROW LEVEL SECURITY;
