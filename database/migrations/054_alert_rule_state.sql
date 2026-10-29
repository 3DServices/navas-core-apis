-- 054_alert_rule_state.sql
--
-- What the alert engine remembers between sweeps, for every condition other
-- than geofences (which keep dll_geozone_presence, one row per unit per zone).
--
-- An alert is sent when an answer CHANGES — the vehicle went over the limit,
-- the ignition went off, the unit fell silent — so the engine has to know the
-- previous answer. One row per rule per unit:
--   condition      the rule's condition when the state was written; a rule
--                  edited to another condition starts again from no state
--   state          the evaluator's memory, e.g. {"over": true} for speed,
--                  {"ignition": "OFF"}, {"offline": false}
--   last_alert_at  when this rule last alerted about this unit
--
-- dll_alert_unit_cursor is where each unit's positions were read up to
-- (record_timestamp, UTC), so a sweep reads only fixes it has not seen. A unit
-- with no row starts from its newest fix.
--
-- Only creates; changes no existing row. Safe to run more than once.

CREATE TABLE IF NOT EXISTS dll_alert_rule_state (
    event_uid      VARCHAR(64)  NOT NULL,
    device_imei    VARCHAR(64)  NOT NULL,
    condition      VARCHAR(40)  NOT NULL,
    state          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    last_alert_at  TIMESTAMP,
    updated_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_uid, device_imei)
);

CREATE INDEX IF NOT EXISTS idx_alert_rule_state_unit
    ON dll_alert_rule_state (device_imei);

CREATE TABLE IF NOT EXISTS dll_alert_unit_cursor (
    device_imei    VARCHAR(64)  PRIMARY KEY,
    last_fix_utc   TIMESTAMP    NOT NULL,
    updated_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dll_alert_rule_state IS
    'Last answer per event rule per unit (endpoints/alert_engine.py); an alert '
    'is sent only when it changes.';
COMMENT ON TABLE dll_alert_unit_cursor IS
    'Newest position (record_timestamp, UTC) the alert engine has evaluated '
    'per unit.';
