#!/usr/bin/env python3
"""Two real query bugs in endpoints/waswa_fleet.py, found by waswa_fleet_check.

1. dll_pause_rules has no column called `target`. pause.py, which has been
   reading and writing that table all along, calls it `target_uid`. My query
   raised, got swallowed by the except, and every unit came back with
   "pause rules could not be read" — so Waswa could never tell a customer that
   their vehicle is dark because billing paused it, which is one of the most
   common real reasons.

2. _stamp parsed exactly one date format. The check showed a heartbeat row
   coming back from Cassandra and still producing last_reported_at: null,
   which means the row was there and the parse failed. statistics.py has
   always tried four formats against this same column, because the data is not
   consistent. Matching that is not defensive programming, it is reading what
   the rest of the codebase already knew.

   This mattered twice over: _stamp is used for the heartbeat AND for every
   position fix, so a format mismatch empties trips and fleet activity too.

Idempotent.
"""
import ast
import io
import sys

PATH = 'endpoints/waswa_fleet.py'

OLD_PAUSE = ('''            cur.execute("SELECT mode, active FROM dll_pause_rules "
                        "WHERE target = %s AND active = TRUE", (unit['imei'],))''')

NEW_PAUSE = ('''            # target_uid, not target: pause.py owns this table and that is
            # what it calls the column. Scope is not filtered here on purpose —
            # a rule on the unit, its group or the account all leave the
            # vehicle dark, and the customer only wants to know that it is.
            cur.execute("SELECT mode, active FROM dll_pause_rules "
                        "WHERE target_uid = %s AND active = TRUE",
                        (unit['imei'],))''')

OLD_STAMP = '''def _stamp(datestamp, timestamp):
    """dll_location_registry stores DD-MM-YYYY and HH:MM:SS as text."""
    try:
        return datetime.strptime(f'{datestamp} {timestamp}', '%d-%m-%Y %H:%M:%S')
    except (TypeError, ValueError):
        return None
'''

NEW_STAMP = '''# Dates arrive as text and not always in the same shape: dll_location_registry
# writes DD-MM-YYYY, dll_pulse_status_registry has been seen holding at least
# two others, and statistics.py has tried four formats against it for as long
# as it has existed. A parse failure here is silent and total — it empties the
# heartbeat, every trip and all of fleet activity at once — so try what the
# rest of the codebase already tries.
_DATE_FORMATS = ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d')
_TIME_FORMATS = ('%H:%M:%S', '%H:%M:%S.%f', '%H:%M')


def _stamp(datestamp, timestamp):
    """A datetime from the text pair, or None if nothing reads it.

    None means "unknown", never "epoch": a zero date would quietly become a
    unit that last reported in 1970 and a trip 56 years long.
    """
    if datestamp is None:
        return None
    date_text = str(datestamp).strip()
    time_text = str(timestamp or '').strip() or '00:00:00'
    if not date_text:
        return None

    day = None
    for fmt in _DATE_FORMATS:
        try:
            day = datetime.strptime(date_text, fmt).date()
            break
        except ValueError:
            continue
    if day is None:
        return None

    for fmt in _TIME_FORMATS:
        try:
            clock = datetime.strptime(time_text, fmt).time()
            return datetime.combine(day, clock)
        except ValueError:
            continue
    # A readable date with an unreadable time is still worth more than nothing:
    # "last reported on the 28th" beats "never reported".
    return datetime.combine(day, datetime.min.time())
'''


def patch(src):
    changes = []

    if 'target_uid = %s AND active = TRUE' in src:
        changes.append('pause-rule column already target_uid')
    elif OLD_PAUSE in src:
        src = src.replace(OLD_PAUSE, NEW_PAUSE, 1)
        changes.append('dll_pause_rules: target -> target_uid')
    else:
        return None, ['!! pause-rule query not found verbatim — stopping']

    if '_DATE_FORMATS' in src:
        changes.append('_stamp already multi-format')
    elif OLD_STAMP in src:
        src = src.replace(OLD_STAMP, NEW_STAMP, 1)
        changes.append('_stamp now tries 4 date and 3 time formats')
    else:
        return None, ['!! _stamp not found verbatim — stopping']

    return src, changes


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    out, changes = patch(src)
    for c in changes:
        print('  ' + c)
    if out is None:
        return 1
    if out == src:
        print('  (nothing to write)')
        return 0
    ast.parse(out)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(out)
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
