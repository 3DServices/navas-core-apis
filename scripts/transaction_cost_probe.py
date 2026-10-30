#!/usr/bin/env python3
"""
transaction_cost_probe.py -- does opening a transaction cost a round trip?

THE OBSERVATION

With connection pooling in place, the statement timings on every dashboard
route split cleanly into two groups:

    first statement in a transaction     ~560 ms
    every statement after it             ~279 ms

The measured round trip to this database is 282 ms. So the second group costs
exactly one round trip, as it should, and the first costs almost exactly two.

THE HYPOTHESIS

This codebase wraps nearly every query in `with conn:`, which opens a
transaction. psycopg2 sends the BEGIN lazily, with the first statement. If
that BEGIN is its own round trip, every transaction pays one extra.

If true the prize is large: three connections per request, each paying one
wasted round trip, is roughly 840 ms per request -- and a read that does not
write does not need a transaction at all.

WHY THIS SCRIPT EXISTS RATHER THAN A CONCLUSION

The numbers fit the hypothesis almost too neatly, and earlier in this work an
equally tidy pattern -- "every route's time is a near-integer multiple of
2,027 ms" -- produced an inference that turned out to be wrong. Tidy arithmetic
is a reason to measure, not to believe.

So this is built to REFUTE as readily as to confirm, and it tests the obvious
competing explanation too:

  PART 1  the floor. SELECT 1 on an open connection, autocommit on. This is
          one round trip and nothing else.

  PART 2  the actual question. On ONE connection, alternating so that network
          drift cannot favour either side:
              (a) SELECT 1 with autocommit ON
              (b) SELECT 1 as the FIRST statement inside a transaction
              (c) SELECT 1 as the SECOND statement in that same transaction
          If the hypothesis holds: b ~ 2a, and c ~ a.
          If b ~ c ~ a, the hypothesis is WRONG and the 560 ms has another
          cause -- which is what part 3 is for.

  PART 3  the competing explanation. Perhaps those statements are simply
          slower queries. The two that appear on every route are timed here
          in autocommit, where no transaction is involved, and the indexes on
          the tables they touch are listed. A blacklist lookup that takes
          280 ms of server time on top of the round trip is a missing index,
          not a BEGIN -- and the fix would be completely different.

READ-ONLY. Issues only SELECTs (and rollbacks of its own empty transactions),
opens and closes its own connection, writes nothing, prints no secret.

Usage:
    python scripts/transaction_cost_probe.py
    python scripts/transaction_cost_probe.py --trials 25
"""

import argparse
import statistics
import sys
import time

sys.path.insert(0, '.')

RTT_NOTE = 282.0        # ms, measured by dashboard_latency_probe.py phase 1


def ms(seconds):
    return seconds * 1000.0


def timed(cursor, sql, params=None):
    began = time.perf_counter()
    cursor.execute(sql, params)
    try:
        cursor.fetchall()
    except Exception:                                      # noqa: BLE001
        pass                                               # no result set
    return time.perf_counter() - began


def summarise(label, samples, baseline=None):
    med = statistics.median(samples)
    line = '   %-38s %7.0f ms   (min %4.0f, max %4.0f, n=%d)' % (
        label, ms(med), ms(min(samples)), ms(max(samples)), len(samples))
    if baseline:
        line += '   = %.2fx' % (med / baseline)
    print(line)
    return med


def verdict(first_median, second_median, floor_median):
    """CONFIRMED / REFUTED / None, from the three medians.

    Extracted so the thresholds can be tested rather than trusted. They are
    set deliberately wide apart: a real extra round trip should put the first
    statement near 2x the second, and no transaction cost at all should put
    them within a few percent. The band between 1.25x and 1.5x is called
    inconclusive on purpose -- a probe that always answers is not measuring.

    The absolute test is against the floor this run MEASURED, not against the
    282 ms noted at the top of this file. A first draft used the constant,
    which is right for this database and wrong for any other: run the same
    probe against a local Postgres where a round trip is 1.5 ms and a genuine
    doubling would be dismissed as noise. A probe should calibrate itself.
    """
    if not second_median or not floor_median:
        return None
    ratio = first_median / second_median
    extra = first_median - second_median
    if ratio >= 1.5 and extra > floor_median * 0.6:
        return True
    if ratio < 1.25:
        return False
    return None


