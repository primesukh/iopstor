-- The About Us founder pair becomes a section an editor can edit, and put on any page.

-- The two chips -- hatched circle, name, job title -- were never prose. They were a
-- `<div class="founders">` written into the end of a rich_text's HTML by the seed, and the classes
-- are bare booleans, which is exactly the markup Quill drops (TECHNICAL 12.3, and 0011's header for
-- the measurement). So that block is one of the editor's named refusals: a single contenteditable
-- blob with no Name field, no Job title field, no way to add a third person, no way to attach a
-- photograph, and last-writer-wins between two editors. It could not be put on a second page either,
-- because it is a string inside one page rather than something the section picker offers.
--
-- 2026-09-15 decided these chips would stay as they were (requirements.md). Using them proved that
-- wrong, so this file does for them what 0011 did for `points` and `definitions`: `people` is a real
-- block type now, each person is three fields, and site.css names the new block in the founders'
-- own rules so the page renders as it always did.
--
-- THIS IS A SPLIT, NOT 0011's ONE-FOR-ONE REPLACE. The chips sit at the END of a rich_text that also
-- holds "Who we are" and two paragraphs, so per match:
--   1. that block's `html` loses the founders div and keeps the prose,
--   2. a `people` block is inserted immediately AFTER it, in the same column,
--   3. the people come from the markup being removed, not from a literal in this file, so a database
--      where somebody has already retyped a name keeps their words. Markup we cannot read leaves the
--      page untouched, which is the right answer: their words are not ours to replace.
--   4. post_drafts gets the same rewrite AND `state = ''`. The state is a CRDT document holding the
--      old shape, and initShared() loads it IN PREFERENCE to blocks, so a stale draft puts the old
--      section straight back on the next open. Clearing it costs nothing: the draft's blocks are
--      rewritten in the same transaction and the document re-seeds from them.
--   5. `data._rich` is dropped FROM THE REWRITTEN BLOCK ONLY. That key is the Quill gate's verdict,
--      stored rather than recomputed because a per-peer verdict splits the document -- and once the
--      div is gone the block is `<h2>` + `<p>`, which Quill holds happily. mountQuill() READS the
--      verdict and never recalculates, so leaving a stored `false` there would keep the page on the
--      old one-at-a-time editor for ever. Unlike 0011 this does NOT sweep every block on the
--      database: 0011 could, because nothing carried a verdict yet; measured today the drafts do
--      (About Us's own carries `false`), and throwing away a neighbour's correct verdict only costs
--      a repaint nobody asked for.
--
-- Matched by CONTENT, never by id: production has its own ids. Every match is built so that no value
-- can make it RAISE rather than simply not match -- a `blocks` that is not an array reads as empty
-- instead of throwing, which a WHERE clause could not have saved us from.
-- Dry-run in Python against the dev database, read-only: exactly one match in `posts` (id 33) and one
-- in `post_drafts` (post 33), both recovering Gulbirr Bhatia and Noshir Dalal with their titles.
-- Safe to run twice: the second run finds no founders div. Nothing to run later.
-- Applying this does NOT bump the cache epoch (flask migrate goes through the apply_migration RPC, not
-- db.update()), so a server already running keeps serving its cached rendering of About Us until it
-- restarts or somebody saves anything in the admin.

do $$
declare
    tgt   record;
    chips text;
    who   jsonb;
begin
    -- ---- the published pages -----------------------------------------------------------------
    -- Descending, because jsonb_insert shifts every index after it: two founder grids in one column
    -- would otherwise put the second block one slot out.
    for tgt in
        select p.id,
               array[(b.ord - 1)::text, 'data', 'cols', (c.ord - 1)::text, (n.ord - 1)::text] as at,
               n.val->'data'->>'html' as html
        from public.posts p,
             lateral jsonb_array_elements(case when jsonb_typeof(p.blocks) = 'array'
                                               then p.blocks else '[]'::jsonb end)   with ordinality b(val, ord),
             lateral jsonb_array_elements(case when jsonb_typeof(b.val->'data'->'cols') = 'array'
                                               then b.val->'data'->'cols' else '[]'::jsonb end) with ordinality c(val, ord),
             lateral jsonb_array_elements(case when jsonb_typeof(c.val) = 'array'
                                               then c.val else '[]'::jsonb end)      with ordinality n(val, ord)
        where b.val->>'type' = 'columns'
          and n.val->>'type' = 'rich_text'
          and n.val->'data'->>'html' like '%<div class="founders">%'
        order by b.ord desc, c.ord desc, n.ord desc
    loop
        -- Bounded to the element, never to end-of-string: anything an editor typed BELOW the chips
        -- in that legacy blob is prose, and prose stays.
        chips := substring(tgt.html from '<div class="founders">.*?</div></div>');
        select coalesce(jsonb_agg(jsonb_build_object('name', m[1], 'role', m[2])), '[]'::jsonb)
          into who
          from regexp_matches(chips, '<b>(.*?)</b><i>(.*?)</i>', 'g') m;
        continue when who = '[]'::jsonb;
        update public.posts
           set blocks = jsonb_insert(
                            jsonb_set(blocks #- (tgt.at || array['data', '_rich']),
                                      tgt.at || array['data', 'html'],
                                      to_jsonb(replace(tgt.html, chips, ''))),
                            tgt.at,
                            jsonb_build_object('type', 'people', 'data', jsonb_build_object('items', who)),
                            true)
         where id = tgt.id;
        raise notice 'posts %: % people after %', tgt.id, jsonb_array_length(who), tgt.at;
    end loop;

    -- ---- and the same pages mid-edit ---------------------------------------------------------
    for tgt in
        select d.post_id as id,
               array[(b.ord - 1)::text, 'data', 'cols', (c.ord - 1)::text, (n.ord - 1)::text] as at,
               n.val->'data'->>'html' as html
        from public.post_drafts d,
             lateral jsonb_array_elements(case when jsonb_typeof(d.blocks) = 'array'
                                               then d.blocks else '[]'::jsonb end)   with ordinality b(val, ord),
             lateral jsonb_array_elements(case when jsonb_typeof(b.val->'data'->'cols') = 'array'
                                               then b.val->'data'->'cols' else '[]'::jsonb end) with ordinality c(val, ord),
             lateral jsonb_array_elements(case when jsonb_typeof(c.val) = 'array'
                                               then c.val else '[]'::jsonb end)      with ordinality n(val, ord)
        where b.val->>'type' = 'columns'
          and n.val->>'type' = 'rich_text'
          and n.val->'data'->>'html' like '%<div class="founders">%'
        order by b.ord desc, c.ord desc, n.ord desc
    loop
        chips := substring(tgt.html from '<div class="founders">.*?</div></div>');
        select coalesce(jsonb_agg(jsonb_build_object('name', m[1], 'role', m[2])), '[]'::jsonb)
          into who
          from regexp_matches(chips, '<b>(.*?)</b><i>(.*?)</i>', 'g') m;
        continue when who = '[]'::jsonb;
        update public.post_drafts
           set blocks = jsonb_insert(
                            jsonb_set(blocks #- (tgt.at || array['data', '_rich']),
                                      tgt.at || array['data', 'html'],
                                      to_jsonb(replace(tgt.html, chips, ''))),
                            tgt.at,
                            jsonb_build_object('type', 'people', 'data', jsonb_build_object('items', who)),
                            true),
               state  = ''
         where post_id = tgt.id;
        raise notice 'post_drafts %: % people after %', tgt.id, jsonb_array_length(who), tgt.at;
    end loop;
end $$;
