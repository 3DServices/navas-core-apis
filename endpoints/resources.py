"""
resources — named containers of a client's geofences, geofence groups and
event rules, shared with chosen users of that client.

The elements stay where they are (dll_geozones, dll_geozone_groups,
dll_device_events) and keep their owners. A resource only says which of them
belong together and who on the client's team may use them:

  * an element in no resource works exactly as it always has;
  * an element in a resource is visible to the client's administrators and to
    users granted that resource, and hidden from the rest of the team;
  * a grant is 'view' (see it, select it, report on it) or 'manage' (also edit,
    delete, and attach or detach units);
  * a grant also brings in elements a teammate owns, so a rule created by one
    user can be shared with another.

Staff build resources in the CMS (/resources/admin/...). The apps read
/resources/mine to label and filter what they show; the list endpoints and
the access guard apply the same policy on the server through resource_policy().
Tables: migration 045.
"""
import uuid

import psycopg2
from flask import Blueprint, request, g, current_app

from .globals import (reply, require_auth, require_staff, log_audit_event,
                      is_customer_account, _is_platform_admin)


resources_bp = Blueprint('resources_bp', __name__)

# Element kinds a resource can hold: table, id column, owner column, name column.
KINDS = {
    'geozone': ('dll_geozones', 'geozone_uid', 'geozone_owner', 'geozone_name'),
    'geozone_group': ('dll_geozone_groups', 'group_uid', 'group_owner', 'group_name'),
    'event_rule': ('dll_device_events', 'event_local_uid', 'owner_org_uid', 'event_display_name'),
}
KIND_LABELS = {
    'geozone': 'geofence',
    'geozone_group': 'geofence group',
    'event_rule': 'event rule',
}
ACCESS_LEVELS = ('view', 'manage')

# Customer roles that see every element of their account. Everyone else on a
# customer's team is limited by resources. Matches team.TEAM_ADMIN_ROLES, plus
# custom admin role names found on live accounts ("Customer Administrator").
ADMIN_ROLES = frozenset({'client_admin', 'customer', 'customer_tracker', 'admin'})


def is_account_admin(role):
    r = str(role or '').strip().lower()
    return r in ADMIN_ROLES or 'admin' in r


def _db():
    return psycopg2.connect(current_app.config['db_link'])


def _ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() if fwd else request.remote_addr


# ── Policy ───────────────────────────────────────────────────────────────────

class ResourcePolicy:
    """What the signed-in user may do with resource-held elements.

    access(kind, uid) answers:
      'open'   - the element is in no resource; nothing changes for it
      'manage' - in a resource, and the user may change it
      'view'   - in a resource, and the user may only see and use it
      'hidden' - in a resource the user has no grant for
    """

    def __init__(self, restricted, account_root, placed=None, grants=None, owned=None):
        self.restricted = restricted
        self.account_root = account_root
        self.placed = placed or {}      # (kind, uid) -> (resource_uid, resource_name)
        self.grants = grants or {}      # resource_uid -> 'view' | 'manage'
        self.owned = owned or set()     # (kind, uid) the user created themselves

    def access(self, kind, uid):
        key = (kind, str(uid))
        where = self.placed.get(key)
        if where is None:
            return 'open'
        if not self.restricted or key in self.owned:
            return 'manage'
        return self.grants.get(where[0], 'hidden')

    def granted_uids(self, kind):
        """Elements of this kind the user reaches through a resource: every
        one in the account's resources for an account admin, the granted ones
        for everyone else. List endpoints add these to the owner's own list."""
        return [uid for (k, uid), (res, _) in self.placed.items()
                if k == kind and (not self.restricted or res in self.grants)]

    def describe(self, kind, uid):
        """The resource fields added to an element in a list response."""
        where = self.placed.get((kind, str(uid)))
        level = self.access(kind, uid)
        return {
            'resource_uid': where[0] if where else None,
            'resource_name': where[1] if where else None,
            'resource_access': 'view' if level == 'view' else 'manage',
        }

    def apply(self, kind, rows, key):
        """Drop hidden elements from a list and label the rest."""
        out = []
        for row in rows:
            uid = row.get(key)
            if self.access(kind, uid) == 'hidden':
                continue
            row.update(self.describe(kind, uid))
            out.append(row)
        return out


