from flask import Blueprint
from flask import request
import psycopg2
import datetime
import random
from flask import current_app
import base64
from flask import g
from .globals import reply, require_permission, require_auth, log_audit_event


rbac_bp = Blueprint('rbac', __name__)


def generate_uid():
    return base64.b64encode(
        str(str(random.randint(45, 9040000)) + str(random.randint(150, 1940101)) + str(random.randint(670, 9111202)))[:18].encode()
    ).decode()


# Logger used for server-side error trails. Client-facing replies stay generic;
# the full traceback is captured here so support can diagnose without leaking
# database schema details into responses.
import logging
_logger = logging.getLogger('rbac')


def _resolve_permissions(cursor, identifiers, account_root):
    """Resolve a list of permission identifiers (permission_uid OR permission_name)
    to their permission_uids.

    Looks up against ``dll_permissions`` matching either column, scoped to the
    caller's ``account_root`` plus the global catalog (``account_root='engine'``).
    Soft-deleted rows are ignored.

    Returns:
        (uids, unknown) — lists of strings. ``unknown`` contains every
        identifier that did not resolve, in input order, with duplicates
        removed.
    """
    if not identifiers:
        return [], []

    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for raw in identifiers:
        ident = str(raw).strip()
        if ident and ident not in seen:
            seen.add(ident)
            ordered.append(ident)

    if not ordered:
        return [], []

    cursor.execute(
        """
        SELECT permission_uid, permission_name
        FROM dll_permissions
        WHERE (permission_uid = ANY(%s) OR permission_name = ANY(%s))
          AND (account_root = %s OR account_root = 'engine')
          AND (is_deleted = FALSE OR is_deleted IS NULL)
        """,
        (ordered, ordered, str(account_root)),
    )
    rows = cursor.fetchall()

    # Build name+uid -> uid lookup so we can match whichever style the caller sent.
    by_key = {}
    for uid, name in rows:
        by_key[uid] = uid
        by_key[name] = uid

    resolved = []
    unknown = []
    for ident in ordered:
        target = by_key.get(ident)
        if target:
            # Dedupe resolved uids too — two names that resolve to the same uid
            # should only show up once.
            if target not in resolved:
                resolved.append(target)
        else:
            unknown.append(ident)

    return resolved, unknown




# ==========================================
# ROLES ENDPOINTS
# ==========================================

@rbac_bp.route("/rbac/roles", methods=["GET", "POST"])
def get_roles():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    if request.method == "POST":
        payload_data = request.get_json() or {}
        account_root = payload_data.get('data', {}).get('account_root', '')
    else:
        account_root = request.args.get('account_root')

    if not account_root:
        return reply('error', 400, 'account_root is required', '')

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT role_uid, role_name, role_description, account_root, created_by, created_at, updated_at FROM dll_roles WHERE account_root = %s AND (is_deleted = FALSE OR is_deleted IS NULL) ORDER BY created_at DESC",
                    (str(account_root),)
                )

                if cursor.rowcount >= 1:
                    rows = cursor.fetchall()
                    roles = []
                    for row in rows:
                        roles.append({
                            "role_uid": row[0],
                            "role_name": row[1],
                            "role_description": row[2],
                            "account_root": row[3],
                            "created_by": row[4],
                            "created_at": str(row[5]),
                            "updated_at": str(row[6])
                        })
                    return reply('success', 200, 'Roles retrieved successfully', roles)
                else:
                    return reply('success', 200, 'No roles found', [])

    except Exception as error:
        return reply('error', 500, str(error), '')


