-- 057_fuel_voucher_number.sql
--
-- Fuel Refill (formerly FuelMath): the number of the fuel voucher a driver
-- hands over at the pump, recorded with the refill (endpoints/fuel_rules.py).
-- Optional. Like the receipt number, one voucher is used once per client --
-- a voided refill frees its voucher.

BEGIN;

ALTER TABLE dll_fuel_issues ADD COLUMN IF NOT EXISTS voucher_number VARCHAR(60);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fuel_voucher
    ON dll_fuel_issues (client_uid, voucher_number)
    WHERE voucher_number IS NOT NULL AND voided_at IS NULL;

COMMIT;
