-- Customer quotes stop being page furniture and become content.
--
-- "What our clients say" on the home page was two `testimonial` blocks inside a `columns` block --
-- words typed into the page itself. Adding a third meant opening the page editor and hand-building
-- a column, which is why there have only ever been two. A testimonial is the same shape as a
-- technology partner: something said by somebody else, shown on our pages, with no page of its own.
-- So it gets the same treatment partners got in 0005 -- a content type with has_pages=false -- and
-- the home section becomes a `post_list` that picks up whatever is in it.
--
-- Where each part of a quote lives, and why there is no `quote` field:
--   title             the person's name
--   excerpt           what they said  (post_form.html relabels the Summary box for this type)
--   featured_media_id their photo     (the card's picture slot, drawn as a round avatar)
--   meta.role         job title       \
--   meta.company      company          > the three optional extras, in field_schema
--   meta.rating       stars out of 5  /
-- Only the name is required. Every other field left blank simply does not render.
--
-- After applying this, RESTART THE APP. `flask migrate` calls the apply_migration RPC rather than
-- db.insert()/update(), so nothing bumps content_epoch(): a server that is already running keeps
-- serving its cached post_types() and its cached home page until it restarts or somebody saves
-- something in the admin. Nothing is wrong; it is just showing you the old copy.

-- ---- the content type --------------------------------------------------------------------------
-- jsonld_type is null on purpose. A has_pages=false type has no page for JSON-LD to sit on, so the
-- column would never be read; `partner` carries 'Organization' only because it predates 0005.
insert into public.post_types (slug, name, url_prefix, hierarchical, jsonld_type, taxonomies, field_schema, has_pages)
values ('testimonial', 'Testimonials', 'testimonials', false, null, '[]'::jsonb,
        '[{"key": "role",    "label": "Job title",      "type": "text",   "required": false},
          {"key": "company", "label": "Company",        "type": "text",   "required": false},
          {"key": "rating",  "label": "Stars out of 5", "type": "number", "required": false}]'::jsonb,
        false)
on conflict (slug) do nothing;

-- ---- the two quotes that were in the page ------------------------------------------------------
-- The same words the seed has always used (cli.py, TESTIMONIALS), so a database seeded from scratch
-- and one migrated up from here end up with the same two entries. `where not exists` on the slug
-- rather than `on conflict`: the unique key is (post_type_id, slug) and the id is only known here
-- as a sub-select, which reads worse than the guard does.
insert into public.posts (post_type_id, slug, title, excerpt, meta, status, published_at)
select t.id, v.slug, v.title, v.excerpt, v.meta, 'published', now()
  from public.post_types t
  join (values
        ('sarah-m', 'Sarah M.', 'I sleep better knowing my family photos and business files are in a ZFS NAS.',
         '{"role": "Photographer"}'::jsonb),
        ('mark-d',  'Mark D.',  'Set it up once. Haven''t had to touch it in 2 years.',
         '{"role": "Small Business Owner"}'::jsonb)
       ) as v(slug, title, excerpt, meta) on true
 where t.slug = 'testimonial'
   and not exists (select 1 from public.posts p where p.post_type_id = t.id and p.slug = v.slug);

-- ---- and the home page's section ---------------------------------------------------------------
-- Matched by CONTENT, never by index or id: production has its own ids, and the block's position in
-- the array is not a promise. Safe to run twice -- the second run finds no `columns` block with that
-- heading, because the first one replaced it.
--
-- The eyebrow keeps the old section's words so the page still reads the same from a distance; the
-- heading is the new line, which is what a section with its own content type deserves.
update public.posts p
   set blocks = (
        select coalesce(jsonb_agg(
            case when b.val->>'type' = 'columns'
                  and b.val->'data'->>'heading' = 'What our clients say'
                 then '{"type": "post_list", "data": {"post_type": "testimonial", "limit": 12,
                        "eyebrow": "What our clients say",
                        "heading": "Trusted by the teams who run on it"}}'::jsonb
                 else b.val
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(p.blocks) with ordinality b(val, ord))
 where exists (
        select 1
          from jsonb_array_elements(p.blocks) b(val)
         where b.val->>'type' = 'columns'
           and b.val->'data'->>'heading' = 'What our clients say');

-- The same pages mid-edit. A working draft holds its own copy of the blocks, and `state` is the
-- stored shared document: leave `state` behind and the next person to open the page puts the old
-- two-column section straight back over this.
update public.post_drafts d
   set blocks = (
        select coalesce(jsonb_agg(
            case when b.val->>'type' = 'columns'
                  and b.val->'data'->>'heading' = 'What our clients say'
                 then '{"type": "post_list", "data": {"post_type": "testimonial", "limit": 12,
                        "eyebrow": "What our clients say",
                        "heading": "Trusted by the teams who run on it"}}'::jsonb
                 else b.val
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(d.blocks) with ordinality b(val, ord)),
       state  = ''
 where exists (
        select 1
          from jsonb_array_elements(d.blocks) b(val)
         where b.val->>'type' = 'columns'
           and b.val->'data'->>'heading' = 'What our clients say');