@rbac_bp.route("/rbac/roles/<role_uid>", methods=["GET"])
def get_role(role_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT role_uid, role_name, role_description, account_root, created_by, created_at, updated_at FROM dll_roles WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (str(role_uid),)
                )

                if cursor.rowcount == 1:
                    row = cursor.fetchone()
                    role = {
                        "role_uid": row[0],
                        "role_name": row[1],
                        "role_description": row[2],
                        "account_root": row[3],
                        "created_by": row[4],
                        "created_at": str(row[5]),
                        "updated_at": str(row[6])
                    }

                    # Also fetch permissions assigned to this role
                    cursor.execute(
                        "SELECT p.permission_uid, p.permission_name, p.permission_description, p.permission_module FROM dll_role_permissions rp JOIN dll_permissions p ON rp.permission_uid = p.permission_uid WHERE rp.role_uid = %s AND (p.is_deleted = FALSE OR p.is_deleted IS NULL)",
                        (str(role_uid),)
                    )
                    permissions = []
                    if cursor.rowcount >= 1:
                        for prow in cursor.fetchall():
                            permissions.append({
                                "permission_uid": prow[0],
                                "permission_name": prow[1],
                                "permission_description": prow[2],
                                "permission_module": prow[3]
                            })
                    role["permissions"] = permissions

                    return reply('success', 200, 'Role retrieved successfully', role)
                else:
                    return reply('error', 404, 'Role not found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


@rbac_bp.route("/rbac/roles/create", methods=["POST"])
@require_permission('rbac.manage')
def create_role():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        if (len(str(payload_data['data']['role_name'])) > 1) and (len(str(payload_data['data']['account_root'])) > 2):

            RoleName = str(payload_data['data']['role_name'])
            RoleDescription = str(payload_data['data'].get('role_description', ''))
            AccountRoot = str(payload_data['data']['account_root'])
            CreatedBy = str(payload_data['data'].get('created_by', ''))
            RoleUID = generate_uid()

            PermissionUIDs = payload_data['data'].get('permissions', [])

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    # Check if role name already exists for this account
                    cursor.execute(
                        "SELECT role_uid FROM dll_roles WHERE role_name = %s AND account_root = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                        (RoleName, AccountRoot,)
                    )

                    if cursor.rowcount >= 1:
                        return reply('error', 400, 'Role name already exists', '')

                    # Resolve incoming permissions (names or uids) to permission_uids
                    # BEFORE inserting the role. If any are unknown, return a clean 400
                    # rather than letting the FK constraint blow up mid-transaction.
                    resolved_uids, unknown_perms = _resolve_permissions(
                        cursor, PermissionUIDs, AccountRoot
                    )
                    if unknown_perms:
                        # Roll back any work so far by re-raising; the `with dbconnect`
                        # block will abort. Reply with details of the unknowns.
                        preview = ', '.join(unknown_perms[:5])
                        more = '' if len(unknown_perms) <= 5 else f' (+{len(unknown_perms) - 5} more)'
                        return reply(
                            'error', 400,
                            f'Unknown permissions: {preview}{more}',
                            {'unknown_permissions': unknown_perms}
                        )

                    cursor.execute(
                        "INSERT INTO dll_roles (role_uid, role_name, role_description, account_root, created_by) VALUES (%s, %s, %s, %s, %s)",
                        (RoleUID, RoleName, RoleDescription, AccountRoot, CreatedBy,)
                    )

                    # Assign resolved permissions to the new role
                    for perm_uid in resolved_uids:
                        cursor.execute(
                            "INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by) VALUES (%s, %s, %s) ON CONFLICT (role_uid, permission_uid) DO NOTHING",
                            (RoleUID, perm_uid, CreatedBy,)
                        )

                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='CREATE',
                        obj=f"Role '{RoleName}' created with {len(resolved_uids)} permissions",
                        domain='RBAC',
                        severity='Alarm',
                        ip_address=request.remote_addr,
                        meta={"role_uid": RoleUID, "role_name": RoleName, "permissions_count": len(resolved_uids)}
                    )

                    return reply('success', 201, 'Role created successfully', {"role_uid": RoleUID})

        else:
            return reply('error', 400, 'Role name and account_root are required', '')

    except Exception as error:
        _logger.exception('create_role failed: %s', error)
        return reply('error', 500, 'Could not create role', '')


