#!/usr/bin/env python3
"""
Run database migration 006 - Add client soft delete columns
"""

import psycopg2
from config import DB_LINK

def run_migration():
    """Execute the migration SQL file"""
    conn = None
    try:
        # Connect to database
        print(f"Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()
        
        # Read migration file
        print("Reading migration file...")
        with open('database/migrations/006_add_client_soft_delete.sql', 'r') as f:
            sql_script = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()
        
        # Verify columns were added
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'dll_client_accounts'
            AND column_name IN ('is_deleted', 'deleted_at', 'deleted_by')
            ORDER BY column_name
        """)
        columns = cursor.fetchall()
        
        # Get total clients count
        cursor.execute("SELECT COUNT(*) FROM dll_client_accounts")
        total_clients = cursor.fetchone()[0]
        
        # Get active clients count (not deleted)
        cursor.execute("SELECT COUNT(*) FROM dll_client_accounts WHERE is_deleted = FALSE OR is_deleted IS NULL")
        active_clients = cursor.fetchone()[0]
        
        print("\n" + "="*70)
        print("✅ Migration completed successfully!")
        print("="*70)
        print(f"✅ Soft delete columns added to dll_client_accounts table")
        print(f"\n📊 New columns:")
        for col in columns:
            print(f"   - {col[0]} ({col[1]}) - Nullable: {col[2]}, Default: {col[3]}")
        
        print(f"\n📈 Client statistics:")
        print(f"   - Total clients: {total_clients}")
        print(f"   - Active clients: {active_clients}")
        print(f"   - Trashed clients: 0")
        
        print("\n🎉 You can now use the following endpoints:")
        print(f"   - PATCH /clients/{{client_uid}}/trash")
        print(f"   - PATCH /clients/{{client_uid}}/restore")
        print(f"   - GET /clients/trashed")
        print(f"   - PATCH /clients/{{client_uid}}/update")
        print("="*70)
        
        cursor.close()
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        if conn:
            conn.rollback()
        raise
    except FileNotFoundError as e:
        print(f"\n❌ Migration file not found: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
            print("\nDatabase connection closed.")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 Starting Migration 006: Add Client Soft Delete")
    print("="*70 + "\n")
    run_migration()
