#!/usr/bin/env python3
"""
waswa_prompt.py — manage Waswa's runtime system prompt.

Migration 030 made the prompt versioned data in dll_waswa_prompts rather than a
constant in assistant.py. This is the way to fill it. A prompt change becomes a
row with a history, not a deploy, and every answer records the prompt_version
that produced it — so when behaviour changes you can tell which change did it,
and rolling back is one command rather than a revert.

    python scripts/waswa_prompt.py --list
    python scripts/waswa_prompt.py --show
    python scripts/waswa_prompt.py --show 2
    python scripts/waswa_prompt.py --load database/prompts/waswa_runtime_v2.md \\
                                   --notes "Part B, scoped to built features"
    python scripts/waswa_prompt.py --activate 2
    python scripts/waswa_prompt.py --rollback

Loading and activating are separate on purpose: a loaded version changes
nothing until you activate it, so you can read it back in place first.
"""

import argparse
import os
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

KEY = 'runtime_system'

PROMPT_DIR = os.path.join('database', 'prompts')


def find_default():
    """The newest prompt file in database/prompts/.

    --load takes an optional path so the command stays short. The full form
    runs past seventy characters, and a terminal that wraps it splits the path
    onto its own line, where it becomes a command of its own and the load
    silently never happens.
    """
    if not os.path.isdir(PROMPT_DIR):
        return None
    names = sorted(n for n in os.listdir(PROMPT_DIR) if n.endswith('.md'))
    return os.path.join(PROMPT_DIR, names[-1]) if names else None


def versions(cur):
    cur.execute(
        "SELECT version, is_active, created_by, created_at, notes, "
        "       LENGTH(body) "
        "FROM dll_waswa_prompts WHERE prompt_key = %s ORDER BY version", (KEY,))
    return cur.fetchall() if cur.rowcount > 0 else []


def show_list(cur):
    rows = versions(cur)
    if not rows:
        print("No prompt versions. Run migration 030, which seeds v1.")
        return
    print(f"{'ver':>4}  {'active':<7} {'chars':>7}  {'created':<20} notes")
    for version, active, by, at, notes, size in rows:
        print(f"{version:>4}  {'ACTIVE' if active else '':<7} {size:>7}  "
              f"{str(at)[:19]:<20} {notes or ''}")
    print(f"\n{sum(1 for r in rows if r[1])} active "
          f"(the database allows only one).")


def show_body(cur, version=None):
    if version:
        cur.execute(
            "SELECT version, body FROM dll_waswa_prompts "
            "WHERE prompt_key = %s AND version = %s", (KEY, version))
    else:
        cur.execute(
            "SELECT version, body FROM dll_waswa_prompts "
            "WHERE prompt_key = %s AND is_active = TRUE", (KEY,))
    if not cur.rowcount:
        raise SystemExit("No such version." if version else "No active version.")
    found, body = cur.fetchone()
    print(f"--- runtime_system v{found} ---\n")
    print(body)


def load(cur, path, notes, activate, created_by):
    with open(path, encoding='utf-8') as handle:
        body = handle.read().strip()
    if not body:
        raise SystemExit(f"{path} is empty.")

    cur.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM dll_waswa_prompts "
        "WHERE prompt_key = %s", (KEY,))
    version = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO dll_waswa_prompts "
        "(prompt_key, version, body, notes, is_active, created_by) "
        "VALUES (%s, %s, %s, %s, FALSE, %s)",
        (KEY, version, body, notes, created_by))
    print(f"Loaded v{version} from {path} ({len(body)} chars), inactive.")

    if activate:
        set_active(cur, version)
    else:
        print(f"Not active. Activate it with:  "
              f"python scripts/waswa_prompt.py --activate {version}")
    return version


def set_active(cur, version):
    cur.execute(
        "SELECT 1 FROM dll_waswa_prompts WHERE prompt_key = %s AND version = %s",
        (KEY, version))
    if not cur.rowcount:
        raise SystemExit(f"No version {version} to activate.")

    cur.execute(
        "SELECT version FROM dll_waswa_prompts "
        "WHERE prompt_key = %s AND is_active = TRUE", (KEY,))
    previous = cur.fetchone()[0] if cur.rowcount else None

    # Both statements are in one transaction, so the unique partial index that
    # allows a single active version is never violated in between.
    cur.execute(
        "UPDATE dll_waswa_prompts SET is_active = FALSE WHERE prompt_key = %s",
        (KEY,))
    cur.execute(
        "UPDATE dll_waswa_prompts SET is_active = TRUE "
        "WHERE prompt_key = %s AND version = %s", (KEY, version))

    if previous == version:
        print(f"v{version} was already active.")
    else:
        print(f"Active prompt: v{previous} -> v{version}")
        print(f"Roll back with:  python scripts/waswa_prompt.py --activate "
              f"{previous}" if previous else "")
    print("Takes effect on the next request; no restart needed.")


def rollback(cur):
    rows = [r for r in versions(cur)]
    if len(rows) < 2:
        raise SystemExit("Nothing to roll back to.")
    active = next((r[0] for r in rows if r[1]), None)
    earlier = [r[0] for r in rows if r[0] != active and r[0] < (active or 0)]
    if not earlier:
        raise SystemExit("No earlier version to roll back to.")
    set_active(cur, max(earlier))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='list versions')
    parser.add_argument('--show', nargs='?', const=0, type=int,
                        metavar='VERSION',
                        help='print a version (default: the active one)')
    parser.add_argument('--load', nargs='?', const='', metavar='PATH',
                        help='load a markdown file as a new version. With no '
                             'path, the newest file in database/prompts/')
    parser.add_argument('--and-activate', action='store_true',
                        help='activate the version just loaded')
    parser.add_argument('--notes', default=None, help='note for --load')
    parser.add_argument('--activate', type=int, metavar='VERSION',
                        help='make this version active')
    parser.add_argument('--rollback', action='store_true',
                        help='activate the previous version')
    parser.add_argument('--by', default='waswa_prompt.py',
                        help='recorded as created_by')
    args = parser.parse_args()

    if not any([args.list, args.show is not None, args.load is not None,
                args.activate, args.rollback]):
        parser.print_help()
        return

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                if args.load is not None:
                    path = args.load or find_default()
                    if not path:
                        raise SystemExit(
                            f'No prompt file given and none found in '
                            f'{PROMPT_DIR}.')
                    if not args.load:
                        print(f"Using {path}")
                    load(cur, path, args.notes,
                         activate=args.and_activate, created_by=args.by)
                if args.activate:
                    set_active(cur, args.activate)
                if args.rollback:
                    rollback(cur)
                if args.show is not None:
                    show_body(cur, args.show or None)
                if args.list:
                    show_list(cur)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
