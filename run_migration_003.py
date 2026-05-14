#!/usr/bin/env python3
"""
Run database migration 003 - Create gateway monitoring table
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
        with open('database/migrations/003_create_gateway_monitoring_tables.sql', 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(migration_sql)
        
        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")
        
        # Verify table was created
        cursor.execute("""
            SELECT COUNT(*) FROM dll_gateway_status WHERE is_current_message = TRUE
        """)
        count = cursor.fetchone()[0]
        print(f"✅ Table dll_gateway_status created with {count} current gateways")
        
        # Show sample data
        cursor.execute("""
            SELECT telecom, api_status, message 
            FROM dll_gateway_status 
            WHERE is_current_message = TRUE
            ORDER BY telecom
        """)
        print("\n📊 Sample gateway data:")
        for row in cursor.fetchall():
            print(f"   - {row[0]}: {row[1]} | {row[2]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        raise

if __name__ == "__main__":
    run_migration()
