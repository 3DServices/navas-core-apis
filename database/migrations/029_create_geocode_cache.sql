-- Migration 029 — Reverse-geocode cache.
--
-- Stores resolved place names keyed by coordinates rounded to 4 decimal places
-- (~11 m buckets). The /data-stream/location/geocoding endpoint reads this
-- first and only calls the external provider (Google / Nominatim) on a miss,
-- which keeps us within rate limits and makes place-name lookups fast and
-- reliable. Failed lookups are NOT cached, so they can resolve later.

CREATE TABLE IF NOT EXISTS dll_geocode_cache (
    lat_key     NUMERIC(9,4) NOT NULL,
    lng_key     NUMERIC(9,4) NOT NULL,
    location    TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (lat_key, lng_key)
);
