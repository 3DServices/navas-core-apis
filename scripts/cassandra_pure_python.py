#!/usr/bin/env python3
"""
cassandra_pure_python.py — run the Cassandra driver without its compiled binaries.

The symptom:

    ImportError: DLL load failed while importing protocol:
    An Application Control policy has blocked this file.

Windows Application Control is refusing to load the driver's compiled
extensions. cassandra-driver 3.30.0 ships 19 .pyd files in site-packages, and
`endpoints/__init__.py` imports `.devices` at module scope, which imports
`cassandra.cluster` — so this does not merely break a script. The Flask app
cannot import at all. The API is down until this is resolved.

The fix is not to argue with the policy. Nine of those .pyd files SHADOW pure
Python modules that ship in the same wheel:

    cluster.py  concurrent.py  connection.py  cqltypes.py  metadata.py
    pool.py     protocol.py    query.py       util.py

The other ten are optional accelerators (bytesio, cmurmur3, cython_marshal,
cython_utils, deserializers, ioutils, numpy_parser, obj_parser, parsing,
row_parser) which the driver imports defensively and does without.

Move all nineteen aside and Python loads the .py versions instead. That is
exactly the install you get from a CASS_DRIVER_NO_EXTENSIONS=1 build, which is
a supported configuration — so this is not a workaround, it is the pure-Python
mode the driver ships for cases like this one. Nothing blocked is loaded, so
the policy is satisfied rather than circumvented.

The cost is speed: deserialising large result sets is slower in Python. For
Waswa's queries, which read a day of fixes or a handful of trips, that is
immaterial. For bulk telemetry reads it is worth measuring.

Fully reversible: --restore puts everything back.

Usage:
    python scripts/cassandra_pure_python.py            # show what would change
    python scripts/cassandra_pure_python.py --apply
    python scripts/cassandra_pure_python.py --restore
"""

import argparse
import glob
import os
import shutil
import sys

STASH = '_blocked_pyd'

# The ones with a .py twin. Losing these to the policy is what broke the import;
# moving them aside is what fixes it.
SHADOWING = ('cluster', 'concurrent', 'connection', 'cqltypes', 'metadata',
             'pool', 'protocol', 'query', 'util')


def find_package(explicit):
    if explicit:
        return explicit
    # The venv as it sits in this repo, then the usual POSIX shapes.
    for pattern in ('.venv/Lib/site-packages/cassandra',
                    '.venv/lib/site-packages/cassandra',
                    '.venv/lib/python*/site-packages/cassandra',
                    'venv/Lib/site-packages/cassandra'):
        for hit in glob.glob(pattern):
            if os.path.isdir(hit):
                return hit
    # Failing that, ask the interpreter that is running us.
    try:
        import cassandra
        return os.path.dirname(cassandra.__file__)
    except Exception:       # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', help='the cassandra package directory')
    ap.add_argument('--apply', action='store_true', help='move the .pyd files aside')
    ap.add_argument('--restore', action='store_true', help='put them back')
    args = ap.parse_args()

    pkg = find_package(args.path)
    if not pkg or not os.path.isdir(pkg):
        print('Could not find the cassandra package. Pass --path.')
        return 1
    print(f'package : {pkg}')
    stash = os.path.join(pkg, STASH)

    if args.restore:
        if not os.path.isdir(stash):
            print('Nothing stashed — already using the compiled extensions.')
            return 0
        moved = 0
        for name in sorted(os.listdir(stash)):
            shutil.move(os.path.join(stash, name), os.path.join(pkg, name))
            moved += 1
        try:
            os.rmdir(stash)
        except OSError:
            pass
        print(f'restored {moved} compiled extension(s).')
        print('If the policy still blocks them, the import will fail again.')
        return 0

    pyds = sorted(glob.glob(os.path.join(pkg, '*.pyd')) +
                  glob.glob(os.path.join(pkg, '*.so')))
    if not pyds:
        if os.path.isdir(stash):
            print('Already pure Python — the extensions are in '
                  f'{STASH}/. Use --restore to undo.')
        else:
            print('No compiled extensions here; this install is already pure '
                  'Python, so the blocked file is somewhere else.')
        return 0

    print(f'\n{len(pyds)} compiled extension(s) found:')
    for path in pyds:
        base = os.path.basename(path).split('.cp')[0].split('.cpython')[0]
        twin = os.path.join(pkg, base + '.py')
        mark = 'shadows ' + base + '.py' if os.path.exists(twin) else 'optional accelerator'
        flag = '*' if base in SHADOWING else ' '
        print(f'  {flag} {os.path.basename(path):<42} {mark}')

    missing = [b for b in SHADOWING
               if not os.path.exists(os.path.join(pkg, b + '.py'))]
    if missing:
        print(f'\n!! These have no .py twin: {missing}')
        print('   Moving their .pyd aside would break the driver outright.')
        print('   Reinstall instead:')
        print('     pip uninstall -y cassandra-driver')
        print('     set CASS_DRIVER_NO_EXTENSIONS=1')
        print('     pip install --no-binary :all: --no-cache-dir cassandra-driver')
        return 1

    if not args.apply:
        print(f'\nDry run. Add --apply to move them into {STASH}/.')
        return 0

    os.makedirs(stash, exist_ok=True)
    for path in pyds:
        shutil.move(path, os.path.join(stash, os.path.basename(path)))
    print(f'\nmoved {len(pyds)} file(s) into {STASH}/')
    print('The driver is now pure Python. Restart Flask and try again.')
    print('Undo at any time with --restore.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
