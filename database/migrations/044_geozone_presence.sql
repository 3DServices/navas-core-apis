-- 044_geozone_presence.sql
--
-- Where the server remembers whether a unit is inside a geofence.
--
-- Geofence alerts used to be worked out in the browser, which had no memory:
-- the first position it saw inside a zone looked like an entry, so opening the
-- tracking screen invented alerts for vehicles that had been parked inside a
-- zone all along. The server now keeps that answer here, and writes an alert
-- only when it CHANGES.
--
-- One row per unit per zone:
--   is_inside          the last answer (true = inside the zone)
--   last_position_ref  the position that answer came from (dll_location_registry
--                      .data_idx); a unit whose position hasn't moved on is
--                      skipped on the next sweep
--   last_checked       when the engine last looked
--
-- A row appearing for the first time is a "first sighting": it records where
-- the unit is and sends nothing.
--
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS dll_geozone_presence (
    device_imei       VARCHAR(64)  NOT NULL,
    geozone_uid       VARCHAR(64)  NOT NULL,
    is_inside         BOOLEAN      NOT NULL DEFAULT FALSE,
    last_position_ref TEXT,
    last_checked      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (device_imei, geozone_uid)
);

CREATE INDEX IF NOT EXISTS idx_geozone_presence_zone
    ON dll_geozone_presence (geozone_uid);

COMMENT ON TABLE dll_geozone_presence IS
    'Last known inside/outside answer per unit per geofence. Written by '
    'endpoints/alert_engine.py; an alert is sent only when the answer changes.';
