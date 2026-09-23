-- The official product ID register, and the repair it makes possible
-- Description: Official_Product_IDs_v26 — 50 products, each with its
-- 3D-PRD code, name, description and service type. This is the document whose
-- absence made migration 037 unable to repair anything: the NAVAS catalogue
-- says which objects are approved, and this says which product they are.
--
-- With it, the 27 products that lost their codes can be matched back by name.
-- But NOT all of them, and the difference matters:
--
--   * Where the name appears once in abi_products_manager, the code and
--     service type can be filled in. Safe.
--   * Where the name appears TWICE — once as the surviving coded row and once
--     as a UUID row created afterwards — filling the second row's code would
--     put the same 3D-PRD code on two rows. That is not a fill, it is a merge,
--     and which row survives depends on what points at it: tokens,
--     subscriptions, installed assets. A migration must not choose.
--
-- So this migration creates the register and the views that classify every
-- row. It changes no product data. scripts/load_official_product_ids.py does
-- the filling, only for rows the views mark safe, and only on request.

-- ── The register ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS abi_official_products (
    product_id     VARCHAR(40)  PRIMARY KEY,      -- 3D-PRD-nnn
    product_name   VARCHAR(200) NOT NULL,
    product_slug   VARCHAR(200) NOT NULL,
    description    TEXT,
    service_type   VARCHAR(80),
    register_version VARCHAR(40) NOT NULL,
    source_ref     VARCHAR(200) NOT NULL,
    active         BOOLEAN      NOT NULL DEFAULT TRUE,
    loaded_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (register_version, product_slug)
);
CREATE INDEX IF NOT EXISTS idx_official_slug ON abi_official_products(product_slug);
CREATE INDEX IF NOT EXISTS idx_official_stype ON abi_official_products(service_type);

COMMENT ON TABLE abi_official_products IS
    'Official_Product_IDs_v26. The authority for what a product is called, '
    'what its 3D-PRD code is, and which service type it belongs to. '
    'Authority level 1.';

-- ── The slug, corrected ─────────────────────────────────────────────────────
-- Migration 037 stripped every non-alphanumeric character, which collapsed
-- iVMS and iVMS+ onto the same key — and OLIWA onto OLIWA+. Those are
-- different products at different prices, and matching one to the other is a
-- worse error than matching nothing. '+' is therefore kept.
--
-- Replaced here rather than edited there so a database that has already run
-- 037 is corrected by running 038, with no need to re-run anything.
CREATE OR REPLACE FUNCTION navas_slug(value text) RETURNS text AS $$
    SELECT LOWER(REGEXP_REPLACE(COALESCE(value, ''), '[^a-zA-Z0-9+]+', '', 'g'));
$$ LANGUAGE sql IMMUTABLE;

COMMENT ON FUNCTION navas_slug(text) IS
    'Normalised product-name key. Keeps ''+'' because iVMS+ and iVMS are '
    'different products; everything else non-alphanumeric is dropped so that '
    '"OLIWA / UKO" and "oliwa/uko" match.';

CREATE OR REPLACE VIEW vw_navas_product_slugs AS
SELECT p.product_uid, navas_slug(p.product_name) AS slug, 'name' AS via
FROM abi_products_manager p
UNION
SELECT a.product_uid, navas_slug(a.alias), 'alias'
FROM abi_product_aliases a;

