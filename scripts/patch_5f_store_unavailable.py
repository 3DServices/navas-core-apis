#!/usr/bin/env python3
"""
patch_5f_store_unavailable.py -- twelve routes crash when Cassandra is down.

Audited, not assumed. Twelve route handlers call get_cassandra_session() and
then use the session object directly (.prepare / .execute) in one of two
broken shapes:

  A. THE GUARD FALLS THROUGH (5 routes in data_handler.py) -- the original
     ticket 5f:

         _cassandra_session: Session = get_cassandra_session()
         if not _cassandra_session:
             print("Failed to get Cassandra session. Cannot process data.")
         # ... and then uses it anyway, fifty lines later

     It detects the problem, writes to stdout where nobody reads it, and
     proceeds to call .prepare() on None.

  B. NO GUARD AT ALL (7 routes) -- same crash, without the print.

Either way the caller receives a 500 carrying
"'NoneType' object has no attribute 'prepare'", which is useless and untrue:
the store is temporarily unreachable, which is a 503.

Twelve more routes were examined and deliberately left alone: they pass the
session to location_store / io_events_store / stops, which raise
PositionsUnavailable, and their routes already turn that into a 503. The
guard there is downstream, by design.

ON 500 vs 503 (ticket 5g, settled here)
The codebase was split: 8 places answered 503 ("temporarily unavailable,
please retry", the B3/B10 convention) and 12 answered 500 ("Failed to connect
to Cassandra", the devices.py convention). 503 is correct -- a cold handshake
or a brief outage is retryable, and 500 tells a client explicitly not to
retry. B10 established this with a host audit behind it (10/10 sequential
connects succeeded). These twelve routes adopt 503.

NOT done here: converting devices.py's OTHER, already-working 500s. Those
routes are not broken, and changing them belongs in its own reviewable
commit rather than riding along with a bug fix.

All three files are CRLF; endings are preserved. Every position is located by
AST, never by a line number typed into this script. Dry run unless --write.
"""

import ast
import io
import sys

CONSTANT = 'STORE_UNAVAILABLE'
MESSAGE = 'Device data is temporarily unavailable, please retry'

TARGETS = {
    'endpoints/data.py': ['trips_report_data', 'night_driving_report_data',
                          'state_report_data', 'overspeeding_report_data',
                          'geozone_report_data'],
    'endpoints/data_handler.py': ['TripsLoader', 'TripsLoader_ByExcel_File',
                                  'TripsLoader_ByPDF_File',
                                  'FuelLevelReport_ByFile',
                                  'FuelLevelReport_ByPDF',
                                  'NightDrivingReport_ByExcell'],
    'endpoints/devices.py': ['update_device'],
}

GLOBALS = 'endpoints/globals.py'

GLOBALS_ADDITION = '''

# The one message for "the data store could not be read". 503, not 500: a
# cold handshake or a brief outage is retryable, and 500 tells a client not to
# retry. Twelve routes used to answer 500 with an AttributeError's text
# instead, because they called .prepare() on a None session.
STORE_UNAVAILABLE = 'Device data is temporarily unavailable, please retry'
'''


def fail(message):
    sys.stderr.write('REFUSED: %s\n' % message)
    raise SystemExit(2)


def read(path):
    with io.open(path, 'r', newline='', encoding='utf-8') as handle:
        text = handle.read()
    nl = '\r\n' if '\r\n' in text else '\n'
    if nl == '\r\n' and text.count('\r\n') != text.count('\n'):
        fail('%s has mixed line endings' % path)
    return text, nl


def session_assign(fn):
    """The `x = get_cassandra_session()` node in this function, or None."""
    for node in ast.walk(fn):
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        if target and 'cassandra_session' in target and node.value is not None \
                and 'get_cassandra_session' in ast.unparse(node.value):
            return node, target
    return None, None


