#!/usr/bin/env python3
"""
patch_b5_fix_callsites.py — undo my mis-targeted edit and place it correctly.

patch_b5_config_cache.py added `prefetched_events=_events` to the WRONG
function. It used new.replace(old, new, 1), and count=1 takes the first match
in the file. All three routes call Config_Sources with byte-identical argument
text, and ComputeTrips_EXCELL (line ~697) comes before trips_history
(line ~1290). So:

  * ComputeTrips_EXCELL now references _events, which does not exist there —
    a NameError for anyone calling /data-stream/trips/excel
  * trips_history never got the prefetch, so event_value_for fell back to
    Cassandra: 40 queries where there should be 0, and the measured 41.53s
    instead of the expected low teens

It compiled, because NameError is a runtime failure, and b5_measure only
exercises trips_history, so neither check could see it. patch_b2_history.py
scoped every edit to the target function's line range for exactly this
reason; this patch did not, and that was the mistake.

This repairs both ends, with the scoping that should have been there:

  1. remove `, prefetched_events=_events` from every call site NOT inside
     trips_history
  2. add it to the four call sites that ARE inside trips_history, and only
     after the line where _events is assigned

Both steps assert what they are editing before they edit it, and the result
is checked for the one property that matters: no reference to _events outside
the function that defines it.

    python scripts/patch_b5_fix_callsites.py            # dry run
    python scripts/patch_b5_fix_callsites.py --apply
"""

import argparse
import difflib
import io
import os
import re
import shutil
import sys
import time

TARGET = os.path.join('endpoints', 'data.py')
FUNC = 'trips_history'
SUFFIX = ', prefetched_events=_events'
KINDS = ('ignition', 'mileage', 'fuel', 'driver_id')


def owners(lines):
    """(line number, function name) for every top-level def, in order."""
    return [(i, m.group(1)) for i, l in enumerate(lines)
            if (m := re.match(r'def (\w+)\(', l))]


def owner_of(index, defs):
    found = [d for d in defs if d[0] < index]
    return found[-1][1] if found else '<module>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    raw = io.open(TARGET, encoding='utf-8', newline='').read()
    crlf = raw.count('\r\n') > raw.count('\n') // 2
    src = raw.replace('\r\n', '\n') if crlf else raw
    print(f'line endings : {"CRLF" if crlf else "LF"} (preserved on write)')

    lines = src.splitlines(keepends=True)
    defs = owners(lines)

    lo = next((i for i, l in enumerate(lines)
               if re.match(rf'def {FUNC}\(', l)), None)
    if lo is None:
        print(f'!! def {FUNC}( not found')
        return 1
    hi = next((j for j in range(lo + 1, len(lines))
               if re.match(r'def \w+\(|@\w+\.route\(', lines[j])), len(lines))
    events_at = next((i for i in range(lo, hi)
                      if re.match(r'\s*_events\s*=', lines[i])), None)
    if events_at is None:
        print(f'!! _events is not assigned inside {FUNC}(); run '
              f'patch_b5_io_events.py first')
        return 1
    print(f'{FUNC}() spans lines {lo + 1}-{hi}, _events assigned at '
          f'{events_at + 1}')

    misplaced = [(i, owner_of(i, defs)) for i, l in enumerate(lines)
                 if SUFFIX in l and not (lo <= i < hi)]
    print(f'\nmisplaced call sites: {len(misplaced)}')
    for i, who in misplaced:
        print(f'   line {i + 1} in {who}()  <- _events undefined here')

    targets = [i for i in range(events_at, hi)
               if 'Config_Sources(' in lines[i] and SUFFIX not in lines[i]
               and any(f"'{k}'" in lines[i] for k in KINDS)]
    print(f'\ncall sites in {FUNC}() still needing it: {len(targets)}')
    for i in targets:
        print(f'   line {i + 1}: {lines[i].strip()[:88]}')

    if len(misplaced) != 4 or len(targets) != 4:
        print('\n!! expected exactly 4 of each. Refusing rather than')
        print('   half-fixing. Re-read the file and update this script.')
        return 1

    out = list(lines)
    for i, _who in misplaced:
        out[i] = out[i].replace(SUFFIX, '')
    for i in targets:
        stripped = out[i].rstrip('\n')
        if not stripped.endswith(')'):
            print(f'!! line {i + 1} does not end with ")"; refusing')
            return 1
        out[i] = stripped[:-1] + SUFFIX + ')' + '\n'

    new = ''.join(out)

    try:
        compile(new, TARGET, 'exec')
    except SyntaxError as error:
        print(f'!! does not compile: line {error.lineno}: {error.msg}')
        return 1
    print('\nthe patched file compiles')

    # The check that would have caught the original mistake.
    check_lines = new.splitlines(keepends=True)
    check_defs = owners(check_lines)
    c_lo = next(i for i, l in enumerate(check_lines)
                if re.match(rf'def {FUNC}\(', l))
    c_hi = next((j for j in range(c_lo + 1, len(check_lines))
                 if re.match(r'def \w+\(|@\w+\.route\(', check_lines[j])),
                len(check_lines))
    # The identifier, not the substring. A plain `'_events' in line` also
    # matches io_events_store, io_events_Found, io_events_data and
    # prefetched_events, which is how the first version of this check
    # reported 33 false positives. \b before an underscore requires a
    # non-word character there, so io_events_Found does not match.
    stray = re.compile(r'\b_events\b')
    strays = [(i + 1, owner_of(i, check_defs))
              for i, l in enumerate(check_lines)
              if stray.search(l) and not (c_lo <= i < c_hi)]
    if strays:
        print('!! _events is still referenced outside '
              f'{FUNC}(): {strays}')
        return 1
    print(f'verified: every _events reference is inside {FUNC}()')
    inside = sum(1 for i in range(c_lo, c_hi)
                 if SUFFIX in check_lines[i])
    print(f'verified: {inside} call site(s) in {FUNC}() carry the prefetch')

    for line in difflib.unified_diff(src.splitlines(), new.splitlines(),
                                     fromfile='data.py (now)',
                                     tofile='data.py (fixed)',
                                     lineterm='', n=1):
        print(line)

    if not args.apply:
        print('\n--- DRY RUN. Nothing written. ---')
        print('    python scripts/patch_b5_fix_callsites.py --apply')
        return 0

    backup = f'{TARGET}.bak.{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    io.open(TARGET, 'w', encoding='utf-8', newline='').write(
        new.replace('\n', '\r\n') if crlf else new)
    print(f'\nwritten. backup at {backup}')
    print('\nThen measure again:')
    print('  python scripts/b5_measure.py')
    print('\nExpect dll_io_events_executed_logs to drop from 40 to 0 counted')
    print('queries: the values now come from data already fetched.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
