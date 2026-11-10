#!/usr/bin/env python3
"""
patch_5g_503_convention.py -- 500 -> 503 when the store is unreachable.

A convention sweep, not a bug fix. Every route touched here already stops
correctly on a None Cassandra session; they just say the wrong thing about it.

500 tells a client NOT to retry. An unreachable Cassandra is almost always
transient -- a cold handshake, a brief outage, a dropped packet -- and a retry
works. B10 established 503 for exactly this in trips_history, with a host
audit behind it (10/10 sequential connects succeeded), and 5f adopted it for
the twelve routes that were crashing. This brings the remaining 21 into line.

Audited first: 21 sites across 4 files, two different messages and two
different reply helpers.

  devices.py          9    reply(...500, 'Failed to connect to Cassandra')
  statistics.py       6    response_out(..., 'Failed to connect...', 500, {})
  device_configs.py   4    reply(...500, 'Failed to connect to Cassandra')
  management.py       2    reply(...500, 'Cassandra connection failed')

Note the two helpers take their arguments in a DIFFERENT ORDER:
    reply(status, status_code, message, data)
    response_out(status, message, status_code, data)
A sweep that assumed one shape would have written the code into the message
field of six routes. Each is rewritten by AST position, not by text.

DELIBERATELY NOT DONE: adding a log line at each site. The 5f routes log
because they were being written from scratch; these already exist and work.
Keeping this diff to "the status code and the message, nothing else" makes it
reviewable at a glance. The missing log lines are a real gap and belong in
their own change.

All four files are CRLF; endings are preserved. Dry run unless --write.
"""

import ast
import io
import sys
from collections import Counter

CONSTANT = 'STORE_UNAVAILABLE'
FILES = ['endpoints/devices.py', 'endpoints/statistics.py',
         'endpoints/device_configs.py', 'endpoints/management.py']


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


def sites(tree):
    """Every (call, code_node, msg_node) answering 500 about Cassandra."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, 'id', None)
        if name not in ('reply', 'response_out') or len(node.args) < 4:
            continue
        # the two helpers order their arguments DIFFERENTLY
        code = node.args[1] if name == 'reply' else node.args[2]
        msg = node.args[2] if name == 'reply' else node.args[1]
        if not (isinstance(code, ast.Constant) and code.value == 500):
            continue
        if not (isinstance(msg, ast.Constant)
                and 'cassandra' in str(msg.value).lower()):
            continue
        out.append((node, name, code, msg))
    return out


def main():
    write = '--write' in sys.argv
    results = {}
    tally = Counter()

    for path in FILES:
        src, nl = read(path)
        flat = src.replace('\r\n', '\n')
        tree = ast.parse(flat)
        found = sites(tree)
        if not found:
            fail('%s: no 500-about-Cassandra sites found -- already patched?'
                 % path)

        lines = src.splitlines(keepends=True)
        edits = []
        for call, helper, code, msg in found:
            if code.lineno != msg.lineno:
                fail('%s line %d: code and message are on different lines'
                     % (path, call.lineno))
            line = lines[code.lineno - 1]
            # rewrite by column offset, right to left so offsets stay valid
            spans = sorted([(code.col_offset, code.end_col_offset, '503'),
                            (msg.col_offset, msg.end_col_offset, CONSTANT)],
                           key=lambda s: -s[0])
            for start, end, text in spans:
                line = line[:start] + text + line[end:]
            edits.append((code.lineno, line))
            tally[path] += 1

        out = list(lines)
        for lineno, line in edits:
            out[lineno - 1] = line
        text = ''.join(out)

        # the constant has to be importable here
        if CONSTANT not in flat:
            tree2 = ast.parse(text.replace('\r\n', '\n'))
            first = min(n.lineno for n in tree2.body
                        if isinstance(n, (ast.Import, ast.ImportFrom)))
            out = text.splitlines(keepends=True)
            out.insert(first - 1,
                       'from .globals import %s%s' % (CONSTANT, nl))
            text = ''.join(out)

        results[path] = (text, nl)

    # ---- verification
    for path, (text, nl) in results.items():
        flat = text.replace('\r\n', '\n')
        compile(flat, path, 'exec')
        tree = ast.parse(flat)

        left = sites(tree)
        if left:
            fail('%s still has %d site(s) answering 500 about Cassandra'
                 % (path, len(left)))

        # every rewritten call must now be 503 AND use the constant, with the
        # argument order each helper actually wants
        good = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, 'id', None)
            if name not in ('reply', 'response_out') or len(node.args) < 4:
                continue
            code = node.args[1] if name == 'reply' else node.args[2]
            msg = node.args[2] if name == 'reply' else node.args[1]
            if isinstance(code, ast.Constant) and code.value == 503 \
                    and isinstance(msg, ast.Name) and msg.id == CONSTANT:
                good += 1
        if good < tally[path]:
            fail('%s: expected >= %d correct 503 sites, found %d'
                 % (path, tally[path], good))

        if not any(isinstance(n, ast.ImportFrom)
                   and any(a.name == CONSTANT for a in n.names)
                   for n in ast.walk(tree)):
            fail('%s does not import %s' % (path, CONSTANT))

        if nl == '\r\n' and text.count('\r\n') != text.count('\n'):
            fail('%s: line endings are no longer uniformly CRLF' % path)

    print('%-28s %s' % ('file', 'sites converted 500 -> 503'))
    for path in FILES:
        print('%-28s %d' % (path.split('/')[-1], tally[path]))
    print('%-28s %d total' % ('', sum(tally.values())))
    print('')
    print('  %-44s %s' % ('message', '%s (one constant)' % CONSTANT))
    print('  %-44s %s' % ('argument order', 'per helper, by AST position'))
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


if __name__ == '__main__':
    sys.exit(main())
