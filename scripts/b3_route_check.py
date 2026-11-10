#!/usr/bin/env python3
"""
b3_route_check.py — do trips/excel and trips/pdf actually produce a file now?

B3 part 1 switched both routes from the Postgres copy of
dll_location_registry (which ends 01-08-2025) to the live Cassandra store
(which begins 05-08-2025). The two share no day, so before this change every
export for a recent date came back 'No Trips Data Found'.

Neither route returns the data. Both reply 'Processing ... Keep Checking' and
record the outcome in dll_reports_downloadable_files, so a 200 proves almost
nothing on its own — the request could 200 and still have written a 'no-data'
row. This therefore checks the FULL path:

    POST the route  ->  200 'Processing'
    GET /data-stream/reports/<uid>/status
                    ->  request_status 'completed' AND a real file_path
    open that file  ->  it exists, is non-empty, and the right format

Each case fails differently if something specific broke:

  1. recent day, excel     the case that returned NOTHING before B3
  2. recent day, pdf       the identical substitution in the other route
  3. status reaches        proves the route got past the read and wrote a
     'completed'           file, not just that it answered 200
  4. the file is real      a .xlsx must open as a zip container with a
                           worksheet; a .pdf must start with %PDF
  5. window Cassandra      07-08 to 11-08-2025 — must be an honest
     lacks                 'No Trips Data Found' and leave 'no-data' in the
                           report row, NOT a 503 and NOT a stuck 'in_process'
  6. no orphan row         a 503 must leave NO report row at all, because the
                           read now happens before the bookkeeping INSERT.
                           Only checked if a 503 actually occurs.

Case 5 matters as much as case 1: 'in_process' left behind on an empty window
would mean the UI shows a report that never finishes.

Read-only apart from the report rows the routes themselves write, which is
their normal behaviour.

Usage:
    python scripts/b3_route_check.py
    python scripts/b3_route_check.py --imei 862846042622426 --day 25-09-2026
"""

import argparse
import os
import sys
import time
import uuid

sys.path.insert(0, '.')

EMPTY_FROM, EMPTY_TO = '07-08-2025', '11-08-2025'
EMPTY_UNIT = '867556044727322'

RESULTS = []


def record(label, ok, blocked, detail):
    mark = 'ok ' if ok else ('-- ' if blocked else '!! ')
    print('   %s%-28s %s' % (mark, label, detail))
    RESULTS.append((label, ok, blocked, detail))


def billing_blocked(message):
    low = str(message).lower()
    return ('billing' in low or 'cant be found' in low or 'not-found' in low)


def export(client, route, imei, start, end, count=10):
    """POST one export request. Returns (code, message, request_uid, seconds)."""
    request_uid = str(uuid.uuid4())
    body = {'data': {
        'device_imei': imei,
        'from_date': start,
        'to_date': end,
        'offset_log': '0',
        'record_count': str(count),
        'request_origin_uid': request_uid,
        'request_origin_user_uid': 'b3-route-check',
    }}
    began = time.time()
    try:
        res = client.post(route, json=body)
        payload = res.get_json() or {}
        return (res.status_code, str(payload.get('message', '')), request_uid,
                time.time() - began)
    except Exception as error:                            # noqa: BLE001
        return 0, 'EXCEPTION %s' % error, request_uid, time.time() - began


def status_of(client, request_uid):
    """The report row, plus HOW the status route answered.

    Returns (row, code, message).

    The first version of this returned {} on anything unexpected and read a
    key named 'request_status'. The route publishes 'file_status' (the SELECT
    column is request_status, the JSON key is not), so every status read came
    back empty -- and because the empty-window assertion accepted '' as
    acceptable, two checks PASSED for the reason the other two failed. An
    unreadable status now carries the route's own code and message so "no row
    exists" can be told apart from "a row exists and a field is missing".
    """
    try:
        res = client.get('/data-stream/reports/%s/status' % request_uid)
        payload = res.get_json() or {}
        code = res.status_code
    except Exception as error:                            # noqa: BLE001
        return {}, 0, 'EXCEPTION %s' % error

    message = str(payload.get('message', ''))
    data = payload.get('data')
    if isinstance(data, list) and data:
        data = data[0]
    return (data if isinstance(data, dict) else {}), code, message


def state_of(row):
    """The status string the route publishes, or None when absent.

    None means "not readable", never "fine".
    """
    if not isinstance(row, dict):
        return None
    for key in ('file_status', 'request_status', 'status'):
        if key in row:
            return str(row[key])
    return None


def looks_like_xlsx(path):
    """A real .xlsx is a zip holding xl/workbook.xml."""
    try:
        import zipfile
        if not zipfile.is_zipfile(path):
            return False, 'not a zip container'
        with zipfile.ZipFile(path) as book:
            names = book.namelist()
        if 'xl/workbook.xml' not in names:
            return False, 'zip without xl/workbook.xml'
        return True, '%d entries' % len(names)
    except Exception as error:                            # noqa: BLE001
        return False, str(error)[:50]


def looks_like_pdf(path):
    try:
        with open(path, 'rb') as handle:
            head = handle.read(5)
        return head == b'%PDF-', repr(head)
    except Exception as error:                            # noqa: BLE001
        return False, str(error)[:50]


