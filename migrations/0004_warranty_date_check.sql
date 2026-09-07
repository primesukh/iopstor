-- 0004_warranty_date_check: a warranty cannot expire before the unit was bought.
--
-- NOT VALID on purpose: the constraint is enforced on every INSERT and UPDATE from now on, but the
-- rows already in the table are not scanned, so applying this can never fail on existing data (there
-- is at least one record with the dates the wrong way round — that is what prompted the check). Fix
-- those rows through /admin/warranty, then promote it to a fully checked constraint with:
--     ALTER TABLE warranties VALIDATE CONSTRAINT warranties_expiry_after_purchase;
--
-- purchase_date is optional, hence the IS NULL arm: without it the row is simply unconstrained.
ALTER TABLE warranties
	ADD CONSTRAINT warranties_expiry_after_purchase
	CHECK (purchase_date IS NULL OR expiry_date >= purchase_date) NOT VALID;
