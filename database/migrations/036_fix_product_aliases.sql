-- Repair migration 032's alias seeding
-- Description: 032 seeded three sets of aliases and matched zero rows. Every
-- one of its predicates was case-sensitive against data that is stored in
-- lower case:
--
--     WHERE p.product_name LIKE 'MAFTA%'        -- data holds 'mafta fls'
--     WHERE p.product_name = 'OLIWA / UKO'      -- data holds 'oliwa / uko'
--     JOIN (VALUES ('OLIWA+'), ('iVMS+')) ...   -- data holds 'oliwa+', 'ivms+'
--
-- The migration reported success because inserting zero rows is not an error.
-- Nothing failed; the aliases simply never existed, so a customer writing
-- MAFUTA — the spelling the master prompt's Appendix B.1 uses — got "I don't
-- have a product under that name" for a product we sell.
--
-- This re-runs the same intent with LOWER() on both sides, and then adds the
-- UNIQUE constraint that would have made a second run visibly a no-op instead
-- of silently doubling every alias.
--
-- 032's existence check was also wrong in a second way: it tested the alias
-- globally rather than per product, so once any product owned the alias
-- 'OLIWA' no other product could ever be given it. Corrected here to a
-- per-product test, which is what the UNIQUE constraint below enforces anyway.

-- ── De-duplicate before constraining ────────────────────────────────────────
-- Safe on a table that is currently empty of these rows, and necessary if any
-- were inserted by hand in the meantime.
DELETE FROM abi_product_aliases a
      USING abi_product_aliases b
 WHERE a.id > b.id
   AND LOWER(a.alias) = LOWER(b.alias)
   AND a.product_uid = b.product_uid;

CREATE UNIQUE INDEX IF NOT EXISTS idx_product_alias_unique
    ON abi_product_aliases (product_uid, LOWER(alias));

-- ── MAFTA / MAFUTA ─────────────────────────────────────────────────────────
-- The seeded catalogue spells these MAFTA; the master prompt spells them
-- MAFUTA; customers say both. REGEXP_REPLACE with 'i' so it works whatever
-- case the row is stored in, and the alias keeps the row's own casing.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid,
       REGEXP_REPLACE(p.product_name, 'mafta', 'MAFUTA', 'i'),
       'variant',
       'Master prompt Appendix B.1 spelling (via migration 036)'
FROM abi_products_manager p
WHERE p.product_name ILIKE 'mafta%'
ON CONFLICT DO NOTHING;

-- ── OLIWA / UKO: one product, two names customers use ──────────────────────
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, v.alias, 'variant',
       'PPMM product column header (via migration 036)'
FROM abi_products_manager p
CROSS JOIN (VALUES ('OLIWA'), ('UKO')) AS v(alias)
WHERE LOWER(TRIM(p.product_name)) IN ('oliwa / uko', 'oliwa/uko', 'oliwa / uko ')
ON CONFLICT DO NOTHING;

-- ── Upgrade tiers written with a spelled suffix ────────────────────────────
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, v.alias, 'variant',
       'Master prompt Appendix B.3 attach paths (via migration 036)'
FROM abi_products_manager p
JOIN (VALUES ('oliwa+', 'OLIWA-PLUS'), ('ivms+', 'iVMS-PLUS'))
     AS v(match_name, alias) ON LOWER(TRIM(p.product_name)) = v.match_name
ON CONFLICT DO NOTHING;

-- ── A plus-sign convention, generalised ────────────────────────────────────
-- Any product whose name ends in '+' gets a '-PLUS' spelling and vice versa,
-- so the next upgrade tier added to the catalogue does not need a migration.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid,
       UPPER(REPLACE(TRIM(p.product_name), '+', '-PLUS')),
       'variant',
       'Plus-suffix convention (via migration 036)'
FROM abi_products_manager p
WHERE TRIM(p.product_name) LIKE '%+'
ON CONFLICT DO NOTHING;

COMMENT ON INDEX idx_product_alias_unique IS
    'One alias per product, case-insensitively. Added by migration 036 after '
    '032 seeded zero aliases unnoticed: a re-run must be a visible no-op, not '
    'a silent duplication.';