_OPEN = ResourcePolicy(False, None)


def _load_policy(user):
    role, account_type = user.get('role'), user.get('account_type')
    root = str(user.get('account_root') or user.get('account_uid') or '')
    customer = is_customer_account(role, account_type) and not _is_platform_admin(role, account_type)
    restricted = customer and not is_account_admin(role)
    if not customer or not root:
        return _OPEN

    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT i.item_type, i.item_uid, r.resource_uid, r.resource_name "
                "FROM dll_resource_items i JOIN dll_resources r USING (resource_uid) "
                "WHERE r.account_root = %s AND r.is_deleted = FALSE", (root,))
            placed = {(t, str(u)): (res, name) for t, u, res, name in cur.fetchall()}
            grants = {}
            if placed:
                cur.execute(
                    "SELECT a.object_uid, a.access_level FROM dll_object_access a "
                    "JOIN dll_resources r ON r.resource_uid = a.object_uid "
                    "WHERE a.object_type = 'resource' AND a.subject_type = 'user' "
                    "AND a.subject_uid = %s AND a.account_root = %s "
                    "AND a.is_deleted = FALSE AND r.is_deleted = FALSE",
                    (str(user.get('account_uid')), root))
                grants = {res: level for res, level in cur.fetchall()}
            # Whoever created an element keeps it, whichever resource it is in.
            owned = set()
            for kind, (table, id_col, owner_col, _) in KINDS.items():
                uids = [u for k, u in placed if k == kind]
                if uids:
                    cur.execute(f"SELECT {id_col} FROM {table} WHERE {id_col} = ANY(%s) "
                                f"AND {owner_col} = %s", (uids, str(user.get('account_uid'))))
                    owned.update((kind, str(r[0])) for r in cur.fetchall())
        return ResourcePolicy(restricted, root, placed, grants, owned)
    except psycopg2.errors.UndefinedTable:
        # Migration 045 not applied yet: behave as before resources existed.
        return _OPEN
    finally:
        conn.close()


def resource_policy():
    """The policy for this request's user (cached on g). Staff, platform admins
    and requests with no signed-in user get the open policy."""
    cached = getattr(g, '_resource_policy', None)
    if cached is not None:
        return cached
    user = getattr(g, 'current_user', None)
    policy = _load_policy(user) if user else _OPEN
    g._resource_policy = policy
    return policy


class ResourceDenied(Exception):
    def __init__(self, kind, uid, level):
        super().__init__(kind)
        self.kind, self.uid, self.level = kind, uid, level

    def message(self):
        label = KIND_LABELS.get(self.kind, 'record')
        if self.level == 'view':
            return f"You have view-only access to this {label}."
        return "This record doesn't belong to your account."


def check_access(refs, changing):
    """Raise ResourceDenied if the user can't reach one of [(kind, uid)], or
    may only view it while [changing] it."""
    policy = resource_policy()
    if not policy.restricted:
        return
    for kind, uid in refs:
        uid = str(uid or '').strip()
        if not uid:
            continue
        level = policy.access(kind, uid)
        if level == 'hidden' or (changing and level == 'view'):
            raise ResourceDenied(kind, uid, level)


# ── Customer: what I can use ────────────────────────────────────────────────

