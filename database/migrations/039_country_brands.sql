-- One product, two country brands
-- Description: OLIWA and UKO are the same product. OLIWA is the Uganda brand,
-- UKO the Kenya brand, and the register carries them as a single entry,
-- 3D-PRD-005 "OLIWA / UKO". Stated by the business on 2026-09-19.
--
-- That fact could not be inferred from the data, and the repair was right to
-- refuse it: abi_products_manager holds 'oliwa' and 'uko' as two separate rows,
-- and filling 3D-PRD-005 onto both looked identical to the eleven genuine
-- duplicate-product rows the repair stops on. The difference is that these two
-- SHOULD both exist — they are one product in two markets — while the other
-- eleven are one product recorded twice by accident.
--
-- So rather than merging the rows, this encodes what makes them legitimately
-- distinct: country. A registered product may have one product row per
-- country, and "another row already holds this code" stops being a conflict
-- when the two rows serve different countries.
--
-- OLIWA+ (3D-PRD-006) is deliberately NOT given a Kenya twin here. The
-- business stated the OLIWA/UKO pairing; nobody has said what the Kenyan
-- upgrade tier is called, and inventing "UKO+" would be exactly the kind of
-- plausible guess this build exists to avoid. vw_navas_country_variants shows
-- it as unpaired until someone says.

-- ── Country on an alias ─────────────────────────────────────────────────────
-- So Waswa can speak the right brand name to the right customer. A Kenyan
-- fleet manager should hear UKO, not OLIWA; getting that wrong reads as though
-- we do not know our own products.
ALTER TABLE abi_product_aliases
    ADD COLUMN IF NOT EXISTS country_scope VARCHAR(80);

COMMENT ON COLUMN abi_product_aliases.country_scope IS
    'The country this name is used in. NULL means the name is used '
    'everywhere. Waswa prefers the alias matching the account country when '
    'naming a product back to a customer.';

-- ── The two rows, marked by country ─────────────────────────────────────────
-- Narrow and idempotent on purpose: it sets country_scope only where it is
-- still empty, and only on rows named exactly oliwa or uko. It writes no code
-- — the repair script does that, once the country makes it unambiguous.
UPDATE abi_products_manager
   SET country_scope = 'Uganda'
 WHERE navas_slug(product_name) = 'oliwa'
   AND COALESCE(country_scope, '') = '';

UPDATE abi_products_manager
   SET country_scope = 'Kenya'
 WHERE navas_slug(product_name) = 'uko'
   AND COALESCE(country_scope, '') = '';

-- 'oliwa plus' is the Uganda upgrade tier; same treatment, no Kenya twin
-- asserted.
UPDATE abi_products_manager
   SET country_scope = 'Uganda'
 WHERE navas_slug(product_name) IN ('oliwaplus', 'oliwa+')
   AND COALESCE(country_scope, '') = '';

-- ── Aliases, now country-scoped ─────────────────────────────────────────────
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, country_scope,
                                 source_ref)
SELECT p.product_uid, v.alias, 'country_brand', v.country,
       'Business statement 2026-09-19: OLIWA is Uganda, UKO is Kenya '
       '(via migration 039)'
FROM abi_products_manager p
JOIN (VALUES ('oliwa', 'OLIWA', 'Uganda'),
             ('oliwa', 'UKO',   'Kenya'),
             ('uko',   'UKO',   'Kenya'),
             ('uko',   'OLIWA', 'Uganda'))
     AS v(match_slug, alias, country) ON navas_slug(p.product_name) = v.match_slug
ON CONFLICT DO NOTHING;

-- The register spells this product "OLIWA / UKO"; neither live row is named
-- that, so without this alias neither can match 3D-PRD-005 at all.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, 'OLIWA / UKO', 'register_name',
       'Official_Product_IDs v26 3D-PRD-005 (via migration 039)'
FROM abi_products_manager p
WHERE navas_slug(p.product_name) IN ('oliwa', 'uko')
ON CONFLICT DO NOTHING;

-- ── Same code in two countries is not a conflict ────────────────────────────
-- Rebuilt with the country test added. Everything else is unchanged, so the
-- eleven genuine duplicates — which have no country on either row — still come
-- back as MERGE.
--
-- DROP then CREATE, not CREATE OR REPLACE: replacing a view cannot change its
-- column list, and this version adds country_scope. Nothing else selects from
-- this view — the repair script queries it directly — so dropping it is safe.
DROP VIEW IF EXISTS vw_navas_product_repair;
CREATE VIEW vw_navas_product_repair AS
WITH matched AS (
    SELECT p.product_uid,
           p.product_name,
           p.product_code,
           p.service_type,
           p.country_scope,
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
           AND y.product_uid <> m.product_uid
           AND COALESCE(y.country_scope, '') = COALESCE(m.country_scope, ''))
                                                                        AS others_holding_the_code,
       CASE
           WHEN m.official_code IS NULL
               THEN 'not in the official register'
           WHEN COALESCE(m.product_code, '') <> ''
            AND m.product_code <> m.official_code
               THEN 'CONFLICT: live code differs from the register'
           WHEN COALESCE(m.product_code, '') = ''
            AND EXISTS (SELECT 1 FROM abi_products_manager y
                         WHERE y.product_code = m.official_code
                           AND y.product_uid <> m.product_uid
                           -- Same code in a DIFFERENT country is the
                           -- OLIWA/UKO case and is allowed. Same code in the
                           -- same country is a duplicate product row.
                           AND COALESCE(y.country_scope, '')
                             = COALESCE(m.country_scope, ''))
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

-- ── Country variants, and the ones still unpaired ───────────────────────────
CREATE OR REPLACE VIEW vw_navas_country_variants AS
SELECT o.product_id,
       o.product_name AS registered_as,
       COUNT(p.product_uid)                                   AS product_rows,
       STRING_AGG(DISTINCT COALESCE(p.country_scope, '(no country)'), ', '
                  ORDER BY COALESCE(p.country_scope, '(no country)')) AS countries,
       STRING_AGG(DISTINCT p.product_name, ', ' ORDER BY p.product_name) AS named
FROM abi_official_products o
JOIN vw_navas_product_slugs s ON s.slug = o.product_slug
JOIN abi_products_manager p   ON p.product_uid = s.product_uid
WHERE o.active = TRUE
GROUP BY o.product_id, o.product_name
HAVING COUNT(DISTINCT p.product_uid) > 1
ORDER BY o.product_id;

COMMENT ON VIEW vw_navas_country_variants IS
    'Registered products backed by more than one product row. Where the rows '
    'carry different countries this is the intended OLIWA/UKO shape; where '
    'they do not, it is a duplicate needing a merge.';
