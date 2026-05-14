-- ============================================================================
-- 012: Seed Frontend Page-Level Permissions
-- ============================================================================
-- Adds view permissions for all CMS frontend pages.
-- These permissions are checked by the ProtectedRoute component
-- and the Sidebar to control page-level access.
--
-- The existing 008 migration only covered backend module permissions
-- (devices.view, clients.view, etc.). This adds the missing page-level
-- permissions used by the frontend route guards.
-- ============================================================================

-- ── Page-level view permissions ─────────────────────────────────────────────

INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    -- NOC Bridge
    ('perm_noc_view',         'noc.view',         'View NOC Bridge dashboard',           'noc',         'engine', 'system'),
    -- Ops War Room
    ('perm_ops_view',         'ops.view',         'View Ops War Room',                   'ops',         'engine', 'system'),
    -- Gatehouse / Monitoring Alpha
    ('perm_gatehouse_view',   'gatehouse.view',   'View Gatehouse / Monitoring Alpha',   'gatehouse',   'engine', 'system'),
    -- Alarms (view permission already exists as alarms.view? — using the existing naming)
    ('perm_alarms_view',      'alarms.view',      'View Alarm Factory and Alarms Center','alarms',      'engine', 'system'),
    -- Tenants
    ('perm_tenants_view',     'tenants.view',     'View Tenant Tower',                   'tenants',     'engine', 'system'),
    -- Billing
    ('perm_billing_view',     'billing.view',     'View Billing pages',                  'billing',     'engine', 'system'),
    -- Money Switchboard
    ('perm_money_view',       'money.view',       'View Money Switchboard',              'money',       'engine', 'system'),
    -- Protocol Port
    ('perm_protocol_view',    'protocol.view',    'View Protocol Port',                  'protocol',    'engine', 'system'),
    -- Firmware
    ('perm_firmware_view',    'firmware.view',     'View Firmware page',                 'firmware',    'engine', 'system'),
    -- SIM / Signal Vault
    ('perm_sim_view',         'sim.view',         'View Signal Vault / SIM management',  'sim',         'engine', 'system'),
    -- Asset Digital Twin
    ('perm_assets_view',      'assets.view',      'View Asset Digital Twin',             'assets',      'engine', 'system'),
    -- System Health
    ('perm_health_view',      'health.view',      'View System Health dashboard',        'health',      'engine', 'system'),
    -- Tokens
    ('perm_tokens_view',      'tokens.view',      'View Token Engine',                   'tokens',      'engine', 'system'),
    -- Payments
    ('perm_payments_view',    'payments.view',    'View Payments page',                  'payments',    'engine', 'system'),
    -- VEBA Marketplace
    ('perm_veba_view',        'veba.view',        'View VEBA Marketplace',               'veba',        'engine', 'system'),
    -- AI Workloads
    ('perm_ai_view',          'ai.view',          'View AI Workloads',                   'ai',          'engine', 'system')
    -- NOTE: perm_audit_view already seeded in 011_seed_audit_permissions.sql
ON CONFLICT (permission_uid) DO NOTHING;


-- ── Assign all new permissions to super_admin ───────────────────────────────
-- (super_admin gets everything — the SELECT picks up all new permissions)

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
SELECT 'role_super_admin', permission_uid, 'system'
FROM dll_permissions
WHERE account_root = 'engine'
  AND permission_uid NOT IN (SELECT permission_uid FROM dll_role_permissions WHERE role_uid = 'role_super_admin')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- ── Also assign to system role ──────────────────────────────────────────────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
SELECT 'role_system', permission_uid, 'system'
FROM dll_permissions
WHERE account_root = 'engine'
  AND permission_uid NOT IN (SELECT permission_uid FROM dll_role_permissions WHERE role_uid = 'role_system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- ── Assign page-view permissions to admin role too ──────────────────────────

INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_admin', 'perm_noc_view',       'system'),
    ('role_admin', 'perm_ops_view',       'system'),
    ('role_admin', 'perm_gatehouse_view', 'system'),
    ('role_admin', 'perm_alarms_view',    'system'),
    ('role_admin', 'perm_tenants_view',   'system'),
    ('role_admin', 'perm_billing_view',   'system'),
    ('role_admin', 'perm_money_view',     'system'),
    ('role_admin', 'perm_protocol_view',  'system'),
    ('role_admin', 'perm_firmware_view',  'system'),
    ('role_admin', 'perm_sim_view',       'system'),
    ('role_admin', 'perm_assets_view',    'system'),
    ('role_admin', 'perm_health_view',    'system'),
    ('role_admin', 'perm_tokens_view',    'system'),
    ('role_admin', 'perm_payments_view',  'system'),
    ('role_admin', 'perm_veba_view',      'system'),
    ('role_admin', 'perm_ai_view',        'system'),
    ('role_admin', 'perm_audit_view',     'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;


-- ============================================================================
-- IMPORTANT: Make sure your current user has 'super_admin' as their role.
--
-- To check your current user:
--   SELECT account_uid, account_name, account_clearance FROM dll_access_relay WHERE access_status = 'active';
--
-- To promote a user to super_admin:
--   UPDATE dll_access_relay SET account_clearance = 'super_admin' WHERE account_uid = '<your_account_uid>';
-- ============================================================================
