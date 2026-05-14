-- Migration: Create dll_refresh_tokens table for JWT refresh token management
-- Run this against the narva_dbl database before deploying the JWT auth changes.

CREATE TABLE IF NOT EXISTS dll_refresh_tokens (
    id              SERIAL PRIMARY KEY,
    token_hash      VARCHAR(64)   NOT NULL UNIQUE,
    account_uid     VARCHAR(255)  NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ   NOT NULL,
    revoked         BOOLEAN       NOT NULL DEFAULT FALSE
);

-- Index for fast lookup by token hash (used on every refresh request)
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash
    ON dll_refresh_tokens (token_hash)
    WHERE revoked = FALSE;

-- Index for revoking all tokens for a user (used on logout-all)
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_account
    ON dll_refresh_tokens (account_uid)
    WHERE revoked = FALSE;

-- Periodic cleanup: delete expired/revoked tokens older than 30 days
-- Schedule this as a cron job or pg_cron task:
--   DELETE FROM dll_refresh_tokens
--   WHERE revoked = TRUE OR expires_at < NOW() - INTERVAL '30 days';
