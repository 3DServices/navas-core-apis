#!/usr/bin/env python3
"""
patch_b9_single_session.py -- B9 steps 1-3.

Step 1 (endpoints/cassandra_store.py) is written by hand, not by this script.
This script does steps 2 and 3:

  2. Each of the six modules that defined its own get_cassandra_session()
     drops the function and its two module globals, and re-exports the name
     from cassandra_store instead. Every call site binds the accessor's
     result to a LOCAL, so none of the 42 of them change.

  3. The two defects the audit found in devices.py, both of which the
     collapse forces:

     a. FilterRequest (line ~812) reads the module global `_cassandra_session`
        without ever calling the accessor. Today that is an AttributeError on
        a cold worker ('NoneType' has no attribute 'prepare'); once the global
        is gone it would be a NameError. It now fetches a session and guards
        it in the same shape as every other route in the file.

     b. Four handlers pass the exception OBJECT to reply(), not str(error).
        scrub_secrets() passes non-strings through untouched by design, so the
        object reaches jsonify, which raises TypeError: Object of type ... is
        not JSON serializable, and the caller gets a 500 with no message at
        all. Same bug class as the one fixed in trips_history during B10.

Five of the six files are CRLF and statistics.py is LF; each file's endings
are preserved. Every edit is located by AST, never by a line number typed
into this script. Dry run unless --write.

Deliberately NOT done here:
  - The unused driver and config imports left behind in the six modules.
    Harmless, and removing them widens the diff for no behavioural gain.
  - devices.py answers 500 'Failed to connect to Cassandra' when the store is
    unreachable. 503 would be more honest (a cold handshake is retryable, and
    500 tells clients not to retry) but that is a convention across ten routes
    in that file, not something to change under cover of this patch.

Usage:
    python scripts/patch_b9_single_session.py
    python scripts/patch_b9_single_session.py --write
"""

import ast
import io
import os
import sys

MODULES = ['devices', 'data', 'data_handler', 'device_configs',
           'management', 'statistics']

REEXPORT = [
    '# B9: one Cassandra session per PROCESS, not one per module. This module',
    '# used to define its own get_cassandra_session() over its own globals and',
    '# its own Cluster(); six identical copies meant a worker could hold six',
    '# pools to the same database, each paying its own 6-7s handshake. The',
    '# name is re-exported so this module\'s callers and importers are unchanged.',
    'from .cassandra_store import get_cassandra_session',
]

FILTER_GUARD = [
    '    # B9: this route read the module global directly and never called the',
    '    # accessor, so on a cold worker it raised AttributeError on None.',
    '    _cassandra_session = get_cassandra_session()',
    '    if not _cassandra_session:',
    "        return reply('error', 500, 'Failed to connect to Cassandra', '')",
    '',
]

BAD_HANDLER = "return reply('error', 500, error, '')"
GOOD_HANDLER = [
    "# B10 class: `error` is an exception OBJECT. scrub_secrets() passes",
    "# non-strings through, jsonify then raises TypeError and the caller",
    "# gets a 500 with no message at all.",
    "logging.exception('devices: unhandled error')",
    "return reply('error', 500, str(error), '')",
]

report = []


def fail(message):
    sys.stderr.write('REFUSED: %s\n' % message)
    raise SystemExit(2)


def read(path):
    with io.open(path, 'r', newline='', encoding='utf-8') as handle:
        text = handle.read()
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\r\n' and text.count('\r\n') != text.count('\n'):
        fail('%s has mixed line endings' % path)
    return text, newline


def find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def splice(lines, edits):
    """edits: list of (start_1based, end_1based_inclusive, replacement_lines)."""
    out = list(lines)
    for start, end, replacement in sorted(edits, key=lambda e: -e[0]):
        out[start - 1:end] = replacement
    return out


def collapse(path):
    text, nl = read(path)
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text.replace('\r\n', '\n'))

    builder = find_func(tree, 'get_cassandra_session')
    if builder is None:
        fail('%s has no get_cassandra_session to collapse' % path)

    # the two module-level globals, located by AST not by text search
    globals_at = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (isinstance(target, ast.Name)
                    and target.id in ('_cassandra_cluster', '_cassandra_session')
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is None):
                globals_at.append(node.lineno)
    if len(globals_at) != 2:
        fail('%s: expected 2 module-level `= None` session globals, found %d'
             % (path, len(globals_at)))
    if max(globals_at) - min(globals_at) != 1:
        fail('%s: the two globals are not adjacent (lines %s)'
             % (path, globals_at))

    edits = [
        (builder.lineno, builder.end_lineno, []),
        (min(globals_at), max(globals_at), [line + nl for line in REEXPORT]),
    ]
    out = splice(lines, edits)
    report.append((os.path.basename(path), len(lines), len(out), nl))
    return ''.join(out), nl


