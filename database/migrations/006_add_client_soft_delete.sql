-- Client Soft Delete Feature Migration
-- Description: Adds soft delete capability to client accounts with is_deleted flag and deleted_at timestamp

-- Add is_deleted column to dll_client_accounts
ALTER TABLE dll_client_accounts 
ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;

-- Add deleted_at column to track when client was trashed
ALTER TABLE dll_client_accounts 
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL;

-- Add deleted_by column to track who deleted the client
ALTER TABLE dll_client_accounts 
ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(100) NULL;

-- Create index for filtering trashed clients
CREATE INDEX IF NOT EXISTS idx_client_is_deleted ON dll_client_accounts(is_deleted);

-- Add comments
COMMENT ON COLUMN dll_client_accounts.is_deleted IS 'Soft delete flag - TRUE if client is trashed';
COMMENT ON COLUMN dll_client_accounts.deleted_at IS 'Timestamp when client was moved to trash';
COMMENT ON COLUMN dll_client_accounts.deleted_by IS 'User/account that deleted the client';
