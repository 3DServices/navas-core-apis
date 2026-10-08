#!/usr/bin/env python3
"""
patch_b3_housekeeping.py -- B3's two leftovers in trips_history_replay.

1. The live body still opens a Postgres connection it does not use.
   B3c swapped the position SELECT for location_store.fixes() but left
   `dbconnect = psycopg2.connect(...)` and the `with dbconnect:` /
   `with dbconnect.cursor() as cursor:` pair in place, so the trip-building
   loop would not have to be re-indented out of two `with` blocks. The cost
   of that shortcut is a connection, a transaction and a cursor opened on
   every replay request to do nothing. This removes all three and performs
   the re-indent.

2. The 74-line tail after the route's own `except` is a mis-merged copy of
   the Excel export: it builds an .xlsx and carries the
   `INSERT INTO dll_reports_downloadable_files` that B12 removed from the
   real Excel route. It also reads a different payload
   (`request_uid`, `request_origin_user_uid`) and holds the LAST
   `dll_location_registry` SELECT anywhere in data.py.

The tail is deleted only if this script re-proves it unreachable. The proof
is an always-exits analysis over the function's first try/except: the tail is
reachable only if that statement can complete without returning or raising.
B3d's missing `else` arms are what made that provable -- before them, an
unknown check_device() state fell through INTO this tail and served an .xlsx
to a caller who asked for replay JSON.

Nothing here may change behaviour, so the set of (status, code, message)
literals reachable in the live body is compared before and after and must be
identical.

data.py is CRLF; line endings are preserved. Dry run unless --write.

Usage:
    python scripts/patch_b3_housekeeping.py
    python scripts/patch_b3_housekeeping.py --write
"""

import ast
import io
import os
import sys

TARGET = os.path.join('endpoints', 'data.py')
FUNC = 'trips_history_replay'


def fail(message):
    sys.stderr.write('REFUSED: %s\n' % message)
    raise SystemExit(2)


def always_exits(statements):
    """True when this statement list cannot complete normally.

    Conservative: anything not understood is assumed to fall through, so a
    False here never licenses a deletion.
    """
    for node in statements:
        if isinstance(node, (ast.Return, ast.Raise)):
            return True
        if isinstance(node, ast.If):
            if (node.orelse and always_exits(node.body)
                    and always_exits(node.orelse)):
                return True
        elif isinstance(node, ast.With):
            if always_exits(node.body):
                return True
        elif isinstance(node, ast.Try):
            body_exits = always_exits(node.body) or always_exits(node.orelse)
            handlers_exit = bool(node.handlers) and all(
                always_exits(h.body) for h in node.handlers)
            if always_exits(node.finalbody):
                return True
            if body_exits and handlers_exit:
                return True
    return False


def sql_mentions(text, table):
    """Occurrences of `table` outside comments.

    data.py keeps two comments explaining why the Postgres copy of
    dll_location_registry is dead; those must survive. Only a reference in
    live code counts.
    """
    count = 0
    for line in text.splitlines():
        code = line.split('#', 1)[0]
        count += code.count(table)
    return count


def reply_literals(node):
    """Every (status, code, message) a `reply(...)` in this subtree can send."""
    found = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = getattr(child.func, 'id', None)
        if name != 'reply' or len(child.args) < 3:
            continue
        parts = []
        for arg in child.args[:3]:
            parts.append(arg.value if isinstance(arg, ast.Constant)
                         else '<dynamic>')
        found.add(tuple(parts))
    return found


