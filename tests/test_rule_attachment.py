#!/usr/bin/env python3
"""
test_rule_attachment.py -- attaching event rules to units, where the alert
engine reads them.

Attach, remove and a unit's rule list used to read and write the Postgres copy
of dll_device_basic_data, which is no longer kept current. The alert engine
(alert_engine.load_units), the vehicle lists and the console's rule editor
read the Cassandra registry. So a rule attached to a vehicle was never checked,
and a vehicle missing from the copy (UBK 415T, CEO-CAR, UA 628BV) was skipped
while the reply said "Devices Attached SuccessFuly". A rule deleted while
still attached made the vehicle's rule list fail with a 500.

What these tests hold the routes to:

  * attach writes the registry, and the engine's own load_units then sees the
    rule; the Postgres copy is updated too where it has the unit
  * a unit that is not registered is reported, never created, and never
    claimed as attached; nothing attached at all is an error
  * attaching twice is reported, not doubled, and device_count follows
  * remove takes the rule off the registry; the rule list reads the registry
    and leaves out deleted rules instead of failing

No database: Cassandra and Postgres are fakes holding a few units.

Run:
    python tests/test_rule_attachment.py
"""

import json
import os
import sys
import types
from collections import namedtuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if 'endpoints' not in sys.modules:
    pkg = types.ModuleType('endpoints')
    pkg.__path__ = [os.path.join(ROOT, 'endpoints')]
    sys.modules['endpoints'] = pkg

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append(
        name if got == want else '%s\n      got  %r\n      want %r'
        % (name, got, want))


UBK = '354002396040196'      # registered; missing from the Postgres copy
UAJ = '867556044728460'      # registered and in the copy
GHOST = '999999999999999'    # not registered anywhere
SPEED = 'EVT-SPEEDING-0001'
ZONE = 'EVT-GEOFENCE-0002'
GONE = 'EVT-DELETED-00003'   # attached, then the rule was deleted

Row = namedtuple('Row', 'device_imei device_name device_client events_attached')


class Result(list):
    def one(self):
        return self[0] if self else None


class Session(object):
    """The Cassandra registry: imei -> events_attached text."""

    def __init__(self, registry):
        self.registry = dict(registry)

    def prepare(self, cql):
        return ' '.join(cql.split())

    def execute(self, cql, params=()):
        cql = ' '.join(cql.split())
        if cql.startswith('SELECT events_attached FROM dll_device_basic_data WHERE device_imei = ?'):
            imei = params[0]
            return Result([Row(imei, '', '', self.registry[imei])] if imei in self.registry else [])
        if cql.startswith('UPDATE dll_device_basic_data SET events_attached = ? WHERE device_imei = ?'):
            # An UPDATE is an upsert in Cassandra: an unknown IMEI gets a row.
            self.registry[params[1]] = params[0]
            return Result()
        if cql == ('SELECT device_imei, device_name, device_client, events_attached '
                   'FROM dll_device_basic_data'):
            return Result(Row(i, 'unit ' + i[-4:], 'CLIENT-1', e) for i, e in self.registry.items())
        raise AssertionError('unexpected CQL: %s' % cql)


class Postgres(object):
    def __init__(self, copy, rules):
        self.copy = dict(copy)        # the stale dll_device_basic_data copy
        self.rules = dict(rules)      # event uid -> [display name, device_count]
        self.opened = self.closed = 0


