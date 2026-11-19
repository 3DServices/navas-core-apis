-- Migration 061: driver scoring rules per client
-- Description: dll_driver_score_configs (the rules a driver scorecard deducts
-- by, endpoints/driver_scoring.py) belongs to a client from now on. Until
-- this, the table had no owner, so every client would have shared one set of
-- rules -- and the routes were never registered, so nothing could write it.
--
-- Rows already in the table keep client_uid NULL: no client is scored by
-- them. A client with no rules of its own is scored by the built-in defaults
-- (driver_scoring.default_rules) until it saves its own.
--
-- The table is created here if it does not exist, with the columns the old
-- routes used. Safe to run again.

CREATE TABLE IF NOT EXISTS dll_driver_score_configs (
    score_uid            VARCHAR(100) PRIMARY KEY,
    score_name           VARCHAR(100),
    score_order          VARCHAR(30),
    score_points_order   VARCHAR(30),
    violation_parameter  VARCHAR(60),
    points_denomination  VARCHAR(20)
);

ALTER TABLE dll_driver_score_configs
    ADD COLUMN IF NOT EXISTS client_uid VARCHAR(100);

-- The most one rule may take off a driver in a period (NULL: no limit), so a
-- single habit cannot wipe out a score on its own if the client so chooses.
ALTER TABLE dll_driver_score_configs
    ADD COLUMN IF NOT EXISTS max_deduction INTEGER;

ALTER TABLE dll_driver_score_configs
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

ALTER TABLE dll_driver_score_configs
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- One rule per violation per client.
CREATE UNIQUE INDEX IF NOT EXISTS uq_driver_score_client_violation
    ON dll_driver_score_configs (client_uid, violation_parameter)
    WHERE client_uid IS NOT NULL;
