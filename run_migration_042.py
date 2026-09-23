#!/usr/bin/env python3
"""Run database migration 042 - documents managed from the AI Console.

Adds the columns that let a document be uploaded as a new version of another,
removed and restored, and records what was withheld from it. Then checks the
server can convert each file type the console accepts.
"""

import importlib

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/042_waswa_document_uploads.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 042 applied.\n")

        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'dll_waswa_sources' AND column_name IN "
                    "('replaces_source_uid','removed_at','redactions','stored_path')")
        found = {r[0] for r in cur.fetchall()}
        print(f"   {'ok   ' if len(found) == 4 else 'CHECK'} new document columns "
              f"present ({len(found)}/4)")

        cur.execute("SELECT COUNT(*) FROM vw_waswa_review_queue "
                    "WHERE item_kind = 'document'")
        print(f"   ok    documents waiting for review: {cur.fetchone()[0]}")

        print("\nFile types the console can accept on this server:")
        for label, module in (('PDF  (.pdf) ', 'pdfplumber'),
                              ('Excel (.xlsx)', 'openpyxl')):
            try:
                importlib.import_module(module)
                print(f"   ok    {label}")
            except ImportError:
                print(f"   CHECK {label} needs: pip install {module}")
        print("   ok    Word (.docx), Markdown (.md), text (.txt)")
        print("\nRestart the API to load the new endpoints.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 042 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
