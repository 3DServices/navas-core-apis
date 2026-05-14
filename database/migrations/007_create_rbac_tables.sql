-- RBAC (Role-Based Access Control) Tables Migration
-- Description: Creates tables for roles, permissions, role-permission mappings, and object-level access control

-- Roles table: defines available roles within an organization
CREATE TABLE IF NOT EXISTS dll_roles (
    role_uid VARCHAR(100) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL,
    role_description VARCHAR(500),
    account_root VARCHAR(100) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    deleted_by VARCHAR(100) NULL
);

-- Permissions table: defines granular permissions (e.g. "devices.view", "devices.edit")
CREATE TABLE IF NOT EXISTS dll_permissions (
    permission_uid VARCHAR(100) PRIMARY KEY,
    permission_name VARCHAR(100) NOT NULL,
    permission_description VARCHAR(500),
    permission_module VARCHAR(100) NOT NULL,
    account_root VARCHAR(100) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    deleted_by VARCHAR(100) NULL
);

-- Role-Permission mapping: assigns permissions to roles
CREATE TABLE IF NOT EXISTS dll_role_permissions (
    id SERIAL PRIMARY KEY,
    role_uid VARCHAR(100) NOT NULL REFERENCES dll_roles(role_uid),
    permission_uid VARCHAR(100) NOT NULL REFERENCES dll_permissions(permission_uid),
    assigned_by VARCHAR(100),
    assigned_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(role_uid, permission_uid)
);

-- Object Access: per-object access rules for users or roles
CREATE TABLE IF NOT EXISTS dll_object_access (
    access_uid VARCHAR(100) PRIMARY KEY,
    account_root VARCHAR(100) NOT NULL,
    subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('user', 'role')),
    subject_uid VARCHAR(100) NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    object_uid VARCHAR(100) NOT NULL,
    access_level VARCHAR(50) NOT NULL DEFAULT 'view',
    granted_by VARCHAR(100),
    granted_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    deleted_by VARCHAR(100) NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_roles_account_root ON dll_roles(account_root);
CREATE INDEX IF NOT EXISTS idx_roles_is_deleted ON dll_roles(is_deleted);
CREATE INDEX IF NOT EXISTS idx_permissions_account_root ON dll_permissions(account_root);
CREATE INDEX IF NOT EXISTS idx_permissions_module ON dll_permissions(permission_module);
CREATE INDEX IF NOT EXISTS idx_permissions_is_deleted ON dll_permissions(is_deleted);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON dll_role_permissions(role_uid);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON dll_role_permissions(permission_uid);
CREATE INDEX IF NOT EXISTS idx_object_access_subject ON dll_object_access(subject_type, subject_uid);
CREATE INDEX IF NOT EXISTS idx_object_access_object ON dll_object_access(object_type, object_uid);
CREATE INDEX IF NOT EXISTS idx_object_access_account_root ON dll_object_access(account_root);
CREATE INDEX IF NOT EXISTS idx_object_access_is_deleted ON dll_object_access(is_deleted);

-- Comments
COMMENT ON TABLE dll_roles IS 'Defines roles that can be assigned to users within an organization';
COMMENT ON TABLE dll_permissions IS 'Defines granular permissions grouped by module';
COMMENT ON TABLE dll_role_permissions IS 'Maps permissions to roles (many-to-many)';
COMMENT ON TABLE dll_object_access IS 'Controls per-object access for specific users or roles';
COMMENT ON COLUMN dll_object_access.subject_type IS 'Whether access is granted to a user or a role';
COMMENT ON COLUMN dll_object_access.object_type IS 'Type of object (e.g. device, group, geozone, client)';
COMMENT ON COLUMN dll_object_access.access_level IS 'Access level (e.g. view, edit, manage, full)';
