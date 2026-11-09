#!/usr/bin/env python3
"""
test_configured_devices.py -- /devices/configured/all, batched.

The route made about eight round trips per unit. For Timothy Mwandha's 35
units that was 153 s from a development machine, and the console's Track
Playback (15 s) and Live Monitoring (30 s) gave up before the list came.

What these tests hold the rewrite to:

  * the reply is the same as before, field for field, at every data level
    (the route as it was in git HEAD is run against the same stores)
  * the number of database round trips no longer grows with the fleet
  * units with no basic-data row are still left out; an empty level still
    says No Devices Found (inhouse: an empty list, as before)

No database: Cassandra and Postgres are fakes answering by statement.

Run:
    python tests/test_configured_devices.py
"""

import importlib.util
import os
import subprocess
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


Basic = namedtuple('Basic', 'device_imei device_name device_simcard device_car_make device_car_model '
                            'device_vin_number device_car_type events_attached device_billing_status device_client')
Reg = namedtuple('Reg', 'device_imei device_vendor device_hardware service_provider_uid')

BASICS = [
    Basic('354002396040196', 'UBK 415T', 'SIM-1', 'Mercedes', 'Benz 2008', 'VIN1', 'car', '[]', 'running', 'CLIENT-1'),
    Basic('860922040927190', 'MOROTO GENSET', None, 'NONE', 'NONE', None, 'generator', None, 'running', 'CLIENT-1'),
    Basic('867556044728460', 'UAJ 712X(Kabale)', 'SIM-3', 'NONE', 'none', '', 'truck', '[]', 'blocked', 'CLIENT-1'),
    Basic('111111111111111', 'other client', 'SIM-4', 'Toyota', 'Hilux', '', 'car', '[]', 'running', 'CLIENT-2'),
]
REGISTRAR = [
    Reg('354002396040196', 'Teltonika', 'FMB920', 'SP-1'),
    Reg('860922040927190', 'Teltonika', 'FMB130', 'SP-1'),
    Reg('867556044728460', 'Concox', 'GT06', 'SP-1'),
    Reg('111111111111111', 'Teltonika', 'FMB920', 'SP-2'),
    Reg('999999999999999', 'Ghost', 'X', 'SP-1'),   # registered, no basic data: left out
]
SIMS = {'SIM-1': '0772000001', 'SIM-3': '0772000003', 'SIM-4': '0772000004'}
CLIENTS = {'CLIENT-1': 'Timothy Mwandha', 'CLIENT-2': 'Someone Else'}
SUBS = {'354002396040196': ('running', '2026-12-31'), '867556044728460': ('expired', '2026-10-01')}

Row = namedtuple('Row', 'device_imei')


class Session(object):
    """Answers the statements both versions make; counts round trips."""

    def __init__(self):
        self.trips = 0

    def prepare(self, cql):
        self.trips += 1
        return cql

    def execute(self, cql, params=()):
        self.trips += 1
        cql = ' '.join(cql.split())
        if 'FROM dll_device_basic_data WHERE device_client = ?' in cql:
            rows = [b for b in BASICS if b.device_client == params[0]]
            return rows if 'device_name' in cql else [Row(b.device_imei) for b in rows]
        if 'FROM dll_device_basic_data WHERE device_imei = ?' in cql:
            return [b for b in BASICS if b.device_imei == params[0]]
        if 'FROM dll_device_basic_data WHERE device_imei IN ?' in cql:
            return [b for b in BASICS if b.device_imei in params[0]]
        if 'FROM dll_device_registrar WHERE service_provider_uid = ?' in cql:
            return [Row(r.device_imei) for r in REGISTRAR if r.service_provider_uid == params[0]]
        if 'FROM dll_device_registrar WHERE device_imei = ?' in cql:
            return [r for r in REGISTRAR if r.device_imei == params[0]]
        if 'FROM dll_device_registrar WHERE device_imei IN ?' in cql:
            return [r for r in REGISTRAR if r.device_imei in params[0]]
        if cql == 'SELECT device_imei FROM dll_device_registrar':
            return [Row(r.device_imei) for r in REGISTRAR]
        raise AssertionError('unexpected CQL: %s' % cql)


class Cursor(object):
    def __init__(self, counter):
        self.counter, self.rows = counter, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.counter['trips'] += 1
        key = params[0]
        many = isinstance(key, (list, tuple, set))
        keys = list(key) if many else [key]
        if 'dll_telecom_assets' in sql:
            self.rows = [(k, SIMS[k]) for k in keys if k in SIMS]
        elif 'dll_client_accounts' in sql:
            self.rows = [(k, CLIENTS[k]) for k in keys if k in CLIENTS]
        elif 'end_date' in sql:
            self.rows = [(k, SUBS[k][1]) for k in keys if k in SUBS]
        elif 'subscription_status' in sql:
            self.rows = [(k, SUBS[k][0]) for k in keys if k in SUBS]
        else:
            raise AssertionError('unexpected SQL: %s' % sql)
        if not many:   # the old per-unit queries select the value alone
            self.rows = [r[1:] for r in self.rows]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class Connection(object):
    def __init__(self, counter):
        self.counter = counter

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return Cursor(self.counter)

    def close(self):
        pass


