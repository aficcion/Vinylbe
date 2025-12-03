#!/usr/bin/env python3
"""
Full cleanup script that cleans both database and provides instructions for localStorage.
"""

import os
import sys
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")

def cleanup_database():
    """Clean up the database."""
    print("Starting database cleanup...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Delete in correct order (respecting foreign keys)
    tables_to_clean = [
        "auth_identity",
        "user_profile_lastfm",
        "user_selected_artist",
        "recommendation",
        "user_albums",
        "user"
    ]
    
    for table in tables_to_clean:
        cursor.execute(f"DELETE FROM {table}")
        deleted = cursor.rowcount
        print(f"Deleting all records from {table}...")
        print(f"  - Deleted {deleted} rows.")
    
    # Delete partial records
    cursor.execute("DELETE FROM albums WHERE is_partial = 1")
    deleted = cursor.rowcount
    print(f"Deleting partial records from albums...")
    print(f"  - Deleted {deleted} rows.")
    
    cursor.execute("DELETE FROM artists WHERE is_partial = 1")
    deleted = cursor.rowcount
    print(f"Deleting partial records from artists...")
    print(f"  - Deleted {deleted} rows.")
    
    conn.commit()
    conn.close()
    print("Database cleanup complete.\n")

def print_localstorage_instructions():
    """Print instructions for clearing localStorage."""
    print("=" * 70)
    print("IMPORTANT: You must also clear your browser's localStorage!")
    print("=" * 70)
    print("\nIn your browser:")
    print("1. Open Developer Tools (F12)")
    print("2. Go to 'Application' tab (or 'Storage' in Firefox)")
    print("3. In the left sidebar, expand 'Local Storage'")
    print("4. Click on 'http://localhost:8000' (or your URL)")
    print("5. Right-click → 'Clear' (or click the 🗑️ icon)")
    print("6. Reload the page (F5)")
    print("\nOR run this in the browser console:")
    print("  localStorage.clear(); location.reload();")
    print("=" * 70)

if __name__ == "__main__":
    cleanup_database()
    print_localstorage_instructions()
