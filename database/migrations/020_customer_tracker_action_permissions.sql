-- ============================================================================
-- 020: Add Action-Level Permissions to customer_tracker Role
-- ============================================================================
-- Migration 019 gave customer_tracker the 9 module-view permissions needed
-- to navigate Oliwa pages. However, each page also checks action-level
-- `can_*` permissions for individual buttons and API calls. Without these,
-- the customer sees "Permission denied" on every action.
--
-- This migration:
--   1. Creates two missing permissions (can_archive_booking_request,
--      can_delete_booking_request) that the backend enforces but were not
--      in the catalog seed.
--   2. Grants ALL VEBA marketplace action permissions to customer_tracker.
--   3. Grants geofence action permissions to customer_tracker.
--
-- Idempotent: ON CONFLICT ... DO NOTHING on all inserts.
-- ============================================================================


-- ── 1. Create permissions that are used by backend but missing from seed ────

INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_archive_booking_request', 'can_archive_booking_request', 'Archive a VEBA booking request',  'veba_booking', 'engine', 'system'),
    ('perm_can_delete_booking_request',  'can_delete_booking_request',  'Delete a VEBA booking request',   'veba_booking', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;


-- ── 2. Grant all VEBA action permissions to customer_tracker ────────────────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    -- Browse & view
    ('role_customer_tracker', 'perm_can_browse_asset_listings',       'system'),
    ('role_customer_tracker', 'perm_can_view_unit_digital_twin',      'system'),
    ('role_customer_tracker', 'perm_can_view_booking',                'system'),

    -- Create & edit listings
    ('role_customer_tracker', 'perm_can_list_asset_on_marketplace',   'system'),
    ('role_customer_tracker', 'perm_can_edit_asset_listing',          'system'),

    -- Booking actions
    ('role_customer_tracker', 'perm_can_book_asset',                  'system'),
    ('role_customer_tracker', 'perm_can_approve_booking_request',     'system'),
    ('role_customer_tracker', 'perm_can_reject_booking_request',      'system'),
    ('role_customer_tracker', 'perm_can_archive_booking_request',     'system'),
    ('role_customer_tracker', 'perm_can_delete_booking_request',      'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ── 3. Grant geofence action permissions to customer_tracker ────────────────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_customer_tracker', 'perm_can_create_geofence', 'system'),
    ('role_customer_tracker', 'perm_can_edit_geofence',   'system'),
    ('role_customer_tracker', 'perm_can_delete_geofence', 'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ── 4. Also grant the two new permissions to super_admin / system / admin ───

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_super_admin', 'perm_can_archive_booking_request', 'system'),
    ('role_super_admin', 'perm_can_delete_booking_request',  'system'),
    ('role_system',      'perm_can_archive_booking_request', 'system'),
    ('role_system',      'perm_can_delete_booking_request',  'system'),
    ('role_admin',       'perm_can_archive_booking_request', 'system'),
    ('role_admin',       'perm_can_delete_booking_request',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ============================================================================
-- VERIFICATION QUERY:
--
--   SELECT p.permission_name
--   FROM dll_role_permissions rp
--   JOIN dll_permissions p ON rp.permission_uid = p.permission_uid
--   WHERE rp.role_uid = 'role_customer_tracker'
--   ORDER BY p.permission_name;
--
-- Expected: 22 rows (9 view + 10 VEBA action + 3 geofence action)
-- ============================================================================
