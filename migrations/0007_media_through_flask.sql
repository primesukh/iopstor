-- Pictures and PDFs are served by this app, not by the Supabase gateway.
--
-- Supabase is going LAN-only: only Flask is reachable from the internet, so a browser can no longer
-- fetch an object straight out of the Storage bucket. Every media address becomes /media/<bucket key>,
-- which public.media_file() answers by fetching the bytes server-side with the service-role key.
--
-- The old absolute URL was frozen into a row at upload time, in four places, so this is a data fix
-- rather than a schema change. The regex matches any host, so it is the same file on every instance.
-- Every statement is guarded: running it twice changes nothing.
--
-- Until this runs, nothing breaks — new uploads already get the new path, old rows keep the address
-- they have. Apply it before taking Supabase off the public network.

-- 1. The media library itself: url is now the path this site serves the object at.
UPDATE media
   SET url = '/media/' || key
 WHERE url <> '/media/' || key;

-- 2. settings.logo_url and settings.default_og_image are copies of a media.url.
UPDATE settings
   SET value = regexp_replace(value::text, 'https?://[^/]+/storage/v1/object/public/[^/]+/', '/media/', 'g')::jsonb
 WHERE value::text ~ '/storage/v1/object/public/';

-- 3. Pictures the editor dropped inside a rich_text block are raw <img src> in the stored HTML —
--    no media id to look up, only the literal address.
UPDATE posts
   SET blocks = regexp_replace(blocks::text, 'https?://[^/]+/storage/v1/object/public/[^/]+/', '/media/', 'g')::jsonb
 WHERE blocks::text ~ '/storage/v1/object/public/';

-- 4. A per-post og_image is typed in as a full URL.
UPDATE posts
   SET seo = regexp_replace(seo::text, 'https?://[^/]+/storage/v1/object/public/[^/]+/', '/media/', 'g')::jsonb
 WHERE seo::text ~ '/storage/v1/object/public/';
