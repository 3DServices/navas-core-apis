"""
scripts/regen_permission_catalog.py — Regenerate the SQL seed migration
from the frontend's permission catalog.

Reads `src/auth/permissionCatalog.ts` from the sibling frontend repo
(path configurable via FRONTEND_DIR env var), parses the PERMISSION_CATALOG
object, and rewrites `database/migrations/013_perm_catalog_seed.sql` with
fresh INSERT statements. Idempotent and safe to run whenever the catalog
changes.

Usage:
    FRONTEND_DIR=../3d-cms-stable-v1 python scripts/regen_permission_catalog.py
    python scripts/regen_permission_catalog.py        # if frontend is sibling
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
SEED_FILE = PROJECT_ROOT / "database" / "migrations" / "013_perm_catalog_seed.sql"
DEFAULT_FRONTEND = PROJECT_ROOT.parent / "3d-cms-stable-v1"

GLOBAL_ACCOUNT_ROOT = "engine"
SEED_DESCRIPTION = "NAVAS catalog permission"
CREATED_BY = "system"


def parse_catalog(catalog_path: Path) -> dict[str, list[str]]:
    """
    Parse src/auth/permissionCatalog.ts and return { module_name: [perm, ...] }.

    The frontend file shape is:
        export const PERMISSION_CATALOG = {
          "Module Name": [ "can_view_x", "can_create_x", ... ],
          ...
        } as const satisfies Record<string, readonly string[]>;
    """
    src = catalog_path.read_text(encoding="utf-8")
    match = re.search(
        r"export const PERMISSION_CATALOG = \{(.*?)\n\} as const",
        src,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"Could not find PERMISSION_CATALOG block in {catalog_path}"
        )
    body = match.group(1)

    modules: dict[str, list[str]] = {}
    entry_pattern = re.compile(r'"([^"]+)"\s*:\s*\[(.*?)\]\s*,?', re.DOTALL)
    for module_name, list_body in entry_pattern.findall(body):
        perms = re.findall(r'"([^"]+)"', list_body)
        if perms:
            modules[module_name] = perms
    return modules


def dedupe_modules(modules: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Some catalog permissions appear in more than one module (e.g.
    can_configure_mfa). Pick the first-seen module so each permission has
    exactly one row in the seed.
    """
    seen: dict[str, str] = {}
    for mod, perms in modules.items():
        for p in perms:
            seen.setdefault(p, mod)
    bucket: dict[str, list[str]] = {}
    for perm, mod in seen.items():
        bucket.setdefault(mod, []).append(perm)
    return bucket


def build_sql(modules: dict[str, list[str]]) -> str:
    total = sum(len(v) for v in modules.values())
    lines: list[str] = []
    lines.append("-- " + "=" * 60)
    lines.append("-- 013_perm_catalog_seed.sql")
    lines.append("-- " + "=" * 60)
    lines.append("-- Seeds the NAVAS catalog permissions into dll_permissions")
    lines.append(f"-- under account_root='{GLOBAL_ACCOUNT_ROOT}'.")
    lines.append("--")
    lines.append("-- Source of truth: <frontend>/src/auth/permissionCatalog.ts")
    lines.append("-- Regenerate with: scripts/regen_permission_catalog.py")
    lines.append("--")
    lines.append("-- Idempotent: ON CONFLICT (permission_uid) DO NOTHING.")
    lines.append(f"-- Total: {total} permissions across {len(modules)} modules.")
    lines.append("-- " + "=" * 60)
    lines.append("")

    for module_name in sorted(modules.keys()):
        perms = sorted(modules[module_name])
        lines.append(f"-- Module: {module_name} ({len(perms)} permissions)")
        lines.append(
            "INSERT INTO dll_permissions "
            "(permission_uid, permission_name, permission_description, "
            "permission_module, account_root, created_by)"
        )
        lines.append("VALUES")
        rows: list[str] = []
        safe_module = module_name.replace("'", "''")
        for perm in perms:
            uid = f"perm_{perm}"
            rows.append(
                f"    ('{uid}', '{perm}', '{SEED_DESCRIPTION}', "
                f"'{safe_module}', '{GLOBAL_ACCOUNT_ROOT}', '{CREATED_BY}')"
            )
        lines.append(",\n".join(rows))
        lines.append("ON CONFLICT (permission_uid) DO NOTHING;")
        lines.append("")

    lines.append("-- " + "=" * 60)
    lines.append("-- Verify seed (expected count is in the header above).")
    lines.append("-- " + "=" * 60)
    lines.append(
        f"-- SELECT COUNT(*) FROM dll_permissions "
        f"WHERE account_root = '{GLOBAL_ACCOUNT_ROOT}' "
        f"AND permission_name LIKE 'can\\_%' ESCAPE '\\';"
    )
    lines.append(f"-- Expected: {total}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    frontend = Path(os.environ.get("FRONTEND_DIR", DEFAULT_FRONTEND)).resolve()
    catalog = frontend / "src" / "auth" / "permissionCatalog.ts"
    if not catalog.is_file():
        print(f"Catalog not found: {catalog}", file=sys.stderr)
        print("Pass FRONTEND_DIR=... to point at the frontend repo.", file=sys.stderr)
        return 1

    modules = parse_catalog(catalog)
    deduped = dedupe_modules(modules)
    sql = build_sql(deduped)
    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(sql, encoding="utf-8")

    total_perms = sum(len(v) for v in deduped.values())
    print(f"Wrote {SEED_FILE}")
    print(f"  {total_perms} permissions across {len(deduped)} modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
