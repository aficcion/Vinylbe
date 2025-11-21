import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from datetime import datetime
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from libs.shared.utils import log_event

_db_pool = None

def _get_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = pool.SimpleConnectionPool(
            1, 5, os.getenv("DATABASE_URL"),
            connect_timeout=5
        )
    return _db_pool

def get_cached_album(artist_name: str, album_name: str) -> dict:
    """Check if album exists in cache (thread-safe)"""
    try:
        conn = _get_pool().getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT 
                        a.id as album_id,
                        a.title,
                        a.year,
                        a.discogs_master_id,
                        a.discogs_release_id,
                        a.rating,
                        a.votes,
                        a.cover_url,
                        ar.name as artist_name
                    FROM albums a
                    JOIN artists ar ON a.artist_id = ar.id
                    WHERE LOWER(ar.name) = LOWER(%s)
                    AND LOWER(a.title) = LOWER(%s)
                    LIMIT 1
                """
                cur.execute(query, (artist_name, album_name))
                result = cur.fetchone()
                
                if result:
                    log_event("recommender-db", "DEBUG", f"✓ Cache HIT: {artist_name} - {album_name}")
                    return dict(result)
                else:
                    log_event("recommender-db", "DEBUG", f"○ Cache MISS: {artist_name} - {album_name}")
                    return None
        finally:
            _get_pool().putconn(conn)
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error fetching album: {str(e)}")
        return None

def create_basic_album_entry(artist_name: str, album_name: str, cover_url: str = None) -> bool:
    """Create basic artist and album entries (thread-safe)"""
    try:
        conn = _get_pool().getconn()
        try:
            with conn.cursor() as cur:
                artist_id = _get_or_create_artist(cur, artist_name)
                
                existing_check = """
                    SELECT id FROM albums 
                    WHERE artist_id = %s AND LOWER(title) = LOWER(%s)
                """
                cur.execute(existing_check, (artist_id, album_name))
                existing = cur.fetchone()
                
                if existing:
                    log_event("recommender-db", "DEBUG", f"Album exists: {artist_name} - {album_name}")
                    return False
                
                insert_album = """
                    INSERT INTO albums (artist_id, title, cover_url, last_updated)
                    VALUES (%s, %s, %s, %s)
                """
                cur.execute(insert_album, (artist_id, album_name, cover_url, datetime.now()))
                conn.commit()
                
                log_event("recommender-db", "DEBUG", f"✓ Created album: {artist_name} - {album_name}")
                return True
        finally:
            _get_pool().putconn(conn)
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error creating album: {artist_name} - {album_name}: {str(e)}")
        return False

def _get_or_create_artist(cur, artist_name: str) -> int:
    """Get or create artist (cursor transaction)"""
    check_query = "SELECT id FROM artists WHERE LOWER(name) = LOWER(%s)"
    cur.execute(check_query, (artist_name,))
    result = cur.fetchone()
    
    if result:
        return result[0]
    
    insert_query = """
        INSERT INTO artists (name, last_updated)
        VALUES (%s, %s)
        RETURNING id
    """
    cur.execute(insert_query, (artist_name, datetime.now()))
    artist_id = cur.fetchone()[0]
    
    log_event("recommender-db", "DEBUG", f"✓ Created artist: {artist_name}")
    return artist_id

def close_pool():
    """Close database pool"""
    global _db_pool
    if _db_pool:
        _db_pool.closeall()
        _db_pool = None