@resources_bp.route('/resources/mine', methods=['GET'])
@require_auth
def my_resources():
    """The resources the signed-in user can use, with the elements in each.
    restricted=false means the user sees every element of the account."""
    user = g.current_user
    policy = resource_policy()
    root = policy.account_root
    if root is None:
        return reply('success', 200, 'No resources', {'restricted': False, 'resources': []})

    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT resource_uid, resource_name, resource_description FROM dll_resources "
                "WHERE account_root = %s AND is_deleted = FALSE ORDER BY LOWER(resource_name)",
                (root,))
            rows = cur.fetchall()
    finally:
        conn.close()

    items = {}
    for (kind, uid), (res, _) in policy.placed.items():
        items.setdefault(res, {k: [] for k in KINDS})[kind].append(uid)

    out = []
    for res, name, description in rows:
        level = 'manage' if not policy.restricted else policy.grants.get(res)
        if level is None:
            continue
        out.append({
            'resource_uid': res,
            'resource_name': name,
            'resource_description': description,
            'access': level,
            'items': items.get(res, {k: [] for k in KINDS}),
        })
    return reply('success', 200, f'{len(out)} resource(s)',
                 {'restricted': policy.restricted, 'account_uid': user.get('account_uid'),
                  'resources': out})


# ── Staff: build and share resources (CMS) ───────────────────────────────────

def _client_exists(cur, client_uid):
    cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s "
                "AND (is_deleted IS NULL OR is_deleted = FALSE)", (client_uid,))
    row = cur.fetchone()
    return row[0] if row else None


def _team(cur, client_uid):
    """account_uid -> row of the client's users (the owner uids of its elements)."""
    cur.execute(
        "SELECT account_uid, display_name, log_username, email, account_clearance, "
        "access_status, account_type FROM dll_access_relay WHERE account_root = %s",
        (client_uid,))
    return {str(r[0]): r for r in cur.fetchall()}


def _owners(client_uid, team):
    return list({client_uid, *team.keys()})


def _resource(cur, resource_uid):
    cur.execute(
        "SELECT resource_uid, account_root, resource_name, resource_description, created_by, "
        "created_at, updated_at FROM dll_resources WHERE resource_uid = %s AND is_deleted = FALSE",
        (resource_uid,))
    return cur.fetchone()


def _payload():
    body = request.get_json(silent=True) or {}
    data = body.get('data', body)
    return data if isinstance(data, dict) else {}


def _actor():
    return str(g.current_user.get('account_uid') or 'system')


def _prune(cur, client_uid):
    """Forget items whose element has been deleted."""
    for kind, (table, id_col, _, _) in KINDS.items():
        cur.execute(
            f"DELETE FROM dll_resource_items i USING dll_resources r "
            f"WHERE i.resource_uid = r.resource_uid AND r.account_root = %s "
            f"AND i.item_type = %s AND NOT EXISTS "
            f"(SELECT 1 FROM {table} e WHERE e.{id_col} = i.item_uid)",
            (client_uid, kind))


def _stamp(value):
    return value.isoformat(sep=' ', timespec='seconds') if value else None


@resources_bp.route('/resources/admin/clients/<string:client_uid>/list', methods=['GET'])
@require_staff('can_view_resource_template')
def list_resources(client_uid):
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                if _client_exists(cur, client_uid) is None:
                    return reply('error', 404, 'Client not found.', '')
                _prune(cur, client_uid)
                cur.execute(
                    "SELECT r.resource_uid, r.resource_name, r.resource_description, r.created_at, "
                    "r.updated_at, "
                    "(SELECT COUNT(*) FROM dll_resource_items i WHERE i.resource_uid = r.resource_uid), "
                    "(SELECT COUNT(*) FROM dll_object_access a WHERE a.object_type = 'resource' "
                    " AND a.object_uid = r.resource_uid AND a.is_deleted = FALSE) "
                    "FROM dll_resources r WHERE r.account_root = %s AND r.is_deleted = FALSE "
                    "ORDER BY LOWER(r.resource_name)", (client_uid,))
                rows = cur.fetchall()
    finally:
        conn.close()
    data = [{
        'resource_uid': r[0], 'resource_name': r[1], 'resource_description': r[2],
        'created_at': _stamp(r[3]), 'updated_at': _stamp(r[4]),
        'item_count': r[5], 'user_count': r[6],
    } for r in rows]
    return reply('success', 200, f'{len(data)} resource(s)', data)


