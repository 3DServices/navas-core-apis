#!/usr/bin/env python3
"""
patch_payment_standing.py -- make _payment_history work.

Two defects, both in endpoints/waswa_context.py::_payment_history:

  1. SUM(total_cost) on a TEXT column. Fails with "function sum(text) does
     not exist" for every account on every request, so the whole slot is lost
     and Waswa has never once reported payment standing.

  2. MAX(payment_date) on a TEXT column. Lexical, not chronological. The
     value is shown to the customer as last_payment_date. Every date in the
     table is ISO today so it happens to be right, but the same mistake on
     DD-MM-YYYY text already produced "the 15 most recent rows" from July
     2025 in scripts/b3_report_rows.py. Ordering by id is correct whatever
     the format, and id is the insertion order.

Why the regex guard rather than ::numeric
-----------------------------------------
The audit found all 81 rows cleanly numeric, so SUM(total_cost::numeric)
would work today and would match statistics.py, which casts this column six
times. It is still the wrong choice here. A hard cast raises on the first
malformed row and silently costs the entire slot again -- which is precisely
the failure being fixed, and it fails SILENTLY in an assistant where it would
be visible in an analytics route. _token_position in this same file already
sums a text column through a regex guard for exactly this reason, and _money
already returns None rather than 0 for an unreadable amount. This matches
both.

A sum over zero readable rows is NOT reported as 0: that would tell a
customer they were charged nothing.

Idempotent and self-checking: refuses to run twice, verifies by AST that the
bad SQL is gone, and preserves the file's line endings.

Usage:
    python scripts/patch_payment_standing.py
    python scripts/patch_payment_standing.py --dry-run
"""

import argparse
import ast
import io
import os
import sys

TARGET = os.path.join('endpoints', 'waswa_context.py')

NEW_CONST = '''# A value ::numeric would accept. total_cost, payment_date, token_quantity
# and every other column on dll_payment_logs are TEXT, so a figure has to be
# guarded before it is summed -- see _payment_history.
_NUMERIC_TEXT = r'^\\s*-?[0-9][0-9,]*(\\.[0-9]+)?\\s*$'


'''

OLD_SQL = '''    try:
        cur.execute(
            "SELECT payment_status, payment_currency, COUNT(*), "
            "       SUM(total_cost), MAX(payment_date) "
            "FROM dll_payment_logs WHERE payment_account = ANY(%s) "
            "GROUP BY payment_status, payment_currency "
            "ORDER BY COUNT(*) DESC",
            (owners,),
        )
        rows = cur.fetchall() if cur.rowcount > 0 else []
    except psycopg2.Error as error:
        return None, f'dll_payment_logs unreadable: {error}'
'''

NEW_SQL = '''    try:
        cur.execute(
            # total_cost is TEXT. Sum only the values that are numbers, and
            # count them, so a total over zero readable rows is never
            # reported as an amount of 0. MAX(payment_date) is deliberately
            # absent: that column is text too, so MAX is lexical rather than
            # chronological. The last payment is taken from the newest row
            # by id below, which is correct whatever the date format.
            "SELECT payment_status, payment_currency, COUNT(*), "
            "       COALESCE(SUM(CASE WHEN total_cost ~ %(re)s "
            "                         THEN REPLACE(TRIM(total_cost), ',', '')"
            "::numeric "
            "                         ELSE 0 END), 0), "
            "       COUNT(*) FILTER (WHERE total_cost ~ %(re)s) "
            "FROM dll_payment_logs WHERE payment_account = ANY(%(uids)s) "
            "GROUP BY payment_status, payment_currency "
            "ORDER BY COUNT(*) DESC",
            {'re': _NUMERIC_TEXT, 'uids': owners},
        )
        rows = cur.fetchall() if cur.rowcount > 0 else []
    except psycopg2.Error as error:
        return None, f'dll_payment_logs unreadable: {error}'
'''

OLD_LOOP = '''    by_status = {}
    charged = {}
    for status, currency, count, total, _ in rows:
        key = status or 'unrecorded'
        by_status[key] = by_status.get(key, 0) + int(count)
        amount = _money(total)
        if amount is None:
            continue
        cur_key = (currency or '').strip().upper() or 'unknown currency'
        charged.setdefault(cur_key, {})
        charged[cur_key][key] = charged[cur_key].get(key, 0) + amount

    last_date = max((r[4] for r in rows if r[4]), default=None)
'''

NEW_LOOP = '''    by_status = {}
    charged = {}
    unreadable = 0
    for status, currency, count, total, readable in rows:
        key = status or 'unrecorded'
        by_status[key] = by_status.get(key, 0) + int(count)
        unreadable += int(count) - int(readable or 0)
        # No readable amount in this group: the sum is 0 because nothing
        # could be added, not because nothing was charged. Report the count
        # and withhold the figure.
        if not readable:
            continue
        amount = _money(total)
        if amount is None:
            continue
        cur_key = (currency or '').strip().upper() or 'unknown currency'
        charged.setdefault(cur_key, {})
        charged[cur_key][key] = charged[cur_key].get(key, 0) + amount
'''

