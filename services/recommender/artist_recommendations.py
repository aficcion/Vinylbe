import os
import time
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

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


class StudioAlbum:
    def __init__(self, title: str, year: str, discogs_master_id: str,
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
                    print(f"[DISCOGS] Rate limit hit (429), retrying in {backoff}s... (attempt {attempt}/{tries})")
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
    rated_albums.sort(key=lambda a: (a.rating or 0, a.votes or 0), reverse=True)
    
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
