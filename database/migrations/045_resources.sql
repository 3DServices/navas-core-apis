-- 045_resources.sql
--
-- Resources: named containers of a client's configuration, shared with chosen
-- users of that client.
--
-- A resource belongs to one client (account_root) and holds existing NAVAS
-- elements by reference — they stay in their own tables, owned as before:
--   geozone        dll_geozones.geozone_uid
--   geozone_group  dll_geozone_groups.group_uid
--   event_rule     dll_device_events.event_local_uid
-- An element is in at most one resource (the primary key below).
--
-- Who may use a resource is kept in dll_object_access (migration 007), which
-- was built for per-object grants and had no rows:
--   subject_type 'user', subject_uid = the user's account_uid,
--   object_type 'resource', object_uid = resource_uid,
--   access_level 'view' (see and use) or 'manage' (also change).
--
-- What it does in the apps (endpoints/resources.py):
--   * elements in no resource behave exactly as before;
--   * an element in a resource is visible to the client's administrators and
--     to users granted that resource — nobody else on the client's team;
--   * a 'view' grant can't edit, delete or attach units to the element.
--
-- Resources are created and managed by staff in the CMS.
--
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS dll_resources (
    resource_uid          VARCHAR(64)  PRIMARY KEY,
    account_root          VARCHAR(100) NOT NULL,
    resource_name         VARCHAR(120) NOT NULL,
    resource_description  TEXT         NOT NULL DEFAULT '',
    created_by            VARCHAR(100),
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_by            VARCHAR(100),
    updated_at            TIMESTAMP,
    is_deleted            BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at            TIMESTAMP,
    deleted_by            VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_resources_account_root
    ON dll_resources (account_root) WHERE is_deleted = FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_resources_client_name
    ON dll_resources (account_root, LOWER(resource_name)) WHERE is_deleted = FALSE;

CREATE TABLE IF NOT EXISTS dll_resource_items (
    item_type     VARCHAR(32)  NOT NULL,
    item_uid      VARCHAR(100) NOT NULL,
    resource_uid  VARCHAR(64)  NOT NULL
        REFERENCES dll_resources (resource_uid) ON DELETE CASCADE,
    added_by      VARCHAR(100),
    added_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (item_type, item_uid)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_resource_item_type') THEN
        ALTER TABLE dll_resource_items ADD CONSTRAINT chk_resource_item_type
            CHECK (item_type IN ('geozone', 'geozone_group', 'event_rule'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_resource_items_resource
    ON dll_resource_items (resource_uid);

-- One live grant per user per object.
CREATE UNIQUE INDEX IF NOT EXISTS uq_object_access_live
    ON dll_object_access (object_type, object_uid, subject_type, subject_uid)
    WHERE is_deleted = FALSE;

COMMENT ON TABLE dll_resources IS
    'Named containers of one client''s geofences, geofence groups and event '
    'rules. Users reach them through dll_object_access (object_type resource).';
COMMENT ON TABLE dll_resource_items IS
    'Which resource an element is in. An element is in at most one resource.';

-- Staff permissions. These keys are already in the catalog (013, "Resources &
-- Template Library"); inserted here too for databases seeded before it.
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description,
                             permission_module, account_root, created_by)
VALUES
    ('perm_can_view_resource_template', 'can_view_resource_template',
     'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_create_resource_template', 'can_create_resource_template',
     'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_edit_resource_template', 'can_edit_resource_template',
     'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_share_resource_template', 'can_share_resource_template',
     'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;
