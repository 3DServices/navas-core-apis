-- Unit-level Pause: rules + analytics events
-- Description: Moves "pause token burn" from a fleet-account switch to per-unit
-- (or per-group) control, with optional auto-pause rules, and logs every
-- pause/resume so the product owner can analyse why customers pause.

-- Auto-pause rules (one per target). mode:
--   'until'   → paused now, auto-resume at resume_at
--   'balance' → auto-pause when the client's token balance falls below threshold
CREATE TABLE IF NOT EXISTS dll_pause_rules (
    id                SERIAL PRIMARY KEY,
    owner_uid         VARCHAR(100) NOT NULL,
    scope             VARCHAR(10)  NOT NULL DEFAULT 'device',   -- 'device' | 'group'
    target_uid        VARCHAR(120) NOT NULL,                    -- device_imei or group_local_uid
    mode              VARCHAR(10)  NOT NULL,                     -- 'until' | 'balance'
    resume_at         TIMESTAMP,                                -- for mode='until'
    balance_threshold NUMERIC,                                  -- for mode='balance'
    active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (owner_uid, scope, target_uid)
);
CREATE INDEX IF NOT EXISTS idx_pause_rules_owner  ON dll_pause_rules(owner_uid);
CREATE INDEX IF NOT EXISTS idx_pause_rules_active ON dll_pause_rules(active) WHERE active = TRUE;

-- Analytics: every pause / resume, with the reason and balance at the time.
CREATE TABLE IF NOT EXISTS dll_pause_events (
    id               SERIAL PRIMARY KEY,
    owner_uid        VARCHAR(100) NOT NULL,
    device_imei      VARCHAR(120),
    group_uid        VARCHAR(120),
    action           VARCHAR(10)  NOT NULL,   -- 'pause' | 'resume'
    reason           VARCHAR(30)  NOT NULL,   -- manual | scheduled_until | low_balance | auto_resume
    balance_at_event NUMERIC,                 -- token balance when the event fired
    source           VARCHAR(10)  NOT NULL DEFAULT 'user',  -- 'user' | 'worker'
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pause_events_owner   ON dll_pause_events(owner_uid);
CREATE INDEX IF NOT EXISTS idx_pause_events_created ON dll_pause_events(created_at);
CREATE INDEX IF NOT EXISTS idx_pause_events_reason  ON dll_pause_events(reason);

COMMENT ON TABLE dll_pause_rules IS
    'Per-unit/group auto-pause rules (pause-until-time or pause-below-balance).';
COMMENT ON TABLE dll_pause_events IS
    'Audit + analytics of every pause/resume, for reducing pause events and growing wallets.';