-- ── What can be repaired, and what cannot ───────────────────────────────────
-- One row per live product, carrying the register match and a verdict.
CREATE OR REPLACE VIEW vw_navas_product_repair AS
WITH matched AS (
    SELECT p.product_uid,
           p.product_name,
           p.product_code,
           p.service_type,
           o.product_id    AS official_code,
           o.product_name  AS official_name,
           o.service_type  AS official_service_type,
           o.description   AS official_description
    FROM abi_products_manager p
    LEFT JOIN LATERAL (
        SELECT o.*
        FROM abi_official_products o
        JOIN vw_navas_product_slugs s
          ON s.slug = o.product_slug AND s.product_uid = p.product_uid
        WHERE o.active = TRUE
        ORDER BY CASE WHEN s.via = 'name' THEN 0 ELSE 1 END, o.product_id
        LIMIT 1
    ) o ON TRUE
)
SELECT m.*,
       (SELECT COUNT(*) FROM abi_products_manager x
         WHERE navas_slug(x.product_name) = navas_slug(m.product_name)) AS rows_with_this_name,
       (SELECT COUNT(*) FROM abi_products_manager y
         WHERE y.product_code = m.official_code
           AND y.product_uid <> m.product_uid)                           AS others_holding_the_code,
       CASE
           WHEN m.official_code IS NULL
               THEN 'not in the official register'
           WHEN COALESCE(m.product_code, '') <> ''
            AND m.product_code <> m.official_code
               THEN 'CONFLICT: live code differs from the register'
           WHEN COALESCE(m.product_code, '') = ''
            AND EXISTS (SELECT 1 FROM abi_products_manager y
                         WHERE y.product_code = m.official_code
                           AND y.product_uid <> m.product_uid)
               THEN 'MERGE: another row already holds this code'
           WHEN COALESCE(m.product_code, '') = ''
               THEN 'fill: code and service type'
           WHEN COALESCE(m.service_type, '') = ''
               THEN 'fill: service type only'
           WHEN m.service_type <> m.official_service_type
               THEN 'CONFLICT: live service type differs from the register'
           ELSE 'ok'
       END AS verdict
FROM matched m;

COMMENT ON VIEW vw_navas_product_repair IS
    'Every product row against the official register, with a verdict. Only '
    'rows whose verdict begins "fill:" may be written automatically. MERGE '
    'rows are duplicate products and need a human to decide which survives.';

-- Register entries with no product row at all.
CREATE OR REPLACE VIEW vw_navas_register_unbuilt AS
SELECT o.product_id, o.product_name, o.service_type, o.description
FROM abi_official_products o
WHERE o.active = TRUE
  AND NOT EXISTS (SELECT 1 FROM vw_navas_product_slugs s
                   WHERE s.slug = o.product_slug)
ORDER BY o.product_id;

-- ── Service-type vocabulary: two approved sources that disagree ─────────────
-- The register uses six values; the NAVAS catalogue lists five service types,
-- and they are not spelled the same ("AI & Video Telematics" against
-- "AI & Video"), while "Add-on-Apps" appears only in the register. Both are
-- approved documents, so this reports the disagreement rather than picking a
-- winner. Waswa uses the register's spelling, because that is what the
-- product rows will be filled with.
-- Created only if migration 037 has already run. This is the ONE thing in 038
-- that needs the catalogue, and the register and the repair are fully useful
-- without it — so a hard reference here would make the whole migration fail on
-- a database where 037 has not run yet, which is exactly what happened. Run
-- 037 and re-run 038 to pick the view up; 038 is idempotent.
DO $do$
BEGIN
    IF to_regclass('public.abi_catalog_objects') IS NULL THEN
        RAISE NOTICE 'abi_catalog_objects not found, so '
                     'vw_navas_service_type_sources was skipped. The register '
                     'and the repair do not need it. Run migration 037, then '
                     're-run 038, to compare service-type vocabularies.';
    ELSE
        EXECUTE $view$
            CREATE OR REPLACE VIEW vw_navas_service_type_sources AS
            SELECT COALESCE(r.service_type, c.object_name) AS service_type,
                   r.products                              AS in_register,
                   (c.object_name IS NOT NULL)             AS in_catalogue,
                   CASE
                       WHEN c.object_name IS NULL
                           THEN 'register only - not a catalogue service type'
                       WHEN r.service_type IS NULL
                           THEN 'catalogue only - no product uses it'
                       ELSE 'both'
                   END                                     AS presence
            FROM (SELECT service_type, COUNT(*) AS products
                    FROM abi_official_products
                   WHERE active = TRUE AND COALESCE(service_type, '') <> ''
                   GROUP BY service_type) r
            FULL OUTER JOIN (SELECT object_name FROM abi_catalog_objects
                              WHERE object_kind = 'service_type'
                                AND active = TRUE) c
              ON navas_slug(c.object_name) = navas_slug(r.service_type)
            ORDER BY 4, 1
        $view$;
    END IF;
END
$do$;
