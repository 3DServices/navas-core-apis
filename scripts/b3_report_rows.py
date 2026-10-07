#!/usr/bin/env python3
"""
b3_report_rows.py — what is actually in dll_reports_downloadable_files?

b3_route_check.py turned up two things that cannot be explained from the code:

  * trips/excel's status read returns HTTP 400 'Unable to complete request',
    which is report_status's `else` branch -- reached only when rowcount is
    NEITHER 1 NOR 0. On a freshly generated UUID that should be impossible.

  * ComputeTrips_PDF contains no INSERT at all, only UPDATEs. Yet a status read
    for a fresh UUID came back with one row, 'completed', and a real file path.
    An UPDATE ... WHERE request_uid = <new uuid> should touch nothing.

Both point at request_uid not behaving as a unique key, but that is a guess.
This measures it instead:

  1. the table's columns and types
  2. its constraints and indexes -- is request_uid unique at all?
  3. the 15 most recent rows
  4. any request_uid held by more than one row
  5. a direct count for the UUIDs a given run used (pass them as arguments)

Strictly read-only: SELECTs against catalogue views and the table. Writes
nothing.

Usage:
    python scripts/b3_report_rows.py
    python scripts/b3_report_rows.py 8e8323eb-35da-4734-8e5b-958c5ec5e168
"""

import sys

sys.path.insert(0, '.')

TABLE = 'dll_reports_downloadable_files'


def section(title):
    print('')
    print('=' * 74)
    print(title)
    print('=' * 74)


def main():
    wanted = [a.strip() for a in sys.argv[1:] if a.strip()]

    import psycopg2
    from config import DB_LINK

    try:
        conn = psycopg2.connect(DB_LINK)
    except Exception as error:                            # noqa: BLE001
        print('could not connect: %s' % str(error)[:120])
        return 1

    conn.autocommit = True
    cur = conn.cursor()

    section('1. COLUMNS')
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
          FROM information_schema.columns
         WHERE table_name = %s
         ORDER BY ordinal_position
    """, (TABLE,))
    rows = cur.fetchall()
    if not rows:
        print('   no such table: %s' % TABLE)
        return 1
    for name, kind, nullable, default in rows:
        print('   %-24s %-28s %s%s'
              % (name, kind, 'NULL' if nullable == 'YES' else 'NOT NULL',
                 '  default %s' % str(default)[:30] if default else ''))

    section('2. CONSTRAINTS AND INDEXES -- is request_uid unique?')
    cur.execute("""
        SELECT c.conname, pg_get_constraintdef(c.oid)
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = %s
    """, (TABLE,))
    cons = cur.fetchall()
    if cons:
        for name, definition in cons:
            print('   %-34s %s' % (name, definition[:90]))
    else:
        print('   NO constraints at all -- no primary key, no unique key.')

    cur.execute('SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s',
                (TABLE,))
    idx = cur.fetchall()
    if idx:
        for name, definition in idx:
            print('   %-34s %s' % (name, definition[:90]))
    else:
        print('   no indexes')

    unique_on_uid = any('UNIQUE' in d.upper() and 'request_uid' in d
                        for _n, d in cons) or \
                    any('UNIQUE' in d.upper() and 'request_uid' in d
                        for _n, d in idx)
    print('')
    print('   -> request_uid unique: %s' % ('YES' if unique_on_uid else 'NO'))
    if not unique_on_uid:
        print('      Without it, one request_uid can hold many rows, which is')
        print('      exactly what makes report_status fall into its `else`')
        print('      branch and answer "Unable to complete request".')

    section('3. THE 15 MOST RECENTLY INSERTED ROWS')
    # ORDER BY id, not request_datestamp.
    #
    # request_datestamp is TEXT in DD-MM-YYYY format, so a text sort orders by
    # DAY OF MONTH first: '30-07-2025' sorts above '29-08-2025'. The first
    # version of this ordered by that column and the "most recent rows" it
    # printed were nothing of the kind. Same trap as local_system_datestamp,
    # which B2 had to solve the same way. id is a serial, so it is the true
    # insertion order.
    try:
        cur.execute("""
            SELECT request_uid, request_status, report_caller,
                   left(coalesce(file_path, '(null)'), 46), request_datestamp
              FROM %s ORDER BY id DESC LIMIT 15
        """ % TABLE)
        for uid, status, caller, path, when in cur.fetchall():
            print('   %-38s %-12s %-16s %s' % (str(uid)[:38], str(status)[:12],
                                               str(caller)[:16], str(when)[:19]))
            print('       %s' % path)
    except Exception as error:                            # noqa: BLE001
        print('   could not list rows: %s' % str(error)[:100])

    section('4. ANY request_uid HELD BY MORE THAN ONE ROW')
    cur.execute("""
        SELECT request_uid, count(*)
          FROM %s GROUP BY request_uid HAVING count(*) > 1
         ORDER BY count(*) DESC LIMIT 20
    """ % TABLE)
    dupes = cur.fetchall()
    if dupes:
        for uid, n in dupes:
            print('   %-40s %d rows' % (str(uid)[:40], n))
        print('')
        print('   That is the explanation for report_status\'s `else` branch.')
    else:
        print('   none -- every request_uid appears at most once, so the')
        print('   duplicate theory is WRONG and the 400 has another cause.')

    cur.execute('SELECT count(*) FROM %s' % TABLE)
    print('')
    print('   total rows in the table: %s' % cur.fetchone()[0])

    cur.execute('SELECT count(*) FROM %s WHERE request_uid IS NULL' % TABLE)
    nulls = cur.fetchone()[0]
    print('   rows with request_uid IS NULL: %s' % nulls)
    if nulls > 1:
        print('      NOTE: report_status matches with `request_uid = %s`, which')
        print('      never matches NULL, so these are invisible to it -- but')
        print('      they are also rows no status lookup can ever resolve.')

    if wanted:
        section('5. THE UUIDs YOU PASSED')
        for uid in wanted:
            cur.execute('SELECT count(*) FROM %s WHERE request_uid = %%s'
                        % TABLE, (uid,))
            count = cur.fetchone()[0]
            print('   %-40s %d row(s)' % (uid, count))
            if count:
                cur.execute("""
                    SELECT request_status, report_caller,
                           coalesce(file_path, '(null)')
                      FROM %s WHERE request_uid = %%s
                """ % TABLE, (uid,))
                for status, caller, path in cur.fetchall():
                    print('        %-12s %-18s %s' % (status, caller, path[:60]))
    else:
        section('5. NO UUIDs PASSED')
        print('   Re-run with the request UUIDs b3_route_check printed, e.g.')
        print('     python scripts/b3_report_rows.py <uuid> <uuid>')
        print('   to see exactly what each request left behind.')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
