import os
import time
import re
import threading
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

MB_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE = "https://api.discogs.com"

HEADERS = {
    "User-Agent": "Vinilogy/1.0 (+https://vinilogy.com; contact@vinilogy.com)"
}

_RE_DISCOGS_MASTER = re.compile(
    r"https?://(?:www\.)?discogs\.com/(?:[a-z]{2}/)?master/(\d+)", re.I
)

CLIENT = httpx.Client(
    headers=HEADERS,
    http2=False,
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
    follow_redirects=True,
)

CACHE_EXPIRY_DAYS = 7

_last_discogs_call_time = 0.0
_MIN_DISCOGS_DELAY = 1.5
_discogs_lock = threading.Lock()


def _get_db_connection():
    """Get PostgreSQL connection"""
    try:
        return psycopg2.connect(os.getenv("DATABASE_URL"))
    except Exception as e:
        print(f"[DB] Connection failed: {e}")
        return None


def _get_cached_artist_albums(artist_name: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached artist albums from PostgreSQL"""
    conn = _get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT id, mbid, last_updated FROM artists WHERE name = %s",
            (artist_name,)
        )
        artist = cursor.fetchone()
        
        if not artist:
            return None
        
        cache_age = datetime.now() - artist["last_updated"]
        if cache_age > timedelta(days=CACHE_EXPIRY_DAYS):
            print(f"[DB] Cache for '{artist_name}' is {cache_age.days} days old (expired)")
            return None
        
        cursor.execute(
            """SELECT title, year, discogs_master_id, discogs_release_id, 
                      rating, votes, cover_url
               FROM albums 
               WHERE artist_id = %s 
               ORDER BY rating DESC NULLS LAST, votes DESC NULLS LAST""",
            (artist["id"],)
        )
        albums = cursor.fetchall()
        
        if not albums:
            return None
        
        print(f"[DB] ✓ Found {len(albums)} cached albums for '{artist_name}' (age: {cache_age.days}d)")
        return [dict(album) for album in albums]
    
    except Exception as e:
        print(f"[DB] Error reading cache for '{artist_name}': {e}")
        return None
    finally:
        conn.close()


def _save_artist_albums(artist_name: str, mbid: str, albums: List['StudioAlbum'], 
                        image_url: Optional[str] = None):
    """Save artist and albums to PostgreSQL"""
    conn = _get_db_connection()
    if not conn:
        print(f"[DB] Cannot save '{artist_name}' - no database connection")
        return
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """INSERT INTO artists (name, mbid, image_url) 
               VALUES (%s, %s, %s) 
               ON CONFLICT (name) 
               DO UPDATE SET mbid = EXCLUDED.mbid, 
                            image_url = EXCLUDED.image_url,
                            last_updated = CURRENT_TIMESTAMP
               RETURNING id""",
            (artist_name, mbid, image_url)
        )
        result = cursor.fetchone()
        if not result:
            return
        artist_id = result["id"]
        
        cursor.execute("DELETE FROM albums WHERE artist_id = %s", (artist_id,))
        
        for album in albums:
            cursor.execute(
                """INSERT INTO albums (artist_id, title, year, discogs_master_id, 
                                      discogs_release_id, rating, votes, cover_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (artist_id, album.title, album.year, album.discogs_master_id,
                 album.discogs_release_id, album.rating, album.votes, album.cover_image)
            )
        
        conn.commit()
        print(f"[DB] ✓ Saved {len(albums)} albums for '{artist_name}' to cache")
    
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error saving '{artist_name}': {e}")
    finally:
        conn.close()


class StudioAlbum:
    def __init__(self, title: str, year: str, discogs_master_id: Optional[str],
                 artist_name: str, rating: Optional[float] = None,
                 votes: Optional[int] = None, cover_image: Optional[str] = None,
                 discogs_release_id: Optional[str] = None, discogs_type: str = "master"):
        self.title = title
        self.year = year
        self.discogs_master_id = discogs_master_id
        self.discogs_release_id = discogs_release_id
        self.discogs_type = discogs_type
        self.artist_name = artist_name
        self.rating = rating
        self.votes = votes
        self.cover_image = cover_image


def _mb_get(path: str, params: Dict[str, Any], tries: int = 5,
            sleep_after_ok: float = 1.0) -> Dict[str, Any]:
    url = f"{MB_BASE}{path}"
    params = {**params, "fmt": "json"}
    last_exc = None
    backoff = 0.6

    for attempt in range(1, tries + 1):
        try:
            r = CLIENT.get(url, params=params)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("Transient", request=r.request, response=r)
            r.raise_for_status()
            time.sleep(sleep_after_ok)
            return r.json()
        except Exception as e:
            last_exc = e
            time.sleep(backoff)
            backoff = min(backoff * 1.7, 5.0)

    raise RuntimeError(f"MB failed: {last_exc}")


def _find_artist_mbid(name: str) -> Optional[str]:
    try:
        data = _mb_get("/artist", {"query": f'artist:"{name}"', "limit": 10})
        artists = data.get("artists", []) or []
        if not artists:
            return None
        exact = [a for a in artists if a.get("name", "").lower() == name.lower()]
        chosen = exact[0] if exact else artists[0]
        return chosen.get("id")
    except Exception:
        return None


def _fetch_release_groups(artist_mbid: str, limit: int = 100):
    try:
        data = _mb_get(
            "/release-group",
            {
                "artist": artist_mbid,
                "primary-type": "Album",
                "inc": "artist-credits+url-rels",
                "limit": min(limit, 100),
            }
        )
        return data.get("release-groups", []) or []
    except Exception:
        return []


def _is_studio_album(rg: Dict[str, Any], artist_mbid: str) -> bool:
    if rg.get("primary-type") != "Album":
        return False
    if rg.get("secondary-types"):
        return False
    ac = rg.get("artist-credit") or []
    if len(ac) != 1:
        return False
    return (ac[0].get("artist") or {}).get("id") == artist_mbid


def _year_from_date(item: Dict[str, Any]) -> str:
    d = item.get("first-release-date") or ""
    return d.split("-")[0] if d else ""


def _discogs_master_from_rels(relations: Any) -> str:
    if not relations:
        return ""
    for rel in relations:
        if rel.get("type") == "discogs":
            url = (rel.get("url") or {}).get("resource", "")
            m = _RE_DISCOGS_MASTER.search(url)
            if m:
                return m.group(1)
    return ""


def _get_artist_image_from_discogs(artist_name: str, discogs_key: str, discogs_secret: str) -> Optional[str]:
    """Get artist image from Discogs search"""
    try:
        data = _discogs_get("/database/search", {
            "q": artist_name,
            "type": "artist",
            "per_page": 1
        }, discogs_key, discogs_secret)
        results = data.get("results", [])
        if results:
            return results[0].get("cover_image")
    except Exception as e:
        print(f"[ARTIST IMAGE] Could not get image for {artist_name}: {e}")
    return None


def _discogs_get(path: str, params: Dict[str, Any],
                 key: str, secret: str,
                 sleep_after_ok: float = 0.25,
                 tries: int = 5):
    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": key, "secret": secret}
    last_exc = None
    backoff = 1.0
    
    for attempt in range(1, tries + 1):
        try:
            r = CLIENT.get(url, params=params)
            if r.status_code == 429:
                if attempt < tries:
                    wait_time = 60.0
                    print(f"[DISCOGS] ⚠️  RATE LIMIT HIT (429) - sleeping {wait_time}s before retry (attempt {attempt}/{tries})")
                    time.sleep(wait_time)
                    continue
            r.raise_for_status()
            time.sleep(sleep_after_ok)
            return r.json()
        except Exception as e:
            last_exc = e
            if attempt < tries:
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 10.0)
    
    raise RuntimeError(f"Discogs API failed after {tries} attempts: {last_exc}")


