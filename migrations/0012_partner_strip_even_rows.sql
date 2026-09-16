-- The technology-partner logo strip lays its rows out evenly, on the pages that already exist.

-- Fourteen partners in a strip sized by width came out 8 + 6 at 1440: a full line and a line with
-- two gaps at the end, which reads as a broken wall rather than a designed one. `post_list` gained
-- an "Items per row" control (blocks.py, EDITOR["choices"]["per_row"]), whose "even" setting works
-- the count out from how many posts the block actually returns -- `even_cols()`, 14 -> 7 -- so the
-- rows stay equal as partners are added or removed instead of needing a number kept up to date.
--
-- The seed sets it on both partner sections (cli.py), but `_get_or_create()` ONLY INSERTS, so a
-- database that already has these pages never sees that edit. Hence this file. It is content, not
-- schema: no column changes and nothing needs running afterwards.
--
-- Matched by CONTENT, never by id -- production has its own ids, and this must also leave alone any
-- partner section where somebody has already chosen a number by hand (that is what the
-- `not (data ? 'per_row')` test is for). Safe to run twice: the second run sets the key on nothing,
-- because every block it would touch now has it.
--
-- TOP-LEVEL BLOCKS ONLY, deliberately. A partner list nested inside a Columns section is left as it
-- is, because site.css turns the fixed count back off inside a column anyway (a fixed number of
-- tracks in half the width squashes the logos), so setting the key there would change nothing
-- visible. An editor who wants it can still pick a number from the section's own panel.
--
-- Before this is applied the app is completely happy: `_cols()` reads `data.get("per_row")`, an
-- absent key means "as many as fit the width", and that is exactly the behaviour these pages have
-- today. Applying it is what makes the rows even.

-- ---- the published pages ---------------------------------------------------------------------
update public.posts p
   set blocks = (
        select coalesce(jsonb_agg(
            case when b.val->>'type' = 'post_list'
                  and b.val->'data'->>'post_type' = 'partner'
                  and not (b.val->'data' ? 'per_row')
                 then jsonb_set(b.val, '{data,per_row}', '"even"'::jsonb)
                 else b.val
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(p.blocks) with ordinality b(val, ord))
 where exists (
        select 1
          from jsonb_array_elements(p.blocks) b(val)
         where b.val->>'type' = 'post_list'
           and b.val->'data'->>'post_type' = 'partner'
           and not (b.val->'data' ? 'per_row'));

-- ---- and the same pages mid-edit ---------------------------------------------------------------
-- A working draft holds its own copy of the blocks, and `state` is the stored shared document. Leave
-- `state` behind and the next person to open the page gets the old shape put straight back over this.
update public.post_drafts d
   set blocks = (
        select coalesce(jsonb_agg(
            case when b.val->>'type' = 'post_list'
                  and b.val->'data'->>'post_type' = 'partner'
                  and not (b.val->'data' ? 'per_row')
                 then jsonb_set(b.val, '{data,per_row}', '"even"'::jsonb)
                 else b.val
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(d.blocks) with ordinality b(val, ord)),
       state  = ''
 where exists (
        select 1
          from jsonb_array_elements(d.blocks) b(val)
         where b.val->>'type' = 'post_list'
           and b.val->'data'->>'post_type' = 'partner'
           and not (b.val->'data' ? 'per_row'));
