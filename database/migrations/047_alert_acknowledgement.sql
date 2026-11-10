-- 047_alert_acknowledgement.sql
--
-- Alert acknowledgement: someone has seen an alert and is dealing with it.
--
-- is_read only says an alert was opened. A fleet manager needs to know which
-- alerts somebody has taken on, who, and how long that took -- the "time to
-- acknowledge" the OLIWA dashboard asks for. Written by
-- PUT /notifications/<notification_uid>/acknowledge (endpoints/events.py).
--
--   acknowledged_at   when it was acknowledged; NULL while it is open
--   acknowledged_by   the account_uid that acknowledged it
--   acknowledge_note  optional, what was done ("called the driver")
--
-- Existing alerts stay unacknowledged. Safe to run more than once.

ALTER TABLE dll_event_notifications
    ADD COLUMN IF NOT EXISTS acknowledged_at  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS acknowledged_by  VARCHAR(64),
    ADD COLUMN IF NOT EXISTS acknowledge_note TEXT;

-- Open alerts per owner, newest first: the triage list.
CREATE INDEX IF NOT EXISTS idx_notif_owner_open
    ON dll_event_notifications (owner_uid, date_triggered DESC)
    WHERE acknowledged_at IS NULL;
