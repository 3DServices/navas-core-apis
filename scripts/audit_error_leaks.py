#!/usr/bin/env python3
"""
audit_error_leaks.py — what do these routes tell a caller when they fail?

B10 started from one observation. A failed Postgres connect produced:

    HTTP 500  'connection to server at "165.232.128.208", port 5432 failed:
               server closed the connection unexpectedly'

That hands the database server's address and port to any caller, and says
nothing a customer can act on. But the IP is the smaller question. The one
worth auditing is:

    CAN THE PASSWORD GET INTO AN ERROR MESSAGE?

The DSN is a URL containing the credentials. psycopg2 raises OperationalError
with text the server or libpq produced, and for some failure shapes libpq
echoes connection parameters back. If any of those reaches str(error) and
that string is returned to the caller, this stops being an information leak
and becomes a credential leak — and the same two passwords are already
recoverable from origin/main, so the last thing we need is a second route to
them.

Section 3 tests that directly against a fake DSN with a known fake password.
No real connection, no real credential.

Also reported:

  1. every handler that returns exception text to the caller, and from which
     function — the blast radius of the pattern, not just the one route
  2. whether reply() sanitises anything before serialising
  4. which status codes those handlers use, because 500 and 503 say different
     things to a client that may retry

Read-only.

Usage:
    python scripts/audit_error_leaks.py
"""

import argparse
import ast
import io
import os
import re
import sys

sys.path.insert(0, '.')

FAKE_DSN = ('postgresql://navas_probe_user:NOT_A_REAL_PASSWORD_9f3a@'
            'host.invalid.example:5432/navas_probe_db')
FAKE_PROBE_VALUE = 'NOT_A_REAL_PASSWORD_9f3a'


def py_files():
    out = []
    for name in sorted(os.listdir('endpoints')):
        if name.endswith('.py'):
            out.append(os.path.join('endpoints', name))
    return out


def main():
    argparse.ArgumentParser().parse_args()

    print('=' * 72)
    print('1. HANDLERS THAT RETURN EXCEPTION TEXT TO THE CALLER')
    print('=' * 72)
    found = []
    for path in py_files():
        try:
            text = io.open(path, encoding='utf-8', errors='ignore').read()
            tree = ast.parse(text)
        except (SyntaxError, OSError):
            continue
        lines = text.splitlines()
        defs = [(n.lineno, n.name) for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)]
        for i, line in enumerate(lines, 1):
            m = re.search(r"reply\(\s*'error'\s*,\s*(\d+)\s*,\s*"
                          r"(str\(\s*error\s*\)|error)\s*,", line)
            if m:
                owner = ([d for d in defs if d[0] < i] or [(0, '?')])[-1][1]
                found.append((path, i, owner, m.group(1), m.group(2)))
    print(f'   {len(found)} handler(s) return the exception to the caller\n')
    by_code = {}
    for path, line, owner, code, form in found:
        by_code.setdefault(code, []).append((path, line, owner, form))
    for code in sorted(by_code):
        print(f'   HTTP {code}: {len(by_code[code])}')
        for path, line, owner, form in by_code[code][:12]:
            print(f'      {path}:{line}  {owner}()  -> {form}')
        if len(by_code[code]) > 12:
            print(f'      ... and {len(by_code[code]) - 12} more')

    print('\n' + '=' * 72)
    print('2. DOES reply() SANITISE ANYTHING?')
    print('=' * 72)
    g = io.open(os.path.join('endpoints', 'globals.py'),
                encoding='utf-8', errors='ignore').read()
    m = re.search(r'def reply\(.*?\n(?:.*\n){0,24}', g)
    if m:
        for line in m.group(0).splitlines():
            print(f'   {line}')
    print('\n   -> whatever is handed to it is what the caller receives.')

    print('\n' + '=' * 72)
    print('3. CAN THE PASSWORD REACH AN ERROR MESSAGE?')
    print('=' * 72)
    print(f'   probing with a FAKE dsn and fake secret {FAKE_PROBE_VALUE!r}')
    print('   (unresolvable host, so nothing is contacted)\n')
    import psycopg2
    leaked = False
    for label, dsn in (('well-formed, host does not resolve', FAKE_DSN),
                       ('malformed dsn', FAKE_DSN.replace('://', ':/')),
                       ('bad port', FAKE_DSN.replace(':5432', ':notaport'))):
        try:
            psycopg2.connect(dsn, connect_timeout=2)
            print(f'   {label}: unexpectedly connected?!')
            continue
        except Exception as error:                      # noqa: BLE001
            message = str(error)
        hit = FAKE_PROBE_VALUE in message
        leaked = leaked or hit
        print(f'   {label}:')
        print(f'      password in str(error)? '
              f'{"YES — CREDENTIAL LEAK" if hit else "no"}')
        print(f'      message: {message.strip().splitlines()[0][:96]}')
        host_hit = 'host.invalid.example' in message
        print(f'      host in message? {"yes" if host_hit else "no"}')
    print()
    if leaked:
        print('   -> THE PASSWORD CAN REACH THE CALLER. This is no longer an')
        print('      information leak, it is a credential leak, and every')
        print('      handler in section 1 is a route to it.')
    else:
        print('   -> the password does not appear in these messages. The host')
        print('      and port do, which is still more than a caller needs,')
        print('      but it is not a credential leak.')

    print('\n' + '=' * 72)
    print('4. WHY THE STATUS CODE MATTERS')
    print('=' * 72)
    print('   500 tells a client the request itself is broken: do not retry.')
    print('   503 says a dependency is unreachable: retrying may well work.')
    print('   Ten sequential connects succeeded in the host audit, so a')
    print('   failed connect is exactly the case where a retry helps — and')
    print('   it is currently reported as 500.')

    print('\n' + '=' * 72)
    print('WHAT B10 SHOULD DO')
    print('=' * 72)
    print('   Wrap the connect in trips_history, log the real error, and')
    print('   return 503 with a message a customer can act on. Then decide')
    print('   from section 1 whether the same pattern elsewhere is one')
    print('   ticket or many — and if section 3 found a credential leak,')
    print('   that decision is not optional.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
