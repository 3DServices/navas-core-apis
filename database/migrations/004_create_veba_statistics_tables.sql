-- VEBA Statistics Tracking Migration
-- Description: Creates table to track VEBA bookings, leakage attempts, and settlement times

-- Create VEBA statistics table
CREATE TABLE IF NOT EXISTS dll_veba_statistics (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL, -- 'booking', 'leakage_attempt'
    device_imei_number VARCHAR(50),
    client_uid VARCHAR(100),
    settlement_time_minutes INTEGER, -- Settlement time in minutes (for p95 calculation)
    event_data JSONB, -- Additional event metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_veba_stats_event_type ON dll_veba_statistics(event_type);
CREATE INDEX IF NOT EXISTS idx_veba_stats_created_at ON dll_veba_statistics(created_at);
CREATE INDEX IF NOT EXISTS idx_veba_stats_event_type_date ON dll_veba_statistics(event_type, created_at);

-- Add comments
COMMENT ON TABLE dll_veba_statistics IS 'Tracks VEBA bookings, leakage attempts, and settlement times for statistics';
COMMENT ON COLUMN dll_veba_statistics.event_type IS 'Type of event: booking, leakage_attempt';
COMMENT ON COLUMN dll_veba_statistics.settlement_time_minutes IS 'Settlement time in minutes for p95 calculation';

-- Insert sample data for testing
INSERT INTO dll_veba_statistics (event_type, device_imei_number, client_uid, settlement_time_minutes, created_at) VALUES
-- Today's bookings (184 records spread throughout the day)
('booking', '123456789012345', 'client-uuid-1', 15, CURRENT_DATE + INTERVAL '8 hours'),
('booking', '123456789012346', 'client-uuid-2', 12, CURRENT_DATE + INTERVAL '8 hours 15 minutes'),
('booking', '123456789012347', 'client-uuid-3', 18, CURRENT_DATE + INTERVAL '8 hours 30 minutes'),
('booking', '123456789012348', 'client-uuid-4', 20, CURRENT_DATE + INTERVAL '9 hours'),
('booking', '123456789012349', 'client-uuid-5', 16, CURRENT_DATE + INTERVAL '9 hours 30 minutes'),
('booking', '123456789012350', 'client-uuid-6', 14, CURRENT_DATE + INTERVAL '10 hours'),
('booking', '123456789012351', 'client-uuid-7', 22, CURRENT_DATE + INTERVAL '10 hours 30 minutes'),
('booking', '123456789012352', 'client-uuid-8', 19, CURRENT_DATE + INTERVAL '11 hours'),
('booking', '123456789012353', 'client-uuid-9', 17, CURRENT_DATE + INTERVAL '11 hours 30 minutes'),
('booking', '123456789012354', 'client-uuid-10', 13, CURRENT_DATE + INTERVAL '12 hours'),

-- Leakage attempts today (17 records)
('leakage_attempt', '987654321098765', 'client-uuid-11', NULL, CURRENT_DATE + INTERVAL '9 hours'),
('leakage_attempt', '987654321098766', 'client-uuid-12', NULL, CURRENT_DATE + INTERVAL '10 hours'),
('leakage_attempt', '987654321098767', 'client-uuid-13', NULL, CURRENT_DATE + INTERVAL '11 hours'),
('leakage_attempt', '987654321098768', 'client-uuid-14', NULL, CURRENT_DATE + INTERVAL '12 hours'),
('leakage_attempt', '987654321098769', 'client-uuid-15', NULL, CURRENT_DATE + INTERVAL '13 hours'),

-- Yesterday's data (for comparison)
('booking', '123456789012355', 'client-uuid-16', 21, CURRENT_DATE - INTERVAL '1 day' + INTERVAL '10 hours'),
('booking', '123456789012356', 'client-uuid-17', 19, CURRENT_DATE - INTERVAL '1 day' + INTERVAL '11 hours'),
('leakage_attempt', '987654321098770', 'client-uuid-18', NULL, CURRENT_DATE - INTERVAL '1 day' + INTERVAL '12 hours');

-- Generate more sample bookings to reach 184 total for today
-- This uses generate_series to create realistic booking data
INSERT INTO dll_veba_statistics (event_type, device_imei_number, client_uid, settlement_time_minutes, created_at)
SELECT 
    'booking',
    '12345678901' || LPAD(gs::text, 4, '0'),
    'client-uuid-' || gs,
    (10 + (random() * 20)::integer), -- Random settlement time between 10-30 minutes
    CURRENT_DATE + (INTERVAL '8 hours') + (gs * INTERVAL '4 minutes') -- Spread throughout the day
FROM generate_series(1, 174) AS gs;

-- Generate remaining leakage attempts to reach 17 total for today
INSERT INTO dll_veba_statistics (event_type, device_imei_number, client_uid, settlement_time_minutes, created_at)
SELECT 
    'leakage_attempt',
    '98765432109' || LPAD(gs::text, 4, '0'),
    'client-uuid-leak-' || gs,
    NULL,
    CURRENT_DATE + (INTERVAL '8 hours') + (gs * INTERVAL '45 minutes')
FROM generate_series(1, 12) AS gs;
