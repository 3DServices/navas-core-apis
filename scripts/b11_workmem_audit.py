#!/usr/bin/env python3
"""
b11_workmem_audit.py -- is work_mem = 10GB real, and what should it be?

The question "was 10GB deliberate?" cannot be asked of the server.  What CAN
be established, without changing anything on the host:

  1. WHERE the value comes from -- postgresql.conf, ALTER SYSTEM, a per-role
     or per-database override.  That decides which file you would edit, and a
     per-role override would mean the global value is not what the API sees.

  2. WHAT IT COSTS AT WORST.  work_mem is granted PER SORT OR HASH NODE, not
     per connection and not per server.  One query with four sort nodes can
     claim 4 x work_mem.  Multiply by concurrent queries and compare to RAM.

  3. HOW MUCH SORT MEMORY THE REAL QUERIES ACTUALLY NEED.  This is the only
     thing that justifies a number, and it is measured, not guessed -- see
     --probe below.

  4. WHETHER THE SERVER HAS BEEN DYING.  Uptime plus the connection stats.

A TRAP THIS SCRIPT DOES NOT FALL INTO: pg_stat_database.temp_files is the
usual evidence for "work_mem is too small" -- it counts queries that spilled
to disk.  At work_mem = 10GB almost nothing CAN spill, so temp_files will be
near zero and that tells you nothing about whether 10MB would suffice.  The
figure is printed, with that caveat, and is not used to conclude anything.

PHASE 1 (default) is strictly read-only: SHOW and SELECT against catalogue
views.  It opens one connection and closes it.

PHASE 2 (--probe) measures how much sort memory the heaviest table really
needs.  It uses SET LOCAL work_mem, which applies to that one transaction and
nothing else -- no other session, no restart, no configuration file touched --
and it runs under SET LOCAL statement_timeout so it cannot sit on the server.
It is still real work on a production box, so it is off by default.

Usage:
    python scripts/b11_workmem_audit.py
    python scripts/b11_workmem_audit.py --probe
    python scripts/b11_workmem_audit.py --probe --probe-mb 10 --timeout-s 30
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

KB = 1024
MB = KB * 1024
GB = MB * 1024


def human(kilobytes):
    """Postgres reports memory settings in kB units."""
    value = kilobytes * KB
    for unit, size in (('GB', GB), ('MB', MB), ('kB', KB)):
        if value >= size:
            return '%.3g %s' % (value / float(size), unit)
    return '%d B' % value


def show(cur, name):
    try:
        cur.execute('SHOW %s' % name)
        return cur.fetchone()[0]
    except Exception as error:                           # noqa: BLE001
        cur.connection.rollback()
        return '? (%s)' % str(error)[:40]


def section(title):
    print('')
    print('=' * 72)
    print(title)
    print('=' * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', action='store_true',
                    help='measure real sort-memory demand (runs queries)')
    ap.add_argument('--probe-mb', type=int, default=10,
                    help='the candidate work_mem to test, in MB (default 10)')
    ap.add_argument('--timeout-s', type=int, default=30,
                    help='statement_timeout for probe queries (default 30)')
    args = ap.parse_args()

    try:
        conn = psycopg2.connect(DB_LINK)
    except Exception as error:                           # noqa: BLE001
        print('could not connect: %s' % str(error)[:120])
        return 1

    conn.autocommit = True
    cur = conn.cursor()

    # ---------------------------------------------------------------- 1. source
    section('1. WHERE DOES work_mem COME FROM?')

    cur.execute("""
        SELECT name, setting, unit, source, sourcefile, sourceline,
               boot_val, reset_val, pending_restart
          FROM pg_settings
         WHERE name IN ('work_mem', 'maintenance_work_mem', 'shared_buffers',
                        'effective_cache_size', 'max_connections',
                        'hash_mem_multiplier', 'temp_buffers')
         ORDER BY name
    """)

    rows = cur.fetchall()
    settings = {}

    for (name, setting, unit, source, sourcefile, sourceline,
         boot_val, reset_val, pending) in rows:
        settings[name] = (setting, unit)
        print('')
        print('   %s = %s %s' % (name, setting, unit or ''))
        print('      set by        : %s' % source)
        print('      file          : %s%s' % (
            sourcefile or '(not visible -- needs superuser or '
                          'pg_read_all_settings)',
            ':%s' % sourceline if sourceline else ''))
        print('      postgres default: %s %s' % (boot_val, unit or ''))
        if setting != reset_val:
            print('      !! session value differs from reset_val %s' % reset_val)
        if pending:
            print('      !! pending_restart -- a changed value is not live yet')

    print('')
    print('   Reading: source "configuration file" means postgresql.conf and')
    print('   you edit that file.  "database"/"user" means a per-database or')
    print('   per-role override is in force and the global value is NOT what')
    print('   this connection gets -- see section 2.')

    # ------------------------------------------------------------ 2. overrides
    section('2. PER-ROLE / PER-DATABASE OVERRIDES')

    cur.execute("""
        SELECT coalesce(d.datname, '(all databases)') AS db,
               coalesce(r.rolname, '(all roles)')     AS role,
               s.setconfig
          FROM pg_db_role_setting s
          LEFT JOIN pg_database d ON d.oid = s.setdatabase
          LEFT JOIN pg_roles    r ON r.oid = s.setrole
         ORDER BY 1, 2
    """)

    overrides = cur.fetchall()

    if not overrides:
        print('   none -- nothing overrides the global settings.')
    else:
        for db, role, config in overrides:
            print('   %-24s %-20s %s' % (db, role, config))
        print('')
        print('   Any work_mem line above beats postgresql.conf for that')
        print('   database/role pair.  Check whether the API role is listed.')

    # ------------------------------------------------------- 3. the arithmetic
    section('3. WHAT IT COSTS AT WORST')

    work_kb = int(settings.get('work_mem', ('0', 'kB'))[0])
    shared_kb = int(settings.get('shared_buffers', ('0', '8kB'))[0]) * 8
    maint_kb = int(settings.get('maintenance_work_mem', ('0', 'kB'))[0])
    max_conn = int(settings.get('max_connections', ('0', ''))[0])

    try:
        hash_mult = float(settings.get('hash_mem_multiplier', ('1', ''))[0])
    except (TypeError, ValueError):
        hash_mult = 1.0

    print('   work_mem              %s   (per SORT OR HASH NODE)' % human(work_kb))
    print('   hash_mem_multiplier   %s   (hash nodes get work_mem x this)'
          % hash_mult)
    print('   shared_buffers        %s' % human(shared_kb))
    print('   maintenance_work_mem  %s' % human(maint_kb))
    print('   max_connections       %s' % max_conn)
    print('')

    cur.execute("SELECT count(*), count(*) FILTER (WHERE state = 'active') "
                "FROM pg_stat_activity")
    total_now, active_now = cur.fetchone()
    print('   connections right now %s (%s running a query)' % (total_now, active_now))
    print('')

    for label, concurrent, nodes in (('1 query, 1 sort node', 1, 1),
                                     ('1 query, 4 sort nodes', 1, 4),
                                     ('10 concurrent, 2 nodes each', 10, 2),
                                     ('%d active now, 2 nodes each'
                                      % max(active_now, 1), max(active_now, 1), 2)):
        worst = work_kb * concurrent * nodes
        print('   %-32s %s' % (label, human(worst)))

    print('')
    print('   Add shared_buffers (%s), which is reserved separately.' % human(shared_kb))
    print('')
    print('   RAM IS NOT READABLE FROM SQL.  To finish this arithmetic you')
    print('   need the host total: ssh to 165.232.128.208 and run  free -h')
    print('   (or check the droplet size in the DigitalOcean panel).  If the')
    print('   box has 12GB, then one query with two sort nodes can ask for')
    print('   more memory than the machine has, and the kernel kills the')
    print('   backend -- which is what "server closed the connection')
    print('   unexpectedly" looks like from the API.')

    # ------------------------------------------------------------- 4. is it dying
    section('4. HAS THE SERVER BEEN DYING?')

    cur.execute("SELECT pg_postmaster_start_time(), "
                "now() - pg_postmaster_start_time()")
    started, uptime = cur.fetchone()
    print('   started %s' % started)
    print('   uptime  %s' % uptime)

    if uptime.total_seconds() < 86400:
        print('')
        print('   -> under a day.  Worth asking why it restarted.  An OOM kill')
        print('      of the postmaster shows up here as a short uptime.')

    section('5. SPILL STATS -- AND WHY THEY PROVE LITTLE HERE')

    cur.execute("""
        SELECT datname, temp_files, pg_size_pretty(temp_bytes),
               xact_commit, xact_rollback, deadlocks
          FROM pg_stat_database
         WHERE datname IS NOT NULL AND temp_files > 0
         ORDER BY temp_bytes DESC
         LIMIT 10
    """)
    spills = cur.fetchall()

    if not spills:
        print('   No database has ever spilled a sort to disk.')
        print('')
        print('   This is EXPECTED at work_mem = %s and is NOT evidence that' % human(work_kb))
        print('   a smaller value would be safe.  Nothing can spill when every')
        print('   sort is handed 10GB.  The measurement that does answer it is')
        print('   --probe below.')
    else:
        for name, files, size, commits, rollbacks, deadlocks in spills:
            print('   %-22s %8s files  %10s  commits=%s rollbacks=%s deadlocks=%s'
                  % (name, files, size, commits, rollbacks, deadlocks))
        print('')
        print('   Spills DID happen, so some query already needed more than')
        print('   work_mem at the time it ran.')

    section('6. IS pg_stat_statements AVAILABLE?')

    cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")
    has_pgss = cur.fetchone()[0] > 0

    if has_pgss:
        print('   yes -- the heaviest real queries can be listed:')
        try:
            cur.execute("""
                SELECT calls, round(mean_exec_time) AS mean_ms,
                       round(total_exec_time) AS total_ms, left(query, 90)
                  FROM pg_stat_statements
                 ORDER BY total_exec_time DESC
                 LIMIT 8
            """)
            for calls, mean_ms, total_ms, text in cur.fetchall():
                print('   %8s calls  mean %6s ms  total %10s ms  %s'
                      % (calls, mean_ms, total_ms, ' '.join(str(text).split())))
        except Exception as error:                       # noqa: BLE001
            print('   (could not read it: %s)' % str(error)[:70])
    else:
        print('   no.  Without it there is no record of which queries are')
        print('   actually expensive, so any work_mem number is a guess about')
        print('   workload.  Enabling it needs shared_preload_libraries and a')
        print('   restart -- that is a separate decision from this one.')

    # --------------------------------------------------------------- 7. probe
    section('7. HOW MUCH SORT MEMORY IS REALLY NEEDED?')

    if not args.probe:
        print('   Skipped.  Re-run with --probe to measure it.')
        print('')
        print('   What --probe does: finds the largest table, then sorts it')
        print('   twice in ONE transaction -- once at the candidate value')
        print('   (%d MB) and once at the current value -- using SET LOCAL,' % args.probe_mb)
        print('   which lasts only for that transaction and affects no other')
        print('   session.  EXPLAIN ANALYZE then reports the real Sort Method:')
        print('   "quicksort Memory: NkB" means it fit, "external merge')
        print('   Disk: NkB" means it needed more than the candidate.  That')
        print('   number is the answer -- round it up and double it.')
    else:
        cur.execute("""
            SELECT c.relname,
                   pg_total_relation_size(c.oid) AS bytes,
                   pg_size_pretty(pg_total_relation_size(c.oid))
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r' AND n.nspname = 'public'
             ORDER BY bytes DESC
             LIMIT 1
        """)
        biggest = cur.fetchone()

        if not biggest:
            print('   no tables found in schema public -- nothing to probe.')
        else:
            table, _bytes, pretty = biggest
            print('   largest table: %s (%s)' % (table, pretty))

            cur.execute("""
                SELECT a.attname
                  FROM pg_attribute a
                  JOIN pg_class c ON c.oid = a.attrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE c.relname = %s AND n.nspname = 'public'
                   AND a.attnum > 0 AND NOT a.attisdropped
                 ORDER BY a.attnum
                 LIMIT 1
            """, (table,))
            column = cur.fetchone()[0]
            print('   sorting on  : %s' % column)
            print('')

            query = ('SELECT count(*) FROM (SELECT %s FROM public.%s '
                     'ORDER BY %s) s' % (column, table, column))

            for label, value in (('candidate %d MB' % args.probe_mb,
                                  '%dMB' % args.probe_mb),
                                 ('current %s' % human(work_kb), None)):
                probe = psycopg2.connect(DB_LINK)
                try:
                    with probe:
                        with probe.cursor() as pcur:
                            pcur.execute("SET LOCAL statement_timeout = '%ds'"
                                         % args.timeout_s)
                            if value:
                                pcur.execute("SET LOCAL work_mem = '%s'" % value)
                            pcur.execute('SHOW work_mem')
                            effective = pcur.fetchone()[0]
                            try:
                                pcur.execute('EXPLAIN (ANALYZE, TIMING OFF) ' + query)
                                plan = '\n'.join(r[0] for r in pcur.fetchall())
                            except Exception as error:   # noqa: BLE001
                                print('   %-22s work_mem=%-8s TIMED OUT / failed: %s'
                                      % (label, effective, str(error)[:50]))
                                continue

                    print('   %-22s work_mem=%s' % (label, effective))
                    for line in plan.split('\n'):
                        stripped = line.strip()
                        if ('Sort Method' in stripped or 'Sort Key' in stripped
                                or 'Disk' in stripped or 'Memory' in stripped):
                            print('        %s' % stripped)
                    print('')
                finally:
                    probe.close()

            print('   Reading: if the candidate run says "quicksort Memory:')
            print('   NkB" it fit comfortably.  If it says "external merge')
            print('   Disk: NkB", the sort needed roughly N kB -- set work_mem')
            print('   above that with headroom, not 10GB.')

    section('WHAT YOU ARE DECIDING')
    print('   a) the value: %s stays, or drops to something the measurement' % human(work_kb))
    print('      in section 7 supports (10MB-64MB is ordinary at')
    print('      shared_buffers %s)' % human(shared_kb))
    print('   b) max_connections %s, which is not a plausible deliberate' % max_conn)
    print('      figure -- Postgres default is 100, and each slot reserves')
    print('      memory whether used or not.  %s are open right now.' % total_now)
    print('')
    print('   Both are edits to postgresql.conf on the host, and work_mem')
    print('   takes effect with a reload (no restart); max_connections needs')
    print('   a restart.  Neither is something this script does.')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
