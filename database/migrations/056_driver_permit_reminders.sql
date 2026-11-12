-- 056_driver_permit_reminders.sql
--
-- Permit-expiry reminders (endpoints/permit_reminders.py): the last reminder
-- sent for each driver, so each stage (30, 14, 7, 1 days before, expired) is
-- sent once. permit_expiry is the date the reminder was for: when the permit
-- is renewed it no longer matches, and the reminders start again.
--
-- A deleted driver (only possible with no history) takes their row with them.

BEGIN;

CREATE TABLE IF NOT EXISTS dll_driver_permit_reminders (
    driver_uid     VARCHAR(100) PRIMARY KEY
                   REFERENCES dll_drivers (driver_uid) ON DELETE CASCADE,
    permit_expiry  DATE         NOT NULL,
    stage          SMALLINT     NOT NULL,
    sent_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMIT;
