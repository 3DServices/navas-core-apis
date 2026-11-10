-- 049_token_usage_daily.sql
--
-- A daily record of how much of each token account has been used, so the
-- OLIWA dashboard can show daily usage per service.
--
-- Nothing in this API records consumption as it happens: whatever bills the
-- units only moves the running totals on dll_user_token_accounts
-- (token_used_units / token_hours_used). This table keeps one reading of that
-- total per account per day; a day's usage is that day's reading minus the
-- day before's (endpoints/token_usage.py).
--
--   client_uid         the wallet (dll_user_token_accounts.client_uid)
--   token_billing_uid  the token account
--   day                local date of the reading (Africa/Kampala)
--   service            product name at the time ('Live Tracking', ...)
--   billing_unit       hour / unit / event / km / ...: amounts in different
--                      units are never added together
--   used_total         the running used total at recorded_at
--   left_total         what was left then, when it read as a number
--   recorded_at        the latest reading of that day wins
--
-- Written by POST /tokens/usage/snapshot/run (schedule it daily, close to
-- midnight) and refreshed for one wallet whenever its usage is read. History
-- starts the day this runs; there is none from before.
--
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS dll_token_usage_daily (
    client_uid         VARCHAR(64)  NOT NULL,
    token_billing_uid  VARCHAR(64)  NOT NULL,
    day                DATE         NOT NULL,
    service            VARCHAR(256),
    billing_unit       VARCHAR(32),
    used_total         NUMERIC(18, 4) NOT NULL,
    left_total         NUMERIC(18, 4),
    recorded_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (client_uid, token_billing_uid, day)
);

CREATE INDEX IF NOT EXISTS idx_token_usage_daily_client_day
    ON dll_token_usage_daily (client_uid, day DESC);