def _search_discogs_master(artist_name: str, album_title: str, key: str, secret: str) -> Optional[str]:
    """Fallback: Search Discogs for master_id by artist + album title"""
    try:
        query = f"{artist_name} {album_title}"
        data = _discogs_get("/database/search", {
            "q": query,
            "type": "master",
            "per_page": 5
        }, key, secret, sleep_after_ok=0.5)
        
        results = data.get("results", [])
        if not results:
            return None
        
        for result in results:
            result_title = result.get("title", "").lower()
            if album_title.lower() in result_title:
                return str(result.get("id", ""))
        
        return str(results[0].get("id", "")) if results else None
    except Exception:
        return None


def _search_discogs_release(artist_name: str, album_title: str, key: str, secret: str) -> Optional[str]:
    """Second fallback: Search Discogs for release_id by artist + album title"""
    try:
        query = f"{artist_name} {album_title}"
        data = _discogs_get("/database/search", {
            "q": query,
            "type": "release",
            "format": "vinyl",
            "per_page": 5
        }, key, secret, sleep_after_ok=0.5)
        
        results = data.get("results", [])
        if not results:
            return None
        
        for result in results:
            result_title = result.get("title", "").lower()
            if album_title.lower() in result_title:
                return str(result.get("id", ""))
        
        return str(results[0].get("id", "")) if results else None
    except Exception:
        return None


