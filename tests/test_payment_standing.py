#!/usr/bin/env python3
"""
test_payment_standing.py -- _payment_history, against a fake cursor.

No database. The cursor is a stub that returns rows the real query would
return, so the behaviour under test is the Python: what gets summed, what gets
withheld, and where last_payment_date comes from.

The cases that matter are the ones where the function must REFUSE to report a
figure: a group whose amounts were all unreadable must contribute its COUNT
and withhold its total, because a sum over nothing is not an amount of zero.

Run:
    python tests/test_payment_standing.py
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# endpoints/__init__.py imports every blueprint, which drags in the Cassandra
# driver and the whole app. This test needs one function. Register a synthetic
# package whose __path__ points at the directory, so `from .globals import ...`
# still resolves while __init__.py never runs -- the suite then has no
# dependency on the driver, exactly like tests/test_cassandra_store.py.
if 'endpoints' not in sys.modules:
    _pkg = types.ModuleType('endpoints')
    _pkg.__path__ = [os.path.join(ROOT, 'endpoints')]
    sys.modules['endpoints'] = _pkg

PASS = []
FAIL = []


def check(name, got, want):
    if got == want:
        PASS.append(name)
    else:
        FAIL.append('%s\n      got  %r\n      want %r' % (name, got, want))


def truthy(name, got):
    check(name, bool(got), True)


class FakeCursor(object):
    """Returns `agg` for the GROUP BY query and `detail` for the id DESC one."""

    def __init__(self, agg, detail=None, detail_raises=False):
        self.agg = agg
        self.detail = detail or []
        self.detail_raises = detail_raises
        self._result = []
        self.rowcount = 0
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if 'ORDER BY id DESC' in sql:
            if self.detail_raises:
                import psycopg2
                raise psycopg2.Error('detail query exploded')
            self._result = self.detail
        else:
            self._result = self.agg
        self.rowcount = len(self._result)

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


def run():
    import endpoints.waswa_context as wc

    # resolve_wallet_owner hits the database; the account family is not what
    # is under test here.
    wc.resolve_wallet_owner = lambda cur, uid: (uid, [uid, 'sibling-uid'])

    # ---- 1. the ordinary case -------------------------------------------
    # (status, currency, count, summed_total, readable_count)
    agg = [
        ('pending',    'UGX', 57, 5700, 57),
        ('successful', 'UGX', 16, 1600, 16),
        ('failed',     'UGX',  5,  500,  5),
        ('successful', 'KES',  1,   99,  1),
    ]
    detail = [
        ('2026-09-18', '99',  'KES', 'successful', '2'),
        ('2026-08-22', '100', 'UGX', 'successful', '1'),
    ]
    out, reason = wc._payment_history(FakeCursor(agg, detail), 'client-1')
    check('1a reason is None on success', reason, None)
    check('1b payments_recorded sums every group', out['payments_recorded'], 79)
    check('1c by_status merges across currencies',
          out['by_status'], {'pending': 57, 'successful': 17, 'failed': 5})
    check('1d amounts split by currency then status',
          out['amount_charged_by_currency_and_status'],
          {'UGX': {'pending': 5700, 'successful': 1600, 'failed': 500},
           'KES': {'successful': 99}})
    check('1e last payment is the NEWEST ROW BY ID, not a text MAX',
          out['last_payment_date'], '2026-09-18')
    check('1f nothing unreadable', out['amounts_unreadable'], 0)
    check('1g recent list is capped by the query, newest first',
          [r['date'] for r in out['recent_payments']],
          ['2026-09-18', '2026-08-22'])

    # ---- 2. a group whose amounts are ALL unreadable ---------------------
    # SQL sums the guarded CASE to 0 and reports readable=0. Reporting that 0
    # would tell a customer they were charged nothing.
    agg = [('pending', 'UGX', 4, 0, 0),
           ('successful', 'UGX', 2, 250, 2)]
    out, reason = wc._payment_history(FakeCursor(agg, []), 'client-1')
    check('2a the unreadable group still contributes its COUNT',
          out['by_status'], {'pending': 4, 'successful': 2})
    check('2b and its amount is WITHHELD, not reported as 0',
          out['amount_charged_by_currency_and_status'],
          {'UGX': {'successful': 250}})
    check('2c unreadable amounts are counted and stated',
          out['amounts_unreadable'], 4)

    # ---- 3. partially readable group ------------------------------------
    agg = [('pending', 'UGX', 10, 600, 6)]
    out, _ = wc._payment_history(FakeCursor(agg, []), 'client-1')
    check('3a the readable part is reported',
          out['amount_charged_by_currency_and_status'], {'UGX': {'pending': 600}})
    check('3b and the 4 unreadable rows are declared',
          out['amounts_unreadable'], 4)

    # ---- 4. no rows ------------------------------------------------------
    out, reason = wc._payment_history(FakeCursor([], []), 'client-1')
    check('4a no payments returns no value', out, None)
    truthy('4b with a reason that names the account',
           reason and 'client-1' in reason)

    # ---- 5. no owner -----------------------------------------------------
    out, reason = wc._payment_history(FakeCursor([], []), None)
    check('5a a missing client_uid is a reason, not a crash', out, None)
    check('5b and says so', reason, 'no client_uid on the account')

    # ---- 6. the detail query fails ---------------------------------------
    agg = [('successful', 'UGX', 3, 300, 3)]
    out, reason = wc._payment_history(
        FakeCursor(agg, [], detail_raises=True), 'client-1')
    check('6a totals survive a failed detail query',
          out['amount_charged_by_currency_and_status'], {'UGX': {'successful': 300}})
    check('6b recent_payments is empty', out['recent_payments'], [])
    check('6c last_payment_date is None rather than invented',
          out['last_payment_date'], None)

    # ---- 7. the SQL actually sent ----------------------------------------
    cur = FakeCursor([('successful', 'UGX', 1, 10, 1)], [])
    wc._payment_history(cur, 'client-1')
    agg_sql = cur.queries[0]
    check('7a no unguarded SUM(total_cost)', 'SUM(total_cost)' in agg_sql, False)
    check('7b no lexical MAX(payment_date)',
          'MAX(payment_date)' in agg_sql, False)
    truthy('7c the numeric guard is applied', '~ %(re)s' in agg_sql)
    truthy('7d the sum is cast after being guarded', '::numeric' in agg_sql)
    truthy('7e readable rows are counted', 'FILTER (WHERE' in agg_sql)
    truthy('7f detail query still orders by id', 'ORDER BY id DESC' in cur.queries[1])

    # ---- 8. the guard regex itself ---------------------------------------
    import re
    rx = re.compile(wc._NUMERIC_TEXT)
    for value, want in [('100', True), ('100.50', True), ('1,200', True),
                        ('  42  ', True), ('-5', True),
                        ('', False), ('N/A', False), ('UGX 100', False),
                        ('abc', False), ('.5', False)]:
        check('8 guard %-10r -> %s' % (value, want), bool(rx.match(value)), want)

    # ---- 9. the note is still there --------------------------------------
    out, _ = wc._payment_history(FakeCursor([('successful', 'UGX', 1, 10, 1)], []),
                                 'client-1')
    truthy('9a the not-a-price-list warning survived the patch',
           'never quote them as what anything costs' in out['note'])
    truthy('9b and the not-a-credit-assessment wording',
           'not a credit assessment' in out['note'])


def main():
    try:
        run()
    except Exception as error:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        print('\nSUITE CRASHED: %s' % error)
        return 1
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('')
    print('  %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
