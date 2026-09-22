-- Waswa AI — customer class on the client account
-- Description: gives customer_class a home so Waswa can stop reporting it as
-- unknown. The classes and their unit bands come from the NAVAS Vision Scope
-- Doc (Appendix B.4): DIAMOND 500+, PLATINUM 201-500, GOLD 61-200,
-- SILVER 11-60, BRONZE 1-10.
--
-- Deliberately NOT backfilled. A class carries credit posture and service
-- commitments, so it is assigned by the business, not computed from a unit
-- count — and the runtime prompt forbids guessing it. Until someone assigns a
-- class, the column stays NULL and Waswa keeps saying it does not know.
--
-- Safe against the existing code: Postgres appends new columns at the end, and
-- clients.py reads dll_client_accounts with SELECT * indexed positionally
-- (row[0..2]) and inserts with a 6-value VALUES list. Both keep working.

ALTER TABLE dll_client_accounts
    ADD COLUMN IF NOT EXISTS customer_class    VARCHAR(16),
    ADD COLUMN IF NOT EXISTS class_assigned_by VARCHAR(100),
    ADD COLUMN IF NOT EXISTS class_assigned_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS class_note        TEXT;

-- Only the five approved classes, or nothing at all.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_client_customer_class'
    ) THEN
        ALTER TABLE dll_client_accounts
            ADD CONSTRAINT chk_client_customer_class
            CHECK (customer_class IS NULL OR customer_class IN
                   ('DIAMOND', 'PLATINUM', 'GOLD', 'SILVER', 'BRONZE'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_client_customer_class
    ON dll_client_accounts(customer_class);

COMMENT ON COLUMN dll_client_accounts.customer_class IS
    'Commercial class assigned by the business (Vision Scope Appendix B.4). '
    'NULL means unassigned — Waswa reports it as unknown rather than guessing.';

-- ── Advisory view, for the humans doing the assigning ───────────────────────
-- Shows each client''s subscribed-unit count and the band that count falls in.
-- This is a worksheet to speed up assignment, NOT the class: Waswa never reads
-- this view, and a band is not an entitlement.
CREATE OR REPLACE VIEW vw_waswa_class_advisory AS
SELECT
    c.client_uid,
    c.client_name,
    c.customer_class                                   AS assigned_class,
    COALESCE(u.subscribed_units, 0)                    AS subscribed_units,
    CASE
        WHEN COALESCE(u.subscribed_units, 0) >= 500 THEN 'DIAMOND'
        WHEN COALESCE(u.subscribed_units, 0) >= 201 THEN 'PLATINUM'
        WHEN COALESCE(u.subscribed_units, 0) >= 61  THEN 'GOLD'
        WHEN COALESCE(u.subscribed_units, 0) >= 11  THEN 'SILVER'
        WHEN COALESCE(u.subscribed_units, 0) >= 1   THEN 'BRONZE'
        ELSE NULL
    END                                                AS band_by_unit_count
FROM dll_client_accounts c
LEFT JOIN (
    SELECT ta.client_uid, COUNT(*) AS subscribed_units
    FROM dll_device_subscriptions ds
    JOIN dll_user_token_accounts ta
      ON ta.token_billing_uid = ds.token_billing_uid
    GROUP BY ta.client_uid
) u ON u.client_uid = c.client_uid
WHERE c.is_deleted = FALSE OR c.is_deleted IS NULL;

COMMENT ON VIEW vw_waswa_class_advisory IS
    'Assignment worksheet: unit-count band beside the assigned class. '
    'Advisory only — the band is not a class and Waswa does not read this.';
