-- Migration 060: the driver an alert is about
-- Description: dll_event_notifications gets the driver the alert concerns,
-- so the console and the app can name them and filter by driver:
--   * a vehicle rule (speeding, geofence, ignition, offline): the driver
--     assigned to the unit when it fired
--   * a fuel rule: the driver the fuel was issued to
--   * a driver rule (driver_permit_expiry, driver_unauthorised): that driver
-- Both columns are NULL for alerts with no driver and for every alert written
-- before this. The alert engine writes them only once they exist
-- (alert_engine._driver_columns), and the list reads them through to_jsonb,
-- so nothing breaks before or after. Safe to run again.

ALTER TABLE dll_event_notifications
    ADD COLUMN IF NOT EXISTS driver_uid VARCHAR(100);

ALTER TABLE dll_event_notifications
    ADD COLUMN IF NOT EXISTS driver_name VARCHAR(150);

COMMENT ON COLUMN dll_event_notifications.driver_uid IS
    'dll_drivers.driver_uid the alert concerns, or NULL (migration 060).';
COMMENT ON COLUMN dll_event_notifications.driver_name IS
    'The driver''s name when the alert fired, kept even if renamed later.';

-- "Alerts about this driver", newest first.
CREATE INDEX IF NOT EXISTS idx_event_notifications_driver
    ON dll_event_notifications (owner_uid, driver_uid, date_triggered DESC)
    WHERE driver_uid IS NOT NULL;
