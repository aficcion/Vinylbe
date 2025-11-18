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
                 votes: Optional[int] = None):
        self.title = title
        self.year = year
        self.discogs_master_id = discogs_master_id
        self.artist_name = artist_name
        self.rating = rating
        self.votes = votes


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
                 sleep_after_ok: float = 0.25):
    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": key, "secret": secret}
    r = CLIENT.get(url, params=params)
    r.raise_for_status()
    time.sleep(sleep_after_ok)
    return r.json()


def _discogs_master_rating(master_id: str, key: str, secret: str) -> Tuple[Optional[float], Optional[int]]:
    if not master_id:
        return None, None

    try:
        data = _discogs_get(f"/masters/{master_id}", {}, key, secret)
        r = (data.get("community") or {}).get("rating") or {}
        if r.get("average") is not None:
            return float(r["average"]), int(r.get("count", 0))

        main_rel = data.get("main_release")
        if not main_rel:
            return None, None

        rel = _discogs_get(f"/releases/{main_rel}", {}, key, secret)
        rr = (rel.get("community") or {}).get("rating") or {}
        if rr.get("average") is None:
            return None, None
        return float(rr["average"]), int(rr.get("count", 0))
    except Exception:
        return None, None


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
    
    albums_with_master = [a for a in studio_albums if a.discogs_master_id]
    
    def fetch_rating(album: StudioAlbum) -> StudioAlbum:
        rating, votes = _discogs_master_rating(album.discogs_master_id, discogs_key, discogs_secret)
        album.rating = rating
        album.votes = votes
        return album
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_album = {executor.submit(fetch_rating, album): album for album in albums_with_master}
        for future in as_completed(future_to_album):
            try:
                future.result()
            except Exception:
                pass
    
    rated_albums = [a for a in albums_with_master if a.rating is not None]
    rated_albums.sort(key=lambda a: (a.rating or 0, a.votes or 0), reverse=True)
    
    return rated_albums[:top_n]


def get_artist_based_recommendations(artist_names: List[str], discogs_key: str,
                                      discogs_secret: str, top_per_artist: int = 3) -> List[Dict[str, Any]]:
    all_albums: List[StudioAlbum] = []
    
    for artist_name in artist_names:
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
            "discogs_master_id": album.discogs_master_id,
            "source": "artist_based"
        }
        recommendations.append(rec)
    
    return recommendations
