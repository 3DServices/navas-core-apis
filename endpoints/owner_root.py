"""
owner_root.py — the client account an alert or geofence is filed under.

Alerts (dll_event_notifications.owner_uid) and geofences
(dll_geozones.geozone_owner) are read by client: the fleet summary, the
console and the OLIWA app all ask for the client's account_root. But they were
written under whatever id the writer had to hand — an alert under the owner
of the rule that raised it, and rules are created under the signed-in user's
account_uid — so a user's own alerts and zones were filed where nobody reads.

client_root() maps any account_uid to its account_root
(dll_access_relay, the same mapping globals.resolve_wallet_owner uses for
token wallets). An id that is already a root, or that no login carries
(a client account, a synthetic owner), is returned unchanged.

No Flask import, so the writers that run outside a request (the alert sweep,
the notifier) and the tests can use it directly. Works with plain and
RealDictCursor cursors.
"""


def _first(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]


def client_root(cursor, owner_uid):
    """The account_root of [owner_uid] when it is a login under a client;
    otherwise [owner_uid] itself (stripped)."""
    uid = str(owner_uid or '').strip()
    if not uid:
        return uid
    cursor.execute(
        "SELECT account_root FROM dll_access_relay WHERE account_uid = %s",
        (uid,))
    root = str(_first(cursor.fetchone()) or '').strip()
    return root or uid


# Moves rows already filed under a login to that login's client. Run by
# migration 051 (database/migrations/051_file_alerts_by_client.sql has the same
# statements); kept here so the tests pin them.
MIGRATE_ALERTS = """
    UPDATE dll_event_notifications n
       SET owner_uid = r.account_root
      FROM dll_access_relay r
     WHERE r.account_uid = n.owner_uid
       AND COALESCE(r.account_root, '') <> ''
       AND r.account_root <> n.owner_uid
"""

MIGRATE_ZONES = """
    UPDATE dll_geozones z
       SET geozone_owner = r.account_root
      FROM dll_access_relay r
     WHERE r.account_uid = z.geozone_owner
       AND COALESCE(r.account_root, '') <> ''
       AND r.account_root <> z.geozone_owner
"""
