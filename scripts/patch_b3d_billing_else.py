#!/usr/bin/env python3
"""
B3d -- two routes fall through their billing check into the wrong behaviour.

check_device() in endpoints/globals.py is:

    if(cursor.rowcount == 1):   return BillingStatus
    elif(cursor.rowcount == 0): return 'not-found'
    # no else

so it returns None whenever rowcount is neither 1 nor 0. Both routes below
then test that value with

    if(... == 'running'): ... elif(... == 'blocked'): ... elif(... == 'not-found'): ...

and no final else, so None falls straight through:

  trips_history         the chain is the last thing in the function, so it
                        returns None and Flask raises "view did not return a
                        response" -- an opaque 500.

  trips_history_replay  WORSE. Execution continues past the try/except into a
                        SECOND try block (the mis-merged copy of the Excel
                        export that lives in this function's tail), so a client
                        that asked for replay JSON silently gets an .xlsx built
                        and a row written to dll_reports_downloadable_files.

This adds the missing final else to both, returning the same
'Unable to complete request' those routes already use for their other
unreachable branches -- no new message in the API surface. On the replay route
it also makes the dead tail genuinely unreachable rather than
reachable-by-accident; the tail itself is left in place as its own ticket,
because deleting ~70 lines of mis-merged code is a bigger decision than
closing the hole that reaches it.

NOT changed, deliberately: check_device() still returns None. Verified that
nothing tests it for truthiness, but endpoints/devices.py publishes it as
"billing_status" in three responses, so returning 'unknown' instead of None
would change three payloads from null to a string. With the else arms in
place, None is handled correctly in every route, so that change is cosmetic
and belongs to whoever owns those clients.

trips_stops is already total -- it guards with `if(... != 'running')` -- and is
left alone.

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

ROUTES = ('trips_history', 'trips_history_replay')
MESSAGE = "'Unable to complete request'"


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def billing_chain(text, name):
    """(outermost If, innermost If) of the device_billing_check chain."""
    for node in ast.parse(text).body:
        if not (isinstance(node, ast.FunctionDef) and node.name == name):
            continue
        outer = None
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and 'device_billing_check' in ast.unparse(sub.test):
                if outer is None or sub.lineno < outer.lineno:
                    outer = sub
        if outer is None:
            return None, None, node
        inner = outer
        while len(inner.orelse) == 1 and isinstance(inner.orelse[0], ast.If):
            inner = inner.orelse[0]
        return outer, inner, node
    raise SystemExit('FAIL: def %s() not found' % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    if MESSAGE.strip("'") in text and text.count('B3d:') > 0:
        print('SKIP: already patched.')
        return 0

    # ---- trips_stops must be left alone; confirm it is already total
    outer, inner, _node = billing_chain(text, 'trips_stops')
    if outer is None or '!=' not in ast.unparse(outer.test):
        print('FAIL: trips_stops is not the negative-form guard this patch')
        print('      assumes. Look before relying on it being total.')
        return 1
    print('trips_stops uses `!= running` -- already total, not touched')
    print('')

    # ---- insertions, collected first then applied bottom-up so earlier
    #      line numbers stay valid
    plan = []

    for name in ROUTES:
        outer, inner, node = billing_chain(text, name)
        if outer is None:
            print('FAIL [%s]: no device_billing_check chain found' % name)
            return 1
        if inner.orelse:
            print('SKIP [%s]: the chain already has a final else at line %d'
                  % (name, inner.orelse[0].lineno))
            continue

        lines = text.split('\n')
        elif_line = lines[inner.lineno - 1]
        indent = len(elif_line) - len(elif_line.lstrip())

        plan.append({
            'name': name,
            'after': inner.end_lineno,
            'indent': indent,
            'test': ast.unparse(inner.test)[:52],
        })

    if not plan:
        print('nothing to do')
        return 0

    lines = text.split('\n')

    for item in sorted(plan, key=lambda i: -i['after']):
        pad = ' ' * item['indent']
        block = [
            '',
            pad + '# B3d: the final else that was missing here.',
            pad + '#',
            pad + '# check_device() returns None when its rowcount is neither 1',
            pad + '# nor 0, and None matched none of the arms above, so control',
            pad + ('# fell out of the chain entirely -- in this route that meant'
                   if item['name'] == 'trips_history'
                   else '# fell through into the mis-merged Excel export in this'),
            pad + ('# returning None and Flask answering an opaque 500.'
                   if item['name'] == 'trips_history'
                   else "# function's tail, building an .xlsx for a caller that"),
        ]
        if item['name'] != 'trips_history':
            block.append(pad + '# asked for replay JSON.')
        block += [
            pad + 'else:',
            pad + '    return reply(\'error\', 400, %s, \'\')' % MESSAGE,
        ]
        lines[item['after']:item['after']] = block

    text = '\n'.join(lines)

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # ---- verify every chain is now total
    for name in ROUTES:
        outer, inner, _node = billing_chain(text, name)
        if not inner.orelse:
            print('FAIL [%s]: the chain still has no final else' % name)
            return 1
        arm = ast.unparse(inner.orelse[0])
        if 'Unable to complete request' not in arm:
            print('FAIL [%s]: the new else does not return the expected reply:'
                  % name)
            print('        %s' % arm[:90])
            return 1

    # trips_stops must be untouched
    outer, inner, _node = billing_chain(text, 'trips_stops')
    if inner.orelse:
        print('FAIL: trips_stops was modified; it should not have been')
        return 1

    for item in plan:
        print('%s' % item['name'])
        print('   * else added after the `%s` arm (line %d)'
              % (item['test'], item['after']))
    print('')
    print('endpoints/data.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
