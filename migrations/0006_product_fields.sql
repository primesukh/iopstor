-- Products: rupees only, and specifications an editor can actually type.
--
-- Two problems, both in the product type's field_schema, and a re-seed cannot fix either of them:
-- _get_or_create() in cli.py only ever INSERTs, so POST_TYPES never updates a row that exists.
--
-- 1. "currency" was a free-text box on every product. Prices are rupees; the choice should not
--    exist. (The Currency box under Settings -> Payments went too. Nothing had ever read it.)
--
-- 2. "specs" was type "json" -- a raw JSON textarea. A mistyped brace saved as a plain string and
--    the specification table then vanished from the live page with no error. And because the value
--    was a JSON *object*, jsonb sorted its keys: the table read Appliance workload, CPU, Memory,
--    Network, Storage, in that order, whatever order it had been written in. It is now type "kv",
--    an ordered array of {k, v} rows edited as label/value boxes with add, remove and reorder.
--
-- The conversion below can only produce alphabetical order, because the order of the object it is
-- reading was thrown away when it was stored. Reorder the rows in /admin once, with the arrows.

UPDATE post_types SET field_schema = '[
  {"key": "price",               "label": "Price",          "type": "number", "required": false},
  {"key": "sku",                 "label": "SKU",            "type": "text",   "required": false},
  {"key": "specs",               "label": "Specifications", "type": "kv",     "required": false},
  {"key": "datasheet_media_id",  "label": "Datasheet PDF",  "type": "media",  "required": false}
]'::jsonb
WHERE slug = 'product';

-- object -> ordered rows, for the products that have specs
UPDATE posts p
SET meta = jsonb_set(p.meta, '{specs}', (
        SELECT coalesce(jsonb_agg(jsonb_build_object('k', key, 'v', value) ORDER BY key), '[]'::jsonb)
        FROM jsonb_each_text(p.meta -> 'specs')))
FROM post_types t
WHERE p.post_type_id = t.id
  AND t.slug = 'product'
  AND jsonb_typeof(p.meta -> 'specs') = 'object';

-- and the currency that is no longer a per-product choice
UPDATE posts p
SET meta = p.meta - 'currency'
FROM post_types t
WHERE p.post_type_id = t.id
  AND t.slug = 'product'
  AND p.meta ? 'currency';