def _discogs_release_data(release_id: str, key: str, secret: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """Get rating and cover from a Discogs release (not master)"""
    if not release_id:
        return None, None, None
    
    try:
        rel = _discogs_get(f"/releases/{release_id}", {}, key, secret)
        rr = (rel.get("community") or {}).get("rating") or {}
        
        cover_image = None
        rel_images = rel.get("images", [])
        if rel_images and len(rel_images) > 0:
            cover_image = rel_images[0].get("uri")
        
        if rr.get("average") is None:
            print(f"[RATING] Release {release_id}: NO RATING")
            return None, None, cover_image
        
        rating = float(rr["average"])
        votes = int(rr.get("count", 0))
        print(f"[RATING] Release {release_id}: rating={rating}, votes={votes}")
        return rating, votes, cover_image
    except Exception as e:
        print(f"[RATING] Release {release_id}: ERROR - {str(e)}")
        return None, None, None


def _discogs_master_data(master_id: str, key: str, secret: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    if not master_id:
        return None, None, None

    try:
        data = _discogs_get(f"/masters/{master_id}", {}, key, secret)
        r = (data.get("community") or {}).get("rating") or {}
        
        cover_image = None
        images = data.get("images", [])
        if images and len(images) > 0:
            cover_image = images[0].get("uri")
        
        if r.get("average") is not None:
            rating = float(r["average"])
            votes = int(r.get("count", 0))
            print(f"[RATING] Master {master_id}: rating={rating}, votes={votes} (from master)")
            return rating, votes, cover_image

        main_rel = data.get("main_release")
        if not main_rel:
            print(f"[RATING] Master {master_id}: NO RATING (no master rating, no main_release)")
            return None, None, cover_image

        print(f"[RATING] Master {master_id}: No master rating, checking main_release {main_rel}")
        rel = _discogs_get(f"/releases/{main_rel}", {}, key, secret)
        rr = (rel.get("community") or {}).get("rating") or {}
        
        if not cover_image:
            rel_images = rel.get("images", [])
            if rel_images and len(rel_images) > 0:
                cover_image = rel_images[0].get("uri")
        
        if rr.get("average") is None:
            print(f"[RATING] Master {master_id}: NO RATING (main_release {main_rel} has no rating)")
            return None, None, cover_image
        
        rating = float(rr["average"])
        votes = int(rr.get("count", 0))
        print(f"[RATING] Master {master_id}: rating={rating}, votes={votes} (from main_release {main_rel})")
        return rating, votes, cover_image
    except Exception as e:
        print(f"[RATING] Master {master_id}: ERROR - {str(e)}")
        return None, None, None


def get_artist_studio_albums(artist_name: str, discogs_key: str, discogs_secret: str,
                              top_n: int = 3) -> List[StudioAlbum]:
    cached_albums = _get_cached_artist_albums(artist_name)
    if cached_albums:
        result = []
        for album_data in cached_albums[:top_n]:
            discogs_type = "master" if album_data.get("discogs_master_id") else "release"
            album = StudioAlbum(
                title=album_data["title"],
                year=album_data["year"],
                discogs_master_id=album_data.get("discogs_master_id"),
                discogs_release_id=album_data.get("discogs_release_id"),
                discogs_type=discogs_type,
                artist_name=artist_name,
                rating=album_data.get("rating"),
                votes=album_data.get("votes"),
                cover_image=album_data.get("cover_url")
            )
            result.append(album)
        return result
    
    mbid = _find_artist_mbid(artist_name)
    if not mbid:
        return []

    release_groups = _fetch_release_groups(mbid, limit=100)
    
    studio_albums: List[StudioAlbum] = []
    for rg in release_groups:
        if not _is_studio_album(rg, mbid):
            continue
        
        title = rg.get("title", "")
        year = _year_from_date(rg)
        rels = rg.get("relations", [])
        discogs_master_id = _discogs_master_from_rels(rels)
        
        album = StudioAlbum(
            title=title,
            year=year,
            discogs_master_id=discogs_master_id,
            artist_name=artist_name,
            rating=None,
            votes=None
        )
        studio_albums.append(album)
    
    albums_with_discogs = []
    albums_without_discogs = []
    
    for album in studio_albums:
        if album.discogs_master_id:
            albums_with_discogs.append(album)
        else:
            albums_without_discogs.append(album)
    
    for album in albums_without_discogs:
        master_id = _search_discogs_master(artist_name, album.title, discogs_key, discogs_secret)
        if master_id:
            album.discogs_master_id = master_id
            album.discogs_type = "master"
            albums_with_discogs.append(album)
        else:
            release_id = _search_discogs_release(artist_name, album.title, discogs_key, discogs_secret)
            if release_id:
                album.discogs_release_id = release_id
                album.discogs_type = "release"
                albums_with_discogs.append(album)
    
    def fetch_data(album: StudioAlbum) -> StudioAlbum:
        print(f"[ALBUM] Fetching rating for '{album.title}' ({album.year}) by {album.artist_name}")
        
        if album.discogs_type == "master" and album.discogs_master_id:
            rating, votes, cover_image = _discogs_master_data(album.discogs_master_id, discogs_key, discogs_secret)
        elif album.discogs_type == "release" and album.discogs_release_id:
            rating, votes, cover_image = _discogs_release_data(album.discogs_release_id, discogs_key, discogs_secret)
        else:
            print(f"[ALBUM] '{album.title}': No Discogs ID available")
            rating, votes, cover_image = None, None, None
        
        album.rating = rating
        album.votes = votes
        album.cover_image = cover_image
        
        if rating is not None:
            print(f"[ALBUM] ✓ '{album.title}': FINAL rating={rating}, votes={votes}")
        else:
            print(f"[ALBUM] ✗ '{album.title}': NO RATING - will be discarded")
        
        return album
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_album = {executor.submit(fetch_data, album): album for album in albums_with_discogs}
        for future in as_completed(future_to_album):
            try:
                future.result()
            except Exception:
                pass
    
    rated_albums = [a for a in albums_with_discogs if a.rating is not None]
    discarded_albums = [a for a in albums_with_discogs if a.rating is None]
    rated_albums.sort(key=lambda a: (a.rating or 0, a.votes or 0), reverse=True)
    
    total_found = len(albums_with_discogs)
    with_rating = len(rated_albums)
    without_rating = len(discarded_albums)
    
    if without_rating > 0:
        print(f"[STATS] ⚠️  {artist_name}: {without_rating} albums discarded (no rating from Discogs)")
        for album in discarded_albums:
            print(f"  - '{album.title}' ({album.year})")
    
    if rated_albums and mbid:
        artist_image = _get_artist_image_from_discogs(artist_name, discogs_key, discogs_secret)
        _save_artist_albums(artist_name, mbid, rated_albums, artist_image)
    
    print(f"[DB] ✓ Saved {with_rating} albums for '{artist_name}' to cache (discarded {without_rating})")
    
    return rated_albums[:top_n]


def get_artist_based_recommendations(artist_names: List[str], discogs_key: str,
                                      discogs_secret: str, top_per_artist: int = 3,
                                      progress_callback=None) -> List[Dict[str, Any]]:
    all_albums: List[StudioAlbum] = []
    
    for idx, artist_name in enumerate(artist_names, 1):
        if progress_callback:
            progress_callback(idx, artist_name)
        
        artist_albums = get_artist_studio_albums(artist_name, discogs_key, discogs_secret, top_n=top_per_artist)
        all_albums.extend(artist_albums)
    
    all_albums.sort(key=lambda a: (a.rating or 0, a.votes or 0), reverse=True)
    
    recommendations = []
    for album in all_albums:
        rec = {
            "album_name": album.title,
            "artist_name": album.artist_name,
            "year": album.year,
            "rating": album.rating,
            "votes": album.votes,
            "discogs_master_id": album.discogs_master_id or album.discogs_release_id,
            "discogs_type": album.discogs_type,
            "image_url": album.cover_image or "https://via.placeholder.com/300x300?text=No+Cover",
            "source": "artist_based"
        }
        recommendations.append(rec)
    
    return recommendations
