-- The approved NAVAS catalogue object universe
-- Description: NAVAS_CATALOG_v26.03.30.xlsx, as a table.
--
-- READ THIS BEFORE ASSUMING WHAT IT FIXES. The catalogue is not a product
-- master. It has no product codes, no prices, no SKUs, and it does not say
-- which service type a feature belongs to. It is a selection document: 238
-- approved objects across eight kinds, each with a short description and ten
-- columns of justification for why it made the cut.
--
-- So this migration does NOT repair the 27 products missing 3D-PRD codes, and
-- it does NOT fill in the 43 products with no service type. Nothing in the
-- approved catalogue contains those facts. Claiming otherwise would mean
-- inventing them, which is the failure this whole build exists to prevent.
--
-- What it does give is the thing that was actually missing: a definition of
-- which objects are approved at all. With it, a product lookup can distinguish
--
--     "no such product"                                 (invented)
--     "approved in the catalogue, no product record yet" (a data gap)
--     "a product record that is not in the catalogue"    (ad-hoc, unapproved)
--
-- Those are three different answers to a customer and Waswa currently gives
-- the first one to all three.
--
-- The five SERVICE TYPES rows are also the canonical vocabulary: AI & Video,
-- Fuel Telematics, Vehicle Telematics, Goods & IoT, Personnel Tracing. Any
-- other value in abi_products_manager.service_type is off-vocabulary, and
-- vw_navas_catalog_reconciliation below says so rather than guessing a mapping.

CREATE TABLE IF NOT EXISTS abi_catalog_objects (
    id              SERIAL PRIMARY KEY,
    catalog_version VARCHAR(40)  NOT NULL,
    object_kind     VARCHAR(32)  NOT NULL,
    object_name     VARCHAR(300) NOT NULL,
    object_slug     VARCHAR(300) NOT NULL,
    short_name      VARCHAR(200),
    description     TEXT,
    rationale       TEXT,                    -- the ten "why it made the cut" columns

    -- Parsed out of the device naming convention, NULL for non-devices.
    -- Master: Standard Vehicle_2G Only_1_Teltonika FMB920
    -- Slave:  BLE Fuel Level Sensor_S1_TD-BLE_Escort_BLE_...
    device_family   VARCHAR(120),
    connectivity    VARCHAR(80),
    device_rank     VARCHAR(12),
    vendor_model    VARCHAR(160),

    ordinal         INTEGER,
    source_ref      VARCHAR(200) NOT NULL,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    loaded_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (catalog_version, object_kind, object_slug)
);

CREATE INDEX IF NOT EXISTS idx_catalog_obj_kind ON abi_catalog_objects(object_kind);
CREATE INDEX IF NOT EXISTS idx_catalog_obj_slug ON abi_catalog_objects(object_slug);
CREATE INDEX IF NOT EXISTS idx_catalog_obj_live
    ON abi_catalog_objects(catalog_version) WHERE active = TRUE;

COMMENT ON TABLE abi_catalog_objects IS
    'The approved catalogue object universe, loaded from NAVAS_CATALOG_*.xlsx '
    'by scripts/load_navas_catalog.py. Not a product master: no codes, no '
    'prices, no service-type mapping. Authority level 1.';
COMMENT ON COLUMN abi_catalog_objects.object_kind IS
    'service_type | core_feature | app | marketplace | tech_vas | '
    'cms_interface | master_device | slave_device';
COMMENT ON COLUMN abi_catalog_objects.object_slug IS
    'Lower-cased, punctuation-stripped name. The join key to '
    'abi_products_manager, because product names there are lower case and the '
    'catalogue writes them in title case — the exact mismatch that made '
    'migration 032 seed zero aliases.';

-- ── The canonical service-type vocabulary ──────────────────────────────────
CREATE OR REPLACE VIEW vw_navas_service_types AS
SELECT object_name AS service_type, description, catalog_version
FROM abi_catalog_objects
WHERE object_kind = 'service_type' AND active = TRUE
ORDER BY object_name;

-- ── Reconciliation: the three-way gap report ───────────────────────────────
-- Deliberately a FULL OUTER JOIN. An inner join would show only what matches,
-- which is the half of this problem nobody needs a report for.
-- Matching is by normalised name OR by any alias, because migration 036 exists
-- precisely so that one product can be found under several spellings. Joining
-- on product_name alone would report a product as unapproved purely because
-- the catalogue writes MAFUTA and the product row says MAFTA.
-- navas_slug and vw_navas_product_slugs are defined identically here and in
-- migration 038, so the two can be run in either order. CREATE OR REPLACE VIEW
-- cannot change a view's column list, so a second definition that differed
-- would fail outright depending on which migration ran last.
CREATE OR REPLACE FUNCTION navas_slug(value text) RETURNS text AS $$
    SELECT LOWER(REGEXP_REPLACE(COALESCE(value, ''), '[^a-zA-Z0-9+]+', '', 'g'));
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE VIEW vw_navas_product_slugs AS
SELECT p.product_uid, navas_slug(p.product_name) AS slug, 'name' AS via
FROM abi_products_manager p
UNION
SELECT a.product_uid, navas_slug(a.alias), 'alias'
FROM abi_product_aliases a;

