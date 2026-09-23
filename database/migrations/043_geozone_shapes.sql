-- 043_geozone_shapes.sql
--
-- Geofences can be drawn as a polygon (4+ corners), a circle (centre and
-- radius) or a line (a route of 2+ points with a thickness — a corridor).
--
-- geozone_points keeps meaning exactly what it meant before: a polygon ring of
-- [lng, lat] pairs. A circle is stored there as a 64-sided polygon and a line
-- as the corridor around it, so every reader of geozone_points — the live
-- monitoring screen and the stream that writes enter/exit events — keeps
-- working without a change. The shape itself is kept beside it:
--
--   geozone_shape         'polygon' | 'circle' | 'line'  (existing rows: polygon)
--   geozone_shape_params  JSON text:
--                           polygon {"points":[{"lat":..,"lng":..},...]}
--                           circle  {"center":{"lat":..,"lng":..},"radius_m":..}
--                           line    {"points":[...],"width_m":..}
--                         NULL on rows created before this migration.
--
-- Also adds the two colour columns the console has been sending on create but
-- the table had nowhere to keep.
--
-- Safe to run more than once.

ALTER TABLE dll_geozones
    ADD COLUMN IF NOT EXISTS geozone_shape        VARCHAR(16) NOT NULL DEFAULT 'polygon',
    ADD COLUMN IF NOT EXISTS geozone_shape_params TEXT,
    ADD COLUMN IF NOT EXISTS geozone_color        VARCHAR(16),
    ADD COLUMN IF NOT EXISTS geozone_label_color  VARCHAR(16);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_geozone_shape') THEN
        ALTER TABLE dll_geozones
            ADD CONSTRAINT chk_geozone_shape
            CHECK (geozone_shape IN ('polygon', 'circle', 'line'));
    END IF;
END
$$;

COMMENT ON COLUMN dll_geozones.geozone_shape IS
    'polygon | circle | line. geozone_points always holds the polygon ring used '
    'for inside/outside checks; this says what the customer drew.';
COMMENT ON COLUMN dll_geozones.geozone_shape_params IS
    'JSON: the drawn shape (points / centre+radius_m / route+width_m). NULL for '
    'zones created before migration 043.';