@resources_bp.route('/resources/admin/clients/<string:client_uid>/catalog', methods=['GET'])
@require_staff('can_view_resource_template')
def client_catalog(client_uid):
    """Everything a resource of this client can hold, and who it can be shared
    with. Each element says which resource it is in now."""
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                if _client_exists(cur, client_uid) is None:
                    return reply('error', 404, 'Client not found.', '')
                _prune(cur, client_uid)
                team = _team(cur, client_uid)
                owners = _owners(client_uid, team)
                cur.execute(
                    "SELECT i.item_type, i.item_uid, r.resource_uid, r.resource_name "
                    "FROM dll_resource_items i JOIN dll_resources r USING (resource_uid) "
                    "WHERE r.account_root = %s AND r.is_deleted = FALSE", (client_uid,))
                placed = {(t, str(u)): (res, name) for t, u, res, name in cur.fetchall()}

                elements = {}
                for kind, (table, id_col, owner_col, name_col) in KINDS.items():
                    cur.execute(f"SELECT {id_col}, {name_col}, {owner_col} FROM {table} "
                                f"WHERE {owner_col} = ANY(%s) ORDER BY LOWER({name_col})",
                                (owners,))
                    elements[kind] = []
                    for uid, name, owner in cur.fetchall():
                        where = placed.get((kind, str(uid)))
                        owner_row = team.get(str(owner))
                        elements[kind].append({
                            'uid': uid, 'name': name, 'owner_uid': owner,
                            'owner_name': (owner_row[1] or owner_row[2]) if owner_row else None,
                            'resource_uid': where[0] if where else None,
                            'resource_name': where[1] if where else None,
                        })
    finally:
        conn.close()

    users = []
    for uid, row in team.items():
        _, display, username, email, role, status, account_type = row
        users.append({
            'account_uid': uid, 'display_name': display, 'username': username,
            'email': email, 'role': role, 'status': status,
            'sees_everything': is_account_admin(role)
            or not is_customer_account(role, account_type),
        })
    users.sort(key=lambda u: str(u['display_name'] or u['username'] or '').lower())
    return reply('success', 200, 'Catalog loaded', {'elements': elements, 'users': users})


@resources_bp.route('/resources/admin/create', methods=['POST'])
@require_staff('can_create_resource_template')
def create_resource():
    data = _payload()
    client_uid = str(data.get('client_uid') or '').strip()
    name = str(data.get('resource_name') or '').strip()
    description = str(data.get('resource_description') or '').strip()
    if not client_uid:
        return reply('error', 400, 'Choose the client this resource belongs to.', '')
    if len(name) < 2 or len(name) > 120:
        return reply('error', 400, 'The resource name must be 2 to 120 characters.', '')

    resource_uid = 'res_' + uuid.uuid4().hex[:20]
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                client_name = _client_exists(cur, client_uid)
                if client_name is None:
                    return reply('error', 404, 'Client not found.', '')
                try:
                    cur.execute(
                        "INSERT INTO dll_resources (resource_uid, account_root, resource_name, "
                        "resource_description, created_by) VALUES (%s, %s, %s, %s, %s)",
                        (resource_uid, client_uid, name, description, _actor()))
                except psycopg2.errors.UniqueViolation:
                    return reply('error', 409, f'{client_name} already has a resource called "{name}".', '')
    finally:
        conn.close()
    log_audit_event(actor=_actor(), action='CREATE', obj=f'Resource "{name}" ({resource_uid})',
                    domain='CLIENT', tenant_id=client_uid, ip_address=_ip())
    return reply('success', 201, 'Resource created', {'resource_uid': resource_uid})


