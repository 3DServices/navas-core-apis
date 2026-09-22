-- An alias must be allowed to name more than one product row
-- Description: migration 039 seeded three aliases where it should have seeded
-- four, and said nothing, because abi_product_aliases.alias carries a GLOBAL
-- unique constraint from migration 032. The 'oliwa' row claimed OLIWA, UKO and
-- 'OLIWA / UKO'; every insert for the 'uko' row then violated that constraint
-- and ON CONFLICT DO NOTHING swallowed it. The visible symptom was 'uko'
-- staying "not in the official register" with no error anywhere.
--
-- A global unique on alias encodes "one name belongs to exactly one product
-- row", which is false here: OLIWA and UKO are one registered product sold as
-- two country rows, and both must answer to the register's name
-- 'OLIWA / UKO'. Migration 036 already added the constraint that is actually
-- wanted — UNIQUE (product_uid, LOWER(alias)) — so the global one is dropped.
--
-- Found by inspection rather than by name, because 032 may have written it as
-- a column constraint (abi_product_aliases_alias_key) or as a standalone
-- index, and the name differs between the two.
--
-- 039 also assigned BOTH brand names to BOTH rows, which was wrong in a
-- quieter way: it would make a lookup for OLIWA return the Kenyan row too.
-- Each row should answer to its own country's brand and to the shared register
-- name, nothing more. Those cross-country rows are removed below.

-- ── Drop any unique that covers the alias column alone ──────────────────────
DO $$
DECLARE
    target   record;
    conname  text;
    dropped  integer := 0;
BEGIN
    FOR target IN
        SELECT i.indexrelid,
               i.indexrelid::regclass::text AS index_name
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
        WHERE i.indrelid = 'abi_product_aliases'::regclass
          AND i.indisunique
          AND i.indnatts = 1          -- one column, so not the 036 composite
          AND a.attname = 'alias'
    LOOP
        SELECT c.conname INTO conname
        FROM pg_constraint c
        WHERE c.conindid = target.indexrelid;

        IF conname IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE abi_product_aliases DROP CONSTRAINT %I', conname);
            RAISE NOTICE 'dropped unique constraint % on alias', conname;
        ELSE
            EXECUTE format('DROP INDEX %s', target.index_name);
            RAISE NOTICE 'dropped unique index % on alias', target.index_name;
        END IF;
        dropped := dropped + 1;
    END LOOP;

    IF dropped = 0 THEN
        RAISE NOTICE 'No global unique on alias found. If uko still fails to '
                     'match the register, the cause is something else — check '
                     'vw_navas_product_slugs for the uko row.';
    END IF;
END
$$;

-- The constraint that should be there. Re-asserted in case 036 has not run.
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_alias_unique
    ON abi_product_aliases (product_uid, LOWER(alias));

-- ── Undo 039's cross-country brand assignments ─────────────────────────────
-- A Ugandan product row should not answer to the Kenyan brand name and the
-- other way round. The register name, which both rows need, is left alone.
DELETE FROM abi_product_aliases a
 USING abi_products_manager p
 WHERE p.product_uid = a.product_uid
   AND a.alias_kind = 'country_brand'
   AND COALESCE(a.country_scope, '') <> ''
   AND COALESCE(p.country_scope, '') <> ''
   AND a.country_scope <> p.country_scope;

-- ── Seed again, now that the constraint allows it ──────────────────────────
-- Each row gets its own country's brand name.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, country_scope,
                                 source_ref)
SELECT p.product_uid, v.alias, 'country_brand', v.country,
       'Business statement 2026-09-19: OLIWA is Uganda, UKO is Kenya '
       '(via migration 040)'
FROM abi_products_manager p
JOIN (VALUES ('oliwa', 'OLIWA', 'Uganda'),
             ('uko',   'UKO',   'Kenya'))
     AS v(match_slug, alias, country) ON navas_slug(p.product_name) = v.match_slug
ON CONFLICT DO NOTHING;

-- And both answer to the name the register uses, which is what lets either row
-- resolve to 3D-PRD-005.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, 'OLIWA / UKO', 'register_name',
       'Official_Product_IDs v26 3D-PRD-005 (via migration 040)'
FROM abi_products_manager p
WHERE navas_slug(p.product_name) IN ('oliwa', 'uko')
ON CONFLICT DO NOTHING;

COMMENT ON TABLE abi_product_aliases IS
    'Other names for an approved product: spelling variants, legacy names, '
    'country brands. An alias may point at more than one product row — OLIWA '
    'and UKO are one registered product in two markets — so uniqueness is per '
    'product, not global.';
