-- Two sections that were never prose become block types, so two people can edit them at once.

-- Quill drives the shared document (0010 + TECHNICAL 12.3) and refuses any block whose markup it
-- would silently damage. Seven of this site's rich_text blocks are refused and keep the old
-- one-at-a-time editor. Two of them are not prose at all: they are DESIGNED SECTIONS written as HTML
-- strings carrying their own classes -- an eyebrow, a section title, a dashed list and a button on
-- the home page; a term-and-description list on NAS.
--
-- The obvious fix was to teach Quill those classes. Measured against the vendored build in a real
-- browser, it cannot work: Parchment's ClassAttributor matches classes shaped `name-value` (which is
-- how ql-align-center works) and every class here is a bare boolean, so all seven probes lost theirs.
-- Surviving would need a custom Blot and a clipboard matcher per class. site.css has carried the
-- answer in a comment since the design landed -- "a rich_text block can carry a whole section" -- and
-- the answer is that it should not have to.
--
-- So `points` and `definitions` are real block types now, and this file moves the two pages into
-- them. Every field becomes a field an editor sees, and the shared document gives each one
-- word-by-word co-editing for free. The rendered HTML is unchanged -- site.css names the new blocks
-- in the same rules -- so both pages look exactly as they did.
--
-- THREE THINGS HAPPEN HERE AND THE CHANGE DOES NOT STICK WITHOUT ALL THREE:
--   1. posts.blocks, the published content.
--   2. post_drafts.blocks AND post_drafts.state. The state is a CRDT document whose sections carry
--      the ids of the OLD shape, and initShared() loads it IN PREFERENCE to blocks -- so a stale
--      draft puts the old section straight back on the next open. Clearing it costs nothing: the
--      draft's blocks are rewritten in the same transaction and the document re-seeds from them.
--   3. data._rich is stripped from every rich_text block. That key is the Quill gate's verdict,
--      stored rather than recomputed because a per-peer verdict splits the document. mountQuill()
--      READS it and never recalculates, so a change to what the gate accepts is invisible to any
--      block already carrying one. Free today -- nothing on this database carries a verdict yet --
--      and not free next time. Every future change to quillKeeps() owes the same line.
--
-- Matched by CONTENT, never by id: production has its own ids, and a page nobody has edited still
-- carries the marker. A database where somebody has already rewritten these sections by hand matches
-- nothing and is left alone, which is the right answer -- their words are not ours to replace.
-- Safe to run twice: the second run finds no marker. Nothing to run later.

do $$
declare
    tgt     record;
    points  jsonb := $json$
    {
      "type": "points",
      "data": {
        "eyebrow": "Built on ZFS",
        "heading": "The file system trusted by Fortune 500 companies, universities and data centres",
        "subheading": "ZFS never compromises on data safety. Every IOPStor appliance inherits it: end-to-end checksums, self-healing pools, and snapshots that recover deleted or corrupt data and protect against ransomware.",
        "items": [
          {
            "text": "Unlimited snapshots and clones: go back to yesterday, last week or last month"
          },
          {
            "text": "RAID-Z: instantaneous build, no write hole, multiple-disk failure tolerance"
          },
          {
            "text": "RAM / SSD / NVMe read-write cache, compression and de-duplication"
          },
          {
            "text": "Hardware agnostic: replace any component from any vendor"
          }
        ],
        "button_label": "All ZFS features",
        "button_url": "/services/storage/nas"
      }
    }
$json$::jsonb;
    defs    jsonb := $json$
    {
      "type": "definitions",
      "data": {
        "heading": "ZFS features, in plain terms",
        "rows": [
          {
            "k": "Zettabyte File System",
            "v": "A file system and logical volume manager with features found in no other. Robust, scalable and easy to administer."
          },
          {
            "k": "128-bit file system",
            "v": "Sixteen billion billion times the capacity of a 64-bit file system."
          },
          {
            "k": "Read/write cache on RAM, SSD or NVMe",
            "v": "Frequent reads are served from cache; writes land in cache first, so there is no write latency."
          },
          {
            "k": "Snapshots and clones",
            "v": "Recover deleted or corrupted data, and stay protected against ransomware."
          },
          {
            "k": "Hot data movement",
            "v": "Move older, unused data off the SSD pool and into the archival pool."
          },
          {
            "k": "End-to-end data integrity",
            "v": "Every block is checksummed."
          },
          {
            "k": "RaidZ",
            "v": "No write hole, instant array build, and a drive failure never interrupts work."
          },
          {
            "k": "Hardware agnostic",
            "v": "No lock-in. Replace any component with any vendor's."
          }
        ]
      }
    }