class Cursor(object):
    def __init__(self, db):
        self.db, self.rows, self.rowcount = db, [], 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        sql = ' '.join(sql.split())
        db = self.db
        if sql.startswith('SELECT device_count FROM dll_device_events'):
            rule = db.rules.get(params[0])
            self.rows = [(rule[1],)] if rule else []
        elif sql.startswith('UPDATE dll_device_events SET device_count'):
            db.rules[params[1]][1] = params[0]
            self.rows = []
        elif sql.startswith('UPDATE dll_device_basic_data SET events_attached'):
            if params[1] in db.copy:
                db.copy[params[1]] = params[0]
            self.rows = []
        elif sql.startswith('SELECT event_local_uid, event_display_name FROM dll_device_events'):
            self.rows = [(u, db.rules[u][0]) for u in params[0] if u in db.rules]
        else:
            raise AssertionError('unexpected SQL: %s' % sql)
        self.rowcount = len(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class Connection(object):
    def __init__(self, db):
        self.db = db
        db.opened += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return Cursor(self.db)

    def close(self):
        self.db.closed += 1


class Policy(object):
    def apply(self, kind, rows, key):
        return rows


def stores():
    session = Session({UBK: '[]', UAJ: json.dumps([GONE])})
    db = Postgres({UAJ: json.dumps([GONE])},
                  {SPEED: ['Speeding 80', '0'], ZONE: ['Left the depot', '3']})
    return session, db


def call(devices, session, db, route, *args, body=None, method='GET'):
    from flask import Flask
    import endpoints.db_pool as db_pool
    devices.get_cassandra_session = lambda: session
    devices.resource_policy = lambda: Policy()
    db_pool.connect = lambda *a, **k: Connection(db)
    app = Flask('test_rule_attachment')
    with app.test_request_context(method=method, json=body):
        response = getattr(devices, route)(*args)
        code = 200
        if isinstance(response, tuple):
            response, code = response[0], response[1]
        return response.get_json(), code


def attach(devices, session, db, rule, imeis):
    return call(devices, session, db, 'AttachDevice', rule,
                body={'data': {'device_list': imeis}}, method='POST')


def run():
    import endpoints.devices as devices
    import endpoints.alert_engine as engine

    # ---- attach reaches the registry, and so the engine ----
    session, db = stores()
    body, _ = attach(devices, session, db, SPEED, [UBK])
    check('1a a unit missing from the Postgres copy is attached', body.get('status'), 'success')
    check('1b and written to the registry', json.loads(session.registry[UBK]), [SPEED])
    engine_view = {u['imei']: u['events'] for u in engine.load_units(session)}
    check('1c the alert engine sees the rule on it', engine_view[UBK], [SPEED])
    check('1d the reply says what happened',
          body.get('data'), {'attached': [UBK], 'already_attached': [], 'not_found': []})
    check('1e the rule counts one unit', db.rules[SPEED][1], '1')
    check('1f the copy is not given a unit it never had', UBK in db.copy, False)

    body, _ = attach(devices, session, db, SPEED, [UAJ])
    check('2a a unit in both stores gets the rule in both',
          (json.loads(session.registry[UAJ]), json.loads(db.copy[UAJ])), ([GONE, SPEED], [GONE, SPEED]))

    body, _ = attach(devices, session, db, SPEED, [UBK, UBK, UAJ])
    check('3a attaching again is reported, not doubled',
          body.get('data'), {'attached': [], 'already_attached': [UBK, UAJ], 'not_found': []})
    check('3b the registry still holds it once', json.loads(session.registry[UBK]), [SPEED])
    check('3c the count is unchanged', db.rules[SPEED][1], '2')

    # ---- what is not attached is not claimed ----
    body, code = attach(devices, session, db, ZONE, [GHOST])
    check('4a an unregistered unit alone is an error, not "attached"',
          (body.get('status'), body.get('message'), code), ('error', 'Device Not Found', 400))
    check('4b and no registry row is made for it', GHOST in session.registry, False)
    check('4c nor counted', db.rules[ZONE][1], '3')

    body, _ = attach(devices, session, db, ZONE, [GHOST, UBK])
    check('4d with others, it is listed as not found',
          (body.get('status'), body.get('data')),
          ('success', {'attached': [UBK], 'already_attached': [], 'not_found': [GHOST]}))

    before = dict(session.registry)
    body, code = attach(devices, session, db, 'EVT-NO-SUCH-RULE', [UBK])
    check('5a an unknown rule attaches nothing',
          (body.get('message'), code, session.registry), ('Event Route Not Found', 400, before))
    body, code = attach(devices, session, db, SPEED, [])
    check('5b an empty list is refused', (body.get('message'), code), ('Some data Is Missing', 400))

    # ---- the rule list reads the registry; a deleted rule is left out ----
    body, code = call(devices, session, db, 'GetDevice_Events', UAJ)
    check('6a a deleted rule no longer fails the list',
          (code, body.get('data')), (200, [{'event_name': 'Speeding 80', 'event_id': SPEED}]))
    body, _ = call(devices, session, db, 'GetDevice_Events', UBK)
    check('6b a unit missing from the copy lists its rules',
          [e['event_id'] for e in body.get('data') or []], [SPEED, ZONE])
    body, _ = call(devices, session, db, 'GetDevice_Events', GHOST)
    check('6c an unregistered unit is not found', body.get('message'), 'Device Not Found')
    session.registry['860922040927190'] = None
    body, _ = call(devices, session, db, 'GetDevice_Events', '860922040927190')
    check('6d an empty events_attached is "No Events Attached"', body.get('message'), 'No Events Attached')

    # ---- remove ----
    body, _ = call(devices, session, db, 'RemoveEvent', UBK, SPEED, method='PUT')
    check('7a remove takes it off the registry',
          (body.get('status'), json.loads(session.registry[UBK])), ('success', [ZONE]))
    check('7b and the engine no longer sees it',
          {u['imei']: u['events'] for u in engine.load_units(session)}[UBK], [ZONE])
    check('7c the count follows', db.rules[SPEED][1], '1')
    body, code = call(devices, session, db, 'RemoveEvent', UBK, SPEED, method='PUT')
    check('7d removing it again is refused', (body.get('message'), code), ('Event Is Not Attached', 400))
    body, _ = call(devices, session, db, 'RemoveEvent', UAJ, GONE, method='PUT')
    check('7e a deleted rule can still be taken off a unit',
          (body.get('status'), json.loads(session.registry[UAJ]), json.loads(db.copy[UAJ])),
          ('success', [SPEED], [SPEED]))
    body, _ = call(devices, session, db, 'RemoveEvent', GHOST, SPEED, method='PUT')
    check('7f an unregistered unit is not found', body.get('message'), 'Device Not Found')

    # ---- the store being down ----
    devices.get_cassandra_session = lambda: None
    for route, args, method in (('AttachDevice', (SPEED,), 'POST'), ('RemoveEvent', (UBK, SPEED), 'PUT'),
                                ('GetDevice_Events', (UBK,), 'GET')):
        from flask import Flask
        with Flask('x').test_request_context(method=method, json={'data': {'device_list': [UBK]}}):
            response = getattr(devices, route)(*args)
            code = response[1] if isinstance(response, tuple) else 200
        check('8 %s says the registry is unavailable' % route, code, 503)

    check('9 every connection opened was handed back', db.closed, db.opened)


if __name__ == '__main__':
    run()
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('\n%d passed, %d failed' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
