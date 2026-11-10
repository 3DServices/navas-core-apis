-- 053_fuel.sql
--
-- FuelMath: fuel issued to drivers for the vehicles they drive, checked
-- against what the tracker saw. There is no station stock: a station is the
-- name on the receipt. Rules in endpoints/fuel_rules.py, routes in
-- endpoints/fuel_registry.py.
--
-- dll_fuel_vehicle_profiles   what a vehicle should use, one row per unit
--   tank_capacity_l           litres the tank holds
--   baseline_km_per_l         expected kilometres per litre
--   tolerance_pct             how far from the baseline still counts as normal
--
-- dll_fuel_issues             one row per fuel issue (a receipt)
--   issued_at                 local time (EAT), when the fuel went in
--   total_cost                litres x unit_price, worked out by the server
--   full_tank                 filled to the top: the fill-to-fill consumption
--                             is measured between two full tanks
--   tracker_*                 where the tracker put the vehicle at issued_at,
--                             read when the issue was recorded
--   km_since_full /           distance and litres since the previous full
--   litres_since_full         tank, and km_per_l at a full tank
--   flags                     comma-separated codes, fuel_rules.FLAGS
--   review_state              none | open | explained | confirmed_loss
--   voided_at                 a mistaken issue is voided, never deleted or
--                             edited: the row and the reason stay

BEGIN;

CREATE TABLE IF NOT EXISTS dll_fuel_vehicle_profiles (
    device_imei        VARCHAR(40)  PRIMARY KEY,
    client_uid         VARCHAR(100) NOT NULL,
    fuel_type          VARCHAR(10)  NOT NULL,
    tank_capacity_l    NUMERIC(7,1) NOT NULL,
    baseline_km_per_l  NUMERIC(6,2) NOT NULL,
    tolerance_pct      SMALLINT     NOT NULL DEFAULT 20,
    updated_by         VARCHAR(100),
    updated_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_fuel_profile_type CHECK (fuel_type IN ('petrol', 'diesel')),
    CONSTRAINT chk_fuel_profile_tank CHECK (tank_capacity_l > 0),
    CONSTRAINT chk_fuel_profile_baseline CHECK (baseline_km_per_l > 0),
    CONSTRAINT chk_fuel_profile_tolerance
        CHECK (tolerance_pct BETWEEN 5 AND 50)
);

CREATE INDEX IF NOT EXISTS ix_fuel_profile_client
    ON dll_fuel_vehicle_profiles (client_uid);

CREATE TABLE IF NOT EXISTS dll_fuel_issues (
    issue_uid          VARCHAR(100)  PRIMARY KEY,
    client_uid         VARCHAR(100)  NOT NULL,
    device_imei        VARCHAR(40)   NOT NULL,
    driver_uid         VARCHAR(100)  NOT NULL REFERENCES dll_drivers (driver_uid),
    issued_at          TIMESTAMP     NOT NULL,
    fuel_type          VARCHAR(10)   NOT NULL,
    litres             NUMERIC(8,2)  NOT NULL,
    unit_price         NUMERIC(10,2) NOT NULL,
    total_cost         NUMERIC(14,2) NOT NULL,
    full_tank          BOOLEAN       NOT NULL DEFAULT FALSE,
    odometer_km        NUMERIC(10,1),
    station_name       VARCHAR(120)  NOT NULL,
    receipt_number     VARCHAR(60),
    payment_method     VARCHAR(20)   NOT NULL,
    notes              TEXT,
    receipt_file       VARCHAR(200),

    tracker_state      VARCHAR(16)   NOT NULL DEFAULT 'unchecked',
    tracker_lat        DOUBLE PRECISION,
    tracker_lon        DOUBLE PRECISION,
    tracker_at         TIMESTAMP,
    tracker_place      TEXT,
    km_since_full      NUMERIC(10,1),
    litres_since_full  NUMERIC(10,2),
    km_per_l           NUMERIC(6,2),
    previous_full_uid  VARCHAR(100),
    flags              VARCHAR(400)  NOT NULL DEFAULT '',

    review_state       VARCHAR(16)   NOT NULL DEFAULT 'none',
    review_note        TEXT,
    reviewed_by        VARCHAR(100),
    reviewed_at        TIMESTAMP,

    voided_at          TIMESTAMP,
    voided_by          VARCHAR(100),
    void_reason        TEXT,

    issued_by          VARCHAR(100),
    created_at         TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_fuel_issue_type CHECK (fuel_type IN ('petrol', 'diesel')),
    CONSTRAINT chk_fuel_issue_litres CHECK (litres > 0),
    CONSTRAINT chk_fuel_issue_price CHECK (unit_price > 0),
    CONSTRAINT chk_fuel_issue_payment
        CHECK (payment_method IN ('cash', 'fuel_card', 'credit', 'mobile_money')),
    CONSTRAINT chk_fuel_issue_review
        CHECK (review_state IN ('none', 'open', 'explained', 'confirmed_loss')),
    CONSTRAINT chk_fuel_issue_tracker
        CHECK (tracker_state IN ('unchecked', 'checked', 'no_data', 'unavailable'))
);

-- A receipt is recorded once per client; a voided one may be recorded again.
CREATE UNIQUE INDEX IF NOT EXISTS uq_fuel_receipt
    ON dll_fuel_issues (client_uid, receipt_number)
    WHERE receipt_number IS NOT NULL AND voided_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_fuel_issue_client_time
    ON dll_fuel_issues (client_uid, issued_at DESC);
CREATE INDEX IF NOT EXISTS ix_fuel_issue_unit_time
    ON dll_fuel_issues (device_imei, issued_at DESC);
CREATE INDEX IF NOT EXISTS ix_fuel_issue_driver_time
    ON dll_fuel_issues (driver_uid, issued_at DESC);
CREATE INDEX IF NOT EXISTS ix_fuel_issue_review
    ON dll_fuel_issues (client_uid, review_state)
    WHERE review_state = 'open';

COMMIT;