def heading(text):
    print()
    print(text)
    print('-' * len(text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=15)
    args = parser.parse_args()

    import psycopg2
    from config import DB_LINK

    print('transaction_cost_probe -- read-only')
    print('reference round trip from phase 1: %.0f ms' % RTT_NOTE)

    conn = psycopg2.connect(DB_LINK)
    try:
        cur = conn.cursor()

        # Warm up. The first statement on a brand-new connection can be slow
        # for reasons that have nothing to do with transactions, and that
        # would contaminate every comparison below.
        conn.autocommit = True
        for _ in range(3):
            timed(cur, 'SELECT 1')

        # ---------------------------------------------------------- part 1
        heading('PART 1  the floor: one round trip, no transaction')
        floor = [timed(cur, 'SELECT 1') for _ in range(args.trials)]
        baseline = summarise('SELECT 1, autocommit ON', floor)

        # ---------------------------------------------------------- part 2
        heading('PART 2  does the first statement in a transaction pay twice?')
        print('   alternating the three cases so network drift cannot favour')
        print('   one of them')
        print()

        auto, first, second, with_block = [], [], [], []
        for _ in range(args.trials):
            conn.autocommit = True
            auto.append(timed(cur, 'SELECT 1'))

            # (d) THE CASE THAT MATTERS NOW. Turning autocommit on removed the
            # round trip at one call site and not at the others, and the one
            # that improved was the only one without a `with conn:` wrapper.
            # So: does the context manager start a transaction anyway, even
            # with autocommit on? If it does, the whole read-only change is
            # defeated everywhere the codebase uses that idiom -- which is
            # almost everywhere.
            with conn:
                with_block.append(timed(cur, 'SELECT 1'))

            conn.autocommit = False
            conn.rollback()                 # back to IDLE; not timed
            first.append(timed(cur, 'SELECT 1'))
            second.append(timed(cur, 'SELECT 1'))
            conn.rollback()

        conn.autocommit = True

        summarise('(a) autocommit ON', auto, baseline)
        d = summarise('(d) autocommit ON, inside `with conn:`',
                      with_block, baseline)
        b = summarise('(b) FIRST in a transaction', first, baseline)
        c = summarise('(c) SECOND in that transaction', second, baseline)

        print()
        extra = ms(b - c)
        ratio = b / c if c else 0
        print('   first costs %.0f ms more than second (%.2fx)' % (extra, ratio))
        print()

        # The (d) verdict is the actionable one.
        d_ratio = d / c if c else 0
        if d_ratio >= 1.5:
            print('   !! `with conn:` STARTS A TRANSACTION EVEN WITH AUTOCOMMIT')
            print('      ON (%.2fx). Setting autocommit is not enough: this'
                  % d_ratio)
            print('      codebase wraps nearly every query in that idiom, so')
            print('      the read-only flag is defeated wherever it is used.')
            print('      The with-block has to go too on those paths.')
        elif d_ratio < 1.25:
            print('   `with conn:` is harmless under autocommit (%.2fx), so'
                  % d_ratio)
            print('   the read-only flag works regardless of the idiom. If a')
            print('   call site did not improve, the cost is the QUERY -- see')
            print('   part 3.')
        else:
            print('   `with conn:` under autocommit is inconclusive at %.2fx.'
                  % d_ratio)
        print()

        confirmed = verdict(b, c, baseline)
        if confirmed is True:
            print('   CONFIRMED. Opening a transaction costs about one extra')
            print('   round trip. The BEGIN is not free.')
        elif confirmed is False:
            print('   REFUTED. The first statement in a transaction costs')
            print('   about the same as any other. The ~560 ms seen on the')
            print('   routes is NOT the transaction -- see part 3.')
        else:
            print('   INCONCLUSIVE at %.2fx. Re-run with more trials before'
                  % ratio)
            print('   drawing anything from this.')

        # ---------------------------------------------------------- part 3
        heading('PART 3  the competing explanation: are those queries just slow?')
        print('   timed with autocommit ON, so no transaction is involved.')
        print('   Anything far above the %.0f ms floor measured in part 1 is'
              % ms(baseline))
        print('   the QUERY being expensive, which would be a different fix')
        print('   entirely.')
        print()

        probes = [
            ('blacklist lookup (jwt_utils)',
             "SELECT 1 FROM dll_token_blacklist WHERE jti = %s",
             ('no-such-jti-probe',)),
            ('one access_relay row',
             "SELECT account_clearance, account_type, account_root "
             "FROM dll_access_relay WHERE account_uid = %s "
             "AND access_status = 'active'",
             ('no-such-account-probe',)),
            ('roles scan',
             "SELECT role_uid FROM dll_roles WHERE role_name = %s "
             "AND (is_deleted = FALSE OR is_deleted IS NULL)",
             ('no-such-role-probe',)),
        ]
        conn.autocommit = True
        for label, sql, params in probes:
            try:
                samples = [timed(cur, sql, params) for _ in range(args.trials)]
                summarise(label, samples, baseline)
            except Exception as error:                     # noqa: BLE001
                print('   %-38s could not run: %s'
                      % (label, str(error).strip().splitlines()[0]))

        print()
        print('   indexes on the tables those touch:')
        cur.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE tablename IN ('dll_token_blacklist', 'dll_access_relay', "
            "'dll_roles', 'dll_role_permissions', 'dll_permissions') "
            "ORDER BY tablename, indexname")
        rows = cur.fetchall()
        if not rows:
            print('      none at all -- every lookup above is a sequential scan')
        seen = set()
        for tablename, indexname, indexdef in rows:
            cols = indexdef.split('(', 1)[-1].rstrip(')')
            print('      %-24s %s' % (tablename, cols))
            seen.add(tablename)
        for table in ('dll_token_blacklist', 'dll_access_relay', 'dll_roles',
                      'dll_role_permissions', 'dll_permissions'):
            if table not in seen:
                print('      %-24s !! NO INDEX' % table)

        # ---------------------------------------------------------- verdict
        heading('WHAT TO DO WITH THIS')
        if confirmed:
            print('   Transactions are costing a round trip each. A read that')
            print('   does not write does not need one: setting autocommit on')
            print('   the pooled connection, or using it for the read-only')
            print('   paths, removes ~%.0f ms per connection used. At three'
                  % extra)
            print('   connections a request that is ~%.0f ms.' % (extra * 3))
            print()
            print('   Do NOT blanket-apply it: anything that writes more than')
            print('   one row still needs its transaction. Start with the')
            print('   read-only helpers -- the permission loader, the')
            print('   blacklist check, resolve_wallet_owner.')
        elif confirmed is False:
            print('   The transaction is not the cost. Look at part 3: if a')
            print('   query is far above the floor, it is the query or a')
            print('   missing index, and that is where the time is.')
        else:
            print('   Inconclusive. More trials, or a quieter moment on the')
            print('   network, before acting on any of it.')

        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
