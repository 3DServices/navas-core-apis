-- ============================================================
-- 015_booking_requests.sql
-- ============================================================
-- Adds dll_booking_requests — the table backing VEBA marketplace bookings.
--
-- Shape mirrors the frontend's BookingRequest TypeScript type
-- (src/api/types/booking.types.ts). A booking request is created when a
-- prospective renter ("requester") wants to book a published listing. The
-- listing's owner reviews and either approves or rejects.
--
-- Critical correctness property: `rate_snapshot` is captured at submission
-- time. Owner-side rate edits made AFTER the request was filed never affect
-- pending requests — the price the requester saw is the price they pay.
--
-- Idempotent: re-running is safe (CREATE TABLE IF NOT EXISTS / CREATE INDEX
-- IF NOT EXISTS).
-- ============================================================

CREATE TABLE IF NOT EXISTS dll_booking_requests (
    -- Identity
    request_uid       VARCHAR(100) PRIMARY KEY,

    -- Listing & asset (denormalised so request rows survive listing changes)
    listing_uid       VARCHAR(100) NOT NULL
        REFERENCES dll_marketplace_listings(listing_uid)
        ON DELETE RESTRICT,
    asset_uid         VARCHAR(100) NOT NULL,

    -- Parties
    requester_uid     VARCHAR(100) NOT NULL,
    requester_root    VARCHAR(100) NOT NULL,
    owner_root        VARCHAR(100) NOT NULL,

    -- Booking window
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    notes             TEXT NULL,

    -- Workflow
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'fulfilled')),

    -- Rate frozen at submission. Shape: { daily_rate, currency, pricing_basis }.
    -- NOT NULL because we want it impossible for a request to exist without
    -- the price the requester agreed to.
    rate_snapshot     JSONB NOT NULL,

    -- Timestamps
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_booking_requests_date_range
        CHECK (end_date >= start_date)
);

-- ============================================================
-- Indexes
-- ============================================================

-- Owner-side inbox: "what requests are waiting on me?"
CREATE INDEX IF NOT EXISTS idx_booking_requests_owner_status
    ON dll_booking_requests (owner_root, status);

-- Requester-side outgoing: "what have I asked for?"
CREATE INDEX IF NOT EXISTS idx_booking_requests_requester_status
    ON dll_booking_requests (requester_root, status);

-- All requests for a given listing (used in lifecycle workflows + audit).
CREATE INDEX IF NOT EXISTS idx_booking_requests_listing
    ON dll_booking_requests (listing_uid);

-- General recency index for activity feeds.
CREATE INDEX IF NOT EXISTS idx_booking_requests_created_at
    ON dll_booking_requests (created_at DESC);

-- ============================================================
-- Comments
-- ============================================================

COMMENT ON TABLE  dll_booking_requests
    IS 'VEBA Marketplace booking requests. Created by requesters; reviewed by listing owners.';
COMMENT ON COLUMN dll_booking_requests.request_uid
    IS 'Primary key. Generated server-side as req_<uuid4>.';
COMMENT ON COLUMN dll_booking_requests.owner_root
    IS 'Tenant of the listing owner. ALWAYS derived from the listing — never trusted from the request body.';
COMMENT ON COLUMN dll_booking_requests.rate_snapshot
    IS 'JSON snapshot of the listing rate at submission time: {daily_rate, currency, pricing_basis}. Never updated.';
COMMENT ON COLUMN dll_booking_requests.status
    IS 'Workflow state: pending (default), approved, rejected, cancelled, fulfilled.';

-- ============================================================
-- Verify migration
-- ============================================================
-- SELECT COUNT(*) FROM dll_booking_requests;       -- expected: 0
-- \d+ dll_booking_requests                          -- schema + FK + indexes
