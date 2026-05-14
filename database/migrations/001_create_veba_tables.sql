-- VEBA Feature Migration
-- Description: Creates tables and seed data for Vehicle Equipment Booking & Assignment (VEBA) feature


-- Create VEBA enabled units table
CREATE TABLE IF NOT EXISTS dll_veba_enabled_units (
    id SERIAL PRIMARY KEY,
    device_imei_number VARCHAR(50) UNIQUE NOT NULL,
    client_uid VARCHAR(100) NOT NULL,
    veba_status VARCHAR(20) DEFAULT 'available',
    enabled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    enabled_by VARCHAR(100),
    notes TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_veba_device_imei ON dll_veba_enabled_units(device_imei_number);
CREATE INDEX IF NOT EXISTS idx_veba_client_uid ON dll_veba_enabled_units(client_uid);
CREATE INDEX IF NOT EXISTS idx_veba_status ON dll_veba_enabled_units(veba_status);

-- Add VEBA token type to registry (if not exists)
-- Note: Adjust the INSERT based on your token_id generation strategy
INSERT INTO dll_tokens_registry 
(token_type, token_name, token_validity, token_amount, date_created, token_currency, token_parameters, token_id)
SELECT 
    'veba', 
    'VEBA Subscription', 
    2592000, -- 30 days in seconds
    0, 
    NOW(), 
    'KES', 
    '[]',
    gen_random_uuid()
WHERE NOT EXISTS (
    SELECT 1 FROM dll_tokens_registry WHERE token_type = 'veba'
);

-- Add comment to table
COMMENT ON TABLE dll_veba_enabled_units IS 'Tracks units that are enabled for VEBA (Vehicle Equipment Booking & Assignment)';
COMMENT ON COLUMN dll_veba_enabled_units.veba_status IS 'Status of VEBA availability: available, unavailable, suspended';
COMMENT ON COLUMN dll_veba_enabled_units.device_imei_number IS 'IMEI number of the device enabled for VEBA';
COMMENT ON COLUMN dll_veba_enabled_units.client_uid IS 'Client/owner UID of the device';
