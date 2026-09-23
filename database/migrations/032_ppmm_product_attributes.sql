-- Waswa AI — Phase 2: PPMM product attributes
-- Description: turns abi_products_manager from a name/code/description list
-- into something Waswa can answer product questions from, and adds the child
-- tables for the attributes that are lists rather than single values.
--
-- Nothing here copies the PPMM catalogue into the schema by hand. The columns
-- are the shape; the values are loaded from a PPMM export by
-- scripts/load_ppmm_attributes.py, so a product change is a re-load rather than
-- a migration. That is the master prompt's A1.3 rule: PPMM -> database ->
-- tool call -> Waswa, never PPMM -> prompt.
--
-- Safe against existing code: products_billing.py selects named columns, and
-- its INSERT lists columns explicitly.

-- ── Product-level attributes ────────────────────────────────────────────────
ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS product_family       VARCHAR(60),
    ADD COLUMN IF NOT EXISTS customer_facing_name VARCHAR(200),
    ADD COLUMN IF NOT EXISTS outcomes             TEXT,
    ADD COLUMN IF NOT EXISTS asset_types          VARCHAR(240),
    ADD COLUMN IF NOT EXISTS token_class          VARCHAR(40),
    ADD COLUMN IF NOT EXISTS country_scope        VARCHAR(160),
    ADD COLUMN IF NOT EXISTS lifecycle_status     VARCHAR(20) DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS authority_level      SMALLINT    DEFAULT 1,
    ADD COLUMN IF NOT EXISTS source_ref           VARCHAR(200),
    ADD COLUMN IF NOT EXISTS catalog_version      VARCHAR(40),
    ADD COLUMN IF NOT EXISTS attributes_loaded_at TIMESTAMP;

COMMENT ON COLUMN abi_products_manager.customer_facing_name IS
    'Name as the customer sees it, per the PPMM naming formula: '
    '[Plain Product Name] - [Brand] [Model] [Key spec]. Waswa speaks this, '
    'never the internal code.';
COMMENT ON COLUMN abi_products_manager.outcomes IS
    'What the customer buys — fuel loss reduced, evidence available. '
    'Waswa leads with these, not with parameters.';
COMMENT ON COLUMN abi_products_manager.authority_level IS
    'Source-priority ladder: 1 = PPMM/approved product data (highest).';

-- ── Aliases ─────────────────────────────────────────────────────────────────
-- Needed on day one: the seeded catalogue spells these MAFTA FLS / MAFTA
-- CANBUS, the master prompt Appendix B.1 spells them MAFUTA, and customers say
-- both. A lookup that fails on a spelling variant reads to the user as "we do
-- not sell that". Aliases resolve the variant; they never invent a product.
CREATE TABLE IF NOT EXISTS abi_product_aliases (
    id           SERIAL PRIMARY KEY,
    product_uid  VARCHAR(100) NOT NULL,
    alias        VARCHAR(160) NOT NULL,
    alias_kind   VARCHAR(20)  NOT NULL DEFAULT 'variant',
        -- variant | legacy | sku | eshop | misspelling
    source_ref   VARCHAR(200),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (alias)
);
CREATE INDEX IF NOT EXISTS idx_product_alias_product ON abi_product_aliases(product_uid);

-- ── Capabilities ────────────────────────────────────────────────────────────
-- Approved capabilities only. Marketing language is not a capability, so every
-- row carries where it came from and at what authority level.
CREATE TABLE IF NOT EXISTS abi_product_capabilities (
    id              SERIAL PRIMARY KEY,
    product_uid     VARCHAR(100) NOT NULL,
    capability      VARCHAR(160) NOT NULL,
    detail          TEXT,
    source_ref      VARCHAR(200),
    authority_level SMALLINT     NOT NULL DEFAULT 1,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (product_uid, capability)
);
CREATE INDEX IF NOT EXISTS idx_product_cap_product ON abi_product_capabilities(product_uid);
CREATE INDEX IF NOT EXISTS idx_product_cap_name    ON abi_product_capabilities(capability);

