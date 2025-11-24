import os
import sqlite3
from datetime import datetime
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from libs.shared.utils import log_event

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "vinylbe.db")

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db_connection():
    """Get SQLite connection and ensure required tables exist"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    _ensure_schema(conn)
    return conn

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create artists and albums tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            mbid TEXT,
            image_url TEXT,
            last_updated TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            year TEXT,
            mbid TEXT,
            discogs_master_id TEXT,
            discogs_release_id TEXT,
            rating REAL,
            votes INTEGER,
            cover_url TEXT,
            last_updated TIMESTAMP,
            FOREIGN KEY (artist_id) REFERENCES artists(id)
        )
        """
    )
    
    # Migration: Add mbid column if it doesn't exist
    try:
        cur.execute("ALTER TABLE albums ADD COLUMN mbid TEXT")
    except sqlite3.OperationalError:
        pass  # Column likely already exists
        
    conn.commit()

def get_cached_album(artist_name: str, album_name: str, mbid: str = None) -> dict:
    """Check if album exists in cache"""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            
            # Try matching by MBID first if available
            if mbid:
                query_mbid = """
                    SELECT 
                        a.id as album_id,
                        a.title,
                        a.year,
                        a.mbid,
                        a.discogs_master_id,
                        a.discogs_release_id,
                        a.rating,
                        a.votes,
                        a.cover_url,
                        ar.name as artist_name
                    FROM albums a
                    JOIN artists ar ON a.artist_id = ar.id
                    WHERE a.mbid = ?
                    LIMIT 1
                """
                cur.execute(query_mbid, (mbid,))
                result = cur.fetchone()
                if result:
                    log_event("recommender-db", "DEBUG", f"✓ Cache HIT (MBID): {mbid}")
                    return result

            # Fallback to name matching
            query = """
                SELECT 
                    a.id as album_id,
                    a.title,
                    a.year,
                    a.mbid,
                    a.discogs_master_id,
                    a.discogs_release_id,
                    a.rating,
                    a.votes,
                    a.cover_url,
                    ar.name as artist_name
                FROM albums a
                JOIN artists ar ON a.artist_id = ar.id
                WHERE LOWER(ar.name) = LOWER(?)
                AND LOWER(a.title) = LOWER(?)
                LIMIT 1
            """
            cur.execute(query, (artist_name, album_name))
            result = cur.fetchone()
            
            if result:
                log_event("recommender-db", "DEBUG", f"✓ Cache HIT: {artist_name} - {album_name}")
                return result
            else:
                log_event("recommender-db", "DEBUG", f"○ Cache MISS: {artist_name} - {album_name}")
                return None
        finally:
            conn.close()
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error fetching album: {str(e)}")
        return None

def create_basic_album_entry(artist_name: str, album_name: str, cover_url: str = None, mbid: str = None) -> bool:
    """Create basic artist and album entries"""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            artist_id = _get_or_create_artist(cur, artist_name)
            
            # Check existence by MBID or Name
            existing = None
            if mbid:
                cur.execute("SELECT id FROM albums WHERE mbid = ?", (mbid,))
                existing = cur.fetchone()
            
            if not existing:
                existing_check = """
                    SELECT id FROM albums 
                    WHERE artist_id = ? AND LOWER(title) = LOWER(?)
                """
                cur.execute(existing_check, (artist_id, album_name))
                existing = cur.fetchone()
            
            if existing:
                # Update MBID if missing
                if mbid:
                    cur.execute("UPDATE albums SET mbid = ? WHERE id = ? AND mbid IS NULL", (mbid, existing['id']))
                    conn.commit()
                log_event("recommender-db", "DEBUG", f"Album exists: {artist_name} - {album_name}")
                return False
            
            insert_album = """
                INSERT INTO albums (artist_id, title, cover_url, mbid, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """
            cur.execute(insert_album, (artist_id, album_name, cover_url, mbid, datetime.now()))
            conn.commit()
            
            log_event("recommender-db", "DEBUG", f"✓ Created album: {artist_name} - {album_name}")
            return True
        finally:
            conn.close()
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error creating album: {artist_name} - {album_name}: {str(e)}")
        return False

def _get_or_create_artist(cur, artist_name: str) -> int:
    """Get or create artist (cursor transaction)"""
    check_query = "SELECT id FROM artists WHERE LOWER(name) = LOWER(?)"
    cur.execute(check_query, (artist_name,))
    result = cur.fetchone()
    
    if result:
        return result['id']
    
    insert_query = """
        INSERT INTO artists (name, last_updated)
        VALUES (?, ?)
        RETURNING id
    """
    # SQLite doesn't support RETURNING in older versions, but we can use lastrowid
    try:
        cur.execute("INSERT INTO artists (name, last_updated) VALUES (?, ?)", (artist_name, datetime.now()))
        return cur.lastrowid
    except sqlite3.Error:
        # Fallback if insert fails (race condition?)
        cur.execute(check_query, (artist_name,))
        return cur.fetchone()['id']

def close_pool():
    """No-op for SQLite"""
    pass
