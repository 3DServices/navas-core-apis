#!/usr/bin/env python3
"""
b11_decide.py -- the last read-only step before the work_mem decision.

b11_probe2.py established the facts that matter:

    RAM 31.3 GB | work_mem 10 GB | shared_buffers 3 GB | max_connections 50000
    sort memory is LINEAR at ~74 bytes/row (100k -> 7.1MB, 500k -> 35.7MB)
    50 backends open, 49 idle, 47 of them opened at postmaster start

Two things it also showed that deserve a direct look, and pg_read_file() is
permitted for this role, so both can be read from here:

  1. Committed_AS (24.5 GB) ALREADY EXCEEDS CommitLimit (23.7 GB), with one
     query running.  Whether that is fatal depends on vm.overcommit_memory:
     with 2 (strict) new large allocations are refused outright; with 0
     (heuristic, the Linux default) they are allowed and the OOM killer
     settles it later.  That one integer decides how 10 GB fails.

  2. WHAT IS ACTUALLY WRITTEN AT postgresql.conf:144.  The comments around a
     hand-edited line are the closest thing to a record of intent that
     exists.  Reading lines 55-150 shows work_mem, maintenance_work_mem,
     shared_buffers and max_connections together, with whatever was written
     beside them.  This is the one check that can answer "was 10GB
     deliberate?" rather than inferring it.

It also prints the sizing table, computed from the measured 74 bytes/row and
the real 31.3 GB, so the recommendation is arithmetic rather than a default
someone read on a blog.

Strictly read-only.  Reads catalogue views and three files through
pg_read_file().  Changes nothing.

Usage:
    python scripts/b11_decide.py
"""

import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

BYTES_PER_ROW = 74.0        # measured: 7134kB/100k and 35726kB/500k agree


def section(title):
    print('')
    print('=' * 72)
    print(title)
    print('=' * 72)


def read_file(cur, path, offset=0, length=12000):
    try:
        cur.execute('SELECT pg_read_file(%s, %s, %s)', (path, offset, length))
        return cur.fetchone()[0]
    except Exception as error:                           # noqa: BLE001
        cur.connection.rollback()
        return None, str(error).strip()[:100]


