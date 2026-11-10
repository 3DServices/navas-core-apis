-- 050_referrals.sql
--
-- Refer & Earn: a referrer gets 24 hours when a company they referred makes
-- its first paid top-up. Rules in endpoints/referral_rules.py.
--
-- dll_referral_codes   one code per client, made by the server on first use
-- dll_referrals        one row per referred client (a client can be referred
--                      once, so referee_client_uid is unique)
--
--   status             pending | qualified | rewarded | rejected
--   qualifying_payment the dll_payment_logs.remote_uid that earned it
--   reward_token_uid   the dll_user_token_accounts.token_billing_uid credited
--   note               why a reward is held or was rejected

BEGIN;

CREATE TABLE IF NOT EXISTS dll_referral_codes (
    client_uid  VARCHAR(100) PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dll_referrals (
    id                  SERIAL PRIMARY KEY,
    referrer_client_uid VARCHAR(100) NOT NULL,
    referee_client_uid  VARCHAR(100) NOT NULL UNIQUE,
    code                VARCHAR(20)  NOT NULL,
    claimed_by          VARCHAR(100),
    status              VARCHAR(16)  NOT NULL DEFAULT 'pending',
    note                TEXT,
    qualifying_payment  VARCHAR(100),
    reward_token_uid    VARCHAR(100),
    claimed_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    qualified_at        TIMESTAMP,
    rewarded_at         TIMESTAMP,
    CONSTRAINT chk_referral_status
        CHECK (status IN ('pending', 'qualified', 'rewarded', 'rejected')),
    CONSTRAINT chk_referral_not_self
        CHECK (referrer_client_uid <> referee_client_uid)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer
    ON dll_referrals(referrer_client_uid, status);

COMMIT;
