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
            image_url TEXT,
            last_updated TIMESTAMP,
            is_partial INTEGER DEFAULT 0
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
            is_partial INTEGER DEFAULT 0,
            FOREIGN KEY (artist_id) REFERENCES artists(id)
        )
        """
    )
    
    # Migration: Add mbid column if it doesn't exist
    try:
        cur.execute("ALTER TABLE albums ADD COLUMN mbid TEXT")
    except sqlite3.OperationalError:
        pass  # Column likely already exists
        
    # Migration: Add is_partial column if it doesn't exist
    try:
        cur.execute("ALTER TABLE albums ADD COLUMN is_partial INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column likely already exists
        
    # Migration: Add is_partial column to artists if it doesn't exist
    try:
        cur.execute("ALTER TABLE artists ADD COLUMN is_partial INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column likely already exists
        # Migration: Add spotify_id column if it doesn't exist
    try:
        cur.execute("ALTER TABLE artists ADD COLUMN spotify_id TEXT UNIQUE")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_artists_spotify_id ON artists(spotify_id)")
    except sqlite3.OperationalError:
        pass  # Column likely already exists

    try:
        cur.execute("ALTER TABLE albums ADD COLUMN spotify_id TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_albums_spotify_id ON albums(spotify_id)")
    except sqlite3.OperationalError:
        pass  # Column likely already exists
        
    conn.commit()

def get_cached_album(artist_name: str, album_name: str, mbid: str = None, spotify_id: str = None) -> dict:
    """Check if album exists in cache"""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            
            # 1. Try matching by Spotify ID
            if spotify_id:
                query_spotify = """
                    SELECT 
                        a.id as album_id,
                        a.title,
                        a.year,
                        a.mbid,
                        a.spotify_id,
                        a.discogs_master_id,
                        a.discogs_release_id,
                        a.rating,
                        a.votes,
                        a.cover_url,
                        a.is_partial,
                        ar.name as artist_name
                    FROM albums a
                    JOIN artists ar ON a.artist_id = ar.id
                    WHERE a.spotify_id = ?
                    LIMIT 1
                """
                cur.execute(query_spotify, (spotify_id,))
                result = cur.fetchone()
                if result:
                    log_event("recommender-db", "DEBUG", f"✓ Cache HIT (Spotify ID): {spotify_id}")
                    return result

            # 2. Try matching by MBID
            if mbid:
                query_mbid = """
                    SELECT 
                        a.id as album_id,
                        a.title,
                        a.year,
                        a.mbid,
                        a.spotify_id,
                        a.discogs_master_id,
                        a.discogs_release_id,
                        a.rating,
                        a.votes,
                        a.cover_url,
                        a.is_partial,
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

            # 3. Fallback to name matching
            query = """
                SELECT 
                    a.id as album_id,
                    a.title,
                    a.year,
                    a.mbid,
                    a.spotify_id,
                    a.discogs_master_id,
                    a.discogs_release_id,
                    a.rating,
                    a.votes,
                    a.cover_url,
                    a.is_partial,
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

def create_basic_album_entry(artist_name: str, album_name: str, cover_url: str = None, mbid: str = None, spotify_id: str = None, artist_spotify_id: str = None) -> bool:
    """Create basic artist and album entries"""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            artist_id = _get_or_create_artist(cur, artist_name, artist_spotify_id)
            
            # Check existence by Spotify ID, MBID or Name
            existing = None
            
            if spotify_id:
                cur.execute("SELECT id FROM albums WHERE spotify_id = ?", (spotify_id,))
                existing = cur.fetchone()
            
            if not existing and mbid:
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
                # Update IDs if missing
                updates = []
                params = []
                if mbid:
                    updates.append("mbid = ?")
                    params.append(mbid)
                if spotify_id:
                    updates.append("spotify_id = ?")
                    params.append(spotify_id)
                
                if updates:
                    params.append(existing['id'])
                    # Only update if null
                    where_clauses = [f"{col.split(' =')[0]} IS NULL" for col in updates]
                    # This logic is a bit complex for single update, let's just update if provided
                    # Actually, better to only update if currently NULL to avoid overwriting
                    
                    # Simplified: just try to update both if provided
                    if mbid:
                        cur.execute("UPDATE albums SET mbid = ? WHERE id = ? AND mbid IS NULL", (mbid, existing['id']))
                    if spotify_id:
                        cur.execute("UPDATE albums SET spotify_id = ? WHERE id = ? AND spotify_id IS NULL", (spotify_id, existing['id']))
                    
                    conn.commit()
                    
                log_event("recommender-db", "DEBUG", f"Album exists: {artist_name} - {album_name}")
                return False
            
            insert_album = """
                INSERT INTO albums (artist_id, title, cover_url, mbid, spotify_id, last_updated, is_partial)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """
            cur.execute(insert_album, (artist_id, album_name, cover_url, mbid, spotify_id, datetime.now()))
            conn.commit()
            
            log_event("recommender-db", "DEBUG", f"✓ Created album: {artist_name} - {album_name}")
            return True
        finally:
            conn.close()
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error creating album: {artist_name} - {album_name}: {str(e)}")
        return False

def _get_or_create_artist(cur, artist_name: str, spotify_id: str = None) -> int:
    """Get or create artist (cursor transaction)"""
    
    # Try by Spotify ID first
    if spotify_id:
        cur.execute("SELECT id FROM artists WHERE spotify_id = ?", (spotify_id,))
        result = cur.fetchone()
        if result:
            return result['id']
            
    # Try by name
    check_query = "SELECT id FROM artists WHERE LOWER(name) = LOWER(?)"
    cur.execute(check_query, (artist_name,))
    result = cur.fetchone()
    
    if result:
        # Update spotify_id if missing
        if spotify_id:
            cur.execute("UPDATE artists SET spotify_id = ? WHERE id = ? AND spotify_id IS NULL", (spotify_id, result['id']))
        return result['id']
    
    # Create new
    try:
        cur.execute(
            "INSERT INTO artists (name, spotify_id, last_updated, is_partial) VALUES (?, ?, ?, 1)", 
            (artist_name, spotify_id, datetime.now())
        )
        return cur.lastrowid
    except sqlite3.Error:
        # Fallback if insert fails (race condition?)
        cur.execute(check_query, (artist_name,))
        return cur.fetchone()['id']

def close_pool():
    """No-op for SQLite"""
    pass
