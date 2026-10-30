#!/usr/bin/env python3
"""Extend scripts/waswa_data_probe.py with the two questions the first run raised.

The first run found something stranger than dormant units: two of the five are
sending heartbeats *this second*, and the newest position row for the whole
account is dated 2025-08-01. A live device with fourteen months of missing
positions is not a dormant device.

Nothing in this repository writes to dll_location_registry — the device
listener does, outside it — so this cannot be settled by reading code. Two
queries settle it instead:

  1. Is the newest row in dll_location_registry recent for ANYONE? If the whole
     table stops in August 2025, the ingestion changed and no amount of work on
     Waswa will produce a trip. If other devices are current, these two units
     are genuinely silent on positions while their modems still check in.

  2. Does dll_trips_auditor have trips for them? That is the table the console's
     own Trips report reads, with a real trip_date rather than DD-MM-YYYY text.
     If it is populated, Waswa should be reading it too — not recomputing trips
     from raw fixes with its own idea of what a trip is. Two answers to "how
     many trips yesterday" that disagree is worse than one that is missing.

Read-only. Idempotent.
"""
import ast
import io
import sys

PATH = 'scripts/waswa_data_probe.py'

NEW_FUNCS = '''
def probe_table_recency(cur):
    """Is the position pipeline alive at all, for anybody?

    Ordered by data_idx rather than by date: data_idx is the insertion order,
    so the newest row is one index lookup. MAX over a text date would mean
    casting every row in the table.
    """
    print('\\n== Is the position pipeline still running? ' + '=' * 35)
    try:
        cur.execute("SELECT local_system_datestamp, local_system_timestamp, "
                    "       data_device_imei "
                    "FROM dll_location_registry ORDER BY data_idx DESC LIMIT 1")
        row = cur.fetchone()
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        print(f'   !! {str(exc).splitlines()[0][:80]}')
        return
    if not row:
        print('   dll_location_registry is EMPTY for every device.')
        return
    date_text, time_text, imei = row
    print(f'   newest row in the whole table : {date_text} {time_text}')
    print(f'   written for                   : {imei}')
    print()
    print('   If that date is recent, the pipeline is fine and the units you')
    print('   probed are simply not sending positions — Waswa is right to say so.')
    print('   If it is old, position ingestion stopped platform-wide, and that')
    print('   is a device-listener problem, not an assistant problem.')


def probe_trips(cur, imeis):
    """dll_trips_auditor — the table the console's Trips report actually reads."""
    print('\\n== dll_trips_auditor (what the Trips report uses) ' + '=' * 28)
    try:
        cur.execute("SELECT COUNT(*) FROM dll_trips_auditor")
        total = cur.fetchone()[0]
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        print(f'   !! cannot read dll_trips_auditor: {str(exc).splitlines()[0][:70]}')
        return
    print(f'   rows in the table, all devices : {total}')

    print(f'\\n   {"imei":<17} {"trips":>7} {"ended":>7}  {"earliest":<12} {"latest":<12}')
    populated = []
    for imei in imeis:
        try:
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE trip_status = 'ended'),
                       MIN(trip_date), MAX(trip_date)
                  FROM dll_trips_auditor WHERE device_imei = %s""", (str(imei),))
            n, ended, lo, hi = cur.fetchone()
        except Exception as exc:                    # noqa: BLE001
            cur.connection.rollback()
            print(f'   {imei:<17} !! {str(exc).splitlines()[0][:50]}')
            continue
        print(f'   {imei:<17} {n:>7} {ended:>7}  '
              f'{str(lo or "-")[:10]:<12} {str(hi or "-")[:10]:<12}')
        if ended:
            populated.append(imei)

    print()
    if populated:
        print(f'   {len(populated)} unit(s) have finished trips here. Waswa should read')
        print('   THIS table, so that it and the Trips report can never disagree.')
    elif total:
        print('   The table has trips for other devices but none for these units.')
    else:
        print('   The table is empty platform-wide; trips are not being recorded.')
'''

OLD_CALL = """        with conn.cursor() as cur:
            probe_positions(cur, imeis)"""

NEW_CALL = """        with conn.cursor() as cur:
            probe_positions(cur, imeis)
            probe_table_recency(cur)
            probe_trips(cur, imeis)"""


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    if 'probe_table_recency' in src:
        print('  already extended')
        return 0

    anchor = 'def probe_heartbeats('
    at = src.find(anchor)
    if at < 0:
        print('  !! probe_heartbeats not found — stopping')
        return 1
    src = src[:at] + NEW_FUNCS.strip('\n') + '\n\n\n' + src[at:]
    print('  added probe_table_recency() and probe_trips()')

    if OLD_CALL not in src:
        print('  !! call site not found — stopping, nothing written')
        return 1
    src = src.replace(OLD_CALL, NEW_CALL, 1)
    print('  wired both into main()')

    ast.parse(src)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(src)
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