def load(name, source):
    spec = importlib.util.spec_from_loader('endpoints.' + name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = 'endpoints'
    sys.modules['endpoints.' + name] = module
    exec(compile(source, name + '.py', 'exec'), module.__dict__)
    return module


def ask(module, level, account):
    from flask import Flask
    import endpoints.db_pool as db_pool
    session = Session()
    counter = {'trips': 0}
    module.get_cassandra_session = lambda: session
    db_pool.connect = lambda *a, **k: (counter.__setitem__('trips', counter['trips'] + 1)
                                       or Connection(counter))
    app = Flask(module.__name__)
    with app.test_request_context(json={'data': {'data_level': level, 'account_uid': account}}):
        response = module.get_configured_devices()
        if isinstance(response, tuple):
            response = response[0]
        body = response.get_json()
    return body, session.trips + counter['trips']


def ask_app(module, client):
    """The mobile app's list: GET /devices/configured/<client>/client."""
    from flask import Flask
    import endpoints.db_pool as db_pool
    session = Session()
    counter = {'trips': 0}
    module.get_cassandra_session = lambda: session
    db_pool.connect = lambda *a, **k: (counter.__setitem__('trips', counter['trips'] + 1)
                                       or Connection(counter))
    app = Flask(module.__name__)
    with app.test_request_context():
        response = module.ClientConfigured_Devices(client)
        if isinstance(response, tuple):
            response = response[0]
        body = response.get_json()
    return body, session.trips + counter['trips']


def run():
    old_source = subprocess.run(['git', 'show', 'HEAD:endpoints/devices.py'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8').stdout
    new_source = open(os.path.join(ROOT, 'endpoints', 'devices.py'), encoding='utf-8').read()
    old = load('devices_old', old_source)
    new = load('devices_new', new_source)

    for level, account in (('client', 'CLIENT-1'), ('service_provider', 'SP-1'), ('inhouse', 'ALL'),
                           ('client', 'NOBODY'), ('service_provider', 'NOBODY')):
        was, old_trips = ask(old, level, account)
        now, new_trips = ask(new, level, account)
        check('1 %s/%s: the reply is the same as before' % (level, account), now, was)
        if was.get('status') == 'success' and level == 'client':
            # A fleet four times the size costs the same number of round trips.
            BASICS.extend(Basic(str(500000000000000 + i), 'unit %d' % i, None, '', '', '', 'car', None,
                                'running', 'CLIENT-1') for i in range(9))
            check('2b client: 12 units cost what 3 did', ask(new, level, account)[1], new_trips)
            del BASICS[-9:]
        if was.get('status') == 'success':
            n = len(was['data'])
            check('2 %s/%s: round trips no longer grow per unit (was %d for %d units)'
                  % (level, account, old_trips, n), new_trips <= 12, True)

    # The mobile app's list: the same reply, at a fixed cost.
    for client in ('CLIENT-1', 'CLIENT-2', 'NOBODY-AT-ALL'):
        was, old_trips = ask_app(old, client)
        now, new_trips = ask_app(new, client)
        check('4 app list %s: the reply is the same as before' % client, now, was)
        if was.get('status') == 'success':
            check('4 app list %s: round trips fixed (was %d)' % (client, old_trips), new_trips <= 12, True)
    check('4 the app list still says "running"',
          {d['subscription_status'] for d in ask_app(new, 'CLIENT-1')[0]['data']}, {'running'})

    body, _ = ask(new, 'client', 'CLIENT-1')
    check('3a the client list is that client\'s units, in order',
          [d['device_name'] for d in body['data']], ['UBK 415T', 'MOROTO GENSET', 'UAJ 712X(Kabale)'])
    check('3b a SIM number, hardware and client name are filled in',
          (body['data'][0]['simcard'], body['data'][0]['hardware'], body['data'][0]['client_name']),
          ('0772000001', 'Teltonika', 'Timothy Mwandha'))
    check('3c no subscription row still says so',
          body['data'][1]['subscription_status'], 'token_subscription_status_not_found')
    body, _ = ask(new, 'service_provider', 'SP-1')
    check('3d a registered unit with no basic data is left out',
          [d['device_imei'] for d in body['data']],
          ['354002396040196', '860922040927190', '867556044728460'])
    check('3e an unknown level is refused', ask(new, 'galaxy', 'XYZ')[0]['message'], 'Unknown data level')


if __name__ == '__main__':
    run()
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('\n%d passed, %d failed' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
