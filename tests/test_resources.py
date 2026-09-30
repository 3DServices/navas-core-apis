"""
Resources, end to end: the staff endpoints the CMS uses, /resources/mine that
the apps read, and the policy on the geofence, geofence group and event rule
routes the apps call.

Runs the real app (Flask test client) against a THROWAWAY database. It creates
and deletes its own clients, users and elements, all with the prefix rtst_.

    RESOURCES_TEST_DATABASE_URL=postgresql://.../narva_restest_db \
    JWT_SECRET=... CASSANDRA_PASSWORD=... \
    python3 -m unittest tests.test_resources -v

It refuses to run against the production database (narva_dbl).
"""
import json
import os
import sys
import unittest
import uuid

TEST_DB = os.environ.get('RESOURCES_TEST_DATABASE_URL', '')
if TEST_DB:
    os.environ['DATABASE_URL'] = TEST_DB
    os.environ['AUTH_GATE_MODE'] = 'enforce'
    os.environ.setdefault('JWT_SECRET', 'rtst-' + uuid.uuid4().hex)
    os.environ.setdefault('CASSANDRA_PASSWORD', 'unused-by-these-tests')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

P = 'rtst_'
CLIENT = P + 'client_a'
OTHER_CLIENT = P + 'client_b'

# account_uid: (account_root, account_type, role)
USERS = {
    P + 'staff': ('engine', 'inhouse', 'super_admin'),
    P + 'staff_noperm': ('engine', 'inhouse', 'rtst_no_such_role'),
    P + 'admin': (CLIENT, 'client', 'admin'),
    P + 'op1': (CLIENT, 'client', 'client_operator'),
    P + 'op2': (CLIENT, 'client', 'client_operator'),
    P + 'viewer': (CLIENT, 'client', 'client_viewer'),
    P + 'other_admin': (OTHER_CLIENT, 'client', 'admin'),
}

Z_IN_R1, Z_OPEN, Z_IN_R2, Z_OTHER, Z_DOOMED = (P + 'z_r1', P + 'z_open', P + 'z_r2',
                                               P + 'z_other', P + 'z_doomed')
G_IN_R1, G_OPEN = P + 'g_r1', P + 'g_open'
E_TEAMMATE, E_OWN_OPEN, E_OWN_IN_R2 = P + 'e_teammate', P + 'e_own_open', P + 'e_own_r2'


def _db():
    import psycopg2
    return psycopg2.connect(TEST_DB)


def _wipe(cur):
    cur.execute("DELETE FROM dll_resource_items WHERE item_uid LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_object_access WHERE subject_uid LIKE %s OR account_root LIKE %s",
                (P + '%', P + '%'))
    cur.execute("DELETE FROM dll_resources WHERE account_root LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_geozones WHERE geozone_uid LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_geozone_groups WHERE group_uid LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_device_events WHERE event_local_uid LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_access_relay WHERE account_uid LIKE %s", (P + '%',))
    cur.execute("DELETE FROM dll_client_accounts WHERE client_uid LIKE %s", (P + '%',))


def _seed(cur):
    for uid, name in ((CLIENT, 'RTST Transport'), (OTHER_CLIENT, 'RTST Other')):
        cur.execute("INSERT INTO dll_client_accounts (client_uid, client_name, client_email, "
                    "date_created, created_by_who, parent_account) VALUES (%s,%s,%s,%s,%s,%s)",
                    (uid, name, uid + '@example.invalid', '2026-09-30', P + 'staff', P + 'staff'))
    for uid, (root, account_type, role) in USERS.items():
        cur.execute("INSERT INTO dll_access_relay (account_root, account_uid, account_type, "
                    "account_clearance, access_status, date_created, email, created_by, "
                    "log_username, log_password, display_name) "
                    "VALUES (%s,%s,%s,%s,'active','2026-09-30',%s,%s,%s,'x',%s)",
                    (root, uid, account_type, role, uid + '@example.invalid', P + 'staff',
                     uid, uid.replace(P, '').title()))
    ring = json.dumps([[32.58, 0.31], [32.59, 0.31], [32.59, 0.32], [32.58, 0.31]])
    for uid, owner in ((Z_IN_R1, CLIENT), (Z_OPEN, CLIENT), (Z_IN_R2, CLIENT),
                       (Z_DOOMED, CLIENT), (Z_OTHER, OTHER_CLIENT)):
        cur.execute("INSERT INTO dll_geozones (geozone_uid, geozone_name, geozone_description, "
                    "geozone_points, geozone_owner, date_created) VALUES (%s,%s,'test',%s,%s,'2026-09-30')",
                    (uid, uid, ring, owner))
    for uid in (G_IN_R1, G_OPEN):
        cur.execute("INSERT INTO dll_geozone_groups VALUES (%s,%s,'test',%s,'2026-09-30')",
                    (uid, uid, CLIENT))
    for uid, owner in ((E_TEAMMATE, P + 'op2'), (E_OWN_OPEN, P + 'op1'), (E_OWN_IN_R2, P + 'op1')):
        cur.execute("INSERT INTO dll_device_events VALUES (%s,%s,'test','speed_threshold','80',"
                    "'2026-09-30',%s,'0','[\"in_app\"]','','')", (uid, uid, owner))


