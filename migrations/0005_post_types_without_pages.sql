-- Some content is data, not a destination.
--
-- A technology partner is a logo on somebody else's page. There is nothing to read on a page of its
-- own, so the type stops having URLs altogether: no detail page, nothing in the sitemap or in
-- llms.txt, and no link on the card that shows the logo. The type's archive and every post_list
-- block carry on working, because neither ever needed a per-post URL.
--
-- The flag is a column rather than a check on the slug in the code: a content type is a row here,
-- so "does this one get pages" is a property of the row like every other.

ALTER TABLE post_types ADD COLUMN IF NOT EXISTS has_pages BOOLEAN NOT NULL DEFAULT true;

UPDATE post_types SET has_pages = false WHERE slug = 'partner';
