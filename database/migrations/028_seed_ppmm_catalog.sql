-- Migration 028 — Seed the PPMM add-on apps catalogue.
--
-- Adds the catalogue metadata columns to abi_products_manager (idempotent) and
-- seeds the official Add-on-Apps (Official Product IDs v26, 3D-PRD-028..050) so
-- mobile clients can browse and subscribe via GET /billing/products/addons.
--
-- product_uid is NOT unique in this table, so we make the seed idempotent by
-- deleting the 3D-PRD-% rows first, then re-inserting.

ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS service_type         VARCHAR(60);
ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS product_code         VARCHAR(40);
ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS product_description  TEXT;

DELETE FROM abi_products_manager WHERE product_uid LIKE '3D-PRD-%';

INSERT INTO abi_products_manager
    (product_uid, product_name, service_type, product_code, product_description)
VALUES
    ('3D-PRD-028', 'dash bi',       'Add-on-Apps', '3D-PRD-028', 'BI Dashboards'),
    ('3D-PRD-029', 'dsc',           'Add-on-Apps', '3D-PRD-029', 'Driver Scorecard'),
    ('3D-PRD-030', 'eco',           'Add-on-Apps', '3D-PRD-030', 'Harsh Driving Behaviour'),
    ('3D-PRD-031', 'epod',          'Add-on-Apps', '3D-PRD-031', 'Electronic Proof of Delivery'),
    ('3D-PRD-032', 'ev',            'Add-on-Apps', '3D-PRD-032', 'Electric Vehicles & Charge App'),
    ('3D-PRD-033', 'friti',         'Add-on-Apps', '3D-PRD-033', 'Freewheeling & Engine Coasting'),
    ('3D-PRD-034', 'hpo',           'Add-on-Apps', '3D-PRD-034', 'Heavy Plant Operations'),
    ('3D-PRD-035', 'inspecta',      'Add-on-Apps', '3D-PRD-035', 'Pre Maintenance Asset Inspection'),
    ('3D-PRD-036', 'jam',           'Add-on-Apps', '3D-PRD-036', 'Street Traffic Jam & Quickest Route'),
    ('3D-PRD-037', 'jms',           'Add-on-Apps', '3D-PRD-037', 'Fatigue & Journey Management'),
    ('3D-PRD-038', 'logistics',     'Add-on-Apps', '3D-PRD-038', 'First & Last Mile Logistics'),
    ('3D-PRD-039', 'marine',        'Add-on-Apps', '3D-PRD-039', 'Boats, Yatches Satelite tracking'),
    ('3D-PRD-040', 'pipo',          'Add-on-Apps', '3D-PRD-040', 'People Certification & Accreditation'),
    ('3D-PRD-041', 'proximity',     'Add-on-Apps', '3D-PRD-041', 'Retail BLE Beacons & RFIDs'),
    ('3D-PRD-042', 'psv',           'Add-on-Apps', '3D-PRD-042', 'Passenger Service Vehicles & Buses'),
    ('3D-PRD-043', 'tawa',          'Add-on-Apps', '3D-PRD-043', 'Power & Telco Site Security'),
    ('3D-PRD-044', 'tow',           'Add-on-Apps', '3D-PRD-044', 'Roadside Rescue Desk, ETA, Routes'),
    ('3D-PRD-045', 'trailers',      'Add-on-Apps', '3D-PRD-045', 'Trailer & Asset Tracking'),
    ('3D-PRD-046', 'ubi',           'Add-on-Apps', '3D-PRD-046', 'User Based Insurance'),
    ('3D-PRD-047', 'veba',          'Add-on-Apps', '3D-PRD-047', 'VEBA APP'),
    ('3D-PRD-048', 'workshop',      'Add-on-Apps', '3D-PRD-048', 'FleetRun APP'),
    ('3D-PRD-049', 'yard & dock',   'Add-on-Apps', '3D-PRD-049', 'Loads, Gateflow, Ports & Deports'),
    ('3D-PRD-050', 'local- server', 'Add-on-Apps', '3D-PRD-050', 'Server on Site');
