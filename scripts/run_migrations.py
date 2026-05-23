"""
scripts/run_migrations.py — Idempotent SQL migration runner.

Reads .sql files from database/migrations/ in numerical order, tracks
applied versions in a `schema_migrations(version, filename, applied_at)`
table, and applies only new ones.

Usage:
    python scripts/run_migrations.py                       # apply pending
    python scripts/run_migrations.py --status              # show applied / pending
    python scripts/run_migrations.py --dry-run             # show plan, don't apply
    python scripts/run_migrations.py --mark-applied-up-to N
        # mark every migration with version <= N as already applied without
        # running it. Use this once to bootstrap an existing database where
        # migrations were applied manually before this runner existed.

Reads DATABASE_URL from the environment (same source config.py uses).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg2

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"

VERSION_PATTERN = re.compile(r"^(\d+)_.+\.sql$")


def get_db_link() -> str:
    link = os.environ.get("DATABASE_URL")
    if not link:
        sys.exit(
            "DATABASE_URL environment variable is not set. "
            "Set it the same way the running app does (see config.py)."
        )
    return link


def discover_migrations() -> list[tuple[int, Path]]:
    """Return migrations as a sorted list of (version_number, file_path)."""
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        match = VERSION_PATTERN.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort(key=lambda pair: pair[0])
    return found


def ensure_tracking_table(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                filename   VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def already_applied(conn) -> set[int]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}


def apply_one(conn, version: int, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql)
        cursor.execute(
            "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s) "
            "ON CONFLICT (version) DO NOTHING",
            (version, path.name),
        )
    conn.commit()


def mark_applied(conn, version: int, filename: str) -> None:
    """Record a migration as applied without executing it."""
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s) "
            "ON CONFLICT (version) DO NOTHING",
            (version, filename),
        )
    conn.commit()


def cmd_status(conn) -> int:
    applied = already_applied(conn)
    migrations = discover_migrations()
    print(f"{len(applied)} applied / {len(migrations)} total\n")
    for version, path in migrations:
        flag = "[x]" if version in applied else "[ ]"
        print(f"  {flag} {version:03d}  {path.name}")
    return 0


def cmd_run(conn, dry_run: bool) -> int:
    applied = already_applied(conn)
    pending = [m for m in discover_migrations() if m[0] not in applied]

    if not pending:
        print("Nothing to apply — database is up to date.")
        return 0

    print(f"{len(pending)} pending migration(s):")
    for version, path in pending:
        print(f"  - {version:03d}  {path.name}")
    if dry_run:
        print("\n(dry-run: no changes made)")
        return 0
    print()

    for version, path in pending:
        print(f"Applying {version:03d}  {path.name} ...", end=" ", flush=True)
        try:
            apply_one(conn, version, path)
            print("ok")
        except Exception as err:
            print(f"FAILED\n  {err}")
            return 1
    print("\nAll migrations applied successfully.")
    return 0


def cmd_mark_up_to(conn, target_version: int) -> int:
    """Mark every migration <= target_version as already applied."""
    applied = already_applied(conn)
    migrations = discover_migrations()
    to_mark = [m for m in migrations if m[0] <= target_version and m[0] not in applied]

    if not to_mark:
        print(f"No new migrations <= {target_version} to mark; nothing to do.")
        return 0

    print(f"Marking {len(to_mark)} migration(s) as already applied:")
    for version, path in to_mark:
        print(f"  - {version:03d}  {path.name}")
        mark_applied(conn, version, path.name)
    print(
        f"\nDone. Use `--status` to verify, then `run_migrations.py` to apply "
        f"anything after version {target_version}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument("--status", action="store_true",
                        help="Show applied / pending and exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run, but don't apply.")
    parser.add_argument("--mark-applied-up-to", type=int, metavar="N",
                        help="Bootstrap: mark every migration with version <= N "
                             "as already applied without running it.")
    args = parser.parse_args()

    if not MIGRATIONS_DIR.is_dir():
        sys.exit(f"Migrations directory not found: {MIGRATIONS_DIR}")

    conn = psycopg2.connect(get_db_link())
    try:
        ensure_tracking_table(conn)
        if args.status:
            return cmd_status(conn)
        if args.mark_applied_up_to is not None:
            return cmd_mark_up_to(conn, args.mark_applied_up_to)
        return cmd_run(conn, args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