def existing_guard(fn, name, after_line):
    """An `if not <name>:` directly following the assignment, or None."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or node.lineno <= after_line:
            continue
        test = node.test
        inner = test.operand if isinstance(test, ast.UnaryOp) \
            and isinstance(test.op, ast.Not) else test
        if isinstance(inner, ast.Name) and inner.id == name \
                and node.lineno <= after_line + 2:
            return node
    return None


def main():
    write = '--write' in sys.argv
    results = {}
    report = []

    # ---- 1. the shared constant
    gsrc, gnl = read(GLOBALS)
    if CONSTANT in gsrc:
        fail('%s already defines %s -- already patched?' % (GLOBALS, CONSTANT))
    gtree = ast.parse(gsrc.replace('\r\n', '\n'))
    anchor = None
    for node in gtree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'reply':
            anchor = node.lineno
            break
    if anchor is None:
        fail('%s has no reply() to anchor the constant above' % GLOBALS)
    glines = gsrc.splitlines(keepends=True)
    addition = [l + gnl for l in GLOBALS_ADDITION.strip('\n').split('\n')] + [gnl]
    results[GLOBALS] = (''.join(glines[:anchor - 1] + addition
                                + glines[anchor - 1:]), gnl)

    # ---- 2. the twelve routes
    for path, names in TARGETS.items():
        src, nl = read(path)
        lines = src.splitlines(keepends=True)
        tree = ast.parse(src.replace('\r\n', '\n'))

        edits = []
        for name in names:
            fn = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    fn = node
                    break
            if fn is None:
                fail('%s: %s not found' % (path, name))

            assign, var = session_assign(fn)
            if assign is None:
                fail('%s: %s has no get_cassandra_session() assignment'
                     % (path, name))

            indent = ' ' * (len(lines[assign.lineno - 1])
                            - len(lines[assign.lineno - 1].lstrip()))
            guard = [
                indent + 'if not %s:' % var,
                indent + "    logging.warning('%s: Cassandra session "
                         "unavailable')" % name,
                indent + "    return reply('error', 503, %s, '')" % CONSTANT,
            ]
            block = [l + nl for l in guard]

            old = existing_guard(fn, var, assign.lineno)
            if old is not None:
                # group A: replace the guard that falls through
                edits.append((old.lineno, old.end_lineno, block))
                report.append((path, name, 'replaced a falling-through guard',
                               old.lineno))
            else:
                # group B: insert one after the assignment
                edits.append((assign.end_lineno + 1, assign.end_lineno, block))
                report.append((path, name, 'added a missing guard',
                               assign.end_lineno))

        out = list(lines)
        for start, end, block in sorted(edits, key=lambda e: -e[0]):
            out[start - 1:end] = block
        text = ''.join(out)

        # imports this file now needs
        text = ensure_imports(path, text, nl)
        results[path] = (text, nl)

    # ---- verification
    for path, (text, nl) in results.items():
        flat = text.replace('\r\n', '\n')
        compile(flat, path, 'exec')
        if text.count('\r\n') != text.count('\n') and nl == '\r\n':
            fail('%s: line endings are no longer uniformly CRLF' % path)

    for path, names in TARGETS.items():
        flat = results[path][0].replace('\r\n', '\n')
        tree = ast.parse(flat)
        for name in names:
            fn = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == name)
            assign, var = session_assign(fn)
            guard = existing_guard(fn, var, assign.lineno)
            if guard is None:
                fail('%s: %s has no guard after the patch' % (path, name))
            replies = [n for n in ast.walk(guard) if isinstance(n, ast.Call)
                       and getattr(n.func, 'id', None) == 'reply']
            if not replies:
                fail('%s: %s guard does not reply()' % (path, name))
            code = replies[0].args[1]
            if not (isinstance(code, ast.Constant) and code.value == 503):
                fail('%s: %s guard does not answer 503' % (path, name))
            msg = replies[0].args[2]
            if not (isinstance(msg, ast.Name) and msg.id == CONSTANT):
                fail('%s: %s guard does not use %s' % (path, name, CONSTANT))

    if 'print("Failed to get Cassandra session' in results[
            'endpoints/data_handler.py'][0]:
        fail('data_handler.py still has a print-and-continue guard')

    # ---- report
    print('%-26s %-30s %s' % ('file', 'route', 'change'))
    for path, name, what, line in report:
        print('%-26s %-30s %s (line %d)'
              % (path.split('/')[-1], name, what, line))
    print('')
    print('  %-44s %d' % ('routes now answering 503', len(report)))
    print('  %-44s %s' % ('shared constant', '%s in globals.py' % CONSTANT))
    print('  %-44s %s' % ('all files compile', 'yes'))
    print('  %-44s %s' % ('line endings', 'preserved'))

    if not write:
        print('')
        print('dry run -- nothing written. Re-run with --write to apply.')
        return 0

    for path, (text, nl) in results.items():
        with io.open(path, 'w', newline='', encoding='utf-8') as handle:
            handle.write(text)
    print('')
    print('written: %d files.' % len(results))
    return 0


def ensure_imports(path, text, nl):
    """Add `import logging` and the STORE_UNAVAILABLE import if missing."""
    flat = text.replace('\r\n', '\n')
    tree = ast.parse(flat)
    lines = text.splitlines(keepends=True)
    inserts = []

    has_logging = any(isinstance(n, ast.Import)
                      and any(a.name == 'logging' for a in n.names)
                      for n in tree.body)
    globals_import = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'globals' \
                or (isinstance(node, ast.ImportFrom) and node.level == 1
                    and node.module == 'globals'):
            globals_import = node
            if any(a.name == CONSTANT for a in node.names):
                globals_import = 'present'
            break

    first = min(n.lineno for n in tree.body
                if isinstance(n, (ast.Import, ast.ImportFrom)))
    if not has_logging:
        inserts.append((first, 'import logging' + nl))
    if globals_import != 'present':
        inserts.append((first, 'from .globals import %s%s' % (CONSTANT, nl)))

    out = list(lines)
    for at, line in sorted(inserts, key=lambda e: -e[0]):
        out.insert(at - 1, line)
    return ''.join(out)


if __name__ == '__main__':
    sys.exit(main())