@resources_bp.route('/resources/admin/<string:resource_uid>/details', methods=['GET'])
@require_staff('can_view_resource_template')
def resource_details(resource_uid):
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                row = _resource(cur, resource_uid)
                if row is None:
                    return reply('error', 404, 'Resource not found.', '')
                client_uid = row[1]
                _prune(cur, client_uid)
                cur.execute("SELECT item_type, item_uid, added_by, added_at FROM dll_resource_items "
                            "WHERE resource_uid = %s", (resource_uid,))
                raw_items = cur.fetchall()
                items = {k: [] for k in KINDS}
                for kind, (table, id_col, _, name_col) in KINDS.items():
                    uids = [u for t, u, _, _ in raw_items if t == kind]
                    if not uids:
                        continue
                    cur.execute(f"SELECT {id_col}, {name_col} FROM {table} WHERE {id_col} = ANY(%s)",
                                (uids,))
                    names = {str(u): n for u, n in cur.fetchall()}
                    items[kind] = sorted(
                        ({'uid': u, 'name': names.get(str(u))} for u in uids),
                        key=lambda i: str(i['name'] or '').lower())
                team = _team(cur, client_uid)
                cur.execute(
                    "SELECT subject_uid, access_level, granted_by, granted_at FROM dll_object_access "
                    "WHERE object_type = 'resource' AND object_uid = %s AND subject_type = 'user' "
                    "AND is_deleted = FALSE", (resource_uid,))
                grants = []
                for uid, level, by, at in cur.fetchall():
                    user = team.get(str(uid))
                    grants.append({
                        'account_uid': uid, 'access_level': level,
                        'display_name': user[1] if user else None,
                        'username': user[2] if user else None,
                        'granted_by': by, 'granted_at': _stamp(at),
                    })
    finally:
        conn.close()
    return reply('success', 200, 'Resource found', {
        'resource_uid': row[0], 'client_uid': client_uid, 'resource_name': row[2],
        'resource_description': row[3], 'created_by': row[4],
        'created_at': _stamp(row[5]), 'updated_at': _stamp(row[6]),
        'items': items, 'access': grants,
    })


@resources_bp.route('/resources/admin/<string:resource_uid>/update', methods=['PUT'])
@require_staff('can_edit_resource_template')
def update_resource(resource_uid):
    data = _payload()
    name = str(data.get('resource_name') or '').strip()
    description = str(data.get('resource_description') or '').strip()
    if len(name) < 2 or len(name) > 120:
        return reply('error', 400, 'The resource name must be 2 to 120 characters.', '')
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                row = _resource(cur, resource_uid)
                if row is None:
                    return reply('error', 404, 'Resource not found.', '')
                try:
                    cur.execute(
                        "UPDATE dll_resources SET resource_name = %s, resource_description = %s, "
                        "updated_by = %s, updated_at = NOW() WHERE resource_uid = %s",
                        (name, description, _actor(), resource_uid))
                except psycopg2.errors.UniqueViolation:
                    return reply('error', 409, f'This client already has a resource called "{name}".', '')
    finally:
        conn.close()
    log_audit_event(actor=_actor(), action='UPDATE', obj=f'Resource "{name}" ({resource_uid})',
                    domain='CLIENT', tenant_id=row[1], ip_address=_ip())
    return reply('success', 200, 'Resource updated', '')


@resources_bp.route('/resources/admin/<string:resource_uid>/delete', methods=['DELETE'])
@require_staff('can_edit_resource_template')
def delete_resource(resource_uid):
    """Delete the resource. Its elements are not touched: they go back to being
    visible to the whole team, as they were before they were put in it."""
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                row = _resource(cur, resource_uid)
                if row is None:
                    return reply('error', 404, 'Resource not found.', '')
                cur.execute("DELETE FROM dll_resource_items WHERE resource_uid = %s", (resource_uid,))
                released = cur.rowcount
                cur.execute(
                    "UPDATE dll_object_access SET is_deleted = TRUE, deleted_at = NOW(), deleted_by = %s "
                    "WHERE object_type = 'resource' AND object_uid = %s AND is_deleted = FALSE",
                    (_actor(), resource_uid))
                cur.execute(
                    "UPDATE dll_resources SET is_deleted = TRUE, deleted_at = NOW(), deleted_by = %s "
                    "WHERE resource_uid = %s", (_actor(), resource_uid))
    finally:
        conn.close()
    log_audit_event(actor=_actor(), action='DELETE', obj=f'Resource "{row[2]}" ({resource_uid})',
                    domain='CLIENT', severity='Warn', tenant_id=row[1], ip_address=_ip())
    return reply('success', 200, 'Resource deleted', {'released_items': released})