-- ── Hardware ────────────────────────────────────────────────────────────────
-- What a product needs on the vehicle. The compatibility tool reads this, and
-- an absent row is why it can answer "cannot confirm" rather than guessing.
CREATE TABLE IF NOT EXISTS abi_product_hardware (
    id            SERIAL PRIMARY KEY,
    product_uid   VARCHAR(100) NOT NULL,
    hardware_name VARCHAR(160) NOT NULL,
    hardware_role VARCHAR(10)  NOT NULL DEFAULT 'master',   -- master | slave
    is_required   BOOLEAN      NOT NULL DEFAULT TRUE,
    notes         TEXT,
    source_ref    VARCHAR(200),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (product_uid, hardware_name)
);
CREATE INDEX IF NOT EXISTS idx_product_hw_product ON abi_product_hardware(product_uid);
CREATE INDEX IF NOT EXISTS idx_product_hw_name    ON abi_product_hardware(hardware_name);

-- ── Market segments and use cases ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS abi_product_segments (
    id            SERIAL PRIMARY KEY,
    product_uid   VARCHAR(100) NOT NULL,
    segment_kind  VARCHAR(20)  NOT NULL,   -- market_segment | use_case | industry
    segment_value VARCHAR(200) NOT NULL,
    source_ref    VARCHAR(200),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (product_uid, segment_kind, segment_value)
);
CREATE INDEX IF NOT EXISTS idx_product_seg_product ON abi_product_segments(product_uid);
CREATE INDEX IF NOT EXISTS idx_product_seg_value   ON abi_product_segments(segment_value);

-- ── Seed the MAFTA / MAFUTA aliases ─────────────────────────────────────────
-- The only aliases seeded here are the ones that are a documented conflict
-- between two approved sources. Everything else comes from the loader.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid,
       REPLACE(p.product_name, 'MAFTA', 'MAFUTA'),
       'variant',
       'Master prompt Appendix B.1 spelling'
FROM abi_products_manager p
WHERE p.product_name LIKE 'MAFTA%'
  AND NOT EXISTS (
      SELECT 1 FROM abi_product_aliases a
      WHERE a.alias = REPLACE(p.product_name, 'MAFTA', 'MAFUTA')
  );

-- 'OLIWA / UKO' is one product under two names customers actually use.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, v.alias, 'variant', 'PPMM product column header'
FROM abi_products_manager p
CROSS JOIN (VALUES ('OLIWA'), ('UKO')) AS v(alias)
WHERE p.product_name = 'OLIWA / UKO'
  AND NOT EXISTS (SELECT 1 FROM abi_product_aliases a WHERE a.alias = v.alias);

-- The master prompt writes the upgrade tiers with a spelled suffix.
INSERT INTO abi_product_aliases (product_uid, alias, alias_kind, source_ref)
SELECT p.product_uid, v.alias, 'variant', 'Master prompt Appendix B.3 attach paths'
FROM abi_products_manager p
JOIN (VALUES ('OLIWA+', 'OLIWA-PLUS'), ('iVMS+', 'iVMS-PLUS'))
     AS v(product_name, alias) ON v.product_name = p.product_name
WHERE NOT EXISTS (SELECT 1 FROM abi_product_aliases a WHERE a.alias = v.alias);

COMMENT ON TABLE abi_product_aliases IS
    'Other names for an approved product (spelling variants, legacy names, '
    'SKU and eShop names). Resolves to an existing product; never creates one.';
COMMENT ON TABLE abi_product_capabilities IS
    'Approved capabilities per product, with the source each came from.';
COMMENT ON TABLE abi_product_hardware IS
    'Hardware a product requires. Absence is meaningful: it is why the '
    'compatibility tool can answer "cannot confirm from data".';
COMMENT ON TABLE abi_product_segments IS
    'Market segments, industries and use cases a product is approved for.';
