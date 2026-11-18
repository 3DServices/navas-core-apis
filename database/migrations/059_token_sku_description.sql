-- Migration 059: token SKU + eShop description
-- Description: Gives catalogue tokens (dll_tokens_registry) the standardized
-- SKU (e.g. NVS.TKN.OLI.T30) and the client-facing eShop description from the
-- NVS token sheet, so the mobile Token Billing screen can search on them.
-- Both columns are optional: tokens created before this keep NULL.
-- Safe to run again.

ALTER TABLE dll_tokens_registry
    ADD COLUMN IF NOT EXISTS token_sku VARCHAR(64);

ALTER TABLE dll_tokens_registry
    ADD COLUMN IF NOT EXISTS token_description TEXT;

COMMENT ON COLUMN dll_tokens_registry.token_sku IS
    'Standardized token SKU from the NVS token sheet, e.g. NVS.TKN.OLI.T30. '
    'One SKU can be priced in several currencies (one row per currency).';

COMMENT ON COLUMN dll_tokens_registry.token_description IS
    'Client-facing eShop description of the token.';

-- One row per SKU per currency; also what the seed script keys on.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tokens_registry_sku_currency
    ON dll_tokens_registry (token_sku, UPPER(token_currency))
    WHERE token_sku IS NOT NULL;
