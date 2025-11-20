import json
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx
import re
from typing import Optional, Dict, Any, List, Tuple

MB_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE = "https://api.discogs.com"
HEADERS = {"User-Agent": "VinylRecommendationSystem/1.0"}

DISCOGS_KEY = os.getenv("DISCOGS_CONSUMER_KEY", "")
DISCOGS_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET", "")

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


def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def _mb_get(path: str, params: Dict[str, Any], tries: int = 5,
            sleep_after_ok: float = 1.0) -> Dict[str, Any]:
    """MusicBrainz API call with retry"""
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

    raise RuntimeError(f"MusicBrainz failed: {last_exc}")


def _discogs_get(path: str, params: Dict[str, Any],
                 sleep_after_ok: float = 0.5,
                 tries: int = 5):
    """Discogs API call with retry and rate limiting"""
    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": DISCOGS_KEY, "secret": DISCOGS_SECRET}
    last_exc = None
    backoff = 1.0
    
    for attempt in range(1, tries + 1):
        try:
            r = CLIENT.get(url, params=params)
            if r.status_code == 429:
                if attempt < tries:
                    print(f"  [DISCOGS] Rate limit hit, retrying in {backoff}s... (attempt {attempt}/{tries})")
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 10.0)
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


def find_artist_mbid(name: str) -> Optional[str]:
    """Find artist MBID from MusicBrainz"""
    try:
        data = _mb_get("/artist", {"query": f'artist:"{name}"', "limit": 10})
        artists = data.get("artists", []) or []
        if not artists:
            return None
        exact = [a for a in artists if a.get("name", "").lower() == name.lower()]
        chosen = exact[0] if exact else artists[0]
        return chosen.get("id")
    except Exception as e:
        print(f"  [ERROR] Could not find MBID for {name}: {e}")
        return None


def fetch_studio_albums(artist_mbid: str, artist_name: str) -> List[Dict[str, Any]]:
    """Fetch studio albums from MusicBrainz"""
    try:
        data = _mb_get(
            "/release-group",
            {
                "artist": artist_mbid,
                "primary-type": "Album",
                "inc": "artist-credits+url-rels",
                "limit": 100,
            }
        )
        release_groups = data.get("release-groups", []) or []
        
        studio_albums = []
        for rg in release_groups:
            if rg.get("primary-type") != "Album":
                continue
            if rg.get("secondary-types"):
                continue
            
            ac = rg.get("artist-credit") or []
            if len(ac) != 1:
                continue
            if (ac[0].get("artist") or {}).get("id") != artist_mbid:
                continue
            
            title = rg.get("title", "")
            first_release = rg.get("first-release-date", "")
            year = first_release.split("-")[0] if first_release else ""
            
            relations = rg.get("relations") or []
            discogs_master_id = None
            for rel in relations:
                if rel.get("type") == "discogs":
                    url = (rel.get("url") or {}).get("resource", "")
                    m = _RE_DISCOGS_MASTER.search(url)
                    if m:
                        discogs_master_id = m.group(1)
                        break
            
            studio_albums.append({
                "title": title,
                "year": year,
                "discogs_master_id": discogs_master_id
            })
        
        return studio_albums
    except Exception as e:
        print(f"  [ERROR] Could not fetch albums for {artist_name}: {e}")
        return []


