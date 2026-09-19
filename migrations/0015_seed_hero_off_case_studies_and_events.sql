-- A case study shows no picture, because it was seeded with a hero that holds nothing.

-- post.html's page head is the design's detail header: breadcrumb, eyebrow, title, lead, the term
-- chips, and the featured picture. It renders only while the first block is neither a hero nor a
-- columns, because a hero draws its own <h1> and carries its own picture, and two page heads on
-- one page is neither. Seeded case studies and events got `[{"type":"hero","data":{"heading":
-- <title>}}]` from _post()'s old default, so the gate closed on every one of them and swallowed
-- the whole head -- the excerpt, the Industry/Solution chips and the "Main picture" an editor had
-- carefully chosen, none of which the empty hero replaced with anything.
--
-- This is the second time. cli.py used to carry the same note above the products, which were
-- seeded without a hero for exactly this reason after the appliance photo never appeared. The
-- default is now gone from _post() itself, so no type can inherit it again; these rows predate
-- that and are what this file fixes.

-- ONLY THE BARE SHAPE. A hero that somebody has since filled in -- a subheading, a picture, a
-- call to action -- holds content that nothing else on the page would show, so it is left exactly
-- where it is. The match is therefore: one block, of type hero, whose data has no key but
-- `heading`. The heading itself is not compared to the title: a renamed page is still a page
-- whose hero says only what the <h1> is about to say again.
--
-- Every test below is written so that no value can make it raise rather than simply not match.
-- jsonb_array_length() would have been the obvious way to say "one block" and it throws on a
-- blocks that is not an array; Postgres is free to evaluate a WHERE in any order, so a guard in
-- front of it does not save you. `blocks->1 IS NULL` says the same thing and returns NULL on
-- anything that is not an array. Likewise the data test is an equality rather than `- 'heading'`,
-- which throws on a scalar. This file runs against rows nobody here can see.
--
-- Rows this skips keep their hero and keep hiding their picture. To see which, before applying:
--
--   SELECT t.slug AS type, p.slug, p.title, p.blocks->0->'data'->>'heading' AS hero_heading,
--          jsonb_array_length(p.blocks) AS n_blocks, p.featured_media_id,
--          (d.post_id IS NOT NULL) AS has_unsaved_draft
--     FROM posts p
--     JOIN post_types t ON t.id = p.post_type_id
--     LEFT JOIN post_drafts d ON d.post_id = p.id
--    WHERE t.slug IN ('case_study', 'event')
--    ORDER BY t.slug, p.menu_order;

-- ONE STATEMENT, NOT TWO. The working draft has to go with the blocks, or the editor reopens the
-- version that still holds the hero and saves it straight back over this -- the same reason
-- `flask seed --reset-content` calls db.clear_draft() after it rewrites a page. The DELETE reads
-- the UPDATE's own RETURNING rather than re-matching on `blocks = '[]'`, so it can only touch the
-- rows this file actually changed: a page that was already empty and has a draft with real work
-- in it is none of its business.
WITH cleared AS (
    UPDATE posts p SET blocks = '[]'::jsonb
      FROM post_types t
     WHERE p.post_type_id = t.id
       AND t.slug IN ('case_study', 'event')
       AND p.blocks->1 IS NULL
       AND p.blocks->0->>'type' = 'hero'
       AND p.blocks->0->'data' = jsonb_build_object('heading', p.blocks->0->'data'->>'heading')
 RETURNING p.id
)
DELETE FROM post_drafts WHERE post_id IN (SELECT id FROM cleared);

-- AFTER APPLYING THIS, RESTART THE APP (0014 says the same, for the same reason). `flask migrate`
-- calls the apply_migration RPC rather than db.insert()/update(), so nothing bumps
-- content_epoch(): a server that is already running keeps serving the cached hero-led page until
-- it restarts or somebody saves in /admin. On a Dokploy deploy this is free -- the `migrate`
-- service gates `app`, which then starts fresh -- and it only bites when this is pasted into
-- Studio against a server that is already up.
--
-- Safe to run twice: the second run matches nothing, because the first left `blocks = '[]'`.
