-- Product service-type Migration
-- Description: Adds a service_type (category) to billing products so the mobile
-- "Buy by budget" product dropdown can render "Service Type - Product Name"
-- (e.g. "AI Video - Dashcam", "Fuel - Mafuta FLS", "Vehicles - Oliwa",
-- "Add-on-App - VEBA"). Admins set the type per product.

ALTER TABLE abi_products_manager
    ADD COLUMN IF NOT EXISTS service_type VARCHAR(60);

COMMENT ON COLUMN abi_products_manager.service_type IS
    'Category prefix shown before the product name (AI Video, Fuel, Vehicles, Add-on-App, ...).';

-- ── OPTIONAL SEED ────────────────────────────────────────────────────────────
-- Fill in the correct service type for each EXISTING product, then run these.
-- (Product names are stored lowercase.) Examples — edit to match your catalogue:
--
-- UPDATE abi_products_manager SET service_type='AI Video'    WHERE product_name IN ('dashcam','dash ai','mdvr','mdvr ai');
-- UPDATE abi_products_manager SET service_type='Fuel'        WHERE product_name IN ('mafuta fls','mafuta station','mafuta canbus','mafuta flow');
-- UPDATE abi_products_manager SET service_type='Vehicles'    WHERE product_name IN ('oliwa','oliwa plus','ivms','ivms plus','guvnor');
-- UPDATE abi_products_manager SET service_type='Add-on-App'  WHERE product_name IN ('veba','epod');