$json$::jsonb;
begin
    -- ---- the published pages -----------------------------------------------------------------
    for tgt in
        select p.id,
               array[(b.ord - 1)::text, 'data', 'cols', (c.ord - 1)::text, (n.ord - 1)::text] as at,
               (n.val->'data'->>'html' like '%<dl class="zfs">%') as is_defs
        from public.posts p,
             lateral jsonb_array_elements(p.blocks)              with ordinality b(val, ord),
             lateral jsonb_array_elements(b.val->'data'->'cols') with ordinality c(val, ord),
             lateral jsonb_array_elements(c.val)                 with ordinality n(val, ord)
        where b.val->>'type' = 'columns'
          and n.val->>'type' = 'rich_text'
          and (n.val->'data'->>'html' like '%<ul class="dash">%'
            or n.val->'data'->>'html' like '%<dl class="zfs">%')
    loop
        update public.posts
           set blocks = jsonb_set(blocks, tgt.at, case when tgt.is_defs then defs else points end)
         where id = tgt.id;
        raise notice 'posts %: % at %', tgt.id, case when tgt.is_defs then 'definitions' else 'points' end, tgt.at;
    end loop;

    -- ---- and the same pages mid-edit ---------------------------------------------------------
    for tgt in
        select d.post_id as id,
               array[(b.ord - 1)::text, 'data', 'cols', (c.ord - 1)::text, (n.ord - 1)::text] as at,
               (n.val->'data'->>'html' like '%<dl class="zfs">%') as is_defs
        from public.post_drafts d,
             lateral jsonb_array_elements(d.blocks)              with ordinality b(val, ord),
             lateral jsonb_array_elements(b.val->'data'->'cols') with ordinality c(val, ord),
             lateral jsonb_array_elements(c.val)                 with ordinality n(val, ord)
        where b.val->>'type' = 'columns'
          and n.val->>'type' = 'rich_text'
          and (n.val->'data'->>'html' like '%<ul class="dash">%'
            or n.val->'data'->>'html' like '%<dl class="zfs">%')
    loop
        update public.post_drafts
           set blocks = jsonb_set(blocks, tgt.at, case when tgt.is_defs then defs else points end),
               state  = ''
         where post_id = tgt.id;
        raise notice 'post_drafts %: % at %', tgt.id, case when tgt.is_defs then 'definitions' else 'points' end, tgt.at;
    end loop;
end $$;

-- ---- the stored gate verdict -----------------------------------------------------------------
-- Two levels, not recursion, because two levels is all the data model has: validate_blocks() refuses
-- a columns inside a column, so a block is either top-level or one level down inside `cols` and there
-- is no third case. Written inline rather than as a function so it needs no DDL and nothing to drop.
update public.posts p
   set blocks = (
        select coalesce(jsonb_agg(
            case
                when b.val->'data' ? 'cols' then jsonb_set(b.val #- '{data,_rich}', '{data,cols}', (
                    select coalesce(jsonb_agg(
                        (select coalesce(jsonb_agg(n.val #- '{data,_rich}' order by n.ord), '[]'::jsonb)
                         from jsonb_array_elements(c.val) with ordinality n(val, ord))
                        order by c.ord), '[]'::jsonb)
                    from jsonb_array_elements(b.val->'data'->'cols') with ordinality c(val, ord)))
                else b.val #- '{data,_rich}'
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(p.blocks) with ordinality b(val, ord))
 where p.blocks::text like '%"_rich"%';

update public.post_drafts d
   set blocks = (
        select coalesce(jsonb_agg(
            case
                when b.val->'data' ? 'cols' then jsonb_set(b.val #- '{data,_rich}', '{data,cols}', (
                    select coalesce(jsonb_agg(
                        (select coalesce(jsonb_agg(n.val #- '{data,_rich}' order by n.ord), '[]'::jsonb)
                         from jsonb_array_elements(c.val) with ordinality n(val, ord))
                        order by c.ord), '[]'::jsonb)
                    from jsonb_array_elements(b.val->'data'->'cols') with ordinality c(val, ord)))
                else b.val #- '{data,_rich}'
            end order by b.ord), '[]'::jsonb)
        from jsonb_array_elements(d.blocks) with ordinality b(val, ord))
 where d.blocks::text like '%"_rich"%';
