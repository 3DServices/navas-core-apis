-- ============================================================================
-- 019: Seed Customer Tracker Role & Oliwa Portal Permissions
-- ============================================================================
-- Creates permissions and a pre-built role for customer accounts that need
-- access to the Oliwa tracking console.
--
-- The Oliwa frontend gates navigation using `<module>.view` permissions.
-- Six of the nine needed permissions already exist (reports.view, events.view,
-- sim.view, veba.view, rbac.view, audit.view). This migration adds the
-- three missing ones and bundles all nine into a "customer_tracker" role.
--
-- When CMS operators create a Customer account and assign this role, the
-- customer can log into Oliwa and see exactly those nine modules.
--
-- Idempotent: ON CONFLICT ... DO NOTHING on all inserts.
-- ============================================================================


-- ── 1. Add the three missing Oliwa page-view permissions ───────────────────

INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    -- Live Monitoring / Fleet Map
    ('perm_live_monitoring_view', 'live.monitoring.view', 'View Oliwa live monitoring map and fleet overview', 'live_monitoring', 'engine', 'system'),
    -- Track Playback / Trip Replay
    ('perm_track_playback_view', 'track.playback.view',  'View Oliwa trip replay and track playback',         'track_playback',  'engine', 'system'),
    -- Geofences (Oliwa module — distinct from CMS geozones)
    ('perm_geofences_view',      'geofences.view',       'View Oliwa geofences and geo-zone boundaries',      'geofences',       'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;


-- ── 2. Also grant the new permissions to super_admin and system roles ──────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_super_admin', 'perm_live_monitoring_view', 'system'),
    ('role_super_admin', 'perm_track_playback_view',  'system'),
    ('role_super_admin', 'perm_geofences_view',       'system'),
    ('role_system',      'perm_live_monitoring_view', 'system'),
    ('role_system',      'perm_track_playback_view',  'system'),
    ('role_system',      'perm_geofences_view',       'system'),
    ('role_admin',       'perm_live_monitoring_view', 'system'),
    ('role_admin',       'perm_track_playback_view',  'system'),
    ('role_admin',       'perm_geofences_view',       'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ── 3. Create the "customer_tracker" role ──────────────────────────────────

INSERT INTO dll_roles (role_uid, role_name, role_description, account_root, created_by)
VALUES (
    'role_customer_tracker',
    'customer_tracker',
    'Default role for customer accounts — grants access to all 9 Oliwa tracking console modules (live monitoring, playback, reports, geofences, events, SIM, VEBA, RBAC, audit)',
    'engine',
    'system'
)
ON CONFLICT (role_uid) DO NOTHING;


-- ── 4. Assign the 9 Oliwa permissions to customer_tracker ─────────────────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    -- The 3 new Oliwa-specific permissions
    ('role_customer_tracker', 'perm_live_monitoring_view', 'system'),
    ('role_customer_tracker', 'perm_track_playback_view',  'system'),
    ('role_customer_tracker', 'perm_geofences_view',       'system'),
    -- The 6 already-existing permissions
    ('role_customer_tracker', 'perm_reports_view',         'system'),
    ('role_customer_tracker', 'perm_events_view',          'system'),
    ('role_customer_tracker', 'perm_sim_view',             'system'),
    ('role_customer_tracker', 'perm_veba_view',            'system'),
    ('role_customer_tracker', 'perm_rbac_view',            'system'),
    ('role_customer_tracker', 'perm_audit_view',           'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ============================================================================
-- VERIFICATION QUERIES (run manually to confirm):
--
--   -- Check the role exists:
--   SELECT * FROM dll_roles WHERE role_uid = 'role_customer_tracker';
--
--   -- Check all 9 permissions are assigned:
--   SELECT p.permission_name, p.permission_description
--   FROM dll_role_permissions rp
--   JOIN dll_permissions p ON rp.permission_uid = p.permission_uid
--   WHERE rp.role_uid = 'role_customer_tracker'
--   ORDER BY p.permission_name;
--
-- Expected output: 9 rows —
--   audit.view, events.view, geofences.view, live.monitoring.view,
--   rbac.view, reports.view, sim.view, track.playback.view, veba.view
-- ============================================================================
