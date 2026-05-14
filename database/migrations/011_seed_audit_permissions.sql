-- Migration 011: Seed Audit Permissions
-- Adds audit module permissions and assigns them to existing roles

-- ==========================================
-- AUDIT PERMISSIONS
-- ==========================================
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_audit_view',    'audit.view',    'View audit events, KPIs, hash chain, approvals and compliance', 'audit', 'engine', 'system'),
    ('perm_audit_approve', 'audit.approve', 'Approve or reject audit approvals (HITL/HIC)',                  'audit', 'engine', 'system'),
    ('perm_audit_export',  'audit.export',  'Request audit data exports',                                    'audit', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- ==========================================
-- ASSIGN TO ROLES
-- ==========================================

-- super_admin: gets all audit permissions (auto-caught by the wildcard query in 008, but explicit here)
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_super_admin', 'perm_audit_view',    'system'),
    ('role_super_admin', 'perm_audit_approve', 'system'),
    ('role_super_admin', 'perm_audit_export',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- admin: view + export (no approve)
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_admin', 'perm_audit_view',   'system'),
    ('role_admin', 'perm_audit_export', 'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- bo1_admin: view only
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_bo1_admin', 'perm_audit_view', 'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- bo_level_support: view only
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_bo_level_support', 'perm_audit_view', 'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;

-- system: all audit permissions
INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by)
VALUES
    ('role_system', 'perm_audit_view',    'system'),
    ('role_system', 'perm_audit_approve', 'system'),
    ('role_system', 'perm_audit_export',  'system')
ON CONFLICT (role_uid, permission_uid) DO NOTHING;
