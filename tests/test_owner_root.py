# -*- coding: utf-8 -*-
"""Tests for endpoints/owner_root.py — alerts and geofences filed by client.

owner_root.py has no Flask import, so it loads directly; the writers are
checked by reading their source, as test_signed_in_gate.py does.

Run:  python tests/test_owner_root.py
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'endpoints'))

import owner_root as orr                                   # noqa: E402

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


class Cursor:
    """dll_access_relay as {account_uid: account_root}; rows as tuples or,
    like a RealDictCursor, dicts."""

    def __init__(self, relay, dicts=False):
        self.relay, self.dicts, self.row, self.asked = relay, dicts, None, []

    def execute(self, sql, args):
        self.asked.append(args[0])
        root = self.relay.get(args[0], Cursor) if args[0] in self.relay else None
        if root is None:
            self.row = None
        else:
            self.row = {'account_root': root} if self.dicts else (root,)

    def fetchone(self):
        return self.row


relay = {'user-1': 'ROOT1', 'ROOT1': 'ROOT1', 'orphan': '', 'nulls': None}

eq('a login under a client: its client', orr.client_root(Cursor(relay), 'user-1'), 'ROOT1')
eq('the client itself: unchanged', orr.client_root(Cursor(relay), 'ROOT1'), 'ROOT1')
eq('an id no login carries: unchanged', orr.client_root(Cursor(relay), 'MTU2Njc0'), 'MTU2Njc0')
eq('a login with no root: unchanged', orr.client_root(Cursor(relay), 'orphan'), 'orphan')
eq('a NULL root: unchanged', orr.client_root(Cursor(relay), 'nulls'), 'nulls')
eq('RealDictCursor rows too', orr.client_root(Cursor(relay, dicts=True), 'user-1'), 'ROOT1')
eq('surrounding spaces are dropped', orr.client_root(Cursor(relay), '  user-1 '), 'ROOT1')
c = Cursor(relay)
eq('nothing named: nothing asked', (orr.client_root(c, ''), c.asked), ('', []))
eq('None is nothing named', orr.client_root(Cursor(relay), None), '')


# ── The migration matches the module, and is safe to repeat ────────────────

def norm(sql):
    return re.sub(r'\s+', ' ', sql).strip().rstrip(';')


with io.open(os.path.join(ROOT, 'database', 'migrations', '051_file_alerts_by_client.sql'),
             encoding='utf-8') as handle:
    migration = '\n'.join(l for l in handle.read().splitlines() if not l.startswith('--'))
statements = [norm(s) for s in migration.split(';') if s.strip()]
eq('migration 051 moves alerts as owner_root says', statements[0], norm(orr.MIGRATE_ALERTS))
eq('migration 051 moves geofences as owner_root says', statements[1], norm(orr.MIGRATE_ZONES))
for name, sql in (('alerts', orr.MIGRATE_ALERTS), ('geofences', orr.MIGRATE_ZONES)):
    eq('%s: only rows whose root differs (a second run moves nothing)' % name,
       'account_root <>' in sql and "COALESCE(r.account_root, '') <> ''" in sql, True)

# ── Every writer files by client ───────────────────────────────────────────


def source(name):
    with io.open(os.path.join(ROOT, 'endpoints', name), encoding='utf-8') as handle:
        return handle.read()


eq('the geofence alert sweep files by client',
   "client_root(cur, rule['owner_uid'] or unit['client'])" in source('alert_engine.py'), True)
eq('POST /notifications/log files by client',
   'owner_uid = client_root(cur, owner_uid)' in source('events.py'), True)
eq('the notifier files by client',
   'owner_uid = client_root(cur, owner_uid)' in source('notifier.py'), True)
eq('a new geofence is filed by client',
   '_GeoZoneOwner = client_root(cursor, _GeoZoneOwner)' in source('geozones.py'), True)


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name, '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
