import os
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

# Path to the SQLite database file (same as used elsewhere in the project)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")


def dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries for easier access."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with foreign key support enabled.

    The connection uses a row factory that returns dictionaries.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create all required tables if they do not already exist.

    The schema follows the specification provided by the user.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Enable foreign keys (already set in get_connection, but keep for safety)
        cur.execute("PRAGMA foreign_keys = ON;")
        # Create tables
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                display_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL CHECK (provider IN ('google', 'lastfm')),
                provider_user_id TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (provider, provider_user_id),
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_profile_lastfm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lastfm_username TEXT NOT NULL,
                top_artists_json TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                UNIQUE (user_id)
            );

            CREATE TABLE IF NOT EXISTS user_selected_artist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                artist_name TEXT NOT NULL,
                mbid TEXT,
                spotify_id TEXT,
                source TEXT NOT NULL CHECK (source IN ('manual', 'lastfm_suggestion')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recommendation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                artist_name TEXT NOT NULL,
                album_title TEXT NOT NULL,
                album_mbid TEXT,
                source TEXT NOT NULL CHECK (source IN ('lastfm', 'manual', 'mixed')),
                status TEXT NOT NULL CHECK (status IN ('neutral', 'favorite', 'disliked', 'owned')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                UNIQUE (user_id, artist_name, album_title)
            );
            """
        )
        
        # Migration: Add spotify_id column if it doesn't exist
        try:
            cur.execute("ALTER TABLE user_selected_artist ADD COLUMN spotify_id TEXT")
        except sqlite3.OperationalError:
            pass  # Column likely already exists
            
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# User and authentication helper functions
# ---------------------------------------------------------------------------

def _create_user(display_name: str, email: Optional[str] = None) -> int:
    """Insert a new user row and return its id."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user (email, display_name) VALUES (?, ?)",
            (email, display_name),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_or_create_user_via_google(email: str, display_name: str, google_sub: str) -> int:
    """Return the user id for a Google login, creating rows as needed.

    * If an auth_identity with provider='google' and provider_user_id=google_sub already exists,
      its associated user_id is returned.
    * Otherwise a new user row is created (using the supplied email and display_name) and a
      corresponding auth_identity row is inserted.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Look for existing identity
        cur.execute(
            "SELECT user_id FROM auth_identity WHERE provider = 'google' AND provider_user_id = ?",
            (google_sub,),
        )
        row = cur.fetchone()
        if row:
            user_id = row["user_id"]
            # Update last_login_at on the user
            cur.execute(
                "UPDATE user SET last_login_at = datetime('now') WHERE id = ?",
                (user_id,),
            )
            conn.commit()
            return user_id
        # No existing identity – create user and identity
        user_id = _create_user(display_name=display_name, email=email)
        cur.execute(
            "INSERT INTO auth_identity (user_id, provider, provider_user_id) VALUES (?, 'google', ?)",
            (user_id, google_sub),
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


def get_or_create_user_via_lastfm(lastfm_username: str) -> int:
    """Return the user id for a Last.fm login, creating rows as needed.

    The display_name is set to the Last.fm username. Email is left NULL.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id FROM auth_identity WHERE provider = 'lastfm' AND provider_user_id = ?",
            (lastfm_username,),
        )
        row = cur.fetchone()
        if row:
            user_id = row["user_id"]
            cur.execute(
                "UPDATE user SET last_login_at = datetime('now') WHERE id = ?",
                (user_id,),
            )
            conn.commit()
            return user_id
        # No existing identity – create a new user and link the identity
        user_id = _create_user(display_name=lastfm_username)
        cur.execute(
            "INSERT INTO auth_identity (user_id, provider, provider_user_id) VALUES (?, 'lastfm', ?)",
            (user_id, lastfm_username),
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


def link_lastfm_to_existing_user(user_id: int, lastfm_username: str) -> None:
    """Link a Last.fm identity to an existing user if it does not already exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM auth_identity WHERE user_id = ? AND provider = 'lastfm' AND provider_user_id = ?",
            (user_id, lastfm_username),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO auth_identity (user_id, provider, provider_user_id) VALUES (?, 'lastfm', ?)",
                (user_id, lastfm_username),
            )
            conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Last.fm profile handling
# ---------------------------------------------------------------------------

def upsert_user_profile_lastfm(user_id: int, lastfm_username: str, top_artists: List[Dict[str, Any]]) -> None:
    """Insert or update the Last.fm profile snapshot for a user.

    * top_artists is stored as JSON text.
    * generated_at is set to the current UTC timestamp in ISO‑8601 format.
    """
    generated_at = datetime.utcnow().isoformat()
    top_artists_json = json.dumps(top_artists)
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Try to update first – if the row does not exist, INSERT.
        cur.execute(
            """
            UPDATE user_profile_lastfm
            SET lastfm_username = ?, top_artists_json = ?, generated_at = ?
            WHERE user_id = ?
            """,
            (lastfm_username, top_artists_json, generated_at, user_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO user_profile_lastfm (user_id, lastfm_username, top_artists_json, generated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, lastfm_username, top_artists_json, generated_at),
            )
        conn.commit()
    finally:
        conn.close()


def get_user_profile_lastfm(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve the Last.fm profile snapshot for a user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM user_profile_lastfm WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            # Parse the JSON string back to a list/dict
            try:
                row["top_artists"] = json.loads(row["top_artists_json"])
            except json.JSONDecodeError:
                row["top_artists"] = []
            del row["top_artists_json"]
        return row
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Selected artists handling
# ---------------------------------------------------------------------------

def add_user_selected_artist(
    user_id: int,
    artist_name: str,
    mbid: Optional[str] = None,
    source: str = "manual",
    spotify_id: Optional[str] = None,  # Keep parameter for backward compatibility but don't use it
) -> None:
    """Insert a new selected artist for the user.

    The source must be either "manual" or "lastfm_suggestion" – the caller is responsible for
    providing a valid value.
    """
    if source not in {"manual", "lastfm_suggestion"}:
        raise ValueError("source must be 'manual' or 'lastfm_suggestion'")
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Check if already exists
        cur.execute(
            "SELECT 1 FROM user_selected_artist WHERE user_id = ? AND artist_name = ?",
            (user_id, artist_name),
        )
        if cur.fetchone():
            return  # Already exists, do nothing

        cur.execute(
            "INSERT INTO user_selected_artist (user_id, artist_name, mbid, source) VALUES (?, ?, ?, ?)",
            (user_id, artist_name, mbid, source),
        )
        conn.commit()
    finally:
        conn.close()




def get_user_selected_artists(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all selected artists for a user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM user_selected_artist WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def remove_user_selected_artist(user_id: int, selection_id: int) -> bool:
    """Remove a selected artist entry. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_selected_artist WHERE id = ? AND user_id = ?",
            (selection_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

def upsert_recommendation_status(
    user_id: int, artist_name: str, album_title: str, status: str
) -> None:
    """Update or insert a recommendation status."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Check if exists
        cur.execute(
            "SELECT id FROM recommendation WHERE user_id = ? AND artist_name = ? AND album_title = ?",
            (user_id, artist_name, album_title),
        )
        row = cur.fetchone()
        
        if row:
            # Update existing
            cur.execute(
                "UPDATE recommendation SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status, row[0]),
            )
        else:
            # Insert new
            cur.execute(
                """
                INSERT INTO recommendation (user_id, artist_name, album_title, status, source)
                VALUES (?, ?, ?, ?, 'manual')
                """,
                (user_id, artist_name, album_title, status),
            )
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Recommendation handling
# ---------------------------------------------------------------------------

def regenerate_recommendations(user_id: int, new_recs: List[Dict[str, Any]]) -> None:
    """Update the recommendation table according to the business rules.

    * new_recs is a list of dicts with keys: artist_name, album_title, album_mbid (optional), source.
    * Existing recommendations with status 'disliked' or 'owned' are never recreated.
    * If a matching recommendation exists with status 'favorite', it is kept as‑is (metadata may be
      updated but status stays 'favorite').
    * If a matching recommendation exists with status 'neutral', its ``updated_at`` timestamp is
      refreshed.
    * Otherwise a new row with status 'neutral' is inserted.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        now_iso = datetime.utcnow().isoformat()
        for rec in new_recs:
            artist = rec.get("artist_name")
            # Handle both album_title (DB convention) and album_name (API convention)
            album = rec.get("album_title") or rec.get("album_name")
            mbid = rec.get("album_mbid")
            
            # Sanitize source field to ensure it matches DB constraints
            # Valid values: 'lastfm', 'manual', 'mixed'
            raw_source = rec.get("source", "mixed")
            if raw_source in {"artist_based", "spotify"}:
                source = "manual"  # Map artist_based and spotify to manual
            elif raw_source in {"lastfm", "manual", "mixed"}:
                source = raw_source
            else:
                source = "mixed"  # Fallback for any other invalid value

            if not artist or not album:
                log_event("gateway", "ERROR", f"Regenerate failed: missing artist or album in {rec}")
                continue
                
            # Check if recommendation already exists
            cur.execute(
                "SELECT id, status FROM recommendation WHERE user_id = ? AND artist_name = ? COLLATE NOCASE AND album_title = ? COLLATE NOCASE",
                (user_id, artist, album),
            )
            existing_row = cur.fetchone()

            if existing_row:
                status = existing_row["status"]
                if status in {"disliked", "owned"}:
                    # Skip – never recreate
                    continue
                if status == "favorite":
                    # Keep as favorite; optionally update metadata (mbid, source)
                    cur.execute(
                        """
                        UPDATE recommendation
                        SET album_mbid = ?, source = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (mbid, source, now_iso, existing_row["id"]),
                    )
                else:  # neutral
                    cur.execute(
                        """
                        UPDATE recommendation
                        SET album_mbid = ?, source = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (mbid, source, now_iso, existing_row["id"]),
                    )
            else:
                # Insert new neutral recommendation
                cur.execute(
                    """
                    INSERT INTO recommendation (user_id, artist_name, album_title, album_mbid, source, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'neutral', ?)
                    """,
                    (user_id, artist, album, mbid, source, now_iso),
                )
        conn.commit()
    finally:
        conn.close()


def get_recommendations_for_user(user_id: int, include_favorites: bool = True) -> List[Dict[str, Any]]:
    """Return a list of recommendation dicts for the user.

    Returns ALL recommendations regardless of status. The frontend will handle filtering
    based on the current view (all, favorites, owned, disliked, etc.).
    The include_favorites parameter is kept for backwards compatibility but is now ignored.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # Base query with JOINs to fetch cover_url from albums table
        # Using COLLATE NOCASE to ensure we match even if capitalization differs
        # Also try matching by MBID if available
        query = """
            SELECT 
                r.*, 
                a.cover_url as cover_url,
                ar.image_url as artist_image_url,
                a.is_partial
            FROM recommendation r
            LEFT JOIN artists ar ON ar.name = r.artist_name COLLATE NOCASE
            LEFT JOIN albums a ON 
                (r.album_mbid IS NOT NULL AND a.mbid = r.album_mbid) 
                OR 
                (a.artist_id = ar.id AND a.title = r.album_title COLLATE NOCASE)
            WHERE r.user_id = ?
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """
            
        cur.execute(query, (user_id,))
        return cur.fetchall()
    finally:
        conn.close()

def get_favorite_recommendations(user_id: int) -> List[Dict[str, Any]]:
    """Return only the recommendations marked as ``favorite`` for the user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT 
                r.*, 
                a.cover_url as cover_url,
                ar.image_url as artist_image_url,
                a.is_partial
            FROM recommendation r
            LEFT JOIN artists ar ON ar.name = r.artist_name COLLATE NOCASE
            LEFT JOIN albums a ON 
                (r.album_mbid IS NOT NULL AND a.mbid = r.album_mbid) 
                OR 
                (a.artist_id = ar.id AND a.title = r.album_title COLLATE NOCASE)
            WHERE r.user_id = ? AND r.status = 'favorite'
            GROUP BY r.id
        """
        cur.execute(query, (user_id,))
        return cur.fetchall()
    finally:
        conn.close()


def update_recommendation_status(user_id: int, recommendation_id: int, new_status: str) -> None:
    """Change the status of a recommendation.

    ``new_status`` must be one of ``neutral``, ``favorite``, ``disliked`` or ``owned``.
    """
    if new_status not in {"neutral", "favorite", "disliked", "owned"}:
        raise ValueError("Invalid status value")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE recommendation SET status = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
            (new_status, recommendation_id, user_id),
        )
        if cur.rowcount == 0:
            raise RuntimeError("Recommendation not found for given user")
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Convenience helpers (optional)
# ---------------------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Return a user record matching the given email, or ``None`` if not found."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user WHERE email = ?", (email,))
        return cur.fetchone()
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Return a user record by its primary key, or ``None`` if not found."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user WHERE id = ?", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def get_random_albums_with_covers(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch random albums that have a cover URL."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, cover_url, artist_id
            FROM albums
            WHERE cover_url IS NOT NULL AND cover_url != ''
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
    except sqlite3.OperationalError:
        # Fallback if albums table doesn't exist or other DB error
        return []
    finally:
        conn.close()


def search_artists(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for artists by name in the database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, image_url, is_partial
            FROM artists
            WHERE name LIKE ? COLLATE NOCASE
            ORDER BY name
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )
        return cur.fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def search_albums(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search for albums by title in the database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.id, a.title, a.cover_url, a.artist_id, a.is_partial,
                   ar.name as artist_name, ar.image_url as artist_image_url
            FROM albums a
            LEFT JOIN artists ar ON a.artist_id = ar.id
            WHERE a.title LIKE ? COLLATE NOCASE
            ORDER BY a.title
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )
        return cur.fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
