#!/usr/bin/env python3
"""
Run database migration 004 - Create VEBA statistics table
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
        with open('database/migrations/004_create_veba_statistics_tables.sql', 'r') as f:
            sql_script = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()
        
        # Verify table creation
        cursor.execute("""
            SELECT COUNT(*) as bookings_today
            FROM dll_veba_statistics
            WHERE event_type = 'booking' AND DATE(created_at) = CURRENT_DATE
        """)
        bookings = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) as leakage_today
            FROM dll_veba_statistics
            WHERE event_type = 'leakage_attempt' AND DATE(created_at) = CURRENT_DATE
        """)
        leakage = cursor.fetchone()[0]
        
        print("\n" + "="*70)
        print("✅ Migration completed successfully!")
        print("="*70)
        print(f"✅ Table dll_veba_statistics created")
        print(f"\n📊 Sample VEBA statistics data:")
        print(f"   - Bookings today: {bookings}")
        print(f"   - Leakage attempts today: {leakage}")
        print("="*70 + "\n")
        
        cursor.close()
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\n❌ Migration failed: {str(e)}\n")
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_migration()