@resources_bp.route('/resources/admin/<string:resource_uid>/items', methods=['PUT'])
@require_staff('can_edit_resource_template')
def set_resource_items(resource_uid):
    """Make the resource hold exactly these elements: {items: [{item_type,
    item_uid}]}. An element already in another resource of the client moves
    here; elements left out are released back to the whole team."""
    data = _payload()
    wanted = data.get('items')
    if not isinstance(wanted, list):
        return reply('error', 400, 'items must be a list of {item_type, item_uid}.', '')
    pairs = []
    for item in wanted:
        if not isinstance(item, dict):
            return reply('error', 400, 'items must be a list of {item_type, item_uid}.', '')
        kind = str(item.get('item_type') or '').strip()
        uid = str(item.get('item_uid') or '').strip()
        if kind not in KINDS or not uid:
            return reply('error', 400, f'Unknown element type "{kind}". Use one of: '
                         + ', '.join(KINDS) + '.', '')
        if (kind, uid) not in pairs:
            pairs.append((kind, uid))

    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                row = _resource(cur, resource_uid)
                if row is None:
                    return reply('error', 404, 'Resource not found.', '')
                client_uid = row[1]
                owners = _owners(client_uid, _team(cur, client_uid))

                for kind, (table, id_col, owner_col, _) in KINDS.items():
                    uids = [u for k, u in pairs if k == kind]
                    if not uids:
                        continue
                    cur.execute(f"SELECT {id_col} FROM {table} WHERE {id_col} = ANY(%s) "
                                f"AND {owner_col} = ANY(%s)", (uids, owners))
                    found = {str(r[0]) for r in cur.fetchall()}
                    missing = [u for u in uids if u not in found]
                    if missing:
                        return reply('error', 400, f'These {KIND_LABELS[kind]}s are not this '
                                     f"client's: {', '.join(missing[:5])}", '')

                cur.execute(
                    "SELECT i.item_type, i.item_uid, r.resource_name FROM dll_resource_items i "
                    "JOIN dll_resources r USING (resource_uid) "
                    "WHERE i.resource_uid <> %s AND (i.item_type, i.item_uid) IN "
                    "(SELECT * FROM unnest(%s::text[], %s::text[]))",
                    (resource_uid, [k for k, _ in pairs] or [''], [u for _, u in pairs] or ['']))
                moved = [{'item_type': t, 'item_uid': u, 'from_resource': n}
                         for t, u, n in cur.fetchall()]

                cur.execute("SELECT item_type, item_uid FROM dll_resource_items WHERE resource_uid = %s",
                            (resource_uid,))
                before = {(t, str(u)) for t, u in cur.fetchall()}
                released = [p for p in before if p not in pairs]
                for kind, uid in released:
                    cur.execute("DELETE FROM dll_resource_items WHERE item_type = %s AND item_uid = %s "
                                "AND resource_uid = %s", (kind, uid, resource_uid))
                for kind, uid in pairs:
                    cur.execute(
                        "INSERT INTO dll_resource_items (item_type, item_uid, resource_uid, added_by) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (item_type, item_uid) DO UPDATE SET "
                        "resource_uid = EXCLUDED.resource_uid, added_by = EXCLUDED.added_by, "
                        "added_at = NOW() WHERE dll_resource_items.resource_uid <> EXCLUDED.resource_uid",
                        (kind, uid, resource_uid, _actor()))
                cur.execute("UPDATE dll_resources SET updated_by = %s, updated_at = NOW() "
                            "WHERE resource_uid = %s", (_actor(), resource_uid))
    finally:
        conn.close()
    log_audit_event(actor=_actor(), action='UPDATE',
                    obj=f'Resource "{row[2]}" elements: {len(pairs)} held, {len(released)} released, '
                        f'{len(moved)} moved in', domain='CLIENT', tenant_id=client_uid, ip_address=_ip())
    return reply('success', 200, 'Resource elements saved',
                 {'held': len(pairs), 'released': len(released), 'moved': moved})


