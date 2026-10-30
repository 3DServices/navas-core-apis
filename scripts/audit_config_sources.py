#!/usr/bin/env python3
"""
audit_config_sources.py — establish the facts B5 will be built on.

B5 proposes memoising the device-config lookups inside Config_Sources. That is
only safe if several things are true, and every one of them is a thing I would
otherwise be assuming:

  1. WHO CALLS IT. A module-level cache would leak across requests and across
     devices. If Config_Sources is called from more than one route, the cache
     must be request-scoped, not global.

  2. WHICH ARGUMENTS VARY. The claim is that the config lookup depends only on
     (config_parameter, device_imei) and not on the fix. If any branch's first
     query also uses target_io_records, the cache key is wrong.

  3. WHAT THE BRANCHES TEST. Config_Sources decides on len(rows) == 1 and falls
     back otherwise. A cache must reproduce the 0-row and 2-or-more-row paths,
     not just the happy one.

  4. WHETHER FAILURE IS DISTINGUISHABLE. cassandra_query returns [] both when
     a query legitimately found nothing and when it raised. Caching the second
     case would turn one transient failure into a whole-request fallback.

This reports all four from the source. It changes nothing.

Usage:
    python scripts/audit_config_sources.py
"""

import ast
import io
import sys

TARGET = 'endpoints/data.py'


def main():
    src = io.open(TARGET, encoding='utf-8', errors='ignore').read()
    tree = ast.parse(src)
    lines = src.splitlines()

    funcs = {n.name: n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}
    if 'Config_Sources' not in funcs:
        print('!! Config_Sources not found')
        return 1
    cs = funcs['Config_Sources']
    print(f'Config_Sources defined at line {cs.lineno}, '
          f'args: {[a.arg for a in cs.args.args]}\n')

    # ── 1. who calls it ────────────────────────────────────────────────────
    print('=' * 70)
    print('1. CALL SITES  (a module-level cache would leak between these)')
    print('=' * 70)
    enclosing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == 'Config_Sources'):
                    first = (inner.args[0].value
                             if inner.args and isinstance(inner.args[0],
                                                          ast.Constant)
                             else '<dynamic>')
                    enclosing.append((node.name, inner.lineno, first))
    by_func = {}
    for fn, ln, what in enclosing:
        by_func.setdefault(fn, []).append((ln, what))
    for fn in sorted(by_func):
        kinds = sorted({w for _l, w in by_func[fn]})
        print(f'   {fn}()  —  {len(by_func[fn])} call(s): {kinds}')
    print(f'\n   total call sites: {len(enclosing)} across '
          f'{len(by_func)} function(s)')
    if len(by_func) > 1:
        print('   -> MORE THAN ONE ROUTE. The cache MUST be request-scoped.')
    else:
        print('   -> one function only, but a module-level cache would still')
        print('      persist across requests and devices. Request-scoped.')

    # ── 2. what each branch's first query depends on ───────────────────────
    print('\n' + '=' * 70)
    print('2. THE CONFIG LOOKUP: does it depend on the fix, or only the device?')
    print('=' * 70)
    body = '\n'.join(lines[cs.lineno - 1:cs.lineno + 200])
    branches = []
    for node in ast.walk(cs):
        if (isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == 'GetThis'
                and node.comparators
                and isinstance(node.comparators[0], ast.Constant)):
            branches.append(node.comparators[0].value)
    print(f'   branches: {branches}')

    calls = [n for n in ast.walk(cs)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'cassandra_query']
    print(f'   cassandra_query calls: {len(calls)}\n')
    first_kind, second_kind = [], []
    for c in calls:
        q = c.args[0].value if isinstance(c.args[0], ast.Constant) else '?'
        params = c.args[1] if len(c.args) > 1 else None
        names = sorted({n.id for n in ast.walk(params) if isinstance(n, ast.Name)}) \
            if params is not None else []
        consts = [n.value for n in ast.walk(params)
                  if isinstance(n, ast.Constant)] if params is not None else []
        table = 'dll_device_local_configs' if 'dll_device_local_configs' in q \
            else ('dll_io_events_executed_logs'
                  if 'dll_io_events_executed_logs' in q else '?')
        row = (c.lineno, table, consts, names)
        (first_kind if table == 'dll_device_local_configs'
         else second_kind).append(row)

    print(f'   -- config lookups ({len(first_kind)}) --')
    fix_dependent = False
    for ln, table, consts, names in first_kind:
        depends = [n for n in names if 'io_record' in n or 'speed' in n]
        if depends:
            fix_dependent = True
        print(f'      line {ln}: params const={consts} names={names}')
    print(f'\n   depends on the FIX (target_io_records / speed)? '
          f'{"YES — cache key would be wrong" if fix_dependent else "NO"}')
    if not fix_dependent:
        print('   -> key on (GetThis, device_imei). Four distinct keys per')
        print('      request, whatever the page size.')

    print(f'\n   -- event-value lookups ({len(second_kind)}) --')
    for ln, table, consts, names in second_kind:
        print(f'      line {ln}: names={names}')
    print('   -> these DO vary per fix; stage 4 handles them, not stage 1.')

    # ── 3. the branch conditions a cache must reproduce ───────────────────
    print('\n' + '=' * 70)
    print('3. THE CONDITIONS ON THE LOOKUP RESULT')
    print('=' * 70)
    tests = set()
    for node in ast.walk(cs):
        if isinstance(node, ast.If):
            seg = ast.unparse(node.test)
            if 'rows' in seg:
                tests.add(seg)
    for t in sorted(tests):
        print(f'   if {t}')
    print('\n   -> a cache must return a value that reproduces each of these,')
    print('      so it has to store the ROW LIST, not a derived answer.')

    # ── 4. is a failed query distinguishable from an empty one? ───────────
    print('\n' + '=' * 70)
    print('4. CAN A FAILURE BE TOLD FROM AN EMPTY RESULT?')
    print('=' * 70)
    inner = next((n for n in ast.walk(cs) if isinstance(n, ast.FunctionDef)
                  and n.name == 'cassandra_query'), None)
    if inner is None:
        print('   !! cassandra_query helper not found')
    else:
        handlers = [h for h in ast.walk(inner) if isinstance(h, ast.ExceptHandler)]
        returns = [ast.unparse(r.value) for r in ast.walk(inner)
                   if isinstance(r, ast.Return) and r.value is not None]
        print(f'   except handlers: {len(handlers)}')
        print(f'   return values  : {returns}')
        empty_on_error = any(
            isinstance(r, ast.Return) and r.value is not None
            and ast.unparse(r.value) == '[]'
            for h in handlers for r in ast.walk(h))
        print(f'\n   returns [] on exception? '
              f'{"YES" if empty_on_error else "no"}')
        if empty_on_error:
            print('   -> "no rows" and "the query broke" are the SAME value.')
            print('      Caching that would turn one transient failure into a')
            print('      whole-request fallback. cassandra_query must report')
            print('      which happened before anything is cached.')

    print('\n' + '=' * 70)
    print('CONCLUSION')
    print('=' * 70)
    print('   Stage 1 is safe only with: a request-scoped cache, keyed on')
    print('   (GetThis, device_imei), storing the row LIST, and populated')
    print('   only when the query actually ran.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
