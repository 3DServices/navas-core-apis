-- 048_geozone_categories.sql
--
-- What a geofence is for, so the dashboard can tell a depot from a customer
-- site from somewhere a vehicle must not go:
--
--   general     no particular role (every existing zone)
--   depot       where vehicles are based, load and park overnight
--   customer    a client or delivery site
--   restricted  a place vehicles must stay out of: entering one is a
--               critical alert
--
-- Set with PUT /geozones/<geozone_id>/category (endpoints/geozones.py) and
-- returned on the geozone list. Read by the fleet summary
-- (GET /fleet/<client_uid>/summary) and by the alert list's severity.
--
-- Also indexes the geofence crossings the fleet summary pairs into visits for
-- dwell time. Safe to run more than once.

ALTER TABLE dll_geozones
    ADD COLUMN IF NOT EXISTS geozone_category VARCHAR(16) NOT NULL DEFAULT 'general';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_geozone_category') THEN
        ALTER TABLE dll_geozones
            ADD CONSTRAINT chk_geozone_category
            CHECK (geozone_category IN ('general', 'depot', 'customer', 'restricted'));
    END IF;
END
$$;

-- Geofence crossings per owner, newest first.
CREATE INDEX IF NOT EXISTS idx_notif_owner_crossings
    ON dll_event_notifications (owner_uid, date_triggered DESC)
    WHERE COALESCE(geozone_name, '') <> '';