@rbac_bp.route("/rbac/roles/<role_uid>/update", methods=["PUT"])
@require_permission('rbac.manage')
def update_role(role_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        data = payload_data.get('data', {})
        update_fields = []
        update_values = []

        if 'role_name' in data:
            update_fields.append("role_name = %s")
            update_values.append(str(data['role_name']))

        if 'role_description' in data:
            update_fields.append("role_description = %s")
            update_values.append(str(data['role_description']))

        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Update role fields if provided
                if update_fields:
                    update_fields.append("updated_at = NOW()")
                    update_values.append(str(role_uid))

                    query = f"UPDATE dll_roles SET {', '.join(update_fields)} WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)"
                    cursor.execute(query, tuple(update_values))

                    if cursor.rowcount == 0:
                        return reply('error', 404, 'Role not found', '')

                # Replace permissions if provided
                if 'permissions' in data:
                    updated_by = str(data.get('updated_by', ''))

                    # Look up this role's account_root so we can scope the resolver
                    # to the same tenant the role belongs to.
                    cursor.execute(
                        "SELECT account_root FROM dll_roles WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                        (str(role_uid),)
                    )
                    role_row = cursor.fetchone()
                    if role_row is None:
                        return reply('error', 404, 'Role not found', '')
                    role_account_root = role_row[0]

                    # Resolve permission names/uids BEFORE making any changes.
                    resolved_uids, unknown_perms = _resolve_permissions(
                        cursor, data['permissions'], role_account_root
                    )
                    if unknown_perms:
                        preview = ', '.join(unknown_perms[:5])
                        more = '' if len(unknown_perms) <= 5 else f' (+{len(unknown_perms) - 5} more)'
                        return reply(
                            'error', 400,
                            f'Unknown permissions: {preview}{more}',
                            {'unknown_permissions': unknown_perms}
                        )

                    # Clear existing permissions (atomic with the inserts below)
                    cursor.execute("DELETE FROM dll_role_permissions WHERE role_uid = %s", (str(role_uid),))
                    # Assign resolved permissions
                    for perm_uid in resolved_uids:
                        cursor.execute(
                            "INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by) VALUES (%s, %s, %s) ON CONFLICT (role_uid, permission_uid) DO NOTHING",
                            (str(role_uid), perm_uid, updated_by,)
                        )

                log_audit_event(
                    actor=g.current_user['account_uid'],
                    action='UPDATE',
                    obj=f"Role {role_uid} updated",
                    domain='RBAC',
                    severity='Alarm',
                    ip_address=request.remote_addr,
                    meta={"role_uid": role_uid, "fields": list(data.keys())}
                )

                return reply('success', 200, 'Role updated successfully', '')

    except Exception as error:
        _logger.exception('update_role failed: %s', error)
        return reply('error', 500, 'Could not update role', '')


@rbac_bp.route("/rbac/roles/<role_uid>/delete", methods=["DELETE"])
@require_permission('rbac.manage')
def delete_role(role_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json() or {}
    deleted_by = str(payload_data.get('data', {}).get('deleted_by', ''))

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "UPDATE dll_roles SET is_deleted = TRUE, deleted_at = NOW(), deleted_by = %s WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (deleted_by, str(role_uid),)
                )

                if cursor.rowcount == 1:
                    # Also remove role-permission mappings
                    cursor.execute("DELETE FROM dll_role_permissions WHERE role_uid = %s", (str(role_uid),))

                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='DELETE',
                        obj=f"Role {role_uid} deleted",
                        domain='RBAC',
                        severity='Crit',
                        ip_address=request.remote_addr,
                        meta={"role_uid": role_uid, "deleted_by": deleted_by}
                    )

                    return reply('success', 200, 'Role deleted successfully', '')
                else:
                    return reply('error', 404, 'Role not found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ==========================================
# PERMISSIONS ENDPOINTS
# ==========================================

@rbac_bp.route("/rbac/permissions", methods=["GET", "POST"])
def get_permissions():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    if request.method == "POST":
        payload_data = request.get_json() or {}
        account_root = payload_data.get('data', {}).get('account_root', '')
    else:
        account_root = request.args.get('account_root')

    if not account_root:
        return reply('error', 400, 'account_root is required', '')

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT permission_uid, permission_name, permission_description, permission_module, account_root, created_by, created_at FROM dll_permissions WHERE (account_root = %s OR account_root = 'engine') AND (is_deleted = FALSE OR is_deleted IS NULL) ORDER BY permission_module, permission_name",
                    (str(account_root),)
                )

                if cursor.rowcount >= 1:
                    rows = cursor.fetchall()
                    permissions = []
                    for row in rows:
                        permissions.append({
                            "permission_uid": row[0],
                            "permission_name": row[1],
                            "permission_description": row[2],
                            "permission_module": row[3],
                            "account_root": row[4],
                            "created_by": row[5],
                            "created_at": str(row[6])
                        })
                    return reply('success', 200, 'Permissions retrieved successfully', permissions)
                else:
                    return reply('success', 200, 'No permissions found', [])

    except Exception as error:
        return reply('error', 500, str(error), '')