def local_path_for(path):
    """file_path holds a PUBLIC URL, not a disk path.

    Both routes build it as config['base_url'] + 'reports-cdn/' + name, and
    write the file to endpoints/../reports-cdn/. The first version of this
    check called os.path.exists() on the https:// URL and failed a route that
    was working. Map the URL back to the repo's own reports-cdn directory so
    the check needs no network.
    """
    text = str(path or '')
    marker = 'reports-cdn/'
    if marker in text:
        name = text.split(marker, 1)[1].split('?')[0].split('#')[0]
        return os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'reports-cdn', name)
    return text


def check_file(label, path):
    if not path or str(path) in ('NO_DIR_PATH', 'None', ''):
        record(label, False, False, 'status row carries no usable file_path: %r'
               % path)
        return

    original = path
    path = local_path_for(path)

    if not os.path.exists(path):
        record(label, False, False,
               'no file at %s (from %s)'
               % (path, str(original)[:46]))
        return
    size = os.path.getsize(path)
    if path.lower().endswith('.xlsx'):
        good, detail = looks_like_xlsx(path)
    elif path.lower().endswith('.pdf'):
        good, detail = looks_like_pdf(path)
    else:
        good, detail = size > 0, 'unknown extension'
    record(label, good and size > 0, False,
           '%s  %d bytes  %s' % (os.path.basename(path), size, detail))


def run_export_case(client, route, label, imei, start, end, expect_rows):
    code, message, request_uid, took = export(client, route, imei, start, end)
    blocked = billing_blocked(message)

    if expect_rows:
        ok = code == 200 and 'processing' in message.lower()
    else:
        ok = code == 400 and 'no trips' in message.lower()

    record(label, ok, blocked, 'HTTP %s %r  %.1fs' % (code, message[:40], took))

    if code == 503:
        row = status_of(client, request_uid)
        record('%s: no orphan row on 503' % label, not row, False,
               'status row %s' % ('absent, correct' if not row else row))
        return None

    return request_uid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    args = ap.parse_args()

    from app import app
    client = app.test_client()

    print('unit %s, day %s' % (args.imei, args.day))
    print('(each export reads positions then builds a file, so allow a '
          'minute each)\n')

    for route, name, want in (
            ('/data-stream/trips/excel', 'excel', 'xlsx'),
            ('/data-stream/trips/pdf', 'pdf', 'pdf')):

        request_uid = run_export_case(
            client, route, '%s: recent day' % name, args.imei, args.day,
            args.day, expect_rows=True)

        if request_uid:
            row, scode, smessage = status_of(client, request_uid)
            state = state_of(row)
            record('%s: status completed' % name, state == 'completed', False,
                   'status HTTP %s %r | file_status=%r file_path=%r'
                   % (scode, smessage[:26], state,
                      str(row.get('file_path'))[:40]))
            if state == 'completed':
                check_file('%s: file is a real %s' % (name, want),
                           row.get('file_path'))
            elif state is None:
                print('        the status route returned no usable row, so')
                print('        whether the export completed is UNKNOWN, not')
                print('        failed -- %s' % (smessage or 'no message'))

        # an empty window must say so, and must not leave the row in_process
        empty_uid = run_export_case(
            client, route, '%s: empty window' % name, EMPTY_UNIT,
            EMPTY_FROM, EMPTY_TO, expect_rows=False)

        if empty_uid:
            row, scode, smessage = status_of(client, empty_uid)
            state = state_of(row)

            # 'no-data' is what the route writes. No row at all is also
            # correct for pdf, which never INSERTs before reading -- but the
            # route must SAY so (400 'No Request Found'), not leave the
            # status unreadable. An absent state is not a pass.
            no_row = (not row) and scode == 400
            acceptable = (state == 'no-data') or no_row

            record('%s: empty window not left in_process' % name,
                   acceptable, False,
                   'status HTTP %s %r | file_status=%r'
                   % (scode, smessage[:26], state))
        print('')

    print('=' * 68)
    good = [r for r in RESULTS if r[1]]
    blocked = [r for r in RESULTS if r[2] and not r[1]]
    bad = [r for r in RESULTS if not r[1] and not r[2]]
    print('   %d as expected, %d billing-blocked, %d wrong'
          % (len(good), len(blocked), len(bad)))

    if blocked:
        print('')
        print('   Those prove nothing: both routes check the device registry')
        print('   and billing before reading a position, so they never reached')
        print('   the code B3 changed.')

    if bad:
        print('')
        print('   NOT working:')
        for label, _ok, _b, detail in bad:
            print('     - %-30s %s' % (label, detail))
        print('')
        print('   location_store is separately tested, so a failure here is')
        print('   in the route: the report-file bookkeeping, the file build,')
        print('   or the len(raw_data_adapter) guards that replaced')
        print('   cursor.rowcount.')
        return 1

    print('')
    print('   B3 part 1 works: both exports read the live store, reach')
    print('   "completed", and leave a real file on disk where before B3 they')
    print('   returned no data for every recent date. An empty window is')
    print('   reported honestly and does not strand a report at in_process.')
    print('')
    print('   Still on Postgres, deliberately: the two trips/history/replay')
    print('   branches (B3c, pending the time-window semantics) and the')
    print('   summary query in replay\'s unreachable tail (B3d).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
