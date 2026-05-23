-- ============================================================
-- 019_unique_active_listing_per_asset.sql
-- ============================================================
-- Prevents two active/paused listings for the same asset.
-- A unique partial index is the cleanest enforcement — the DB
-- rejects the INSERT before the app even sees it. Archived and
-- draft listings are excluded so an asset can be re-listed
-- after archiving.
--
-- Idempotent: CREATE … IF NOT EXISTS.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_marketplace_listings_one_active_per_asset
    ON dll_marketplace_listings (asset_uid)
    WHERE status IN ('active', 'paused');
