#!/usr/bin/env python3
"""
Migrate data from PostgreSQL backup to SQLite database.
This script reads from the PostgreSQL database and writes to vinylbe.db
"""
import sqlite3
import subprocess
import json
import os
import sys

# Paths
SQLITE_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")
PSQL_BIN = "/opt/homebrew/opt/postgresql@17/bin/psql"

def run_psql_query(query):
    """Run a PostgreSQL query and return JSON results"""
    cmd = [
        PSQL_BIN,
        '-d', 'vinylbe',
        '-t',  # Tuples only
        '-A',  # Unaligned output
        '-F', '|',  # Field separator
        '-c', query
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running query: {result.stderr}")
        return []
    
    return result.stdout.strip()

def create_sqlite_tables():
    """Create SQLite tables matching the schema"""
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    
    # Drop existing tables
    print("Dropping existing tables...")
    cur.execute("DROP TABLE IF EXISTS user_albums")
    cur.execute("DROP TABLE IF EXISTS albums")
    cur.execute("DROP TABLE IF EXISTS artists")
    
    # Create artists table
    print("Creating artists table...")
    cur.execute("""
        CREATE TABLE artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            mbid TEXT,
            image_url TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create albums table
    print("Creating albums table...")
    cur.execute("""
        CREATE TABLE albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            year TEXT,
            discogs_master_id TEXT,
            discogs_release_id TEXT,
            rating REAL,
            votes INTEGER,
            cover_url TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (artist_id) REFERENCES artists(id),
            UNIQUE(artist_id, title, year)
        )
    """)
    
    # Create user_albums table
    print("Creating user_albums table...")
    cur.execute("""
        CREATE TABLE user_albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            album_id INTEGER NOT NULL,
            play_count INTEGER DEFAULT 0,
            last_played TIMESTAMP,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (album_id) REFERENCES albums(id),
            UNIQUE(user_id, album_id)
        )
    """)
    
    # Create indexes
    print("Creating indexes...")
    cur.execute("CREATE INDEX idx_albums_artist_id ON albums(artist_id)")
    cur.execute("CREATE INDEX idx_albums_title ON albums(title)")
    cur.execute("CREATE INDEX idx_artists_name ON artists(name)")
    cur.execute("CREATE INDEX idx_user_albums_user_id ON user_albums(user_id)")
    
    conn.commit()
    conn.close()
    print("✓ Tables created successfully")

def migrate_artists():
    """Migrate artists from PostgreSQL to SQLite"""
    print("\n=== Migrating Artists ===")
    
    # Get artists from PostgreSQL
    output = run_psql_query("SELECT id, name, mbid, image_url FROM artists ORDER BY id")
    
    if not output:
        print("No artists found in PostgreSQL")
        return
    
    lines = output.split('\n')
    print(f"Found {len(lines)} artists to migrate")
    
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    
    migrated = 0
    for line in lines:
        if not line.strip():
            continue
            
        parts = line.split('|')
        if len(parts) < 2:
            continue
        
        pg_id = parts[0]
        name = parts[1] if len(parts) > 1 else None
        mbid = parts[2] if len(parts) > 2 and parts[2] else None
        image_url = parts[3] if len(parts) > 3 and parts[3] else None
        
        try:
            cur.execute("""
                INSERT INTO artists (id, name, mbid, image_url)
                VALUES (?, ?, ?, ?)
            """, (pg_id, name, mbid, image_url))
            migrated += 1
        except sqlite3.IntegrityError as e:
            print(f"Skipping duplicate artist: {name}")
    
    conn.commit()
    conn.close()
    print(f"✓ Migrated {migrated} artists")

def migrate_albums():
    """Migrate albums from PostgreSQL to SQLite"""
    print("\n=== Migrating Albums ===")
    
    # Get albums from PostgreSQL
    output = run_psql_query("""
        SELECT id, artist_id, title, year, discogs_master_id, discogs_release_id, 
               rating, votes, cover_url 
        FROM albums 
        ORDER BY id
    """)
    
    if not output:
        print("No albums found in PostgreSQL")
        return
    
    lines = output.split('\n')
    print(f"Found {len(lines)} albums to migrate")
    
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    
    migrated = 0
    for line in lines:
        if not line.strip():
            continue
            
        parts = line.split('|')
        if len(parts) < 3:
            continue
        
        pg_id = parts[0]
        artist_id = parts[1]
        title = parts[2] if len(parts) > 2 else None
        year = parts[3] if len(parts) > 3 and parts[3] else None
        discogs_master_id = parts[4] if len(parts) > 4 and parts[4] else None
        discogs_release_id = parts[5] if len(parts) > 5 and parts[5] else None
        rating = parts[6] if len(parts) > 6 and parts[6] else None
        votes = parts[7] if len(parts) > 7 and parts[7] else None
        cover_url = parts[8] if len(parts) > 8 and parts[8] else None
        
        try:
            cur.execute("""
                INSERT INTO albums (id, artist_id, title, year, discogs_master_id, 
                                  discogs_release_id, rating, votes, cover_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pg_id, artist_id, title, year, discogs_master_id, discogs_release_id,
                  rating, votes, cover_url))
            migrated += 1
        except sqlite3.IntegrityError as e:
            print(f"Skipping duplicate album: {title}")
    
    conn.commit()
    conn.close()
    print(f"✓ Migrated {migrated} albums")

def verify_migration():
    """Verify the migration was successful"""
    print("\n=== Verification ===")
    
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM artists")
    artist_count = cur.fetchone()[0]
    print(f"SQLite artists: {artist_count}")
    
    cur.execute("SELECT COUNT(*) FROM albums")
    album_count = cur.fetchone()[0]
    print(f"SQLite albums: {album_count}")
    
    # Show sample data
    cur.execute("SELECT name FROM artists LIMIT 5")
    artists = cur.fetchall()
    print(f"\nSample artists: {', '.join([a[0] for a in artists])}")
    
    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("POSTGRESQL TO SQLITE MIGRATION")
    print("=" * 60)
    
    # Check if PostgreSQL is accessible
    try:
        result = subprocess.run(
            [PSQL_BIN, '-d', 'vinylbe', '-c', 'SELECT 1'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Error: Cannot connect to PostgreSQL database 'vinylbe'")
            print("Make sure PostgreSQL is running and the database exists")
            sys.exit(1)
    except FileNotFoundError:
        print(f"Error: psql not found at {PSQL_BIN}")
        sys.exit(1)
    
    # Backup existing SQLite database
    if os.path.exists(SQLITE_DB):
        backup_path = SQLITE_DB + ".backup"
        print(f"\nBacking up existing database to {backup_path}")
        import shutil
        shutil.copy2(SQLITE_DB, backup_path)
    
    # Run migration
    create_sqlite_tables()
    migrate_artists()
    migrate_albums()
    verify_migration()
    
    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)
