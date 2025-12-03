import sys
import os
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway.db import get_connection

def cleanup_db():
    print("Starting database cleanup...")
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # 1. Delete all user related data
        # Due to foreign keys (ON DELETE CASCADE), deleting from 'user' might be enough for some, 
        # but let's be explicit to be safe and cover tables that might not have cascades or are loose.
        
        tables_to_clear = [
            "auth_identity",
            "user_profile_lastfm",
            "user_selected_artist",
            "recommendation",
            "user_albums",
            "user"
        ]
        
        for table in tables_to_clear:
            print(f"Deleting all records from {table}...")
            cur.execute(f"DELETE FROM {table}")
            print(f"  - Deleted {cur.rowcount} rows.")

        # 2. Delete partial records
        print("Deleting partial records from albums...")
        cur.execute("DELETE FROM albums WHERE is_partial = 1")
        print(f"  - Deleted {cur.rowcount} rows.")

        print("Deleting partial records from artists...")
        cur.execute("DELETE FROM artists WHERE is_partial = 1")
        print(f"  - Deleted {cur.rowcount} rows.")
        
        conn.commit()
        print("Cleanup complete.")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_db()