def get_discogs_master_data(master_id: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """Get rating, votes, and cover from Discogs master"""
    if not master_id:
        return None, None, None
    
    try:
        data = _discogs_get(f"/masters/{master_id}", {})
        r = (data.get("community") or {}).get("rating") or {}
        
        cover_url = None
        images = data.get("images", [])
        if images and len(images) > 0:
            cover_url = images[0].get("uri")
        
        rating = float(r["average"]) if r.get("average") is not None else None
        votes = int(r.get("count", 0)) if r.get("average") is not None else None
        
        return rating, votes, cover_url
    except Exception as e:
        print(f"  [WARNING] Could not get Discogs data for master {master_id}: {e}")
        return None, None, None


def get_artist_image_from_discogs(artist_name: str) -> Optional[str]:
    """Get artist image from Discogs search"""
    try:
        data = _discogs_get("/database/search", {
            "q": artist_name,
            "type": "artist",
            "per_page": 1
        })
        results = data.get("results", [])
        if results:
            return results[0].get("cover_image")
    except Exception as e:
        print(f"  [WARNING] Could not get artist image for {artist_name}: {e}")
    return None


def seed_artist(conn, artist_name: str):
    """Seed a single artist with all albums"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print(f"\n{'='*60}")
    print(f"Processing: {artist_name}")
    print(f"{'='*60}")
    
    cursor.execute("SELECT id FROM artists WHERE name = %s", (artist_name,))
    existing = cursor.fetchone()
    if existing:
        print(f"✓ Artist '{artist_name}' already exists in database (ID: {existing['id']}), skipping...")
        return
    
    print(f"[1/4] Finding MusicBrainz ID...")
    mbid = find_artist_mbid(artist_name)
    if not mbid:
        print(f"✗ Could not find MBID for {artist_name}, skipping...")
        return
    print(f"✓ Found MBID: {mbid}")
    
    print(f"[2/4] Fetching discography...")
    albums = fetch_studio_albums(mbid, artist_name)
    print(f"✓ Found {len(albums)} studio albums")
    
    print(f"[3/4] Getting artist image...")
    image_url = get_artist_image_from_discogs(artist_name)
    if image_url:
        print(f"✓ Got artist image")
    
    print(f"[4/4] Saving to database...")
    cursor.execute(
        "INSERT INTO artists (name, mbid, image_url) VALUES (%s, %s, %s) RETURNING id",
        (artist_name, mbid, image_url)
    )
    artist_id = cursor.fetchone()["id"]
    print(f"✓ Artist saved (ID: {artist_id})")
    
    albums_saved = 0
    for i, album in enumerate(albums, 1):
        print(f"  [{i}/{len(albums)}] Processing: {album['title']} ({album['year']})")
        
        rating, votes, cover_url = None, None, None
        if album["discogs_master_id"]:
            rating, votes, cover_url = get_discogs_master_data(album["discogs_master_id"])
            if rating:
                print(f"    ✓ Rating: {rating:.1f}/5 ({votes} votes)")
        
        cursor.execute(
            """INSERT INTO albums (artist_id, title, year, discogs_master_id, rating, votes, cover_url) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (artist_id, title, year) DO NOTHING""",
            (artist_id, album["title"], album["year"], album["discogs_master_id"], rating, votes, cover_url)
        )
        albums_saved += 1
    
    conn.commit()
    print(f"✓ Saved {albums_saved} albums for {artist_name}")
    print(f"{'='*60}\n")


def main():
    """Main seeding function"""
    print("\n" + "="*60)
    print("VINYL RECOMMENDATION SYSTEM - DATABASE SEEDER")
    print("="*60 + "\n")
    
    if not DISCOGS_KEY or not DISCOGS_SECRET:
        print("✗ ERROR: DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET environment variables must be set")
        return
    
    with open("seed_artists.json", "r") as f:
        artist_names = json.load(f)
    
    print(f"📋 Loaded {len(artist_names)} artists to seed")
    print(f"⏱️  Estimated time: ~{len(artist_names) * 2} minutes (with rate limiting)\n")
    
    conn = get_db_connection()
    
    successful = 0
    failed = 0
    
    for i, artist_name in enumerate(artist_names, 1):
        print(f"[{i}/{len(artist_names)}] ", end="")
        try:
            seed_artist(conn, artist_name)
            successful += 1
        except Exception as e:
            print(f"✗ FAILED to seed {artist_name}: {e}")
            failed += 1
    
    conn.close()
    
    print("\n" + "="*60)
    print("SEEDING COMPLETE")
    print("="*60)
    print(f"✓ Successful: {successful}")
    print(f"✗ Failed: {failed}")
    print(f"📊 Total: {len(artist_names)}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
