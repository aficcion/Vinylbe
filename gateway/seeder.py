import os
import re
import asyncio
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from gateway.db_utils import get_db_connection

MB_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE = "https://api.discogs.com"
HEADERS = {"User-Agent": "VinylRecommendationSystem/1.0"}

DISCOGS_KEY = os.getenv("DISCOGS_CONSUMER_KEY", "") or os.getenv("DISCOGS_KEY", "")
DISCOGS_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET", "") or os.getenv("DISCOGS_SECRET", "")

_RE_DISCOGS_MASTER = re.compile(
    r"https?://(?:www\.)?discogs\.com/(?:[a-z]{2}/)?master/(\d+)", re.I
)

async def _mb_get(client: httpx.AsyncClient, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """MusicBrainz API call with retry"""
    url = f"{MB_BASE}{path}"
    params = {**params, "fmt": "json"}
    
    for attempt in range(3):
        try:
            r = await client.get(url, params=params)
            if r.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(1)
                continue
            r.raise_for_status()
            await asyncio.sleep(1.0) # Rate limiting
            return r.json()
        except Exception as e:
            await asyncio.sleep(1)
    
    return {}

async def _discogs_get(client: httpx.AsyncClient, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Discogs API call with retry"""
    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": DISCOGS_KEY, "secret": DISCOGS_SECRET}
    
    for attempt in range(3):
        try:
            r = await client.get(url, params=params)
            if r.status_code == 429:
                log_event("seeder", "WARNING", f"Discogs rate limit hit (429) on {path}, retrying...")
                await asyncio.sleep(2)
                continue
            
            if r.status_code != 200:
                log_event("seeder", "WARNING", f"Discogs API error {r.status_code} on {path}: {r.text[:100]}")
                r.raise_for_status()
                
            await asyncio.sleep(0.5)
            return r.json()
        except Exception as e:
            log_event("seeder", "ERROR", f"Discogs request failed (attempt {attempt+1}): {str(e)}")
            await asyncio.sleep(1)
            
    return {}

async def find_artist_mbid(client: httpx.AsyncClient, name: str) -> Optional[str]:
    try:
        data = await _mb_get(client, "/artist", {"query": f'artist:"{name}"', "limit": 10})
        artists = data.get("artists", []) or []
        if not artists:
            return None
        exact = [a for a in artists if a.get("name", "").lower() == name.lower()]
        chosen = exact[0] if exact else artists[0]
        return chosen.get("id")
    except Exception:
        return None

async def fetch_studio_albums(client: httpx.AsyncClient, artist_mbid: str) -> List[Dict[str, Any]]:
    try:
        data = await _mb_get(
            client,
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
    except Exception:
        return []

from libs.shared.utils import log_event

async def get_discogs_master_data(client: httpx.AsyncClient, master_id: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    if not master_id:
        return None, None, None
    
    try:
        log_event("seeder", "DEBUG", f"Fetching Discogs master data for ID: {master_id}")
        master_data = await _discogs_get(client, f"/masters/{master_id}", {})
        
        if not master_data:
            log_event("seeder", "WARNING", f"No data returned for master {master_id}")
            return None, None, None
            
        # Get cover from master
        cover_url = None
        images = master_data.get("images", [])
        if images and len(images) > 0:
            cover_url = images[0].get("uri")
            
        # Get rating from main release
        rating = None
        votes = None
        
        main_release_url = master_data.get("main_release_url")
        if main_release_url:
            # Extract release ID from URL to use _discogs_get with path
            # URL format: https://api.discogs.com/releases/12345
            release_id = main_release_url.split("/")[-1]
            
            log_event("seeder", "DEBUG", f"Fetching main release {release_id} for master {master_id} to get rating")
            release_data = await _discogs_get(client, f"/releases/{release_id}", {})
            
            if release_data:
                r = (release_data.get("community") or {}).get("rating") or {}
                if r.get("average") is not None:
                    try:
                        rating = float(r["average"])
                        votes = int(r.get("count", 0))
                        log_event("seeder", "DEBUG", f"Found rating {rating} ({votes} votes) for master {master_id}")
                    except (ValueError, TypeError) as e:
                        log_event("seeder", "ERROR", f"Error parsing rating for release {release_id}: {e}")
        
        if rating is None:
            log_event("seeder", "DEBUG", f"No rating found for master {master_id} (checked main release)")
        
        return rating, votes, cover_url
    except Exception as e:
        log_event("seeder", "ERROR", f"Exception in get_discogs_master_data for {master_id}: {str(e)}")
        return None, None, None

async def get_artist_image_from_discogs(client: httpx.AsyncClient, artist_name: str) -> Optional[str]:
    try:
        data = await _discogs_get(client, "/database/search", {
            "q": artist_name,
            "type": "artist",
            "per_page": 1
        })
        results = data.get("results", [])
        if results:
            return results[0].get("cover_image")
    except Exception:
        pass
    return None

async def sync_artist(artist_id: int) -> Dict[str, Any]:
    """Sync artist data from external sources"""
    conn = get_db_connection()
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            cur = conn.cursor()
            cur.execute("SELECT name, mbid FROM artists WHERE id = ?", (artist_id,))
            row = cur.fetchone()
            if not row:
                return {"status": "error", "message": "Artist not found"}
            
            artist_name = row['name']
            current_mbid = row['mbid']
            
            # 1. Find/Update MBID
            mbid = await find_artist_mbid(client, artist_name)
            if not mbid:
                # Fallback to existing if we can't find it (maybe API down)
                mbid = current_mbid
            
            if not mbid:
                return {"status": "error", "message": "Could not find MBID for artist"}
            
            # 2. Get Image
            image_url = await get_artist_image_from_discogs(client, artist_name)
            
            # Update Artist
            cur.execute(
                "UPDATE artists SET mbid = ?, image_url = COALESCE(?, image_url), last_updated = ? WHERE id = ?",
                (mbid, image_url, datetime.now(), artist_id)
            )
            
            # 3. Fetch Albums
            albums = await fetch_studio_albums(client, mbid)
            
            added = 0
            updated = 0
            
            for album in albums:
                # Check if exists
                cur.execute(
                    "SELECT id, discogs_master_id FROM albums WHERE artist_id = ? AND title = ?",
                    (artist_id, album['title'])
                )
                existing_album = cur.fetchone()
                
                rating, votes, cover_url = None, None, None
                if album["discogs_master_id"]:
                    rating, votes, cover_url = await get_discogs_master_data(client, album["discogs_master_id"])
                
                if existing_album:
                    # Update
                    cur.execute("""
                        UPDATE albums 
                        SET year = ?, 
                            discogs_master_id = COALESCE(?, discogs_master_id),
                            rating = COALESCE(?, rating),
                            votes = COALESCE(?, votes),
                            cover_url = COALESCE(?, cover_url),
                            last_updated = ?
                        WHERE id = ?
                    """, (
                        album['year'], 
                        album['discogs_master_id'], 
                        rating, 
                        votes, 
                        cover_url, 
                        datetime.now(), 
                        existing_album['id']
                    ))
                    updated += 1
                else:
                    # Insert
                    cur.execute("""
                        INSERT INTO albums (artist_id, title, year, discogs_master_id, rating, votes, cover_url, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        artist_id, 
                        album['title'], 
                        album['year'], 
                        album['discogs_master_id'], 
                        rating, 
                        votes, 
                        cover_url, 
                        datetime.now()
                    ))
                    added += 1
            
            conn.commit()
            return {
                "status": "success", 
                "message": f"Synced {artist_name}: {added} albums added, {updated} updated",
                "details": {"added": added, "updated": updated}
            }
            
        finally:
            conn.close()

async def sync_album(album_id: int) -> Dict[str, Any]:
    """Sync single album data from Discogs"""
    conn = get_db_connection()
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            cur = conn.cursor()
            cur.execute("SELECT title, discogs_master_id FROM albums WHERE id = ?", (album_id,))
            row = cur.fetchone()
            if not row:
                return {"status": "error", "message": "Album not found"}
            
            master_id = row['discogs_master_id']
            if not master_id:
                return {"status": "error", "message": "Album has no Discogs Master ID"}
            
            rating, votes, cover_url = await get_discogs_master_data(client, master_id)
            
            if rating is None and cover_url is None:
                return {"status": "warning", "message": "No data found on Discogs"}
            
            cur.execute("""
                UPDATE albums 
                SET rating = COALESCE(?, rating),
                    votes = COALESCE(?, votes),
                    cover_url = COALESCE(?, cover_url),
                    last_updated = ?
                WHERE id = ?
            """, (rating, votes, cover_url, datetime.now(), album_id))
            
            conn.commit()
            return {
                "status": "success", 
                "message": f"Updated album {row['title']}",
                "details": {"rating": rating, "votes": votes}
            }
            
        finally:
            conn.close()
