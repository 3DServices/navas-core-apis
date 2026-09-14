-- PPMM Product Catalog seed (Official Product IDs v26)
-- Adds product_code + product_description to abi_products_manager and seeds the
-- official 50-product catalog (idempotent: safe to re-run). product_uid is set
-- to the official 3D-PRD id so rows are stable and match the catalogue.

-- service_type is normally added by migration 027; add it here too (IF NOT
-- EXISTS) so this seed is self-contained even if 027 was skipped.
ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS service_type        VARCHAR(60),
    ADD COLUMN IF NOT EXISTS product_code        VARCHAR(40),
    ADD COLUMN IF NOT EXISTS product_description TEXT;

-- Idempotent: clear any prior catalogue seed, then re-insert (product_uid has
-- no unique constraint here, so we can't use ON CONFLICT).
DELETE FROM abi_products_manager WHERE product_uid LIKE '3D-PRD-%';

INSERT INTO abi_products_manager (product_uid, product_code, product_name, product_description, service_type) VALUES
 ('3D-PRD-001','3D-PRD-001','DASHCAM','Standard DashCAM','AI & Video Telematics'),
 ('3D-PRD-002','3D-PRD-002','DASH AI','DashCAM & ADAS & DSM','AI & Video Telematics'),
 ('3D-PRD-003','3D-PRD-003','MDVR','Mobile Digital Video Recorder','AI & Video Telematics'),
 ('3D-PRD-004','3D-PRD-004','MDVR AI','MDVR & ADAS & DSM','AI & Video Telematics'),
 ('3D-PRD-005','3D-PRD-005','OLIWA / UKO','Basic Car Tracking','Vehicle Telematics'),
 ('3D-PRD-006','3D-PRD-006','OLIWA+','OLIWA & Immobilizer','Vehicle Telematics'),
 ('3D-PRD-007','3D-PRD-007','GUVNA','Speed Governor','Vehicle Telematics'),
 ('3D-PRD-008','3D-PRD-008','iVMS','In Vehicle Monitoring System','Vehicle Telematics'),
 ('3D-PRD-009','3D-PRD-009','iVMS+','iVMS & Sensors','Vehicle Telematics'),
 ('3D-PRD-010','3D-PRD-010','PIKI','Field Staff (Motor Bikes)','Vehicle Telematics'),
 ('3D-PRD-011','3D-PRD-011','MAFTA FLS','iVMS+ & FLS','Fuel Telematics'),
 ('3D-PRD-012','3D-PRD-012','MAFTA CANBUS','iVMS & FLS & CANbus','Fuel Telematics'),
 ('3D-PRD-013','3D-PRD-013','MAFTA FLOW','iVMS & FLS & Flow Meter','Fuel Telematics'),
 ('3D-PRD-014','3D-PRD-014','MAFTA STATION','Forecourt Pumps & ATG & AVI','Fuel Telematics'),
 ('3D-PRD-015','3D-PRD-015','MAFTA CARD','MAFTA STN + Fuel Card','Fuel Telematics'),
 ('3D-PRD-016','3D-PRD-016','GENSET','Genset & FLS','Fuel Telematics'),
 ('3D-PRD-017','3D-PRD-017','ANIMO','Animal Tracking, Livestock & Pets','Goods & IoT'),
 ('3D-PRD-018','3D-PRD-018','BARIDI','Fridges, Coolers, Reefers, ColdRooms','Goods & IoT'),
 ('3D-PRD-019','3D-PRD-019','CIT','Cash In Transit','Goods & IoT'),
 ('3D-PRD-020','3D-PRD-020','KAGO','eLock Cargo Tracking','Goods & IoT'),
 ('3D-PRD-021','3D-PRD-021','PAWA','Genset Fuel & Mains Power','Goods & IoT'),
 ('3D-PRD-022','3D-PRD-022','PASO','Parcels & Packages','Goods & IoT'),
 ('3D-PRD-023','3D-PRD-023','BODY CAM','Field Staff (Pocket Camera)','Personnel Tracing'),
 ('3D-PRD-024','3D-PRD-024','CAPO','Field Staff GPS Watch','Personnel Tracing'),
 ('3D-PRD-025','3D-PRD-025','PATROL','Field Staff (Clock-In) Site Roll Call','Personnel Tracing'),
 ('3D-PRD-026','3D-PRD-026','TOTO','School Kids','Personnel Tracing'),
 ('3D-PRD-027','3D-PRD-027','WIATAG','Field Staff (SmartPhone)','Personnel Tracing'),
 ('3D-PRD-028','3D-PRD-028','DASH BI','BI Dashboards','Add-on-Apps'),
 ('3D-PRD-029','3D-PRD-029','DSC','Driver Scorecard','Add-on-Apps'),
 ('3D-PRD-030','3D-PRD-030','ECO','Harsh Driving Behaviour','Add-on-Apps'),
 ('3D-PRD-031','3D-PRD-031','EPOD','Electronic Proof of Delivery','Add-on-Apps'),
 ('3D-PRD-032','3D-PRD-032','EV','Electric Vehicles & Charge App','Add-on-Apps'),
 ('3D-PRD-033','3D-PRD-033','FRITI','Freewheeling & Engine Coasting','Add-on-Apps'),
 ('3D-PRD-034','3D-PRD-034','HPO','Heavy Plant Operations','Add-on-Apps'),
 ('3D-PRD-035','3D-PRD-035','INSPECTA','Pre Maintenance Asset Inspection','Add-on-Apps'),
 ('3D-PRD-036','3D-PRD-036','JAM','Street Traffic Jam & Quickest Route','Add-on-Apps'),
 ('3D-PRD-037','3D-PRD-037','JMS','Fatigue & Journey Management','Add-on-Apps'),
 ('3D-PRD-038','3D-PRD-038','LOGISTICS','First & Last Mile Logistics','Add-on-Apps'),
 ('3D-PRD-039','3D-PRD-039','MARINE','Boats, Yatches Satelite tracking','Add-on-Apps'),
 ('3D-PRD-040','3D-PRD-040','PIPO','People Certification & Accreditation','Add-on-Apps'),
 ('3D-PRD-041','3D-PRD-041','PROXIMITY','Retail BLE Beacons & RFIDs','Add-on-Apps'),
 ('3D-PRD-042','3D-PRD-042','PSV','Passenger Service Vehicles & Buses','Add-on-Apps'),
 ('3D-PRD-043','3D-PRD-043','TAWA','Power & Telco Site Security','Add-on-Apps'),
 ('3D-PRD-044','3D-PRD-044','TOW','Roadside Rescue Desk, ETA, Routes','Add-on-Apps'),
 ('3D-PRD-045','3D-PRD-045','TRAILERS','Field Staff (SmartPhone)','Add-on-Apps'),
 ('3D-PRD-046','3D-PRD-046','UBI','User Based Insurance','Add-on-Apps'),
 ('3D-PRD-047','3D-PRD-047','VEBA','VEBA APP','Add-on-Apps'),
 ('3D-PRD-048','3D-PRD-048','WORKSHOP','FleetRun APP','Add-on-Apps'),
 ('3D-PRD-049','3D-PRD-049','YARD & DOCK','Loads, Gateflow, Ports & Deports','Add-on-Apps'),
 ('3D-PRD-050','3D-PRD-050','LOCAL- SERVER','Server on Site','Add-on-Apps');

COMMENT ON COLUMN abi_products_manager.product_code IS
    'Official catalogue product code (e.g. 3D-PRD-047).';
