# -*- coding: utf-8 -*-
"""Tests for check_device's read of the unit register (globals.billing_status).

globals.py imports Flask, Postgres and the config, none of which this needs,
so billing_status is compiled from source on its own, as
test_cassandra_store.py does, and given a fake Cassandra session.

Run:  python tests/test_check_device.py
"""

import ast
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(os.path.dirname(HERE), 'endpoints', 'globals.py')

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


def _load(name):
    with open(SOURCE, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {'logging': logging}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), SOURCE, 'exec'), scope)
    return scope[name]


billing_status = _load('billing_status')


class Row:
    def __init__(self, status):
        self.device_billing_status = status


class Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class Session:
    """A Cassandra session holding {imei: billing status}."""

    def __init__(self, register, fail=False):
        self.register = register
        self.fail = fail
        self.queries = []

    def prepare(self, cql):
        if self.fail:
            raise RuntimeError('connection reset')
        return cql

    def execute(self, stmt, params):
        self.queries.append((stmt, params))
        status = self.register.get(params[0])
        return Result(None if status is None else Row(status))


register = Session({'354002396040196': 'running', '867556044728460': 'blocked',
                    '862846042622160': None})

eq('UBK 415T, registered since the move to Cassandra, is running',
   billing_status(register, '354002396040196'), 'running')
eq('a blocked unit is blocked', billing_status(register, '867556044728460'),
   'blocked')
eq('an unregistered unit is not-found',
   billing_status(register, '000000000000000'), 'not-found')
eq('an IMEI given as a number is read as text',
   billing_status(register, 354002396040196), 'running')
eq('it reads the Cassandra register',
   'dll_device_basic_data' in register.queries[0][0], True)
eq('the store unreachable is unavailable, not not-found',
   billing_status(None, '354002396040196'), 'unavailable')
eq('a failed read is unavailable, not not-found',
   billing_status(Session({}, fail=True), '354002396040196'), 'unavailable')


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
