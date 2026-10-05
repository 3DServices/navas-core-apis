#!/usr/bin/env python3
"""
audit_io_names.py — the last unknowns before B5 is written.

Opening the IO-events gate runs code that has NEVER executed, because the
Postgres lookup feeding it has always returned zero rows. Two lines in there
are landmines, both visible by reading:

    IO_NameValue_adapter = cursor.fetchone()
    IO_NameValue_Extracted = IO_NameValue_adapter[0]

fetchone() returns None when the IO id is absent from the vendor's name table,
and None[0] is a TypeError. And IO_ID_Found is assigned only in the 'ruptela'
and 'teltonika' branches, so a device of any other vendor raises NameError —
even though the else branch above it does set the table names. That is the
same shape as the .get_json() bug: wrong code sitting safely behind a gate
that was always false.

So before writing anything this establishes:

  1. VENDOR of the test unit, and therefore which name table is used
  2. RESOLUTION: of the event_uid_executed values Cassandra actually returns,
     how many exist in that table. Every miss is a TypeError today.
  3. FAN-OUT: how many IO events per fix, because each one costs a name
     lookup
  4. data_idx: it is text in Cassandra and integer in Postgres, and the SQL
     ordered by it DESC. Are the values numeric, and does ordering them as
     text differ from ordering them as numbers?
  5. DRIVER: whether cassandra.concurrent is available, since 0.3s per round
     trip times N fixes is the remaining cost and concurrency is the fix

Read-only.

Usage:
    python scripts/audit_io_names.py --imei 862846042622426 --day 25-09-2026
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402
from endpoints import location_store                    # noqa: E402

VENDOR_TABLES = {
    'ruptela':   ('dll_io_events_config', 'io_display_name',
                  'io_event_vendor_uid'),
    'teltonika': ('dll_teltonika_avl_list', 'avl_io_name', 'avl_io_id'),
}
DEFAULT_TABLE = ('dll_io_events_config', 'io_display_name',
                 'io_event_vendor_uid')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    print('=' * 72)
    print('5. DRIVER: CAN THE PER-FIX LOOKUPS BE ISSUED CONCURRENTLY?')
    print('=' * 72)
    try:
        import cassandra
        print(f'   cassandra-driver {cassandra.__version__}')
        from cassandra import concurrent as cc
        for name in ('execute_concurrent', 'execute_concurrent_with_args'):
            print(f'   cassandra.concurrent.{name}: '
                  + ('available' if hasattr(cc, name) else 'MISSING'))
        print('   -> concurrency is available; N round trips become ~1')
    except Exception as error:                          # noqa: BLE001
        print(f'   !! {error}')
        print('   -> without it, fall back to execute_async + result() on a')
        print('      batch of futures, which the driver supports natively.')

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('\n!! no Cassandra session')
            return 1
        rows, _t = location_store.fixes(session, args.imei, args.day,
                                        args.day, limit=args.count)
        uids = [str(r['io_uid']) for r in rows if r['io_uid']]

        conn = psycopg2.connect(DB_LINK)
        try:
            with conn.cursor() as cur:
                print('\n' + '=' * 72)
                print('1. VENDOR, AND THE NAME TABLE IT SELECTS')
                print('=' * 72)
                cur.execute("SELECT device_hardware, device_vendor "
                            "FROM dll_device_registrar WHERE device_imei=%s",
                            (str(args.imei),))
                got = cur.fetchone()
                vendor = str(got[1]).strip().lower() if got else None
                print(f'   dll_device_registrar: {got}')
                print(f'   vendor as the route sees it: {vendor!r}')
                table, value_col, cond_col = VENDOR_TABLES.get(
                    vendor, DEFAULT_TABLE)
                print(f'   name table : {table}')
                print(f'   columns    : {value_col} keyed on {cond_col}')
                if vendor not in VENDOR_TABLES:
                    print('\n   !! vendor is NEITHER ruptela NOR teltonika.')
                    print('      The loop never assigns IO_ID_Found for this')
                    print('      case -> NameError the moment the gate opens.')
                    print('      This unit alone proves the bug is reachable.')

                print('\n' + '=' * 72)
                print('3. FAN-OUT, AND 4. data_idx ORDERING')
                print('=' * 72)
                per_fix, all_ids, idx_samples = [], [], []
                for uid in uids:
                    try:
                        events = list(session.execute(
                            "SELECT event_uid_executed, event_value_executed, "
                            "data_idx FROM dll_io_events_executed_logs "
                            "WHERE io_parent_io_event_uid=%s;", (uid,)))
                    except Exception as error:          # noqa: BLE001
                        print(f'   {uid[:10]}…: ERROR {str(error)[:40]}')
                        continue
                    per_fix.append(len(events))
                    for e in events:
                        all_ids.append(str(e.event_uid_executed))
                        idx_samples.append(e.data_idx)
                if per_fix:
                    print(f'   IO events per fix: min {min(per_fix)}, '
                          f'max {max(per_fix)}, total {sum(per_fix)}')
                    print(f'   -> name lookups a {len(uids)}-fix page needs: '
                          f'{sum(per_fix)} (or {len(set(all_ids))} distinct)')
                sample = [s for s in idx_samples if s is not None][:8]
                print(f'\n   data_idx samples: {sample}')
                numeric = all(str(s).strip().lstrip('-').isdigit()
                              for s in sample) if sample else False
                print(f'   all numeric? {numeric}')
                if numeric and len(sample) > 1:
                    as_text = sorted(sample, reverse=True)
                    as_num = sorted(sample, key=lambda s: int(s), reverse=True)
                    print(f'   text order  : {as_text}')
                    print(f'   number order: {as_num}')
                    print(f'   SAME? {as_text == as_num}'
                          + ('' if as_text == as_num
                             else "  <- must cast to int, or the order lies"))

                print('\n' + '=' * 72)
                print('2. DO THE IO IDS RESOLVE? (every miss is a TypeError)')
                print('=' * 72)
                if not all_ids:
                    print('   no IO events to resolve.')
                else:
                    wanted = sorted(set(all_ids))
                    # exactly as the route builds it, per vendor
                    probe = ([w + '.0' for w in wanted] if vendor == 'ruptela'
                             else wanted)
                    cur.execute(
                        f"SELECT {cond_col}, {value_col} FROM {table} "
                        f"WHERE {cond_col} = ANY(%s)", (probe,))
                    found = {str(k): v for k, v in cur.fetchall()}
                    hits = sum(1 for p in probe if p in found)
                    print(f'   distinct IO ids in the data : {len(wanted)}')
                    print(f'   resolved in {table:<22}: {hits}')
                    print(f'   UNRESOLVED                  : '
                          f'{len(probe) - hits}')
                    if hits < len(probe):
                        missing = [p for p in probe if p not in found][:6]
                        print(f'   e.g. {missing}')
                        print('\n   -> each of these hits None[0] today. The')
                        print('      lookup must tolerate a miss instead of')
                        print('      raising, or opening the gate takes the')
                        print('      route down.')
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    print(f'\n   rows in {table}: {cur.fetchone()[0]}')
        finally:
            conn.close()

    print('\n' + '=' * 72)
    print('WHAT B5 MUST HANDLE')
    print('=' * 72)
    print('   a. read IO events from Cassandra (partition-key point lookup)')
    print('   b. order by data_idx as a NUMBER, not as text')
    print('   c. tolerate an unresolved IO id rather than raising')
    print('   d. assign IO_ID_Found for every vendor, not two of them')
    print('   e. cache the four per-device config lookups per request')
    print('   f. issue the per-fix lookups concurrently, not 0.3s at a time')
    return 0


if __name__ == '__main__':
    sys.exit(main())
