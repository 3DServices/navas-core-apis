#!/usr/bin/env python3
"""
b11_probe2.py -- the B11 probe, done correctly this time.

WHAT WAS WRONG WITH THE FIRST ONE.  b11_workmem_audit.py --probe sorted the
whole of dll_io_events_executed_logs (11 GB).  A full sort of 11 GB cannot
finish in 30 seconds at ANY work_mem, so both the 10 MB run and the 10 GB run
hit the statement timeout and the comparison measured nothing.  The timeout
was not the finding -- the probe was simply the wrong shape.

The fix is to sort a BOUNDED number of rows.  Sort memory scales with rows x
row width, so measuring 100k / 500k / 2M rows gives kB-per-row, and that
extrapolates to whatever the real queries sort.  Each step is bounded, so it
finishes, and the Sort Method line reports exactly what was used.

Also answered here, both read-only:

  * TOTAL HOST RAM, if the role may read /proc/meminfo through
    pg_read_file().  That is the figure SQL "cannot" give -- it can, when the
    role has pg_read_server_files or is superuser.  Worth one attempt before
    asking anyone to ssh anywhere.

  * THE 55 OPEN CONNECTIONS.  Section 3 of the first audit reported 55 open
    with 1 active.  54 idle connections is its own problem and may matter
    more than work_mem: it is 54 backends each able to claim work_mem the
    moment they run a sort.

Every query here is a SELECT or an EXPLAIN under SET LOCAL, which lasts for
one transaction and touches no other session, no file and no restart.

Usage:
    python scripts/b11_probe2.py
    python scripts/b11_probe2.py --rows 100000,500000,2000000 --timeout-s 60
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402


def section(title):
    print('')
    print('=' * 72)
    print(title)
    print('=' * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', default='100000,500000,2000000',
                    help='row counts to sort, comma separated')
    ap.add_argument('--candidates', default='4MB,16MB,64MB',
                    help='work_mem values to test, comma separated')
    ap.add_argument('--timeout-s', type=int, default=60)
    args = ap.parse_args()

    row_counts = [int(r) for r in args.rows.split(',') if r.strip()]
    candidates = [c.strip() for c in args.candidates.split(',') if c.strip()]

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True
    cur = conn.cursor()

    # ------------------------------------------------------------ 1. host RAM
    section('1. TOTAL HOST RAM -- can SQL see it after all?')

    ram_kb = None
    try:
        cur.execute("SELECT pg_read_file('/proc/meminfo', 0, 2000)")
        meminfo = cur.fetchone()[0]
        for line in meminfo.split('\n'):
            if line.startswith('MemTotal:'):
                ram_kb = int(line.split()[1])
            if line.split(':')[0] in ('MemTotal', 'MemAvailable', 'SwapTotal',
                                      'Committed_AS', 'CommitLimit'):
                print('   %s' % ' '.join(line.split()))
    except Exception as error:                           # noqa: BLE001
        conn.rollback()
        print('   not permitted: %s' % str(error).strip()[:90])
        print('   -> the role lacks pg_read_server_files.  The RAM figure has')
        print('      to come from the host (ssh + free -h) or the droplet size.')

    if ram_kb:
        print('')
        print('   MemTotal = %.1f GB' % (ram_kb / 1048576.0))
        cur.execute("SELECT setting::bigint FROM pg_settings WHERE name='work_mem'")
        work_kb = cur.fetchone()[0]
        print('   work_mem = %.1f GB  -> ONE sort node can ask for %.0f%% of RAM'
              % (work_kb / 1048576.0, 100.0 * work_kb / ram_kb))
        cur.execute("SELECT setting::bigint*8 FROM pg_settings WHERE name='shared_buffers'")
        shared_kb = cur.fetchone()[0]
        print('   shared_buffers %.1f GB (%.0f%% of RAM)'
              % (shared_kb / 1048576.0, 100.0 * shared_kb / ram_kb))

    # -------------------------------------------------------- 2. idle backends
    section('2. THE OPEN CONNECTIONS -- who are they?')

    cur.execute("""
        SELECT coalesce(nullif(application_name, ''), '(none)') AS app,
               coalesce(usename, '(none)')                      AS role,
               coalesce(client_addr::text, 'local')             AS client,
               state,
               count(*)                                         AS n,
               max(now() - backend_start)                       AS oldest,
               max(now() - state_change)                        AS idle_longest
          FROM pg_stat_activity
         WHERE backend_type = 'client backend'
         GROUP BY 1, 2, 3, 4
         ORDER BY n DESC
         LIMIT 20
    """)

    print('   %-20s %-14s %-16s %-10s %5s %-16s %s'
          % ('application', 'role', 'client', 'state', 'n', 'oldest', 'idle for'))
    for app, role, client, state, count, oldest, idle in cur.fetchall():
        print('   %-20s %-14s %-16s %-10s %5s %-16s %s'
              % (str(app)[:20], str(role)[:14], str(client)[:16],
                 str(state)[:10], count, str(oldest)[:16], str(idle)[:16]))

    cur.execute("""
        SELECT count(*) FILTER (WHERE state = 'idle'),
               count(*) FILTER (WHERE state = 'idle in transaction'),
               count(*) FILTER (WHERE state = 'active'),
               count(*)
          FROM pg_stat_activity WHERE backend_type = 'client backend'
    """)
    idle, idle_tx, active, total = cur.fetchone()
    print('')
    print('   idle %s | idle in transaction %s | active %s | total %s'
          % (idle, idle_tx, active, total))
    if idle_tx:
        print('   !! "idle in transaction" holds locks and blocks vacuum.')
    print('   Each one of these %s backends can claim work_mem per sort node' % total)
    print('   the moment it runs a query.')

    # ------------------------------------------------------------- 3. the probe
    section('3. HOW MUCH SORT MEMORY DOES A SORT ACTUALLY NEED?')

    cur.execute("""
        SELECT c.relname, pg_size_pretty(pg_total_relation_size(c.oid)),
               c.reltuples::bigint
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r' AND n.nspname = 'public'
         ORDER BY pg_total_relation_size(c.oid) DESC
         LIMIT 1
    """)
    table, pretty, est_rows = cur.fetchone()
    print('   table %s (%s, ~%s rows estimated)' % (table, pretty, est_rows))

    cur.execute("""
        SELECT a.attname, t.typname, a.attlen
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_type t ON t.oid = a.atttypid
         WHERE c.relname = %s AND n.nspname = 'public'
           AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY a.attnum LIMIT 1
    """, (table,))
    column, typname, _attlen = cur.fetchone()
    print('   sorting one column: %s (%s)' % (column, typname))
    print('')
    print('   %-12s %-10s %-44s' % ('rows', 'work_mem', 'Sort Method'))
    print('   ' + '-' * 68)

    findings = []

    def sort_queries(rows):
        """Two shapes, in order of preference.

        The plain ORDER-BY-in-a-subquery form is simplest, but the planner is
        allowed to drop an ORDER BY whose result nothing depends on, which
        would leave no Sort node to measure.  The window-function form cannot
        be optimised away, so it is the fallback.  The script tries the first
        and only falls back when no Sort node appears -- it never reports a
        measurement it did not actually take.
        """
        inner = ('SELECT %s FROM public.%s LIMIT %d' % (column, table, rows))
        return [
            'SELECT count(*) FROM (SELECT %s FROM (%s) x ORDER BY %s) s'
            % (column, inner, column),
            'SELECT count(*) FROM (SELECT row_number() OVER (ORDER BY %s) AS rn '
            'FROM (%s) x) s' % (column, inner),
        ]

    for rows in row_counts:
        query = sort_queries(rows)[0]

        for candidate in candidates:
            probe = psycopg2.connect(DB_LINK)
            try:
                with probe:
                    with probe.cursor() as pcur:
                        pcur.execute("SET LOCAL statement_timeout = '%ds'"
                                     % args.timeout_s)
                        pcur.execute("SET LOCAL work_mem = %s", (candidate,))
                        try:
                            pcur.execute('EXPLAIN (ANALYZE, TIMING OFF, '
                                         'BUFFERS OFF) ' + query)
                            plan = [r[0].strip() for r in pcur.fetchall()]
                        except Exception as error:       # noqa: BLE001
                            print('   %-12s %-10s TIMED OUT (%ds)'
                                  % (rows, candidate, args.timeout_s))
                            continue

                method = next((l for l in plan if 'Sort Method' in l), None)

                if method is None:
                    # the planner dropped the ORDER BY -- retry with the
                    # window-function form, which it cannot drop
                    fallback = psycopg2.connect(DB_LINK)
                    try:
                        with fallback:
                            with fallback.cursor() as fcur:
                                fcur.execute("SET LOCAL statement_timeout = '%ds'"
                                             % args.timeout_s)
                                fcur.execute("SET LOCAL work_mem = %s", (candidate,))
                                try:
                                    fcur.execute('EXPLAIN (ANALYZE, TIMING OFF) '
                                                 + sort_queries(rows)[1])
                                    plan2 = [r[0].strip() for r in fcur.fetchall()]
                                    method = next((l for l in plan2
                                                   if 'Sort Method' in l),
                                                  '(no sort node in either form)')
                                except Exception as error:   # noqa: BLE001
                                    method = 'TIMED OUT on fallback (%ds)' % args.timeout_s
                    finally:
                        fallback.close()

                print('   %-12s %-10s %s' % (rows, candidate, method))
                findings.append((rows, candidate, method))
            finally:
                probe.close()

        print('   ' + '-' * 68)

    # --------------------------------------------------------------- 4. verdict
    section('4. WHAT THE MEASUREMENT SAYS')

    fitted = [f for f in findings if 'quicksort' in f[2] or 'top-N' in f[2]]
    spilled = [f for f in findings if 'external' in f[2]]

    if not findings:
        print('   nothing measured -- every probe timed out.  Raise')
        print('   --timeout-s or lower --rows and run it again.')
    else:
        print('   fit in memory : %d of %d runs' % (len(fitted), len(findings)))
        print('   spilled to disk: %d of %d runs' % (len(spilled), len(findings)))
        print('')
        if fitted:
            biggest = max(fitted, key=lambda f: f[0])
            print('   Largest sort that fit: %s rows at work_mem=%s'
                  % (biggest[0], biggest[1]))
            print('   %s' % biggest[2])
            print('')
            print('   A sort that fits at %s does not need 10 GB.  Read the' % biggest[1])
            print('   "Memory: NkB" figure above, take the largest realistic')
            print('   row count your queries sort, scale it, and add headroom.')
        if spilled:
            print('')
            print('   Spills seen -- those runs needed more than the candidate.')
            print('   The "Disk: NkB" figure is roughly what that sort wanted.')

    print('')
    print('   Note: these sort ONE column.  A query sorting a whole wide row')
    print('   needs proportionally more, so size up from the per-row cost')
    print('   rather than treating these numbers as the final answer.')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
