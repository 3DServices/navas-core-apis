-- 058_client_branding.sql
--
-- A client's own look for the OLIWA web console and mobile app: two colours
-- and the assistant's name (endpoints/branding.py, rules in
-- endpoints/branding_rules.py).
--
-- dll_client_branding   one row per client (client_uid = account_root)
--   enabled ... allowed_admins   set by 3D Services staff in the CMS
--                                (branding.control): may the client customise,
--                                which parts, and which of its administrators
--   brand_color, accent_color,   the look; NULL = the default (OLIWA teal,
--   assistant_name               "Waswa")
--
-- And the two staff permissions, in the catalogue the CMS role editor reads:
--   branding.control   switch branding on/off per client, choose who may edit
--   branding.override  change or reset a client's look on their behalf

BEGIN;

CREATE TABLE IF NOT EXISTS dll_client_branding (
    client_uid            VARCHAR(100) PRIMARY KEY,
    enabled               BOOLEAN      NOT NULL DEFAULT FALSE,
    allow_colors          BOOLEAN      NOT NULL DEFAULT TRUE,
    allow_assistant_name  BOOLEAN      NOT NULL DEFAULT TRUE,
    admin_scope           VARCHAR(10)  NOT NULL DEFAULT 'all',
    allowed_admins        TEXT[]       NOT NULL DEFAULT '{}',
    brand_color           VARCHAR(7),
    accent_color          VARCHAR(7),
    assistant_name        VARCHAR(24),
    controlled_by         VARCHAR(100),
    controlled_at         TIMESTAMP,
    updated_by            VARCHAR(100),
    updated_at            TIMESTAMP,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_branding_scope CHECK (admin_scope IN ('all', 'selected')),
    CONSTRAINT chk_branding_brand CHECK (brand_color IS NULL OR brand_color ~ '^#[0-9A-F]{6}$'),
    CONSTRAINT chk_branding_accent CHECK (accent_color IS NULL OR accent_color ~ '^#[0-9A-F]{6}$')
);

INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_branding_control', 'branding.control',
     'Switch client branding on or off, and choose which client administrators may change it',
     'Users & Permissions', 'engine', 'system'),
    ('perm_branding_override', 'branding.override',
     'Change or reset a client''s colours and assistant name on their behalf',
     'Users & Permissions', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

COMMIT;
