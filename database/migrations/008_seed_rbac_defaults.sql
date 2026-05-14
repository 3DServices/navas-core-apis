-- Seed Default RBAC Roles & Permissions
-- Description: Populates default roles, permissions (per module), and role-permission mappings
-- These are system-level defaults under account_root = 'engine'

-- ==========================================
-- DEFAULT PERMISSIONS (grouped by module)
-- ==========================================

-- Devices module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_devices_view',   'devices.view',   'View devices and device details',          'devices', 'engine', 'system'),
    ('perm_devices_create', 'devices.create', 'Register and onboard new devices',         'devices', 'engine', 'system'),
    ('perm_devices_edit',   'devices.edit',   'Edit device settings and configuration',   'devices', 'engine', 'system'),
    ('perm_devices_delete', 'devices.delete', 'Remove or decommission devices',           'devices', 'engine', 'system'),
    ('perm_devices_command','devices.command','Send commands to devices (block/restore)',  'devices', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Clients module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_clients_view',   'clients.view',   'View client accounts',           'clients', 'engine', 'system'),
    ('perm_clients_create', 'clients.create', 'Create new client accounts',     'clients', 'engine', 'system'),
    ('perm_clients_edit',   'clients.edit',   'Edit client account details',    'clients', 'engine', 'system'),
    ('perm_clients_delete', 'clients.delete', 'Delete client accounts',         'clients', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Users module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_users_view',     'users.view',          'View user accounts',                 'users', 'engine', 'system'),
    ('perm_users_create',   'users.create',        'Create new user accounts',           'users', 'engine', 'system'),
    ('perm_users_edit',     'users.edit',          'Edit user account details',          'users', 'engine', 'system'),
    ('perm_users_delete',   'users.delete',        'Block or lock user accounts',        'users', 'engine', 'system'),
    ('perm_users_reset_pwd','users.reset_password','Reset user passwords',               'users', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Groups module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_groups_view',   'groups.view',   'View device groups',           'groups', 'engine', 'system'),
    ('perm_groups_create', 'groups.create', 'Create device groups',         'groups', 'engine', 'system'),
    ('perm_groups_edit',   'groups.edit',   'Edit device groups',           'groups', 'engine', 'system'),
    ('perm_groups_delete', 'groups.delete', 'Delete device groups',         'groups', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Geozones module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_geozones_view',   'geozones.view',   'View geozones',           'geozones', 'engine', 'system'),
    ('perm_geozones_create', 'geozones.create', 'Create geozones',         'geozones', 'engine', 'system'),
    ('perm_geozones_edit',   'geozones.edit',   'Edit geozones',           'geozones', 'engine', 'system'),
    ('perm_geozones_delete', 'geozones.delete', 'Delete geozones',         'geozones', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Drivers module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_drivers_view',   'drivers.view',   'View drivers',              'drivers', 'engine', 'system'),
    ('perm_drivers_create', 'drivers.create', 'Create driver profiles',    'drivers', 'engine', 'system'),
    ('perm_drivers_edit',   'drivers.edit',   'Edit driver profiles',      'drivers', 'engine', 'system'),
    ('perm_drivers_delete', 'drivers.delete', 'Delete driver profiles',    'drivers', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Finance module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_finance_view',     'finance.view',     'View financial records and invoices',   'finance', 'engine', 'system'),
    ('perm_finance_create',   'finance.create',   'Create invoices and billing records',   'finance', 'engine', 'system'),
    ('perm_finance_edit',     'finance.edit',     'Edit financial records',                'finance', 'engine', 'system'),
    ('perm_finance_approve',  'finance.approve',  'Approve payments and transactions',     'finance', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Reports module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_reports_view',     'reports.view',     'View and generate reports',    'reports', 'engine', 'system'),
    ('perm_reports_export',   'reports.export',   'Export reports to file',       'reports', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Events module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_events_view',   'events.view',   'View device events and alerts',      'events', 'engine', 'system'),
    ('perm_events_manage', 'events.manage', 'Configure event rules and alerts',   'events', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Gateways module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_gateways_view',   'gateways.view',   'View gateways',           'gateways', 'engine', 'system'),
    ('perm_gateways_create', 'gateways.create', 'Register new gateways',   'gateways', 'engine', 'system'),
    ('perm_gateways_edit',   'gateways.edit',   'Edit gateway settings',   'gateways', 'engine', 'system'),
    ('perm_gateways_delete', 'gateways.delete', 'Remove gateways',         'gateways', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- RBAC module (meta - who can manage roles/permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_rbac_view',   'rbac.view',   'View roles, permissions and access rules',   'rbac', 'engine', 'system'),
    ('perm_rbac_manage', 'rbac.manage', 'Create, edit and delete roles/permissions',  'rbac', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- System module
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_system_settings', 'system.settings', 'Access and modify system settings',   'system', 'engine', 'system'),
    ('perm_system_metrics',  'system.metrics',  'View system metrics and health',      'system', 'engine', 'system'),
    ('perm_system_billing',  'system.billing',  'Manage token billing and accounts',   'system', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;


-- ==========================================
-- DEFAULT ROLES
-- ==========================================

INSERT INTO dll_roles (role_uid, role_name, role_description, account_root, created_by)
VALUES
    ('role_super_admin',      'super_admin',      'Full system access with all permissions',                              'engine', 'system'),
    ('role_admin',            'admin',            'Organization admin with full access to their account resources',       'engine', 'system'),
    ('role_bo1_admin',        'bo1_admin',        'Back-office level 1 admin with management capabilities',              'engine', 'system'),
    ('role_bo_level_support', 'bo_level_support', 'Back-office support with read access and limited actions',            'engine', 'system'),
    ('role_user',             'user',             'Standard user with read-only access to assigned resources',            'engine', 'system'),
    ('role_system',           'system',           'System service account for automated operations',                      'engine', 'system')
ON CONFLICT (role_uid) DO NOTHING;


-- ==========================================
-- ROLE-PERMISSION MAPPINGS
-- ==========================================

-- super_admin: ALL permissions
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
SELECT 'role_super_admin', permission_uid, 'system'
FROM dll_permissions WHERE account_root = 'engine'
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- admin: everything except system settings and rbac management
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
SELECT 'role_admin', permission_uid, 'system'
FROM dll_permissions
WHERE account_root = 'engine'
  AND permission_uid NOT IN ('perm_system_settings', 'perm_rbac_manage', 'perm_system_billing')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- bo1_admin: view/create/edit across most modules, no delete, no finance approve
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_bo1_admin', 'perm_devices_view',    'system'),
    ('role_bo1_admin', 'perm_devices_create',  'system'),
    ('role_bo1_admin', 'perm_devices_edit',    'system'),
    ('role_bo1_admin', 'perm_devices_command', 'system'),
    ('role_bo1_admin', 'perm_clients_view',    'system'),
    ('role_bo1_admin', 'perm_clients_create',  'system'),
    ('role_bo1_admin', 'perm_clients_edit',    'system'),
    ('role_bo1_admin', 'perm_users_view',      'system'),
    ('role_bo1_admin', 'perm_users_create',    'system'),
    ('role_bo1_admin', 'perm_users_edit',      'system'),
    ('role_bo1_admin', 'perm_users_reset_pwd', 'system'),
    ('role_bo1_admin', 'perm_groups_view',     'system'),
    ('role_bo1_admin', 'perm_groups_create',   'system'),
    ('role_bo1_admin', 'perm_groups_edit',     'system'),
    ('role_bo1_admin', 'perm_geozones_view',   'system'),
    ('role_bo1_admin', 'perm_geozones_create', 'system'),
    ('role_bo1_admin', 'perm_geozones_edit',   'system'),
    ('role_bo1_admin', 'perm_drivers_view',    'system'),
    ('role_bo1_admin', 'perm_drivers_create',  'system'),
    ('role_bo1_admin', 'perm_drivers_edit',    'system'),
    ('role_bo1_admin', 'perm_finance_view',    'system'),
    ('role_bo1_admin', 'perm_finance_create',  'system'),
    ('role_bo1_admin', 'perm_reports_view',    'system'),
    ('role_bo1_admin', 'perm_reports_export',  'system'),
    ('role_bo1_admin', 'perm_events_view',     'system'),
    ('role_bo1_admin', 'perm_events_manage',   'system'),
    ('role_bo1_admin', 'perm_gateways_view',   'system'),
    ('role_bo1_admin', 'perm_gateways_create', 'system'),
    ('role_bo1_admin', 'perm_gateways_edit',   'system'),
    ('role_bo1_admin', 'perm_rbac_view',       'system'),
    ('role_bo1_admin', 'perm_system_metrics',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- bo_level_support: read access + limited actions (reset password, commands)
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_bo_level_support', 'perm_devices_view',    'system'),
    ('role_bo_level_support', 'perm_devices_command', 'system'),
    ('role_bo_level_support', 'perm_clients_view',    'system'),
    ('role_bo_level_support', 'perm_users_view',      'system'),
    ('role_bo_level_support', 'perm_users_reset_pwd', 'system'),
    ('role_bo_level_support', 'perm_groups_view',     'system'),
    ('role_bo_level_support', 'perm_geozones_view',   'system'),
    ('role_bo_level_support', 'perm_drivers_view',    'system'),
    ('role_bo_level_support', 'perm_finance_view',    'system'),
    ('role_bo_level_support', 'perm_reports_view',    'system'),
    ('role_bo_level_support', 'perm_events_view',     'system'),
    ('role_bo_level_support', 'perm_gateways_view',   'system'),
    ('role_bo_level_support', 'perm_system_metrics',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- user: read-only on core modules
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_user', 'perm_devices_view',   'system'),
    ('role_user', 'perm_clients_view',   'system'),
    ('role_user', 'perm_groups_view',    'system'),
    ('role_user', 'perm_geozones_view',  'system'),
    ('role_user', 'perm_drivers_view',   'system'),
    ('role_user', 'perm_reports_view',   'system'),
    ('role_user', 'perm_events_view',    'system'),
    ('role_user', 'perm_gateways_view',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- system: all permissions (service account)
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
SELECT 'role_system', permission_uid, 'system'
FROM dll_permissions WHERE account_root = 'engine'
ON CONFLICT (role_uid, permission_uid) DO NOTHING;