@rbac_bp.route("/rbac/permissions/create", methods=["POST"])
@require_permission('rbac.manage')
def create_permission():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        data = payload_data.get('data', {})
        permission_name = str(data.get('permission_name', ''))
        permission_description = str(data.get('permission_description', ''))
        permission_module = str(data.get('permission_module', ''))
        account_root = str(data.get('account_root', ''))
        created_by = str(data.get('created_by', ''))

        if len(permission_name) < 2 or len(permission_module) < 2 or len(account_root) < 2:
            return reply('error', 400, 'permission_name, permission_module and account_root are required', '')

        permission_uid = generate_uid()

        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Check if permission name already exists for this account
                cursor.execute(
                    "SELECT permission_uid FROM dll_permissions WHERE permission_name = %s AND account_root = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (permission_name, account_root,)
                )

                if cursor.rowcount >= 1:
                    return reply('error', 400, 'Permission name already exists', '')

                cursor.execute(
                    "INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
                    (permission_uid, permission_name, permission_description, permission_module, account_root, created_by,)
                )

                log_audit_event(
                    actor=g.current_user['account_uid'],
                    action='CREATE',
                    obj=f"Permission '{permission_name}' created in module '{permission_module}'",
                    domain='RBAC',
                    severity='Alarm',
                    ip_address=request.remote_addr,
                    meta={"permission_uid": permission_uid, "permission_name": permission_name, "module": permission_module}
                )

                return reply('success', 201, 'Permission created successfully', {"permission_uid": permission_uid})

    except Exception as error:
        return reply('error', 500, str(error), '')


