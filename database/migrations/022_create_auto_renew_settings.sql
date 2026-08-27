-- Auto-Renew Settings Migration
-- Description: Per-client preference for automatically renewing device
-- subscriptions from the client's EXISTING wallet balance (no auto-purchase).
-- Consumed by the Token Auto-Renew screen (settings) and, later, the
-- auto-renew background worker.

CREATE TABLE IF NOT EXISTS dll_auto_renew_settings (
    id              SERIAL PRIMARY KEY,
    client_uid      VARCHAR(100) NOT NULL UNIQUE,
    enabled         BOOLEAN      NOT NULL DEFAULT FALSE,
    paused          BOOLEAN      NOT NULL DEFAULT FALSE,
    target_hours    INTEGER      NOT NULL DEFAULT 50,   -- low-water mark to maintain
    renewal_period  INTEGER      NOT NULL DEFAULT 1,    -- months to renew each cycle
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Fast lookup by client, and a partial index for the worker's "who is enabled" sweep.
CREATE INDEX IF NOT EXISTS idx_auto_renew_client
    ON dll_auto_renew_settings(client_uid);
CREATE INDEX IF NOT EXISTS idx_auto_renew_enabled
    ON dll_auto_renew_settings(enabled) WHERE enabled = TRUE;

COMMENT ON TABLE dll_auto_renew_settings IS
    'Per-client auto-renew preference. Renews device subscriptions from existing wallet balance.';
COMMENT ON COLUMN dll_auto_renew_settings.target_hours IS
    'Renew a device when its remaining tracking time falls to/below this many hours.';
COMMENT ON COLUMN dll_auto_renew_settings.renewal_period IS
    'How many months of subscription to attach on each auto-renew.';