@resources_bp.route('/resources/admin/<string:resource_uid>/access', methods=['PUT'])
@require_staff('can_share_resource_template', 'can_edit_resource_template')
def set_resource_access(resource_uid):
    """Share the resource with exactly these users: {access: [{account_uid,
    access_level: view|manage}]}. Users left out lose their grant."""
    data = _payload()
    wanted = data.get('access')
    if not isinstance(wanted, list):
        return reply('error', 400, 'access must be a list of {account_uid, access_level}.', '')
    grants = {}
    for item in wanted:
        if not isinstance(item, dict):
            return reply('error', 400, 'access must be a list of {account_uid, access_level}.', '')
        uid = str(item.get('account_uid') or '').strip()
        level = str(item.get('access_level') or 'view').strip().lower()
        if not uid:
            return reply('error', 400, 'Each grant needs an account_uid.', '')
        if level not in ACCESS_LEVELS:
            return reply('error', 400, 'access_level must be "view" or "manage".', '')
        grants[uid] = level

    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                row = _resource(cur, resource_uid)
                if row is None:
                    return reply('error', 404, 'Resource not found.', '')
                client_uid = row[1]
                team = _team(cur, client_uid)
                strangers = [u for u in grants if u not in team]
                if strangers:
                    return reply('error', 400, "Resources can only be shared with the client's own "
                                 f"users. Not on this client: {', '.join(strangers[:5])}", '')

                cur.execute(
                    "SELECT subject_uid, access_level FROM dll_object_access WHERE object_type = 'resource' "
                    "AND object_uid = %s AND subject_type = 'user' AND is_deleted = FALSE",
                    (resource_uid,))
                current = {str(u): lvl for u, lvl in cur.fetchall()}

                for uid in current:
                    if uid not in grants:
                        cur.execute(
                            "UPDATE dll_object_access SET is_deleted = TRUE, deleted_at = NOW(), "
                            "deleted_by = %s WHERE object_type = 'resource' AND object_uid = %s "
                            "AND subject_type = 'user' AND subject_uid = %s AND is_deleted = FALSE",
                            (_actor(), resource_uid, uid))
                for uid, level in grants.items():
                    if uid in current:
                        if current[uid] != level:
                            cur.execute(
                                "UPDATE dll_object_access SET access_level = %s, granted_by = %s, "
                                "granted_at = NOW() WHERE object_type = 'resource' AND object_uid = %s "
                                "AND subject_type = 'user' AND subject_uid = %s AND is_deleted = FALSE",
                                (level, _actor(), resource_uid, uid))
                    else:
                        cur.execute(
                            "INSERT INTO dll_object_access (access_uid, account_root, subject_type, "
                            "subject_uid, object_type, object_uid, access_level, granted_by) "
                            "VALUES (%s, %s, 'user', %s, 'resource', %s, %s, %s)",
                            ('acc_' + uuid.uuid4().hex[:20], client_uid, uid, resource_uid,
                             level, _actor()))
                cur.execute("UPDATE dll_resources SET updated_by = %s, updated_at = NOW() "
                            "WHERE resource_uid = %s", (_actor(), resource_uid))
    finally:
        conn.close()
    log_audit_event(actor=_actor(), action='UPDATE',
                    obj=f'Resource "{row[2]}" shared with {len(grants)} user(s)',
                    domain='RBAC', tenant_id=client_uid, ip_address=_ip())
    return reply('success', 200, 'Access saved', {'granted': len(grants)})
