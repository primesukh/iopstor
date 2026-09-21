-- The RSS feed is a feed of the site, not of the blog.
--
-- /feed.xml carried one post type, found in code by slug ("post"). The site publishes case studies,
-- events and datasheets far more often than blog posts -- there is exactly one blog post -- so an
-- editor who published all week watched a feed that never moved and reported it as broken. It was
-- not: it was a blog feed on a site whose news is not blog posts.
--
-- Which types the feed carries becomes a property of the row, like in_sitemap beside it, rather than
-- a slug spelled in public.py. Services, partners and testimonials stay out: they are the catalogue,
-- and they change without anything having happened.
--
-- The default is false, so a type somebody adds later is not silently broadcast; the UPDATE is what
-- opts the four editorial types in. A re-seed could not do this -- cli.py's _get_or_create() only
-- inserts, so it never touches a post_types row that already exists.
--
-- Safe to run twice. Nothing to run later.

ALTER TABLE post_types ADD COLUMN IF NOT EXISTS in_feed BOOLEAN NOT NULL DEFAULT false;

UPDATE post_types SET in_feed = true WHERE slug IN ('post', 'case_study', 'event', 'datasheet');
