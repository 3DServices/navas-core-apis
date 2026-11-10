-- 052_drivers.sql
--
-- Driver management: a client registers its drivers and attaches each to a
-- vehicle. Rules in endpoints/driver_rules.py, routes in endpoints/
-- driver_registry.py.
--
-- dll_drivers              one row per driver, owned by a client
--   phone                  normalised, +256772123456
--   permit_classes         comma-separated codes, e.g. "B,CM"
--   ibutton_id             the driver's iButton tag, upper-case hex, as the
--                          tracker reports it in driver_id: a known tag in a
--                          unit's data says who is driving
--   national_id            optional (NIN)
--   status                 active | suspended | blacklisted | inactive
--
-- dll_driver_assignments   who drove which unit, when. A row with ended_at
--                          NULL is the current assignment; the partial unique
--                          indexes keep it to one per driver and one per unit,
--                          so two requests at once cannot double-assign.

BEGIN;

CREATE TABLE IF NOT EXISTS dll_drivers (
    driver_uid       VARCHAR(100) PRIMARY KEY,
    client_uid       VARCHAR(100) NOT NULL,
    full_name        VARCHAR(150) NOT NULL,
    phone            VARCHAR(20)  NOT NULL,
    permit_number    VARCHAR(40)  NOT NULL,
    permit_expiry    DATE         NOT NULL,
    permit_classes   VARCHAR(60)  NOT NULL,
    ibutton_id       VARCHAR(20),
    national_id      VARCHAR(20),
    employee_number  VARCHAR(40),
    photo_file       VARCHAR(200),
    emergency_name   VARCHAR(150),
    emergency_phone  VARCHAR(20),
    home_branch      VARCHAR(100),
    notes            TEXT,
    status           VARCHAR(16)  NOT NULL DEFAULT 'active',
    status_reason    TEXT,
    created_by       VARCHAR(100),
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_driver_status
        CHECK (status IN ('active', 'suspended', 'blacklisted', 'inactive'))
);

-- Unique within a client: the same person cannot be registered twice.
CREATE UNIQUE INDEX IF NOT EXISTS uq_driver_phone
    ON dll_drivers (client_uid, phone);
CREATE UNIQUE INDEX IF NOT EXISTS uq_driver_permit
    ON dll_drivers (client_uid, permit_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_driver_ibutton
    ON dll_drivers (client_uid, ibutton_id) WHERE ibutton_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_driver_nin
    ON dll_drivers (client_uid, national_id) WHERE national_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_driver_client
    ON dll_drivers (client_uid, status);

CREATE TABLE IF NOT EXISTS dll_driver_assignments (
    id           SERIAL       PRIMARY KEY,
    driver_uid   VARCHAR(100) NOT NULL REFERENCES dll_drivers (driver_uid),
    device_imei  VARCHAR(40)  NOT NULL,
    client_uid   VARCHAR(100) NOT NULL,
    assigned_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    assigned_by  VARCHAR(100),
    ended_at     TIMESTAMP,
    ended_by     VARCHAR(100),
    end_reason   VARCHAR(40),
    CONSTRAINT chk_assignment_order
        CHECK (ended_at IS NULL OR ended_at >= assigned_at)
);

-- One current assignment per driver, and per unit.
CREATE UNIQUE INDEX IF NOT EXISTS uq_assignment_open_driver
    ON dll_driver_assignments (driver_uid) WHERE ended_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_assignment_open_unit
    ON dll_driver_assignments (device_imei) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_assignment_unit_time
    ON dll_driver_assignments (device_imei, assigned_at DESC);
CREATE INDEX IF NOT EXISTS ix_assignment_driver_time
    ON dll_driver_assignments (driver_uid, assigned_at DESC);

COMMIT;
