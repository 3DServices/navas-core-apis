#!/usr/bin/env python3
"""
audit_payment_total_cost.py -- can total_cost be summed, and how?

Why
---
endpoints/waswa_context.py::_payment_history runs SUM(total_cost) and fails
with "function sum(text) does not exist", for every account on every request.
Waswa has never been able to report payment standing to anyone.

The rest of the repo already knows this column is text: statistics.py sums it
six times as SUM(pl.total_cost::numeric). So the established convention is a
hard ::numeric cast -- but a hard cast RAISES on any value that is not a valid
numeric ('', 'N/A', '1,200', a currency symbol). One bad row would kill the
lookup again, and would also mean those six statistics queries are a latent
crash rather than working code.

_token_position in the same file takes the other approach: a regex guard that
sums only parseable values and counts how many were parseable, so it can never
raise and never reports a sum of zero readable rows as a balance of 0.

Which fix is correct depends on the data, not on taste. This script asks.

Read-only: SELECTs and information_schema only. It never casts without a
guard, so it cannot fail on the data it is inspecting.

Usage:
    python scripts/audit_payment_total_cost.py
"""

import sys

sys.path.insert(0, '.')

# A value that ::numeric would accept. Deliberately stricter than Postgres
# (which also takes leading +, exponents and whitespace forms) so that
# anything flagged here is genuinely worth looking at.
NUMERIC_RE = r'^\s*-?[0-9][0-9]*(\.[0-9]+)?\s*$'

COLUMNS = """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'dll_payment_logs'
  AND column_name IN ('total_cost', 'payment_date', 'token_quantity',
                      'payment_status', 'payment_currency', 'payment_account')
ORDER BY column_name;
"""

SHAPE = """
SELECT
    COUNT(*)                                                  AS rows_total,
    COUNT(*) FILTER (WHERE total_cost IS NULL)                AS null_cost,
    COUNT(*) FILTER (WHERE total_cost = '')                   AS empty_cost,
    COUNT(*) FILTER (WHERE total_cost ~ %(re)s)               AS parseable,
    COUNT(*) FILTER (WHERE total_cost IS NOT NULL
                       AND total_cost !~ %(re)s)              AS not_parseable
FROM dll_payment_logs;
"""

BAD_SAMPLES = """
SELECT total_cost, payment_currency, payment_status, COUNT(*)
FROM dll_payment_logs
WHERE total_cost IS NOT NULL AND total_cost !~ %(re)s
GROUP BY total_cost, payment_currency, payment_status
ORDER BY COUNT(*) DESC
LIMIT 20;
"""

STATUSES = """
SELECT payment_status, payment_currency, COUNT(*),
       COUNT(*) FILTER (WHERE total_cost ~ %(re)s) AS parseable
FROM dll_payment_logs
GROUP BY payment_status, payment_currency
ORDER BY COUNT(*) DESC
LIMIT 20;
"""

# The two accounts the eval set is bound to.
EVAL_ACCOUNTS = [
    'f8e17a96-b5b1-483b-938d-7cf4673692f6',
    '3f20c477-4446-4070-ad96-79aaa6877bd9',
]


def main():
    import psycopg2
    from config import DB_LINK
    from endpoints.globals import resolve_wallet_owner

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True          # mirror endpoints/assistant.py
    try:
        with conn.cursor() as cur:
            print('=' * 86)
            print('  dll_payment_logs -- column types')
            print('=' * 86)
            cur.execute(COLUMNS)
            for name, dtype, nullable in cur.fetchall():
                flag = ''
                if name == 'total_cost':
                    flag = ('   <- SUM() fails on this type'
                            if dtype in ('text', 'character varying')
                            else '   <- already numeric; the error must come '
                                 'from somewhere else')
                print('  %-20s %-20s null=%s%s' % (name, dtype, nullable, flag))

            print('')
            print('=' * 86)
            print('  can every row be cast?')
            print('=' * 86)
            cur.execute(SHAPE, {'re': NUMERIC_RE})
            total, nulls, empties, ok, bad = cur.fetchone()
            print('  rows                     %d' % total)
            print('  total_cost IS NULL       %d   (a cast ignores these)'
                  % nulls)
            print("  total_cost = ''          %d   %s"
                  % (empties, '<- ::numeric RAISES on these' if empties else ''))
            print('  parseable as a number    %d' % ok)
            print('  NOT parseable            %d   %s'
                  % (bad, '<- ::numeric RAISES on these' if bad else ''))

            if bad:
                print('')
                print('  the values that would break a hard cast:')
                cur.execute(BAD_SAMPLES, {'re': NUMERIC_RE})
                for value, currency, status, count in cur.fetchall():
                    print('      %-24r currency=%-6s status=%-12s x%d'
                          % (value, currency, status, count))

            print('')
            print('=' * 86)
            print('  statuses and currencies as stored')
            print('=' * 86)
            print('  %-18s %-10s %8s %10s'
                  % ('payment_status', 'currency', 'rows', 'parseable'))
            cur.execute(STATUSES, {'re': NUMERIC_RE})
            for status, currency, count, parseable in cur.fetchall():
                print('  %-18s %-10s %8d %10d'
                      % (status, currency, count, parseable))

            print('')
            print('=' * 86)
            print('  the two accounts the eval set is bound to')
            print('=' * 86)
            for uid in EVAL_ACCOUNTS:
                cur.execute(
                    'SELECT account_root FROM dll_access_relay '
                    'WHERE account_uid = %s', (uid,))
                root = cur.fetchone()
                if not root:
                    print('  %s  no relay row' % uid)
                    continue
                _, owners = resolve_wallet_owner(cur, root[0])
                cur.execute(
                    'SELECT COUNT(*), '
                    '       COUNT(*) FILTER (WHERE total_cost ~ %(re)s), '
                    '       MAX(payment_date) '
                    'FROM dll_payment_logs '
                    'WHERE payment_account = ANY(%(uids)s)',
                    {'re': NUMERIC_RE, 'uids': owners})
                rows, parseable, last = cur.fetchone()
                print('  %s' % uid)
                print('      client %s, %d uid(s) in the account family'
                      % (root[0], len(owners)))
                print('      payment rows %d, parseable %d, last %s'
                      % (rows, parseable, last))
                if rows == 0:
                    print('      -> this account has no payments, so even a '
                          'fixed query returns "no payments logged"')

            print('')
            print('=' * 86)
            print('  what this means for the fix')
            print('=' * 86)
            if bad or empties:
                print('  A hard ::numeric cast is NOT safe: %d row(s) would'
                      % (bad + empties))
                print('  raise invalid input syntax and lose the slot again.')
                print('  Use the regex-guarded pattern from _token_position,')
                print('  which sums only parseable values and counts them.')
                print('')
                print('  It also means statistics.py lines 1520, 1521, 1860-')
                print('  1863, 1878 and 1896 are a latent crash: they all use')
                print('  SUM(pl.total_cost::numeric) with no guard.')
            else:
                print('  Every value is cleanly numeric, so SUM(total_cost::')
                print('  numeric) is safe and matches what statistics.py')
                print('  already does. The regex guard would still be more')
                print('  defensive against future bad rows -- a judgement')
                print('  call, not a correctness one.')
    finally:
        conn.close()
    print('')
    print('  Read-only. Nothing was written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
