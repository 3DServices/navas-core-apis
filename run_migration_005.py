#!/usr/bin/env python3
"""
Run database migration 005 - Create tenant management tables
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
        with open('database/migrations/005_create_tenants_tables.sql', 'r') as f:
            sql_script = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()
        
        # Verify table creation and get statistics
        cursor.execute("""
            SELECT COUNT(*) as total_tenants FROM dll_tenants
        """)
        total_tenants = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT tenant_tier, COUNT(*) as count
            FROM dll_tenants
            WHERE tenant_status != 'trashed'
            GROUP BY tenant_tier
            ORDER BY 
                CASE tenant_tier
                    WHEN 'TOP' THEN 1
                    WHEN 'DEAL' THEN 2
                    WHEN 'CLIENT' THEN 3
                    WHEN 'ORG' THEN 4
                END
        """)
        tier_counts = cursor.fetchall()
        
        cursor.execute("""
            SELECT COUNT(*) as trashed_count
            FROM dll_tenants
            WHERE tenant_status = 'trashed'
        """)
        trashed_count = cursor.fetchone()[0]
        
        print("\n" + "="*70)
        print("✅ Migration completed successfully!")
        print("="*70)
        print(f"✅ Table dll_tenants created")
        print(f"✅ View vw_tenant_hierarchy created")
        print(f"✅ Trigger update_tenant_timestamp created")
        print(f"\n📊 Sample tenant hierarchy data:")
        print(f"   Total tenants: {total_tenants}")
        print(f"\n   By tier:")
        for tier, count in tier_counts:
            print(f"   - {tier}: {count} tenant(s)")
        print(f"\n   Trashed: {trashed_count}")
        print("\n" + "="*70)
        print("\n🚀 Tenant management endpoints are now ready!")
        print("\nAvailable endpoints:")
        print("   POST   /tenants/create          - Create a new tenant")
        print("   GET    /tenants/all             - List all active tenants")
        print("   POST   /tenants/import          - Bulk import from CSV/JSON")
        print("   GET    /tenants/import/template - Download CSV template")
        print("   GET    /tenants/trashed         - List soft-deleted tenants")
        print("   PATCH  /tenants/{id}/trash      - Soft-delete a tenant")
        print("   PATCH  /tenants/{id}/restore    - Restore a trashed tenant")
        print("\n" + "="*70)
        
        cursor.close()
        
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"\n❌ Migration failed!")
        print(f"Error: {e}")
        raise
    
    except FileNotFoundError as e:
        print(f"\n❌ Migration file not found!")
        print(f"Error: {e}")
        raise
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\n❌ Unexpected error!")
        print(f"Error: {e}")
        raise
    
    finally:
        if conn:
            conn.close()
            print("\nDatabase connection closed.")

if __name__ == '__main__':
    print("\n" + "="*70)
    print("Running Migration 005: Create Tenant Management Tables")
    print("="*70 + "\n")
    
    try:
        run_migration()
        print("\n✅ All done!\n")
    except Exception as e:
        print("\n❌ Migration aborted.\n")
        exit(1)
