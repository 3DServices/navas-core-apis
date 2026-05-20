-- ============================================================
-- 017: Flag accounts still using legacy (non-bcrypt) passwords
-- ============================================================
-- After removing the base64 fallback from the login code, any
-- account whose log_password does NOT start with '$2' can no
-- longer authenticate.
--
-- This migration:
--   1. Identifies those accounts.
--   2. Marks them with access_status = 'password_reset_required'
--      so they appear in the admin panel for manual reset.
--
-- An admin can then use PUT /users/<uid>/reset-password to give
-- the user a temporary password (which will be stored as bcrypt).
-- ============================================================

-- Step 1: Audit — list affected accounts (run as SELECT first to review)
-- SELECT account_uid, log_username, display_name, access_status
-- FROM dll_access_relay
-- WHERE log_password IS NOT NULL
--   AND log_password NOT LIKE '$2%';

-- Step 2: Flag them
UPDATE dll_access_relay
SET    access_status = 'password_reset_required'
WHERE  log_password IS NOT NULL
  AND  log_password NOT LIKE '$2%'
  AND  access_status = 'active';
