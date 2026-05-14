-- Migration: Create gateway monitoring table
-- Created: 2026-03-04
-- Description: Simple table for tracking mobile money gateway status messages

-- Gateway status table - stores current and historical status messages
CREATE TABLE IF NOT EXISTS dll_gateway_status (
    id SERIAL PRIMARY KEY,
    telecom VARCHAR(100) NOT NULL,
    api_status VARCHAR(50) NOT NULL,
    message TEXT,
    is_current_message BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries on current messages
CREATE INDEX IF NOT EXISTS idx_gateway_status_current ON dll_gateway_status(telecom, is_current_message) WHERE is_current_message = TRUE;
CREATE INDEX IF NOT EXISTS idx_gateway_status_created_at ON dll_gateway_status(created_at DESC);

-- Insert sample gateway status data
INSERT INTO dll_gateway_status (telecom, api_status, message, is_current_message) VALUES
('M-Pesa KE', 'OK', 'success 98.9% • p95 9.2s', TRUE),
('MTN MoMo UG', 'OK', 'success 97.6% • p95 11.4s', TRUE),
('Airtel UG', 'DEGRADED', 'success 91.2% • webhook fail 6.7%', TRUE),
('Airtel KE', 'OK', 'success 96.8% • settle delay 18m', TRUE);

COMMENT ON TABLE dll_gateway_status IS 'Mobile money gateway status and monitoring messages';
COMMENT ON COLUMN dll_gateway_status.telecom IS 'Gateway/telecom name (e.g., M-Pesa KE, MTN MoMo UG)';
COMMENT ON COLUMN dll_gateway_status.api_status IS 'Current status (OK, DEGRADED, DOWN, MAINTENANCE)';
COMMENT ON COLUMN dll_gateway_status.message IS 'Status message with metrics (e.g., success rate, latency)';
COMMENT ON COLUMN dll_gateway_status.is_current_message IS 'TRUE for current status, FALSE for historical records';
