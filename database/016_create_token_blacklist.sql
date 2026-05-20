-- ============================================================
-- 016: JWT Token Blacklist
-- ============================================================
-- Stores JTI (JWT ID) claims of access tokens that have been
-- revoked before their natural expiry (e.g. on logout).
--
-- The decode_access_token() function checks this table on every
-- request.  Rows can be safely purged once their expires_at has
-- passed, since expired tokens are already rejected by JWT
-- validation itself.
-- ============================================================

CREATE TABLE IF NOT EXISTS dll_token_blacklist (
    jti             VARCHAR(64)     PRIMARY KEY,
    account_uid     VARCHAR(128)    NOT NULL,
    expires_at      TIMESTAMPTZ     NOT NULL,
    revoked_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Index for the periodic cleanup job (DELETE WHERE expires_at < NOW())
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires
    ON dll_token_blacklist (expires_at);

-- Cleanup: remove expired entries (run periodically or via pg_cron)
-- DELETE FROM dll_token_blacklist WHERE expires_at < NOW();