@rbac_bp.route("/rbac/permissions/<permission_uid>/update", methods=["PUT"])
@require_permission('rbac.manage')
def update_permission(permission_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        data = payload_data.get('data', {})
        updated_by = str(data.get('updated_by', ''))
        update_fields = []
        update_values = []

        if 'permission_name' in data:
            update_fields.append("permission_name = %s")
            update_values.append(str(data['permission_name']))

        if 'permission_description' in data:
            update_fields.append("permission_description = %s")
            update_values.append(str(data['permission_description']))

        if 'permission_module' in data:
            update_fields.append("permission_module = %s")
            update_values.append(str(data['permission_module']))

        if not update_fields:
            return reply('error', 400, 'No fields to update', '')

        update_values.append(str(permission_uid))

        with dbconnect:
            with dbconnect.cursor() as cursor:
                query = f"UPDATE dll_permissions SET {', '.join(update_fields)} WHERE permission_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)"
                cursor.execute(query, tuple(update_values))

                if cursor.rowcount == 1:
                    log_audit_event(
                        actor=updated_by or g.current_user['account_uid'],
                        action='UPDATE',
                        obj=f"Permission {permission_uid} updated",
                        domain='RBAC',
                        severity='Warn',
                        ip_address=request.remote_addr,
                        meta={"permission_uid": permission_uid, "updated_by": updated_by, "fields": list(data.keys())}
                    )
                    return reply('success', 200, 'Permission updated successfully', '')
                else:
                    return reply('error', 404, 'Permission not found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


@rbac_bp.route("/rbac/permissions/<permission_uid>/delete", methods=["DELETE"])
@require_permission('rbac.manage')
def delete_permission(permission_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json() or {}
    deleted_by = str(payload_data.get('data', {}).get('deleted_by', ''))

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Guard: refuse to delete a permission that belongs to the system
                # catalog (account_root='engine'). These rows are seeded from the
                # frontend catalog and shared across all tenants; deleting one
                # would break the Role Creator UI for every tenant at once.
                cursor.execute(
                    "SELECT account_root FROM dll_permissions WHERE permission_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (str(permission_uid),)
                )
                row = cursor.fetchone()
                if row is None:
                    return reply('error', 404, 'Permission not found', '')
                if row[0] == 'engine':
                    return reply('error', 403, 'System catalog permissions cannot be deleted', '')

                cursor.execute(
                    "UPDATE dll_permissions SET is_deleted = TRUE, deleted_at = NOW(), deleted_by = %s WHERE permission_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (deleted_by, str(permission_uid),)
                )

                if cursor.rowcount == 1:
                    # Also remove from role-permission mappings
                    cursor.execute("DELETE FROM dll_role_permissions WHERE permission_uid = %s", (str(permission_uid),))

                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='DELETE',
                        obj=f"Permission {permission_uid} deleted",
                        domain='RBAC',
                        severity='Crit',
                        ip_address=request.remote_addr,
                        meta={"permission_uid": permission_uid}
                    )

                    return reply('success', 200, 'Permission deleted successfully', '')
                else:
                    return reply('error', 404, 'Permission not found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ==========================================
# USER PERMISSION RESOLUTION
# ==========================================

# Get all permissions for a specific user (via their role)
@rbac_bp.route("/rbac/users/<user_uid>/permissions", methods=["GET"])
def get_user_permissions(user_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Get user's role from dll_access_relay
                cursor.execute(
                    "SELECT account_clearance FROM dll_access_relay WHERE account_uid = %s",
                    (str(user_uid),)
                )

                if cursor.rowcount == 0:
                    return reply('error', 404, 'User not found', '')

                user_role = cursor.fetchone()[0]

                # Get role_uid from role name
                cursor.execute(
                    "SELECT role_uid, role_name FROM dll_roles WHERE role_name = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (str(user_role),)
                )

                if cursor.rowcount == 0:
                    return reply('success', 200, 'No role mapping found for user', {"role": user_role, "permissions": []})

                role_data = cursor.fetchone()
                role_uid = role_data[0]
                role_name = role_data[1]

                # Get permissions for this role
                cursor.execute(
                    "SELECT p.permission_uid, p.permission_name, p.permission_description, p.permission_module FROM dll_role_permissions rp JOIN dll_permissions p ON rp.permission_uid = p.permission_uid WHERE rp.role_uid = %s AND (p.is_deleted = FALSE OR p.is_deleted IS NULL) ORDER BY p.permission_module, p.permission_name",
                    (str(role_uid),)
                )
                permissions = []
                if cursor.rowcount >= 1:
                    for prow in cursor.fetchall():
                        permissions.append({
                            "permission_uid": prow[0],
                            "permission_name": prow[1],
                            "permission_description": prow[2],
                            "permission_module": prow[3]
                        })

                return reply('success', 200, 'User permissions retrieved', {
                    "role": role_name,
                    "role_uid": role_uid,
                    "permissions": permissions
                })

    except Exception as error:
        return reply('error', 500, str(error), '')


# ==========================================
# RBAC DASHBOARD STATISTICS
# ==========================================

# 1. Total Active Roles
@rbac_bp.route("/rbac/stats/active-roles", methods=["GET"])
def get_active_roles_count():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM dll_roles WHERE is_deleted = FALSE OR is_deleted IS NULL"
                )
                count = cursor.fetchone()[0]
                return reply('success', 200, 'Total active roles retrieved', {"total_active_roles": count})

    except Exception as error:
        return reply('error', 500, str(error), '')


# 2. Total User Permissions
@rbac_bp.route("/rbac/stats/total-permissions", methods=["GET"])
def get_total_permissions_count():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM dll_permissions WHERE is_deleted = FALSE OR is_deleted IS NULL"
                )
                count = cursor.fetchone()[0]
                return reply('success', 200, 'Total permissions retrieved', {"total_permissions": count})

    except Exception as error:
        return reply('error', 500, str(error), '')


# 3. Actively Logged In Clients (client users who logged in within last 24 hours)
@rbac_bp.route("/rbac/stats/active-clients", methods=["GET"])
def get_active_logged_in_clients():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(DISTINCT ar.account_root)
                    FROM dll_access_relay ar
                    INNER JOIN dll_client_accounts ca ON ar.account_root = ca.client_uid
                    WHERE ar.last_login_at >= NOW() - INTERVAL '24 hours'
                      AND ar.access_status = 'active'
                      AND (ca.is_deleted = FALSE OR ca.is_deleted IS NULL)
                """)
                count = cursor.fetchone()[0]
                return reply('success', 200, 'Actively logged in clients retrieved', {"total_active_clients": count})

    except Exception as error:
        return reply('error', 500, str(error), '')


# 4. Actively Logged In 3D Clients (internal/3D Services users who logged in within last 24 hours)
@rbac_bp.route("/rbac/stats/active-3d-clients", methods=["GET"])
def get_active_logged_in_3d_clients():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(DISTINCT ar.account_uid)
                    FROM dll_access_relay ar
                    WHERE ar.last_login_at >= NOW() - INTERVAL '24 hours'
                      AND ar.access_status = 'active'
                      AND ar.account_root NOT IN (
                          SELECT client_uid FROM dll_client_accounts WHERE is_deleted = FALSE OR is_deleted IS NULL
                      )
                """)
                count = cursor.fetchone()[0]
                return reply('success', 200, 'Actively logged in 3D clients retrieved', {"total_active_3d_clients": count})

    except Exception as error:
        return reply('error', 500, str(error), '')


# 5. Total Users Belonging to Clients
@rbac_bp.route("/rbac/stats/client-users", methods=["GET"])
def get_client_users_count():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM dll_access_relay ar
                    INNER JOIN dll_client_accounts ca ON ar.account_root = ca.client_uid
                    WHERE ar.access_status = 'active'
                      AND (ca.is_deleted = FALSE OR ca.is_deleted IS NULL)
                """)
                count = cursor.fetchone()[0]
                return reply('success', 200, 'Total users belonging to clients retrieved', {"total_client_users": count})

    except Exception as error:
        return reply('error', 500, str(error), '')


# 6. User Count Per Role (how many users have each role assigned)
@rbac_bp.route("/rbac/stats/role-user-counts", methods=["GET"])
def get_role_user_counts():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT r.role_uid, COUNT(ar.account_uid) AS user_count
                    FROM dll_roles r
                    LEFT JOIN dll_access_relay ar ON ar.account_clearance = r.role_name
                    WHERE (r.is_deleted = FALSE OR r.is_deleted IS NULL)
                    GROUP BY r.role_uid
                """)
                counts = {}
                if cursor.rowcount >= 1:
                    for row in cursor.fetchall():
                        counts[row[0]] = row[1]
                return reply('success', 200, 'Role user counts retrieved', counts)

    except Exception as error:
        return reply('error', 500, str(error), '')


# 7. Roles Using Each Permission (how many roles reference each permission)
@rbac_bp.route("/rbac/stats/permission-role-counts", methods=["GET"])
def get_permission_role_counts():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT rp.permission_uid, COUNT(DISTINCT rp.role_uid) AS role_count
                    FROM dll_role_permissions rp
                    JOIN dll_roles r ON rp.role_uid = r.role_uid AND (r.is_deleted = FALSE OR r.is_deleted IS NULL)
                    GROUP BY rp.permission_uid
                """)
                counts = {}
                if cursor.rowcount >= 1:
                    for row in cursor.fetchall():
                        counts[row[0]] = row[1]
                return reply('success', 200, 'Permission role counts retrieved', counts)

    except Exception as error:
        return reply('error', 500, str(error), '')
