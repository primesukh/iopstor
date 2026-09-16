-- The header menu stops linking to Technology Partners.

-- The client asked for the link to come out of the top navigation. The page itself stays exactly
-- where it is: /technology-partners still resolves, still has its .md twin, is still in the sitemap
-- and is still linked from the footer. Only the header entry goes.
--
-- Menus are editor content -- Menus in the admin writes this same row -- so on dev this file is
-- interchangeable with deleting the item on that screen. It exists because `_get_or_create()` ONLY
-- INSERTS, so the matching seed edit (cli.py) never reaches a database that already has a header
-- row, and because production's menu is a separate row nobody would otherwise remember to fix.
--
-- Matched by URL, never by position: the live header has been rearranged by hand since it was seeded
-- (Technology Partners sits at the top level here, while the seed nests it under Company), so an
-- index would remove the wrong item. Both shapes are handled -- the top-level entry and a child of
-- any dropdown -- and everything else in the row is rebuilt in its existing order.
--
-- Safe to run twice: the second run matches nothing, because the WHERE finds no such URL left.
-- Nothing to run afterwards. No column changes.
--
-- ONE THING TO EXPECT. get_menu() is process-cached (db._proc_cached), and the epoch that normally
-- invalidates it is bumped by db.update() -- which a hand-applied .sql file does not go through. The
-- cache carries CACHE_TTL = 30s ("the ceiling on staleness if a bump is ever missed"), so every
-- worker picks the new header up within half a minute on its own; a restart is not needed. On the
-- public site Cloudflare's s-maxage=60 can hold a rendered page for up to another minute.

update public.menus
   set items = (
        select coalesce(jsonb_agg(
            case when i.val ? 'children'
                 then jsonb_set(i.val, '{children}', (
                        select coalesce(jsonb_agg(c.val order by c.ord), '[]'::jsonb)
                          from jsonb_array_elements(i.val->'children') with ordinality c(val, ord)
                         where c.val->>'url' is distinct from '/technology-partners'))
                 else i.val
            end order by i.ord), '[]'::jsonb)
          from jsonb_array_elements(items) with ordinality i(val, ord)
         where i.val->>'url' is distinct from '/technology-partners')
 where slug = 'header'
   and (exists (select 1
                  from jsonb_array_elements(items) i(val)
                 where i.val->>'url' = '/technology-partners')
     or exists (select 1
                  from jsonb_array_elements(items) i(val),
                       lateral jsonb_array_elements(coalesce(i.val->'children', '[]'::jsonb)) c(val)
                 where c.val->>'url' = '/technology-partners'));