@unittest.skipUnless(TEST_DB, 'set RESOURCES_TEST_DATABASE_URL to a throwaway database')
class ResourcesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if TEST_DB.rstrip('/').split('/')[-1].split('?')[0] == 'narva_dbl':
            raise RuntimeError('Refusing to run against the production database.')
        from endpoints import Sentinel_Fleet
        from endpoints.jwt_utils import create_access_token
        cls.app = Sentinel_Fleet()
        cls.app.config['db_link'] = TEST_DB
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()
        cls.tokens = {uid: create_access_token(uid, role, account_type, root)
                      for uid, (root, account_type, role) in USERS.items()}
        conn = _db()
        with conn, conn.cursor() as cur:
            with open(os.path.join(os.path.dirname(__file__), '..', 'database', 'migrations',
                                   '045_resources.sql'), encoding='utf-8') as fh:
                cur.execute(fh.read())
            _wipe(cur)
            _seed(cur)
        conn.close()

    @classmethod
    def tearDownClass(cls):
        conn = _db()
        with conn, conn.cursor() as cur:
            _wipe(cur)
        conn.close()

    # helpers
    def call(self, method, path, who, body=None):
        headers = {'Authorization': 'Bearer ' + self.tokens[who]} if who else {}
        kwargs = {'headers': headers}
        if body is not None:
            kwargs['json'] = {'data': body}
        res = getattr(self.client, method)(path, **kwargs)
        return res.status_code, res.get_json()

    def ok(self, method, path, who, body=None):
        code, out = self.call(method, path, who, body)
        self.assertLess(code, 300, f'{method.upper()} {path} as {who}: {code} {out}')
        return out['data']

    def denied(self, method, path, who, body=None, code=403):
        got, out = self.call(method, path, who, body)
        self.assertEqual(got, code, f'{method.upper()} {path} as {who}: expected {code}, got {got} {out}')
        return out

    def zones(self, who):
        code, out = self.call('get', f'/geozones/{CLIENT}/list/client/load', who)
        if code == 400 and out['message'] == 'No Geozones Found':
            return {}
        self.assertEqual(code, 200, out)
        return {z['geozone_uid']: z for z in out['data']}

    def groups(self, who):
        return {g['group_uid']: g for g in self.ok('get', f'/geozones/groups/{CLIENT}/list', who)}

    def rules(self, who, owner=None):
        code, out = self.call('post', '/events/getall', who,
                              {'load_level': 'usri', 'owner_uid': owner or who})
        if code == 400 and out['message'] == 'No Events Found':
            return {}
        self.assertEqual(code, 200, out)
        return {e['event_uid']: e for e in out['data']}

    def make_resource(self, name, items=(), access=()):
        uid = self.ok('post', '/resources/admin/create', P + 'staff',
                      {'client_uid': CLIENT, 'resource_name': name,
                       'resource_description': 'test'})['resource_uid']
        self.ok('put', f'/resources/admin/{uid}/items', P + 'staff',
                {'items': [{'item_type': t, 'item_uid': u} for t, u in items]})
        self.ok('put', f'/resources/admin/{uid}/access', P + 'staff',
                {'access': [{'account_uid': u, 'access_level': lvl} for u, lvl in access]})
        return uid

    def drop_resource(self, uid):
        self.ok('delete', f'/resources/admin/{uid}/delete', P + 'staff')

    # ── staff side (CMS) ─────────────────────────────────────────────────────

    def test_staff_create_validation(self):
        uid = self.make_resource('Depot North')
        try:
            out = self.denied('post', '/resources/admin/create', P + 'staff',
                              {'client_uid': CLIENT, 'resource_name': 'depot north'}, code=409)
            self.assertIn('already has a resource', out['message'])
            self.denied('post', '/resources/admin/create', P + 'staff',
                        {'client_uid': CLIENT, 'resource_name': 'x'}, code=400)
            self.denied('post', '/resources/admin/create', P + 'staff',
                        {'client_uid': '', 'resource_name': 'Valid name'}, code=400)
            self.denied('post', '/resources/admin/create', P + 'staff',
                        {'client_uid': P + 'nobody', 'resource_name': 'Valid name'}, code=404)
            self.denied('put', f'/resources/admin/{uid}/update', P + 'staff',
                        {'resource_name': ''}, code=400)
            self.ok('put', f'/resources/admin/{uid}/update', P + 'staff',
                    {'resource_name': 'Depot North Renamed', 'resource_description': 'new'})
            detail = self.ok('get', f'/resources/admin/{uid}/details', P + 'staff')
            self.assertEqual(detail['resource_name'], 'Depot North Renamed')
            self.assertEqual(detail['resource_description'], 'new')
            self.denied('get', f'/resources/admin/{P}missing/details', P + 'staff', code=404)
        finally:
            self.drop_resource(uid)

    def test_staff_routes_are_closed_to_others(self):
        for path in (f'/resources/admin/clients/{CLIENT}/list',
                     f'/resources/admin/clients/{CLIENT}/catalog'):
            self.denied('get', path, P + 'admin')          # customer admin
            self.denied('get', path, P + 'op1')            # customer user
            self.denied('get', path, P + 'staff_noperm')   # staff without the permission
            self.denied('get', path, None, code=401)       # not signed in
        self.denied('post', '/resources/admin/create', P + 'admin',
                    {'client_uid': CLIENT, 'resource_name': 'Sneaky'})

    def test_catalog_lists_elements_and_users(self):
        uid = self.make_resource('Catalog Check', items=[('geozone', Z_IN_R1)])
        try:
            cat = self.ok('get', f'/resources/admin/clients/{CLIENT}/catalog', P + 'staff')
            zones = {z['uid']: z for z in cat['elements']['geozone']}
            self.assertEqual(set(zones), {Z_IN_R1, Z_OPEN, Z_IN_R2, Z_DOOMED})
            self.assertNotIn(Z_OTHER, zones)                          # other client's
            self.assertEqual(zones[Z_IN_R1]['resource_uid'], uid)
            self.assertIsNone(zones[Z_OPEN]['resource_uid'])
            self.assertEqual({g['uid'] for g in cat['elements']['geozone_group']}, {G_IN_R1, G_OPEN})
            rules = {e['uid']: e for e in cat['elements']['event_rule']}
            self.assertEqual(set(rules), {E_TEAMMATE, E_OWN_OPEN, E_OWN_IN_R2})
            self.assertEqual(rules[E_TEAMMATE]['owner_uid'], P + 'op2')  # teammate-owned counts
            users = {u['account_uid']: u for u in cat['users']}
            self.assertEqual(set(users), {P + 'admin', P + 'op1', P + 'op2', P + 'viewer'})
            self.assertTrue(users[P + 'admin']['sees_everything'])
            self.assertFalse(users[P + 'op1']['sees_everything'])
            listed = self.ok('get', f'/resources/admin/clients/{CLIENT}/list', P + 'staff')
            self.assertEqual([r['item_count'] for r in listed if r['resource_uid'] == uid], [1])
        finally:
            self.drop_resource(uid)

    def test_items_validation_and_moving(self):
        r1 = self.make_resource('Items One', items=[('geozone', Z_IN_R1)])
        r2 = self.make_resource('Items Two')
        try:
            out = self.denied('put', f'/resources/admin/{r2}/items', P + 'staff',
                              {'items': [{'item_type': 'geozone', 'item_uid': Z_OTHER}]}, code=400)
            self.assertIn("not this client's", out['message'])
            self.denied('put', f'/resources/admin/{r2}/items', P + 'staff',
                        {'items': [{'item_type': 'poi', 'item_uid': Z_OPEN}]}, code=400)
            self.denied('put', f'/resources/admin/{r2}/items', P + 'staff',
                        {'items': 'nope'}, code=400)
            moved = self.ok('put', f'/resources/admin/{r2}/items', P + 'staff',
                            {'items': [{'item_type': 'geozone', 'item_uid': Z_IN_R1},
                                       {'item_type': 'event_rule', 'item_uid': E_TEAMMATE}]})
            self.assertEqual([m['item_uid'] for m in moved['moved']], [Z_IN_R1])
            self.assertEqual(self.ok('get', f'/resources/admin/{r1}/details', P + 'staff')['items']['geozone'], [])
            self.assertEqual({i['uid'] for i in self.ok('get', f'/resources/admin/{r2}/details',
                                                        P + 'staff')['items']['geozone']}, {Z_IN_R1})
            released = self.ok('put', f'/resources/admin/{r2}/items', P + 'staff',
                               {'items': [{'item_type': 'event_rule', 'item_uid': E_TEAMMATE}]})
            self.assertEqual(released['released'], 1)
        finally:
            self.drop_resource(r1)
            self.drop_resource(r2)

    def test_access_validation(self):
        uid = self.make_resource('Access Rules')
        try:
            out = self.denied('put', f'/resources/admin/{uid}/access', P + 'staff',
                              {'access': [{'account_uid': P + 'other_admin', 'access_level': 'view'}]},
                              code=400)
            self.assertIn("client's own users", out['message'])
            self.denied('put', f'/resources/admin/{uid}/access', P + 'staff',
                        {'access': [{'account_uid': P + 'op1', 'access_level': 'owner'}]}, code=400)
            self.ok('put', f'/resources/admin/{uid}/access', P + 'staff',
                    {'access': [{'account_uid': P + 'op1', 'access_level': 'view'},
                                {'account_uid': P + 'op2', 'access_level': 'manage'}]})
            self.ok('put', f'/resources/admin/{uid}/access', P + 'staff',
                    {'access': [{'account_uid': P + 'op1', 'access_level': 'manage'}]})
            grants = {a['account_uid']: a['access_level'] for a in
                      self.ok('get', f'/resources/admin/{uid}/details', P + 'staff')['access']}
            self.assertEqual(grants, {P + 'op1': 'manage'})
            conn = _db()
            with conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM dll_object_access WHERE object_uid = %s "
                            "AND subject_uid = %s AND is_deleted = FALSE", (uid, P + 'op1'))
                self.assertEqual(cur.fetchone()[0], 1)          # updated in place, not duplicated
            conn.close()
        finally:
            self.drop_resource(uid)

    # ── customer side (mobile app, OLIWA console) ───────────────────────────

    def test_hidden_without_a_grant(self):
        uid = self.make_resource('Hidden', items=[('geozone', Z_IN_R1), ('geozone_group', G_IN_R1),
                                                  ('event_rule', E_TEAMMATE)])
        try:
            zones = self.zones(P + 'op1')
            self.assertNotIn(Z_IN_R1, zones)
            self.assertIn(Z_OPEN, zones)
            self.assertEqual(zones[Z_OPEN]['resource_access'], 'manage')
            self.assertIsNone(zones[Z_OPEN]['resource_uid'])
            self.assertNotIn(G_IN_R1, self.groups(P + 'op1'))
            self.assertIn(G_OPEN, self.groups(P + 'op1'))
            self.assertNotIn(E_TEAMMATE, self.rules(P + 'op1', owner=P + 'op2'))
            for method, path, body in (
                ('get', f'/geozones/{Z_IN_R1}/details', None),
                ('put', f'/geozones/{Z_IN_R1}/update', {'new_geozone_name': 'x'}),
                ('delete', f'/geozones/{Z_IN_R1}/delete', None),
                ('get', f'/geozones/{Z_IN_R1}/attached-devices', None),
                ('put', f'/geozones/groups/{G_IN_R1}/update', {'group_name': 'renamed'}),
                ('get', f'/events/{E_TEAMMATE}/details', None),
                ('post', f'/events/{E_TEAMMATE}/update', {'event_name': 'x'}),
                ('delete', f'/events/{E_TEAMMATE}/delete', None),
            ):
                out = self.denied(method, path, P + 'op1', body)
                self.assertEqual(out['message'], "This record doesn't belong to your account.")
            self.denied('post', f'/geozones/groups/{G_OPEN}/assign', P + 'op1',
                        {'geozone_uids': [Z_IN_R1]})                     # hidden zone in the body
            self.assertNotIn(Z_IN_R1, self.zones(P + 'viewer'))
            mine = self.ok('get', '/resources/mine', P + 'op1')
            self.assertTrue(mine['restricted'])
            self.assertEqual(mine['resources'], [])
        finally:
            self.drop_resource(uid)

    def test_view_grant_can_see_but_not_change(self):
        uid = self.make_resource('Viewable', items=[('geozone', Z_IN_R1), ('geozone_group', G_IN_R1),
                                                    ('event_rule', E_TEAMMATE)],
                                 access=[(P + 'op1', 'view')])
        try:
            zones = self.zones(P + 'op1')
            self.assertEqual(zones[Z_IN_R1]['resource_access'], 'view')
            self.assertEqual(zones[Z_IN_R1]['resource_name'], 'Viewable')
            self.assertEqual(self.groups(P + 'op1')[G_IN_R1]['resource_access'], 'view')
            # the teammate's rule arrives in op1's own list through the grant
            rules = self.rules(P + 'op1')
            self.assertEqual(rules[E_TEAMMATE]['resource_access'], 'view')
            self.assertIn(E_OWN_OPEN, rules)
            self.ok('get', f'/geozones/{Z_IN_R1}/details', P + 'op1')
            self.ok('get', f'/events/{E_TEAMMATE}/details', P + 'op1')
            for method, path, body in (
                ('put', f'/geozones/{Z_IN_R1}/update', {'new_geozone_name': 'x'}),
                ('delete', f'/geozones/{Z_IN_R1}/delete', None),
                ('post', f'/geozones/{Z_IN_R1}/attach', {'devices': []}),
                ('put', f'/geozones/groups/{G_IN_R1}/update', {'group_name': 'renamed'}),
                ('delete', f'/geozones/groups/{G_IN_R1}/delete', None),
                ('post', f'/geozones/groups/{G_IN_R1}/assign', {'geozone_uids': [Z_OPEN]}),
                ('post', f'/events/{E_TEAMMATE}/update', {'event_name': 'x'}),
                ('delete', f'/events/{E_TEAMMATE}/delete', None),
                ('post', f'/devices/events/{E_TEAMMATE}/attach', {'device_list': []}),
            ):
                out = self.denied(method, path, P + 'op1', body)
                self.assertIn('view-only access', out['message'])
            mine = self.ok('get', '/resources/mine', P + 'op1')
            self.assertEqual([(r['resource_uid'], r['access']) for r in mine['resources']],
                             [(uid, 'view')])
            self.assertEqual(mine['resources'][0]['items']['geozone'], [Z_IN_R1])
            # op2 has no grant but created E_TEAMMATE, so keeps it
            self.assertEqual(self.rules(P + 'op2')[E_TEAMMATE]['resource_access'], 'manage')
        finally:
            self.drop_resource(uid)

    def test_manage_grant_can_change(self):
        uid = self.make_resource('Manageable', items=[('geozone', Z_IN_R1), ('geozone_group', G_IN_R1),
                                                      ('event_rule', E_TEAMMATE)],
                                 access=[(P + 'op1', 'manage')])
        try:
            self.assertEqual(self.zones(P + 'op1')[Z_IN_R1]['resource_access'], 'manage')
            self.ok('put', f'/geozones/groups/{G_IN_R1}/update', P + 'op1',
                    {'group_name': 'Renamed by op1', 'group_description': 'ok'})
            self.ok('post', f'/geozones/groups/{G_IN_R1}/assign', P + 'op1', {'geozone_uids': [Z_IN_R1]})
            self.ok('post', f'/events/{E_TEAMMATE}/update', P + 'op1', {
                'event_name': 'Renamed rule', 'event_description': 'changed by op1',
                'event_condition': 'speed_threshold', 'event_condition_value': '90',
                'alert_email': '', 'alert_phone_numbers': '', 'alert_channels': ['in_app']})
            self.assertEqual(self.rules(P + 'op1')[E_TEAMMATE]['event_name'], 'Renamed rule')
        finally:
            self.drop_resource(uid)

    def test_creator_keeps_own_element(self):
        uid = self.make_resource('Not Op1s', items=[('event_rule', E_OWN_IN_R2)],
                                 access=[(P + 'op2', 'view')])
        try:
            self.assertEqual(self.rules(P + 'op1')[E_OWN_IN_R2]['resource_access'], 'manage')
            self.ok('get', f'/events/{E_OWN_IN_R2}/details', P + 'op1')
            self.assertEqual(self.rules(P + 'op2')[E_OWN_IN_R2]['resource_access'], 'view')
            self.assertNotIn(E_OWN_IN_R2, self.rules(P + 'viewer', owner=P + 'op1'))
        finally:
            self.drop_resource(uid)

    def test_account_admin_sees_everything(self):
        r1 = self.make_resource('Admin One', items=[('geozone', Z_IN_R1)])
        r2 = self.make_resource('Admin Two', items=[('geozone', Z_IN_R2)])
        try:
            zones = self.zones(P + 'admin')
            self.assertEqual({Z_IN_R1, Z_IN_R2, Z_OPEN} - set(zones), set())
            self.assertEqual(zones[Z_IN_R1]['resource_access'], 'manage')
            self.assertEqual(zones[Z_IN_R2]['resource_name'], 'Admin Two')
            self.ok('get', f'/geozones/{Z_IN_R2}/details', P + 'admin')
            self.ok('put', f'/resources/admin/{r2}/items', P + 'staff',
                    {'items': [{'item_type': 'geozone', 'item_uid': Z_IN_R2},
                               {'item_type': 'event_rule', 'item_uid': E_TEAMMATE}]})
            rules = self.rules(P + 'admin')          # admin's own list, no rules of their own
            self.assertEqual(set(rules), {E_TEAMMATE})
            self.assertEqual(rules[E_TEAMMATE]['resource_access'], 'manage')
            mine = self.ok('get', '/resources/mine', P + 'admin')
            self.assertFalse(mine['restricted'])
            self.assertEqual({r['resource_uid'] for r in mine['resources']}, {r1, r2})
            self.assertTrue(all(r['access'] == 'manage' for r in mine['resources']))
        finally:
            self.drop_resource(r1)
            self.drop_resource(r2)

    def test_other_client_and_staff(self):
        uid = self.make_resource('Tenant Wall', items=[('geozone', Z_IN_R1)], access=[(P + 'op1', 'manage')])
        try:
            self.denied('get', f'/geozones/{CLIENT}/list/client/load', P + 'other_admin')
            self.denied('get', f'/geozones/{Z_IN_R1}/details', P + 'other_admin')
            self.assertEqual(self.ok('get', '/resources/mine', P + 'other_admin')['resources'], [])
            zones = self.zones(P + 'staff')                       # staff: nothing hidden
            self.assertIn(Z_IN_R1, zones)
            mine = self.ok('get', '/resources/mine', P + 'staff')
            self.assertEqual((mine['restricted'], mine['resources']), (False, []))
        finally:
            self.drop_resource(uid)

    def test_delete_releases_elements(self):
        uid = self.make_resource('Temporary', items=[('geozone', Z_IN_R1)])
        self.assertNotIn(Z_IN_R1, self.zones(P + 'op1'))
        released = self.ok('delete', f'/resources/admin/{uid}/delete', P + 'staff')['released_items']
        self.assertEqual(released, 1)
        zones = self.zones(P + 'op1')
        self.assertIn(Z_IN_R1, zones)
        self.assertIsNone(zones[Z_IN_R1]['resource_uid'])
        self.denied('get', f'/resources/admin/{uid}/details', P + 'staff', code=404)
        conn = _db()
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dll_object_access WHERE object_uid = %s "
                        "AND is_deleted = FALSE", (uid,))
            self.assertEqual(cur.fetchone()[0], 0)
        conn.close()

    def test_deleted_element_leaves_resource(self):
        uid = self.make_resource('Pruning', items=[('geozone', Z_DOOMED)], access=[(P + 'op1', 'manage')])
        try:
            self.ok('delete', f'/geozones/{Z_DOOMED}/delete', P + 'op1')
            detail = self.ok('get', f'/resources/admin/{uid}/details', P + 'staff')
            self.assertEqual(detail['items']['geozone'], [])
        finally:
            self.drop_resource(uid)


if __name__ == '__main__':
    unittest.main()