def main():
    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True
    cur = conn.cursor()

    # ------------------------------------------------- 1. overcommit policy
    section('1. HOW WOULD A 10 GB ALLOCATION FAIL?')

    for path, label in (('/proc/sys/vm/overcommit_memory', 'overcommit_memory'),
                        ('/proc/sys/vm/overcommit_ratio', 'overcommit_ratio'),
                        ('/proc/sys/vm/swappiness', 'swappiness')):
        got = read_file(cur, path, 0, 32)
        if isinstance(got, tuple):
            print('   %-20s unreadable (%s)' % (label, got[1]))
        else:
            print('   %-20s %s' % (label, str(got).strip()))

    got = read_file(cur, '/proc/sys/vm/overcommit_memory', 0, 32)
    mode = str(got).strip() if not isinstance(got, tuple) else None

    print('')
    if mode == '2':
        print('   -> STRICT (2).  Committed_AS already exceeds CommitLimit, so')
        print('      a backend asking for 10 GB is refused at malloc and the')
        print('      query errors out.  That is "out of memory" in the log and')
        print('      a failed request to the API.')
    elif mode == '0':
        print('   -> HEURISTIC (0), the Linux default.  A 10 GB request is')
        print('      granted on paper and the kernel OOM-kills a backend when')
        print('      the pages are actually touched.  From the API side that')
        print('      is exactly "server closed the connection unexpectedly".')
    elif mode == '1':
        print('   -> ALWAYS OVERCOMMIT (1).  Every allocation succeeds; the')
        print('      OOM killer is the only limit.  Worst of the three for a')
        print('      database.')
    else:
        print('   -> could not read it; ask on the host:')
        print('      cat /proc/sys/vm/overcommit_memory')

    # -------------------------------------------- 2. what the conf file says
    section('2. WHAT IS ACTUALLY WRITTEN IN postgresql.conf')

    conf = read_file(cur, '/etc/postgresql/16/main/postgresql.conf', 0, 40000)

    if isinstance(conf, tuple):
        print('   unreadable (%s)' % conf[1])
        print('   -> read it on the host:')
        print('      sed -n "60,150p" /etc/postgresql/16/main/postgresql.conf')
    else:
        lines = conf.split('\n')
        wanted = (65, 133, 144, 146)
        print('   the four hand-edited lines, with their neighbours:')
        shown = set()
        for target in wanted:
            lo, hi = max(1, target - 2), min(len(lines), target + 2)
            print('')
            for number in range(lo, hi + 1):
                if number in shown:
                    continue
                shown.add(number)
                marker = '>>' if number == target else '  '
                print('   %s %4d | %s' % (marker, number, lines[number - 1]))

        # any comment mentioning a reason
        print('')
        print('   every line in the file that mentions work_mem:')
        for number, line in enumerate(lines, 1):
            if 'work_mem' in line:
                print('      %4d | %s' % (number, line.rstrip()))

    # ------------------------------------------------------- 3. sizing table
    section('3. SIZING, FROM THE MEASURED 74 BYTES/ROW AND 31.3 GB')

    cur.execute("""
        SELECT (SELECT setting::bigint FROM pg_settings WHERE name='work_mem'),
               (SELECT setting::bigint*8 FROM pg_settings WHERE name='shared_buffers'),
               (SELECT setting::int FROM pg_settings WHERE name='max_connections'),
               (SELECT count(*) FROM pg_stat_activity
                 WHERE backend_type='client backend')
    """)
    work_kb, shared_kb, max_conn, open_now = cur.fetchone()

    ram_kb = None
    meminfo = read_file(cur, '/proc/meminfo', 0, 2000)
    if not isinstance(meminfo, tuple):
        for line in str(meminfo).split('\n'):
            if line.startswith('MemTotal:'):
                ram_kb = int(line.split()[1])

    print('   how many rows each candidate holds in memory (one text column):')
    print('')
    print('   %-10s %14s %14s' % ('work_mem', 'rows it fits', 'measured check'))
    for mb, note in ((4, 'spilled at 100k - measured'),
                     (16, 'fit 100k at 7.1MB - measured'),
                     (64, 'fit 500k at 35.7MB - measured'),
                     (256, 'extrapolated'),
                     (1024, 'extrapolated'),
                     (10240, 'the current setting')):
        rows = int(mb * 1048576 / BYTES_PER_ROW)
        print('   %-10s %14s   %s' % ('%dMB' % mb, '{:,}'.format(rows), note))

    full_table_gb = 55278184 * BYTES_PER_ROW / 1073741824.0
    print('')
    print('   sorting the WHOLE 55,278,184-row table on one text column would')
    print('   need about %.1f GB in memory.  That is the only shape of query' % full_table_gb)
    print('   on this database that comes anywhere near 10 GB -- and a wide-row')
    print('   sort would need more.  So 10 GB is not a random number; it is')
    print('   plausibly sized for one batch/BI query.  The objection is not the')
    print('   size, it is that it is GLOBAL.')

    print('')
    print('   worst-case claim, at the %s backends open right now:' % open_now)
    print('')
    print('   %-10s %12s %12s %12s' % ('work_mem', '1 node each', '2 nodes each',
                                       'vs 31.3 GB'))
    for mb in (16, 64, 256, 1024, 10240):
        one = mb * open_now / 1024.0
        two = one * 2
        verdict = 'fits' if (two + shared_kb / 1048576.0) < 25 else 'OVER'
        print('   %-10s %10.1f GB %10.1f GB %12s'
              % ('%dMB' % mb, one, two, verdict))

    print('')
    print('   plus shared_buffers %.1f GB, reserved separately.' % (shared_kb / 1048576.0))
    if ram_kb:
        print('   RAM %.1f GB.  Hash nodes get work_mem x hash_mem_multiplier'
              % (ram_kb / 1048576.0))
        print('   (2), so halve the headroom again for a hash-heavy plan.')
    print('')
    print('   max_connections is %s, so nothing caps that multiplication.' % max_conn)
    print('   The 50 open today are the accident, not the limit.')

    # ---------------------------------------------------------- 4. the pool
    section('4. THE 47 IDLE BACKENDS -- POOL, NOT LEAK')

    cur.execute("""
        SELECT coalesce(nullif(application_name,''),'(none)') AS app,
               count(*),
               min(backend_start), max(backend_start),
               max(backend_start) - min(backend_start) AS spread
          FROM pg_stat_activity
         WHERE backend_type = 'client backend'
         GROUP BY 1 ORDER BY 2 DESC
    """)
    print('   %-20s %5s %-28s %s' % ('application', 'n', 'first opened', 'spread'))
    for app, count, first, _last, spread in cur.fetchall():
        print('   %-20s %5s %-28s %s' % (str(app)[:20], count, str(first)[:26], spread))

    cur.execute("SELECT pg_postmaster_start_time()")
    print('')
    print('   postmaster started %s' % cur.fetchone()[0])
    print('')
    print('   If the oldest backends cluster at postmaster start with a small')
    print('   spread, that is a connection POOL pre-warming, which is normal')
    print('   and healthy -- not the leak I called it earlier.  A leak would')
    print('   show connections opening steadily over time, spread out.')
    print('')
    print('   It still matters here: a legitimate pool of 47 is 47 backends')
    print('   that can each claim work_mem per sort node. 3d-spartan-bi being')
    print('   a BI tool is also the most likely reason someone wanted 10 GB.')
    print('   The fix for that is a per-session SET in the BI job, or its own')
    print('   role with ALTER ROLE ... SET work_mem -- not a global default.')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
