-- 055_fuel_driver_optional.sql
--
-- A fuel issue no longer needs a driver. When the app sends none, the server
-- uses whoever was assigned to the vehicle at the time on the receipt; when
-- nobody was, the issue is stored without one and carries a 'no_driver'
-- notice. The reference to dll_drivers stays: a driver that IS recorded must
-- still be one of the client's drivers.
--
-- Run after 053. Changes no row. Safe to run more than once.

ALTER TABLE dll_fuel_issues ALTER COLUMN driver_uid DROP NOT NULL;
