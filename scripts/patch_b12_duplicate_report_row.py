#!/usr/bin/env python3
"""
B12 -- trips/excel inserts its report row twice, so the status endpoint
cannot answer.

MEASURED, not inferred. b3_report_rows.py found six request_uids with two rows
each, all six from trips/excel; no trips/pdf uid is duplicated. Both rows of
one uid were 'completed' with the SAME file_path, while only one .xlsx had been
written -- so one file, one UPDATE (which hits every matching row), two INSERTs.

The two inserts:

    data.py:668   LogReport_Request(OriginRequest_UID, OriginUser_UID)
                  -> INSERT ... (request_uid, file_path, report_caller,
                                 request_status, request_datestamp)
    data.py:706   cursor.execute("INSERT ... (request_uid, file_path,
                                 report_caller, request_status)")

Identical values; the inline one omits request_datestamp, leaving it NULL.
ComputeTrips_PDF calls the helper and has NO inline INSERT, which is exactly
why pdf's status resolves and excel's does not -- report_status does

    if rowcount == 1: ... elif rowcount == 0: 'No Request Found'
    else:             'Unable to complete request'

so two rows land in the `else`. The customer's file is on the CDN and the
status endpoint tells them the request cannot be completed.

THE FIX: delete the inline INSERT and keep the helper. The helper's row is the
better one -- it sets request_datestamp, which report_status returns.

WHY NOT A UNIQUE CONSTRAINT ON request_uid: it would be good hygiene (the
table's only key is a serial id), but adding it now would make excel's second
insert RAISE instead of making the route correct. Remove the duplicate first;
a constraint can follow as a guard against the next one.

NOT B3's doing: both statements predate it. B3 only made excel exports produce
files again, which is what made the broken status visible.

Dry run by default. Pass --apply to write.
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'data.py')

INSERT_MARK = 'INSERT INTO dll_reports_downloadable_files'
HELPER_CALL = 'LogReport_Request(OriginRequest_UID, OriginUser_UID)'


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def body_of(text, name):
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, node.end_lineno
    raise SystemExit('FAIL: def %s() not found' % name)


def inline_inserts(text, name):
    lo, hi = body_of(text, name)
    lines = text.split('\n')
    return [i for i in range(lo, hi + 1)
            if INSERT_MARK in lines[i - 1] and 'cursor.execute' in lines[i - 1]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    # ---- the reference shape: pdf must have the helper and no inline insert
    pdf_inline = inline_inserts(text, 'ComputeTrips_PDF')
    lo, hi = body_of(text, 'ComputeTrips_PDF')
    pdf_calls = '\n'.join(text.split('\n')[lo - 1:hi]).count(HELPER_CALL)

    if pdf_inline or pdf_calls != 1:
        print('FAIL: ComputeTrips_PDF is not the clean reference this patch')
        print('      assumes (%d inline INSERTs, %d helper calls). Look before'
              % (len(pdf_inline), pdf_calls))
        print('      changing excel to match it.')
        return 1
    print('reference: ComputeTrips_PDF has 1 helper call and 0 inline INSERTs')

    # ---- excel
    excel_inline = inline_inserts(text, 'ComputeTrips_EXCELL')
    lo, hi = body_of(text, 'ComputeTrips_EXCELL')
    excel_calls = '\n'.join(text.split('\n')[lo - 1:hi]).count(HELPER_CALL)

    if excel_calls != 1:
        print('FAIL: expected exactly 1 LogReport_Request call in excel, found %d'
              % excel_calls)
        return 1

    if not excel_inline:
        print('SKIP: ComputeTrips_EXCELL has no inline INSERT -- already fixed.')
        return 0

    if len(excel_inline) != 1:
        print('FAIL: expected exactly 1 inline INSERT in excel, found %d at %s'
              % (len(excel_inline), excel_inline))
        return 1

    target_line = excel_inline[0]
    lines = text.split('\n')
    indent = len(lines[target_line - 1]) - len(lines[target_line - 1].lstrip())

    note = (' ' * indent
            + '# B12: the inline INSERT that stood here is gone. '
              'LogReport_Request()')
    note2 = (' ' * indent
             + '# above already inserted this row -- with request_datestamp, '
               'which')
    note3 = (' ' * indent
             + '# this one omitted -- so every excel export left TWO rows and '
               'made')
    note4 = (' ' * indent
             + '# report_status answer "Unable to complete request" while the '
               'file')
    note5 = (' ' * indent + '# sat on the CDN. ComputeTrips_PDF never had this '
                            'line.')

    lines[target_line - 1:target_line] = [note, note2, note3, note4, note5]
    text = '\n'.join(lines)

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # ---- verify: excel now matches pdf's shape
    still = inline_inserts(text, 'ComputeTrips_EXCELL')
    lo, hi = body_of(text, 'ComputeTrips_EXCELL')
    chunk = '\n'.join(text.split('\n')[lo - 1:hi])

    if still:
        print('FAIL: an inline INSERT survives at %s' % still)
        return 1
    if chunk.count(HELPER_CALL) != 1:
        print('FAIL: the LogReport_Request call was disturbed')
        return 1
    if 'raw_data_adapter' not in chunk or 'location_store.fixes' not in chunk:
        print("FAIL: B3's live read is no longer in excel")
        return 1

    # the helper itself must be untouched
    helper_lo, helper_hi = body_of(text, 'LogReport_Request')
    helper = '\n'.join(text.split('\n')[helper_lo - 1:helper_hi])
    if INSERT_MARK not in helper or 'request_datestamp' not in helper:
        print('FAIL: LogReport_Request no longer inserts with a datestamp')
        return 1

    print('ComputeTrips_EXCELL')
    print('   * removed the inline INSERT at line %d' % target_line)
    print('   * LogReport_Request() at line %d is now the only insert'
          % (text.split('\n').index(
              [l for l in text.split('\n') if HELPER_CALL in l][0]) + 1))
    print('   * excel now matches pdf: 1 helper call, 0 inline INSERTs')
    print('')
    print('endpoints/data.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    print('')
    print('The six duplicated rows already in the table are NOT cleaned up by')
    print('this patch -- deleting production rows is yours to decide. Until')
    print('they are removed, those six request_uids keep returning "Unable to')
    print('complete request". New exports will be fine.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