OLD_RETURN = """        'last_payment_date': str(last_date) if last_date else None,"""

NEW_RETURN = """        # The newest row by id, not MAX() over a text date.
        'last_payment_date': recent[0]['date'] if recent else None,
        'amounts_unreadable': unreadable,"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        print('cannot find %s -- run this from the repository root' % TARGET)
        return 1

    with io.open(TARGET, 'rb') as fh:
        raw = fh.read()
    crlf = b'\r\n' in raw
    src = raw.decode('utf-8')
    if crlf:
        src = src.replace('\r\n', '\n')
    before_lines = src.count('\n')

    if '_NUMERIC_TEXT' in src:
        print('ALREADY PATCHED -- _NUMERIC_TEXT is already defined.')
        print('Nothing to do.')
        return 0

    for label, old in (('aggregate query', OLD_SQL),
                       ('totals loop', OLD_LOOP),
                       ('return value', OLD_RETURN)):
        if src.count(old) != 1:
            print('REFUSING: the %s did not match exactly once (found %d).'
                  % (label, src.count(old)))
            print('The file has changed since this patch was written. Stopping'
                  ' rather than editing the wrong place.')
            return 1

    anchor = "def _payment_history(cur, owner_uid):"
    if src.count(anchor) != 1:
        print('REFUSING: could not locate _payment_history exactly once.')
        return 1

    patched = src
    patched = patched.replace(anchor, NEW_CONST + anchor)
    patched = patched.replace(OLD_SQL, NEW_SQL)
    patched = patched.replace(OLD_LOOP, NEW_LOOP)
    patched = patched.replace(OLD_RETURN, NEW_RETURN)

    # _money's docstring asserts the opposite of the truth, which is probably
    # how the missing cast survived review.
    patched = patched.replace(
        "    total_cost is numeric, but this table has enough history that a "
        "Decimal is\n    not guaranteed.",
        "    total_cost is TEXT on this table, so this receives whatever the\n"
        "    column holds, or a Decimal once SQL has summed the guarded rows.")

    # ---------------- verify before writing ----------------
    try:
        tree = ast.parse(patched)
    except SyntaxError as error:
        print('REFUSING: the patched file does not parse -- %s' % error)
        return 1

    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == '_payment_history'), None)
    if fn is None:
        print('REFUSING: _payment_history vanished from the patched tree.')
        return 1

    # Check the AST, never the raw text. A comment explaining that
    # MAX(payment_date) was REMOVED contains the string MAX(payment_date),
    # and a text check fails a correct patch on its own explanation. This
    # codebase has that mistake on record twice; this is the third time it
    # was attempted and the first time it was caught before shipping.
    literals = ' '.join(n.value for n in ast.walk(fn)
                        if isinstance(n, ast.Constant)
                        and isinstance(n.value, str))
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}

    problems = []
    if 'SUM(total_cost)' in literals:
        problems.append('the unguarded SUM(total_cost) is still in the SQL')
    if 'MAX(payment_date)' in literals:
        problems.append('MAX(payment_date) is still in the SQL')
    if 'last_date' in names:
        problems.append('the lexical last_date is still referenced')
    if '_NUMERIC_TEXT' not in names:
        problems.append('the guard is not used inside the function')
    if problems:
        print('REFUSING: verification failed inside _payment_history:')
        for p in problems:
            print('   - %s' % p)
        return 1

    # Nothing outside this one function may change.
    others = [n.name for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)]
    if len(others) != len(set(others)):
        print('REFUSING: duplicate function definitions after patching.')
        return 1

    after_lines = patched.count('\n')
    print('endpoints/waswa_context.py  %d -> %d lines' % (before_lines, after_lines))
    print('')
    print('  SUM(total_cost)        -> guarded sum + a readable-row count')
    print('  MAX(payment_date)      -> gone; last payment is the newest row by id')
    print('  amounts_unreadable     -> new, so an unreadable amount is stated')
    print('  _money docstring       -> corrected (the column is text, not numeric)')
    print('')
    print('  line endings preserved: %s' % ('CRLF' if crlf else 'LF'))

    if args.dry_run:
        print('')
        print('  --dry-run: nothing written.')
        return 0

    out = patched.replace('\n', '\r\n') if crlf else patched
    with io.open(TARGET, 'wb') as fh:
        fh.write(out.encode('utf-8'))
    print('')
    print('  written.')
    print('')
    print('  Verify with:')
    print('      python scripts/audit_payment_total_cost.py')
    print('      Remove-Item tests\\waswa_eval\\questions.json')
    print('      python scripts/waswa_eval_build.py')
    print('  payment_standing should now resolve for both clients instead of')
    print('  reporting an SQL error.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
