-- Auto-Renew Audit Log Migration
-- Description: Records every action the auto-renew worker takes (or would take
-- in dry-run mode), so operators can verify behaviour before enabling live
-- renewals and audit what happened afterward.

CREATE TABLE IF NOT EXISTS dll_auto_renew_log (
    id                SERIAL PRIMARY KEY,
    client_uid        VARCHAR(100) NOT NULL,
    device_imei       VARCHAR(100),
    token_billing_uid VARCHAR(100),
    outcome           VARCHAR(40)  NOT NULL,  -- renewed | would_renew | skipped_no_tokens | low_balance | error
    message           TEXT,
    dry_run           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auto_renew_log_client
    ON dll_auto_renew_log(client_uid);
CREATE INDEX IF NOT EXISTS idx_auto_renew_log_created
    ON dll_auto_renew_log(created_at);

COMMENT ON TABLE dll_auto_renew_log IS
    'Audit trail of auto-renew worker actions (real and dry-run).';
