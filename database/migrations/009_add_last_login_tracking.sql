-- Last Login Tracking Migration
-- Description: Adds last_login_at column to dll_access_relay to track active login sessions

-- Add last_login_at column
ALTER TABLE dll_access_relay
ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP NULL;

-- Create index for querying actively logged in users
CREATE INDEX IF NOT EXISTS idx_access_relay_last_login ON dll_access_relay(last_login_at);

-- Comments
COMMENT ON COLUMN dll_access_relay.last_login_at IS 'Timestamp of the users most recent login';