-- Two halves unioned, rather than one FULL OUTER JOIN.
--
-- A full outer join over the slug table multiplies: a product with three
-- aliases that matches nothing appears three times, and the totals then
-- overstate how bad the data is. One row per catalogue object on one side, one
-- row per unmatched product on the other, is what a person can act on.
CREATE OR REPLACE VIEW vw_navas_catalog_reconciliation AS
SELECT c.object_slug AS slug,
       c.object_name,
       c.object_kind,
       p.product_uid,
       p.product_name,
       p.product_code,
       p.service_type,
       -- How many product rows answer to this catalogue object. Anything above
       -- 1 means the row shown was chosen by a tiebreak, and the reader needs
       -- to know that rather than trust it: 11 names in abi_products_manager
       -- exist twice, and silently picking one is how "iVMS" once resolved to
       -- "api book".
       COALESCE((SELECT COUNT(DISTINCT s.product_uid)
                 FROM vw_navas_product_slugs s
                 WHERE s.slug = c.object_slug), 0) AS matching_products,
       CASE
           WHEN p.product_uid IS NULL     THEN 'catalogue object has no product record'
           WHEN COALESCE(p.product_code, '')  = '' THEN 'matched, but product has no code'
           WHEN COALESCE(p.service_type, '') = '' THEN 'matched, but product has no service type'
           ELSE 'matched'
       END AS status
FROM abi_catalog_objects c
LEFT JOIN LATERAL (
        -- The catalogue row wins when two products share a name: 11 names in
        -- abi_products_manager exist twice, once as the seeded catalogue row
        -- and once ad-hoc, and picking arbitrarily is how "iVMS" resolved to
        -- "api book" in the token seed script.
        SELECT pm.product_uid, pm.product_name, pm.product_code, pm.service_type
        FROM abi_products_manager pm
        JOIN vw_navas_product_slugs s ON s.product_uid = pm.product_uid
        WHERE s.slug = c.object_slug
        ORDER BY CASE WHEN pm.product_code LIKE '3D-PRD-%' THEN 0 ELSE 1 END,
                 pm.product_uid
        LIMIT 1
     ) p ON TRUE
WHERE c.active = TRUE AND c.object_kind <> 'service_type'

UNION ALL

-- Deliberately not "unapproved". The catalogue lists the features, apps and
-- devices INSIDE the platforms; it does not list OLIWA or UKO themselves, so a
-- platform row legitimately matches nothing here. Calling that unapproved
-- would send somebody to delete a real product.
SELECT navas_slug(pm.product_name),
       NULL, NULL,
       pm.product_uid, pm.product_name, pm.product_code, pm.service_type,
       0,
       'no matching catalogue object (platform, or named differently)'
FROM abi_products_manager pm
WHERE NOT EXISTS (
        SELECT 1
        FROM vw_navas_product_slugs s
        JOIN abi_catalog_objects c
          ON c.object_slug = s.slug
         AND c.active = TRUE
         AND c.object_kind <> 'service_type'
        WHERE s.product_uid = pm.product_uid);

COMMENT ON VIEW vw_navas_catalog_reconciliation IS
    'Every approved catalogue object and every product row, matched by '
    'normalised name. The status column separates an invented product from a '
    'missing product record from an unapproved ad-hoc product.';

-- Service types in use that do not match the approved five.
--
-- Two kinds of drift, reported separately because they need different fixes.
-- A value that is off-vocabulary is a decision for the business. A value that
-- differs only in casing is a data-entry slip — but it still breaks every
-- exact-match filter and every GROUP BY, and this codebase has already been
-- bitten twice by case sensitivity (migration 032 seeded zero aliases; the
-- token seed script picked the wrong product). A case-insensitive check alone
-- would hide it, so it is checked both ways.
CREATE OR REPLACE VIEW vw_navas_service_type_drift AS
SELECT p.service_type,
       COUNT(*) AS products,
       CASE WHEN EXISTS (
                SELECT 1 FROM abi_catalog_objects c
                WHERE c.object_kind = 'service_type'
                  AND LOWER(TRIM(c.object_name)) = LOWER(TRIM(p.service_type)))
            THEN 'casing differs from the approved spelling'
            ELSE 'not in the approved vocabulary'
       END AS drift,
       (SELECT c.object_name FROM abi_catalog_objects c
         WHERE c.object_kind = 'service_type'
           AND LOWER(TRIM(c.object_name)) = LOWER(TRIM(p.service_type))
         LIMIT 1) AS approved_spelling
FROM abi_products_manager p
WHERE COALESCE(p.service_type, '') <> ''
  AND NOT EXISTS (
      SELECT 1 FROM abi_catalog_objects c
      WHERE c.object_kind = 'service_type'
        AND TRIM(c.object_name) = TRIM(p.service_type))   -- exact, not ILIKE
GROUP BY p.service_type
ORDER BY products DESC;
