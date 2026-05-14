-- Migration: Fix token_hours_left data type
-- Description: Change token_hours_left from TEXT to NUMERIC for proper numeric comparisons
-- Date: 2026-01-26

-- Alter the token_hours_left column type from TEXT to NUMERIC
ALTER TABLE dll_user_token_accounts 
ALTER COLUMN token_hours_left TYPE NUMERIC USING CAST(token_hours_left AS NUMERIC);

ALTER TABLE dll_user_token_accounts 
ALTER COLUMN token_hours_used TYPE NUMERIC USING CAST(token_hours_used AS NUMERIC);

-- Add comments
COMMENT ON COLUMN dll_user_token_accounts.token_hours_left IS 'Remaining token hours (stored as NUMERIC for calculations)';
COMMENT ON COLUMN dll_user_token_accounts.token_hours_used IS 'Used token hours (stored as NUMERIC for calculations)';
