#!/usr/bin/env python3
"""Run database migration 035 - the Waswa knowledge corpus.

Checks after applying, because two things in this migration can fail quietly:

  * the generated tsvector column. If PostgreSQL accepted it but the expression
    is wrong, every search returns nothing and looks like an empty corpus.
    So we index a throwaway row and confirm a query matches it.
  * the GIN index. Without it searches still work, just slowly, which is the
    kind of thing nobody notices until the corpus is large.
"""

import psycopg2
from config import DB_LINK

PROBE_SOURCE = '__migration_035_probe__'


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/035_waswa_knowledge.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()
        print("Migration 035 applied.\n")

        # --- tables present -------------------------------------------------
        for table in ('dll_waswa_authority_levels', 'dll_waswa_sources',
                      'dll_waswa_chunks'):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = %s", (table,))
            print(f"   {'ok  ' if cursor.fetchone()[0] else 'FAIL'} table {table}")

        # --- the GIN index --------------------------------------------------
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            ('idx_waswa_chunk_fts',))
        row = cursor.fetchone()
        ok = bool(row) and 'gin' in row[0].lower()
        print(f"   {'ok  ' if ok else 'FAIL'} GIN index on search_vector")

        # --- the generated column actually indexes text ----------------------
        cursor.execute(
            "INSERT INTO dll_waswa_sources "
            "(source_uid, title, authority_level, file_hash, review_status) "
            "VALUES (%s, %s, 6, %s, 'rejected') "
            "ON CONFLICT (source_uid) DO NOTHING",
            (PROBE_SOURCE, 'migration probe', '0' * 64))
        cursor.execute(
            "INSERT INTO dll_waswa_chunks "
            "(chunk_uid, source_uid, ordinal, heading_path, body, char_count, "
            " content_hash, authority_level) "
            "VALUES (%s, %s, 1, %s, %s, %s, %s, 6) "
            "ON CONFLICT (chunk_uid) DO NOTHING",
            (PROBE_SOURCE, PROBE_SOURCE, 'Immobiliser policy',
             'A driver coaching report is generated weekly for each fleet.',
             58, '1' * 64))

        cursor.execute(
            "SELECT ts_rank(search_vector, plainto_tsquery('english', %s)) "
            "FROM dll_waswa_chunks WHERE chunk_uid = %s "
            "  AND search_vector @@ plainto_tsquery('english', %s)",
            ('driver coaching', PROBE_SOURCE, 'driver coaching'))
        hit = cursor.fetchone()
        print(f"   {'ok  ' if hit else 'FAIL'} full-text match on chunk body"
              f"{'' if hit else ' — the generated column is not indexing text'}")

        cursor.execute(
            "SELECT 1 FROM dll_waswa_chunks WHERE chunk_uid = %s "
            "  AND search_vector @@ plainto_tsquery('english', %s)",
            (PROBE_SOURCE, 'immobiliser'))
        heading_hit = cursor.fetchone()
        print(f"   {'ok  ' if heading_hit else 'FAIL'} full-text match on heading_path")

        # The probe must not survive. A corpus with a nonsense row in it is
        # worse than no corpus, because it is invisible.
        cursor.execute("DELETE FROM dll_waswa_sources WHERE source_uid = %s",
                       (PROBE_SOURCE,))
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM dll_waswa_chunks WHERE source_uid = %s",
                       (PROBE_SOURCE,))
        print(f"   {'ok  ' if cursor.fetchone()[0] == 0 else 'FAIL'} "
              f"probe removed (ON DELETE CASCADE works)")

        # --- what is waiting for a human -------------------------------------
        cursor.execute("SELECT authority_level, label FROM vw_waswa_authority_unconfirmed")
        pending = cursor.fetchall()
        if pending:
            print(f"\n   {len(pending)} authority level(s) seeded but NOT confirmed "
                  f"by the business:")
            for level, label in pending:
                print(f"      {level}  {label}")
            print("   Confirm with:  UPDATE dll_waswa_authority_levels "
                  "SET confirmed = TRUE WHERE authority_level = n;")

        cursor.execute("SELECT COUNT(*) FROM dll_waswa_sources")
        print(f"\n   Corpus: {cursor.fetchone()[0]} source document(s) ingested so far.")
        print("   Next:   python scripts/ingest_waswa_knowledge.py --dry-run")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 035 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
