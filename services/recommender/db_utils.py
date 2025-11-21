import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from libs.shared.utils import log_event


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def get_cached_album(artist_name: str, album_name: str) -> dict:
    """
    Check if album exists in cache
    Returns album data if found, None otherwise
    """
    try:
        with get_db_connection() as conn:
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
                        a.last_updated,
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
                    log_event("recommender-db", "INFO", 
                             f"Cache HIT: {artist_name} - {album_name}")
                    return dict(result)
                else:
                    log_event("recommender-db", "INFO", 
                             f"Cache MISS: {artist_name} - {album_name}")
                    return None
    except Exception as e:
        log_event("recommender-db", "ERROR", f"Error fetching album: {str(e)}")
        return None


def create_basic_album_entry(artist_name: str, album_name: str, cover_url: str = None):
    """
    Create basic artist and album entries in database
    Used for albums discovered via Last.fm that aren't in cache yet
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                artist_id = _get_or_create_artist(cur, artist_name)
                
                existing_check = """
                    SELECT id FROM albums 
                    WHERE artist_id = %s AND LOWER(title) = LOWER(%s)
                """
                cur.execute(existing_check, (artist_id, album_name))
                existing = cur.fetchone()
                
                if existing:
                    log_event("recommender-db", "INFO", 
                             f"Album already exists: {artist_name} - {album_name}")
                    return
                
                insert_album = """
                    INSERT INTO albums (artist_id, title, cover_url, last_updated)
                    VALUES (%s, %s, %s, %s)
                """
                cur.execute(insert_album, (artist_id, album_name, cover_url, datetime.now()))
                conn.commit()
                
                log_event("recommender-db", "INFO", 
                         f"Created basic album entry: {artist_name} - {album_name}")
    except Exception as e:
        log_event("recommender-db", "ERROR", 
                 f"Error creating album entry for {artist_name} - {album_name}: {str(e)}")


def _get_or_create_artist(cur, artist_name: str) -> int:
    """
    Get artist ID if exists, otherwise create basic artist entry
    """
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
    
    log_event("recommender-db", "INFO", f"Created basic artist entry: {artist_name}")
    return artist_id
