"""
tests/test_permission_catalog.py — Smoke tests for the seeded permission
catalog (migration 013).

These tests assume the migration runner has already applied 013 against
the database pointed at by DATABASE_URL. Each test is small, fast, and
read-only — safe to run in CI.

Run:
    pytest tests/test_permission_catalog.py
"""

from __future__ import annotations

import os

import psycopg2
import pytest


GLOBAL_ACCOUNT_ROOT = "engine"
EXPECTED_MIN_PERMISSIONS = 500  # the catalog has 531; allow slack for future trims
EXPECTED_MIN_MODULES = 40       # the catalog has 47 modules


@pytest.fixture(scope="module")
def db_connection():
    db_link = os.environ.get("DATABASE_URL")
    if not db_link:
        pytest.skip("DATABASE_URL not set; skipping integration smoke test.")
    conn = psycopg2.connect(db_link)
    try:
        yield conn
    finally:
        conn.close()


def _count_catalog(conn, where_clause: str = "") -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM dll_permissions "
            "WHERE account_root = %s "
            "AND (is_deleted = FALSE OR is_deleted IS NULL) "
            + where_clause,
            (GLOBAL_ACCOUNT_ROOT,),
        )
        return cursor.fetchone()[0]


def test_catalog_has_been_seeded(db_connection):
    """The catalog migration created at least the bulk of the permissions."""
    count = _count_catalog(
        db_connection,
        "AND permission_name LIKE 'can\\_%' ESCAPE '\\'",
    )
    assert count >= EXPECTED_MIN_PERMISSIONS, (
        f"Expected at least {EXPECTED_MIN_PERMISSIONS} catalog permissions, "
        f"found {count}. Did migration 013 run?"
    )


def test_catalog_spans_multiple_modules(db_connection):
    """Permissions are tagged with their module of origin."""
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(DISTINCT permission_module) FROM dll_permissions "
            "WHERE account_root = %s AND permission_name LIKE 'can\\_%' ESCAPE '\\' "
            "AND (is_deleted = FALSE OR is_deleted IS NULL)",
            (GLOBAL_ACCOUNT_ROOT,),
        )
        modules = cursor.fetchone()[0]
    assert modules >= EXPECTED_MIN_MODULES, (
        f"Expected at least {EXPECTED_MIN_MODULES} modules, found {modules}."
    )


def test_known_permission_present(db_connection):
    """A representative permission from the catalog is present."""
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT permission_module FROM dll_permissions "
            "WHERE permission_name = %s AND account_root = %s",
            ("can_view_unit", GLOBAL_ACCOUNT_ROOT),
        )
        row = cursor.fetchone()
    assert row is not None, "can_view_unit should be seeded"
    assert row[0], "can_view_unit should have a permission_module tagged"


def test_catalog_rows_have_consistent_metadata(db_connection):
    """Every catalog row has the expected sentinel description + created_by."""
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM dll_permissions "
            "WHERE account_root = %s "
            "AND permission_name LIKE 'can\\_%' ESCAPE '\\' "
            "AND (permission_description IS NULL OR created_by IS NULL)",
            (GLOBAL_ACCOUNT_ROOT,),
        )
        bad = cursor.fetchone()[0]
    assert bad == 0, f"{bad} catalog rows have missing metadata"
