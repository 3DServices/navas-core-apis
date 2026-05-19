-- ============================================================
-- 014_marketplace_listings.sql
-- ============================================================
-- Adds dll_marketplace_listings — the table backing the VEBA Marketplace
-- "List on VEBA" / "My Listings" / Marketplace-browse feature.
--
-- Column shapes mirror the frontend's VebaListing TypeScript type
-- (src/api/types/veba.types.ts). Lifecycle is modelled via the `status`
-- enum-style column (active / paused / archived / draft) instead of a
-- separate is_deleted flag — `archived` is the soft-delete state.
--
-- No FK on asset_uid: device records live in Cassandra (dll_device_registrar)
-- so the relationship is referential rather than enforced. The asset_summary
-- JSONB column carries a denormalised snapshot of the asset at create time
-- so the marketplace cards render without a cross-store join.
--
-- Idempotent: re-running is safe (CREATE TABLE IF NOT EXISTS / CREATE INDEX
-- IF NOT EXISTS).
-- ============================================================

CREATE TABLE IF NOT EXISTS dll_marketplace_listings (
    -- Identity & ownership
    listing_uid          VARCHAR(100) PRIMARY KEY,
    asset_uid            VARCHAR(100) NOT NULL,
    account_root         VARCHAR(100) NOT NULL,
    created_by           VARCHAR(100) NOT NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),

    -- Commercial terms
    daily_rate           NUMERIC(12, 2) NOT NULL CHECK (daily_rate >= 0),
    currency             VARCHAR(8)     NOT NULL,
    pricing_basis        VARCHAR(20)    NOT NULL
        CHECK (pricing_basis IN ('per_day', 'per_hour', 'per_km', 'per_trip')),
    hourly_rate          NUMERIC(12, 2) NULL CHECK (hourly_rate IS NULL OR hourly_rate >= 0),
    availability_start   DATE           NULL,
    availability_end     DATE           NULL,
    geographic_scope     VARCHAR(200)   NULL,
    operator_included    BOOLEAN        NOT NULL DEFAULT FALSE,
    notes                TEXT           NULL,

    -- Surfacing
    visibility           VARCHAR(20)    NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'tenant')),
    status               VARCHAR(20)    NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived', 'draft')),

    -- Denormalised asset snapshot (display_name, asset_class, owner_org, country, photo_url)
    asset_summary        JSONB          NULL,

    -- Sanity: an availability window, if both ends are set, must be a forward range.
    CONSTRAINT chk_marketplace_listings_availability_range
        CHECK (
            availability_start IS NULL
            OR availability_end IS NULL
            OR availability_end >= availability_start
        )
);

-- ============================================================
-- Indexes
-- ============================================================

-- "My Listings" / owner views: filter by tenant + lifecycle state.
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_account_root_status
    ON dll_marketplace_listings (account_root, status);

-- Asset detail blade reverse lookup: "is this asset currently listed?"
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_asset_uid
    ON dll_marketplace_listings (asset_uid);

-- Marketplace browse (the hot read path): only active listings matter.
-- Partial index keeps the index small even as archived rows accumulate.
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_browse
    ON dll_marketplace_listings (visibility, status, created_at DESC)
    WHERE status = 'active';

-- General-purpose recency index for owner dashboards and audit views.
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_created_at
    ON dll_marketplace_listings (created_at DESC);

-- ============================================================
-- Comments (documentation surfaced via psql \d+ and pgAdmin)
-- ============================================================

COMMENT ON TABLE  dll_marketplace_listings
    IS 'VEBA Marketplace listings — links an asset (registry) to commercial terms (rate, availability, visibility).';
COMMENT ON COLUMN dll_marketplace_listings.listing_uid
    IS 'Primary key. Generated server-side via generate_uid().';
COMMENT ON COLUMN dll_marketplace_listings.asset_uid
    IS 'Reference to an asset in the device/asset registry. Not FK-enforced because asset records live in Cassandra.';
COMMENT ON COLUMN dll_marketplace_listings.account_root
    IS 'Owning tenant (always derived server-side from the caller''s JWT, never trusted from the request body).';
COMMENT ON COLUMN dll_marketplace_listings.pricing_basis
    IS 'Primary basis for the daily_rate. Secondary basis available via hourly_rate.';
COMMENT ON COLUMN dll_marketplace_listings.visibility
    IS 'public = visible to every authenticated user on the marketplace; tenant = visible only to the owning account_root (internal pool).';
COMMENT ON COLUMN dll_marketplace_listings.status
    IS 'Lifecycle state: active (live), paused (hidden but preserved), archived (soft-delete; new bookings blocked), draft (not yet published).';
COMMENT ON COLUMN dll_marketplace_listings.asset_summary
    IS 'Denormalised asset snapshot at create time: {display_name, asset_class, owner_org, country, photo_url}.';

-- ============================================================
-- Verify migration
-- ============================================================
-- SELECT COUNT(*) FROM dll_marketplace_listings;  -- expected: 0 immediately after migration
-- \d+ dll_marketplace_listings                    -- show schema + indexes + comments
