#!/usr/bin/env python3
"""
patch_b6_trips_distance.py — trips_data has never worked in trips/history.

Ticket B6. Not caused by B2: the line is byte-identical in the pre-B2 backup.

    distance_pool_x = Calculate_DistanceX(...)
    distance_adapter = distance_pool_x.get_json()     <- AttributeError

Calculate_DistanceX returns a JSON STRING. Its own docstring says so — "Every
caller does json.loads() on the result" — and the excel route (line ~757) and
the pdf route (line ~997) both do exactly that. Only trips/history calls
.get_json(), which is a Flask response method, on a str.

So every trip with real start and end coordinates raised AttributeError, the
handler turned it into reply('error', 500, error, ''), and jsonify then failed
to serialise the exception object — producing an unhandled 500 with an empty
message. That is why the route answered HTTP 500 with '' rather than naming
its own bug.

It went unnoticed because the code never ran: trips/history read the Postgres
copy, which has held no rows since 06-08-2025, so recent requests returned
"No Trips Found" before reaching this loop, and on older parked data the trips
list was empty. B2 pointed the route at the live store, which made it
reachable for the first time.

Two changes, both copied from the working call sites rather than invented:

  1. json.loads instead of .get_json(), with the CORDS_ERROR guard and the
     float() the other two routes use. Without the guard, round(distance) a
     few lines later raises on the error string.

  2. reply('error', 500, str(error), '') instead of passing the exception
     object. An exception is not JSON serialisable, so today every 500 from
     this route becomes an unhandled TypeError and the client gets nothing
     useful. One occurrence in the file, so this is a local fix.

Dry run by default:

    python scripts/patch_b6_trips_distance.py
    python scripts/patch_b6_trips_distance.py --apply
"""

import argparse
import difflib
import io
import os
import shutil
import sys
import time

TARGET = os.path.join('endpoints', 'data.py')

OLD_DISTANCE = """                                                distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                                distance_adapter = distance_pool_x.get_json()
                                                distance = distance_adapter['distance_covered']
"""

NEW_DISTANCE = """                                                distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                                # Calculate_DistanceX returns a JSON STRING, as its own
                                                # docstring states and as the excel and pdf routes already
                                                # do. .get_json() is a response-object method, so this
                                                # raised AttributeError on every trip that had real
                                                # coordinates — which is why trips_data was always empty.
                                                distance_adapter = json.loads(distance_pool_x)
                                                if distance_adapter['distance_covered'] != 'CORDS_ERROR':
                                                    distance = float(distance_adapter['distance_covered'])
                                                else:
                                                    # round(distance) below would raise on the error
                                                    # string. The other routes report 0 for a leg whose
                                                    # distance could not be worked out.
                                                    distance = 0
"""

OLD_HANDLER = """    except Exception as error:
        return reply('error', 500, error, '')
"""

NEW_HANDLER = """    except Exception as error:
        # An exception object is not JSON serialisable, so passing it here
        # turned every 500 into an unhandled TypeError inside jsonify and the
        # caller received an empty message. Log the traceback, return the text.
        logging.exception('trips_history failed')
        return reply('error', 500, str(error), '')
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write the change')
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        print(f'!! {TARGET} not found. Run from the repository root.')
        return 1

    raw = io.open(TARGET, encoding='utf-8', newline='').read()
    crlf = raw.count('\r\n') > raw.count('\n') // 2
    src = raw.replace('\r\n', '\n') if crlf else raw
    print(f'line endings : {"CRLF" if crlf else "LF"} (preserved on write)')

    if 'distance_adapter = json.loads(distance_pool_x)' in src:
        print('Already patched. Nothing to do.')
        return 0

    problems = []
    if src.count(OLD_DISTANCE) != 1:
        problems.append(f'the distance block matched {src.count(OLD_DISTANCE)} '
                        f'time(s), expected 1')
    if src.count(OLD_HANDLER) != 1:
        problems.append(f'the 500 handler matched {src.count(OLD_HANDLER)} '
                        f'time(s), expected 1')
    if problems:
        print('!! refusing to patch:')
        for p in problems:
            print(f'     - {p}')
        return 1

    new = src.replace(OLD_DISTANCE, NEW_DISTANCE).replace(OLD_HANDLER,
                                                          NEW_HANDLER)
    try:
        compile(new, TARGET, 'exec')
    except SyntaxError as error:
        print(f'!! patched file does not compile: line {error.lineno}: '
              f'{error.msg}. Nothing written.')
        return 1
    print('the patched file compiles')

    if 'import json' not in new and 'import json\n' not in new:
        print('!! json is not imported in data.py — add it before applying')
        return 1
    if 'import logging' not in new:
        print('!! logging is not imported in data.py — add it before applying')
        return 1
    print('json and logging are both imported')

    for line in difflib.unified_diff(src.splitlines(), new.splitlines(),
                                     fromfile='data.py (now)',
                                     tofile='data.py (patched)',
                                     lineterm='', n=2):
        print(line)

    if not args.apply:
        print('\n--- DRY RUN. Nothing written. ---')
        print('    python scripts/patch_b6_trips_distance.py --apply')
        return 0

    backup = f'{TARGET}.bak.{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    io.open(TARGET, 'w', encoding='utf-8', newline='').write(
        new.replace('\n', '\r\n') if crlf else new)
    print(f'\nwritten. backup at {backup}')
    print('\nThen re-run:')
    print('  python scripts/b2_route_check.py --imei 862846042622426 '
          '--day 25-09-2026')
    print('\ntrips_data should now be populated, and a 500 — if any remains —')
    print('will carry a readable message instead of an empty one.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
