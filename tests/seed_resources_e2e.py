"""
Seed (or --wipe) the browser end-to-end fixtures for resources in a THROWAWAY
database: one staff user, one client with an admin and two operators, three
geofences, a geofence group and two event rules. Everything is prefixed e2e_.

    RESOURCES_TEST_DATABASE_URL=postgresql://.../narva_restest_db python3 tests/seed_resources_e2e.py
    RESOURCES_TEST_DATABASE_URL=... python3 tests/seed_resources_e2e.py --wipe
"""
import json
import os
import sys

import bcrypt
import psycopg2

DB = os.environ.get('RESOURCES_TEST_DATABASE_URL', '')
if not DB or DB.rstrip('/').split('/')[-1].split('?')[0] == 'narva_dbl':
    sys.exit('Set RESOURCES_TEST_DATABASE_URL to a throwaway database (never narva_dbl).')

PASSWORD = 'E2e-Resources-2026'
CLIENT = 'e2e_client_a'
USERS = [  # uid, root, type, role, username, display
    ('e2e_staff', 'engine', 'inhouse', 'super_admin', 'e2e.staff', 'E2E Staff'),
    ('e2e_admin', CLIENT, 'client', 'admin', 'e2e.admin', 'Fleet Admin'),
    ('e2e_op1', CLIENT, 'client', 'client_operator', 'e2e.op1', 'Operator One'),
    ('e2e_op2', CLIENT, 'client', 'client_operator', 'e2e.op2', 'Operator Two'),
]
RING = json.dumps([[32.58, 0.31], [32.59, 0.31], [32.59, 0.32], [32.58, 0.31]])


def wipe(cur):
    cur.execute("DELETE FROM dll_resource_items WHERE item_uid LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_object_access WHERE account_root LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_resources WHERE account_root LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_geozones WHERE geozone_uid LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_geozone_groups WHERE group_uid LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_device_events WHERE event_local_uid LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_access_relay WHERE account_uid LIKE 'e2e_%'")
    cur.execute("DELETE FROM dll_client_accounts WHERE client_uid LIKE 'e2e_%'")


def seed(cur):
    cur.execute("INSERT INTO dll_client_accounts (client_uid, client_name, client_email, date_created, "
                "created_by_who, parent_account) VALUES (%s, 'E2E Haulage', 'e2e@example.invalid', "
                "'2026-09-30', 'e2e_staff', 'e2e_staff')", (CLIENT,))
    hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    for uid, root, account_type, role, username, display in USERS:
        cur.execute("INSERT INTO dll_access_relay (account_root, account_uid, account_type, account_clearance, "
                    "access_status, date_created, email, created_by, log_username, log_password, display_name) "
                    "VALUES (%s,%s,%s,%s,'active','2026-09-30',%s,'e2e_staff',%s,%s,%s)",
                    (root, uid, account_type, role, username + '@example.invalid', username, hashed, display))
    for uid, name in (('e2e_z_north', 'depot north'), ('e2e_z_south', 'depot south'),
                      ('e2e_z_border', 'border post')):
        cur.execute("INSERT INTO dll_geozones (geozone_uid, geozone_name, geozone_description, geozone_points, "
                    "geozone_owner, date_created) VALUES (%s,%s,'E2E zone',%s,%s,'2026-09-30')",
                    (uid, name, RING, CLIENT))
    cur.execute("INSERT INTO dll_geozone_groups VALUES ('e2e_g_north','northern zones','E2E group',%s,'2026-09-30')",
                (CLIENT,))
    for uid, name, owner in (('e2e_e_speed', 'Overspeed 80', 'e2e_op2'),
                             ('e2e_e_ignition', 'Ignition watch', 'e2e_op1')):
        cur.execute("INSERT INTO dll_device_events VALUES (%s,%s,'E2E rule','speed_threshold','80',"
                    "'2026-09-30',%s,'0','[\"in_app\"]','','')", (uid, name, owner))


if __name__ == '__main__':
    conn = psycopg2.connect(DB)
    with conn, conn.cursor() as cur:
        wipe(cur)
        if '--wipe' not in sys.argv:
            seed(cur)
    conn.close()
    print('wiped' if '--wipe' in sys.argv else f'seeded; password for every e2e user: {PASSWORD}')