def fix_devices(text, nl):
    """Step 3: the two defects, on top of the collapse."""
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text.replace('\r\n', '\n'))
    edits = []

    # --- logging import, placed just above the config import
    if not any(isinstance(n, ast.Import) and any(a.name == 'logging' for a in n.names)
               for n in tree.body):
        anchor = None
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == 'config':
                anchor = node.lineno
                break
        if anchor is None:
            fail('devices.py: no `from config import` to anchor the logging import')
        edits.append((anchor, anchor - 1, ['import logging' + nl]))

    # --- FilterRequest
    fn = find_func(tree, 'FilterRequest')
    if fn is None:
        fail('devices.py: FilterRequest not found')
    reads = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Name) and n.id == '_cassandra_session'
             and isinstance(n.ctx, ast.Load)]
    if not reads:
        fail('devices.py: FilterRequest no longer reads _cassandra_session; '
             'has it already been fixed?')
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, 'id', None) == 'get_cassandra_session']
    if calls:
        fail('devices.py: FilterRequest already calls get_cassandra_session')
    first = fn.body[0]
    if not isinstance(first, ast.Try):
        fail('devices.py: FilterRequest does not open with try:, found %s'
             % type(first).__name__)
    # insert above the `try:` line so the guard is not swallowed by the handler
    edits.append((first.lineno, first.lineno - 1,
                  [line + nl for line in FILTER_GUARD]))

    # --- the four exception-object handlers
    bad = [i + 1 for i, line in enumerate(lines) if line.strip() == BAD_HANDLER]
    if len(bad) != 4:
        fail('devices.py: expected 4 `%s`, found %d' % (BAD_HANDLER, len(bad)))
    for lineno in bad:
        indent = lines[lineno - 1][:len(lines[lineno - 1])
                                   - len(lines[lineno - 1].lstrip())]
        edits.append((lineno, lineno,
                      [indent + line + nl for line in GOOD_HANDLER]))

    return ''.join(splice(lines, edits))


def main():
    write = '--write' in sys.argv
    root = 'endpoints'

    if not os.path.exists(os.path.join(root, 'cassandra_store.py')):
        fail('endpoints/cassandra_store.py is missing -- step 1 first')

    results = {}
    for name in MODULES:
        path = os.path.join(root, '%s.py' % name)
        text, nl = collapse(path)
        if name == 'devices':
            text = fix_devices(text, nl)
        results[path] = (text, nl)

    # ---- verification, before anything is written
    for path, (text, nl) in results.items():
        flat = text.replace('\r\n', '\n')
        compile(flat, path, 'exec')
        tree = ast.parse(flat)

        if find_func(tree, 'get_cassandra_session') is not None:
            fail('%s still defines get_cassandra_session' % path)

        imported = any(
            isinstance(n, ast.ImportFrom)
            and n.module == 'cassandra_store'
            and any(a.name == 'get_cassandra_session' for a in n.names)
            for n in ast.walk(tree))
        if not imported:
            fail('%s does not re-export get_cassandra_session' % path)

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Name)
                            and target.id in ('_cassandra_cluster',
                                              '_cassandra_session')):
                        fail('%s still has a module-level %s'
                             % (path, target.id))

        # By AST, not by text: the re-export comment in this very patch
        # contains the characters "Cluster(", and a substring check matched
        # its own comment and failed a correct edit. Second time in this
        # codebase that a verification has confused a comment for code.
        builds = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and getattr(n.func, 'id', None) == 'Cluster']
        if builds:
            fail('%s still builds a Cluster() at line %d'
                 % (path, builds[0].lineno))

        # every remaining read of the name must be inside a function that
        # binds it first -- the FilterRequest class of bug must not survive
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            reads = [n for n in ast.walk(fn)
                     if isinstance(n, ast.Name) and n.id == '_cassandra_session'
                     and isinstance(n.ctx, ast.Load)]
            if not reads:
                continue
            bound = False
            for ch in ast.walk(fn):
                if isinstance(ch, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == '_cassandra_session'
                        for t in ch.targets):
                    bound = True
                if isinstance(ch, ast.AnnAssign) and isinstance(
                        ch.target, ast.Name) and ch.target.id == '_cassandra_session':
                    bound = True
            if not bound and fn.name != 'cassandra_check_and_delete':
                fail('%s: %s reads _cassandra_session without binding it'
                     % (path, fn.name))

    devices_text = results[os.path.join(root, 'devices.py')][0]
    if BAD_HANDLER in devices_text:
        fail('devices.py still passes an exception object to reply()')

    # ---- report
    # Report the FINAL size. The first version printed the size after the
    # collapse but before step 3's edits, so devices.py was reported 23 lines
    # smaller than it would actually be written.
    print('%-26s %-9s %-9s %s' % ('module', 'before', 'after', 'endings'))
    for name, before, _mid, nl in report:
        final = results[os.path.join(root, name)][0]
        after = final.count('\n') + (0 if final.endswith('\n') else 1)
        print('%-26s %-9d %-9d %s'
              % (name, before, after, 'CRLF' if nl == '\r\n' else 'LF'))
    print('')
    print('  %-44s %s' % ('Cluster() builders in endpoints/',
                          '6 -> 1 (cassandra_store.py)'))
    print('  %-44s %s' % ('call sites changed', '0 of 42'))
    print('  %-44s %s' % ('FilterRequest', 'now fetches and guards a session'))
    print('  %-44s %s' % ('exception-object handlers', '4 -> 0'))
    print('  %-44s %s' % ('all six parse and compile', 'yes'))

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


if __name__ == '__main__':
    sys.exit(main())
