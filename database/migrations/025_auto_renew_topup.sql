-- Auto Top-Up Settings Migration (Phase 1 of "keep tracking alive 24/7")
-- Description: Extends per-client auto-renew settings with AUTO TOP-UP — when the
-- wallet runs low, the worker can initiate a mobile-money collection (which
-- prompts the customer for their PIN) to buy more tokens. No PIN is ever stored;
-- the telco/gateway handles the PIN prompt. Consent is explicit and spend is
-- capped per day.

ALTER TABLE dll_auto_renew_settings
    ADD COLUMN IF NOT EXISTS top_up_enabled     BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS top_up_token_uid   VARCHAR(100),          -- token package to buy
    ADD COLUMN IF NOT EXISTS top_up_quantity    INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS momo_number        VARCHAR(30),           -- mobile money number to charge
    ADD COLUMN IF NOT EXISTS daily_topup_limit  INTEGER     NOT NULL DEFAULT 1,  -- max auto top-ups/day
    ADD COLUMN IF NOT EXISTS channels           VARCHAR(120) NOT NULL DEFAULT 'in_app', -- csv: in_app,push,sms,whatsapp,email
    ADD COLUMN IF NOT EXISTS consent_at         TIMESTAMP,             -- when the client opted in to auto top-up
    ADD COLUMN IF NOT EXISTS last_topup_at      TIMESTAMP;             -- cooldown / audit

COMMENT ON COLUMN dll_auto_renew_settings.top_up_enabled IS
    'When TRUE (and consent given), the worker may buy tokens via mobile money on low balance.';
COMMENT ON COLUMN dll_auto_renew_settings.daily_topup_limit IS
    'Safety cap: maximum number of automatic top-ups initiated per day for this client.';
COMMENT ON COLUMN dll_auto_renew_settings.consent_at IS
    'Explicit opt-in timestamp for auto top-up. Required before any charge is initiated.';
