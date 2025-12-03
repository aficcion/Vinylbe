import sqlite3
import os
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from services.recommender.db_utils import get_db_connection

def check_duplicates():
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("--- Checking 'Alcalá Norte' ---")
    cur.execute("SELECT id, title, artist_id, is_partial, discogs_master_id FROM albums WHERE title LIKE '%Alcal%' OR title LIKE '%alcal%'")
    rows = cur.fetchall()
    for r in rows:
        print(dict(r))
        
    print("\n--- Checking 'Suck It and See' ---")
    cur.execute("SELECT id, title, artist_id, is_partial, discogs_master_id FROM albums WHERE title LIKE '%Suck It%'")
    rows = cur.fetchall()
    for r in rows:
        print(dict(r))

if __name__ == "__main__":
    check_duplicates()