def main():
    write = '--write' in sys.argv

    with io.open(TARGET, 'r', newline='') as handle:
        src = handle.read()
    lines = src.splitlines(keepends=True)

    crlf = src.count('\r\n')
    if crlf == 0:
        fail('%s has no CRLF endings; expected a CRLF file' % TARGET)

    tree = ast.parse(src.replace('\r\n', '\n'))
    func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == FUNC:
            func = node
            break
    if func is None:
        fail('%s not found' % FUNC)

    tries = [n for n in func.body if isinstance(n, ast.Try)]
    if len(tries) != 2:
        fail('expected exactly 2 top-level try blocks in %s, found %d'
             % (FUNC, len(tries)))
    live, tail = tries

    # ---- the proof the deletion is gated on
    if not always_exits([live]):
        fail('the live try/except can complete normally, so the tail at '
             'line %d is REACHABLE. Not deleting it.' % tail.lineno)
    print('proof: the live try/except always returns or raises, so lines '
          '%d-%d are unreachable' % (tail.lineno, tail.end_lineno))

    # The tail must be the Excel mis-merge, not something else that grew here.
    tail_text = ''.join(lines[tail.lineno - 1:tail.end_lineno])
    for marker in ('dll_location_registry', 'to_excel',
                   'dll_reports_downloadable_files'):
        if marker not in tail_text:
            fail('the tail does not contain %r -- it is not the block this '
                 'patch was written for' % marker)

    before = reply_literals(live)

    # ---- edit 1: drop the unused `with dbconnect:` pair and re-indent
    withs = [n for n in ast.walk(live) if isinstance(n, ast.With)]
    outer = None
    for node in sorted(withs, key=lambda n: n.lineno):
        if 'dbconnect' in lines[node.lineno - 1]:
            outer = node
            break
    if outer is None:
        fail('no `with dbconnect:` found in the live body')

    inner_line = lines[outer.lineno].strip()
    if not inner_line.startswith('with dbconnect.cursor()'):
        fail('expected `with dbconnect.cursor() as cursor:` directly after '
             'line %d, found %r' % (outer.lineno, inner_line))
    if len(outer.body) != 1 or not isinstance(outer.body[0], ast.With):
        fail('the outer `with dbconnect:` holds more than the inner with')

    inner = outer.body[0]
    # Look only at Load-context uses inside the BODY. Walking the `with`
    # itself finds its own `as cursor` binding target and refuses a correct
    # patch -- which is exactly what the first run of this script did.
    for statement in inner.body:
        for child in ast.walk(statement):
            if (isinstance(child, ast.Name) and child.id == 'cursor'
                    and isinstance(child.ctx, ast.Load)):
                fail('`cursor` is still read inside the with block at line %d'
                     % child.lineno)

    body_start = inner.body[0].lineno           # first real statement
    body_end = outer.end_lineno                 # last line of the block
    block = lines[body_start - 1:body_end]

    shifted = []
    for raw in block:
        stripped = raw.strip()
        if not stripped:
            shifted.append(raw)                 # blank / whitespace-only
            continue
        if not raw.startswith(' ' * 8):
            fail('line %r has less than 8 spaces of indent; cannot '
                 're-indent safely' % raw[:40])
        shifted.append(raw[8:])

    # keep any comment lines that sit between the `with` and the first
    # statement (there are none today, but refuse rather than drop them)
    gap = lines[outer.lineno + 1:body_start - 1]
    if any(line.strip() for line in gap):
        fail('unexpected content between the with statements and the body')

    new_lines = (lines[:outer.lineno - 1] + shifted + lines[body_end:])

    # ---- edit 2: drop the now-unused connect in the live body
    connect_at = None
    for index in range(live.lineno, outer.lineno):
        if 'dbconnect = psycopg2.connect(' in new_lines[index - 1]:
            connect_at = index
            break
    if connect_at is None:
        fail('no `dbconnect = psycopg2.connect(` in the live body')
    new_lines = new_lines[:connect_at - 1] + new_lines[connect_at:]

    # ---- edit 3: delete the tail
    #
    # Derive the shift from the line count rather than counting the removed
    # lines by hand. The first version of this script assumed edits 1 and 2
    # dropped 3 lines when they drop 4 -- edit 1 also takes the blank line
    # between the two `with` statements -- and the off-by-one left the tail's
    # `try:` behind with its body deleted.
    shift = len(lines) - len(new_lines)
    tail_from = tail.lineno - shift
    tail_to = tail.end_lineno - shift
    if new_lines[tail_from - 1].strip() != 'try:':
        fail('line %d is %r, not the tail\'s `try:` -- refusing to delete '
             'by line number' % (tail_from, new_lines[tail_from - 1].strip()))
    check = ''.join(new_lines[tail_from - 1:tail_to])
    if 'dll_location_registry' not in check or 'to_excel' not in check:
        fail('the tail is not where the shifted line numbers say it is')
    if sql_mentions(''.join(new_lines[tail_to:]), 'dll_location_registry'):
        fail('there is still a dll_location_registry read after the tail')
    # also take the blank lines between the live except and the tail
    first = tail_from - 1
    while first > 1 and not new_lines[first - 1].strip():
        first -= 1
    new_lines = new_lines[:first] + new_lines[tail_to:]

    out = ''.join(new_lines)

    # ---- the result must parse, and must not have changed behaviour
    new_tree = ast.parse(out.replace('\r\n', '\n'))
    new_func = None
    for node in ast.walk(new_tree):
        if isinstance(node, ast.FunctionDef) and node.name == FUNC:
            new_func = node
            break
    if new_func is None:
        fail('%s vanished from the result' % FUNC)

    new_tries = [n for n in new_func.body if isinstance(n, ast.Try)]
    if len(new_tries) != 1:
        fail('expected 1 try block after the edit, found %d' % len(new_tries))

    after = reply_literals(new_tries[0])
    if after != before:
        fail('the reachable reply() literals changed.\n  gone:  %r\n  new:   %r'
             % (sorted(before - after), sorted(after - before)))

    func_text = ''.join(new_lines[new_func.lineno - 1:new_func.end_lineno])
    if 'dbconnect' in func_text:
        fail('`dbconnect` still appears in %s' % FUNC)
    live_refs = sql_mentions(out, 'dll_location_registry')
    if live_refs:
        fail('data.py still has %d live (non-comment) reference(s) to '
             'dll_location_registry' % live_refs)

    before_connects = src.count('psycopg2.connect(')
    after_connects = out.count('psycopg2.connect(')
    if before_connects - after_connects != 2:
        fail('psycopg2.connect( count moved by %d, expected 2'
             % (before_connects - after_connects))

    compile(out.replace('\r\n', '\n'), TARGET, 'exec')

    if out.count('\r\n') != out.count('\n'):
        fail('line endings are no longer uniformly CRLF')

    print('')
    print('  %-44s %d -> %d lines' % (TARGET, len(lines), len(new_lines)))
    print('  %-44s %d -> %d' % ('psycopg2.connect( in file',
                                before_connects, after_connects))
    print('  %-44s %d live, %d in comments'
          % ('dll_location_registry in file', live_refs,
             out.count('dll_location_registry') - live_refs))
    print('  %-44s %d, unchanged' % ('reachable reply() literals', len(after)))
    print('  %-44s %s' % ('line endings', 'CRLF preserved'))

    if not write:
        print('')
        print('dry run -- nothing written. Re-run with --write to apply.')
        return 0

    with io.open(TARGET, 'w', newline='') as handle:
        handle.write(out)
    print('')
    print('written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
