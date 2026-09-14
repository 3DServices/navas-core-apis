-- User Profile Fields Migration
-- Description: Adds a profile picture URL and date of birth to user accounts
-- (dll_access_relay). date_of_birth powers birthday marketing; profile_pic
-- stores the relative URL of an uploaded avatar served by the users blueprint.

ALTER TABLE dll_access_relay
    ADD COLUMN IF NOT EXISTS profile_pic   VARCHAR(255),
    ADD COLUMN IF NOT EXISTS date_of_birth DATE;

COMMENT ON COLUMN dll_access_relay.profile_pic IS
    'Relative URL of the account avatar, e.g. /users/profile-photos/<file>.';
COMMENT ON COLUMN dll_access_relay.date_of_birth IS
    'Account holder date of birth (used for birthday marketing).';
