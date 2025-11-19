import os
import time
from typing import List, Optional, Tuple
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Last.fm Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
DISCOGS_BASE = "https://api.discogs.com"
DISCOGS_KEY = os.getenv("DISCOGS_KEY")
DISCOGS_SECRET = os.getenv("DISCOGS_SECRET")

HEADERS = {
    "User-Agent": "Vinilogy/1.0 (+https://vinilogy.com; contact@vinilogy.com)"
}


class ArtistSearchResult(BaseModel):
    name: str
    image_url: Optional[str] = None
    genres: List[str] = []
    mbid: Optional[str] = None


class SearchResponse(BaseModel):
    artists: List[ArtistSearchResult]
    search_time_ms: float


class LastFMClient:
    def __init__(self, api_key: str, base_url: str = LASTFM_BASE_URL,
                 discogs_key: Optional[str] = None, discogs_secret: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.discogs_key = discogs_key
        self.discogs_secret = discogs_secret

    def _clean_artist_name(self, name: str) -> str:
        """Remove Discogs ID numbers like (11), (3) from artist names"""
        import re
        # Remove patterns like (11), (3), (2) at the end of the name
        cleaned = re.sub(r'\s*\(\d+\)\s*$', '', name)
        return cleaned.strip()

    def search_artists_discogs(self, query: str, limit: int = 5) -> Tuple[List[ArtistSearchResult], float]:
        start_time = time.time()

        if not self.discogs_key or not self.discogs_secret:
            return [], 0.0

        try:
            params = {
                "q": query.strip(),
                "type": "artist",
                "key": self.discogs_key,
                "secret": self.discogs_secret,
                "per_page": str(limit * 2),  # Fetch more to account for duplicates
            }

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{DISCOGS_BASE}/database/search", params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])

            # Track seen names and their first image
            seen_names = {}
            artists: List[ArtistSearchResult] = []

            for res in results:
                raw_title = res.get("title", "")
                thumb = res.get("thumb")

                # Clean the name
                clean_name = self._clean_artist_name(raw_title)

                # Skip if we've already seen this clean name
                if clean_name in seen_names:
                    continue

                # Mark as seen and store the first image
                seen_names[clean_name] = thumb

                # Get genres using the CLEAN name
                genres = self._get_genres_from_lastfm(clean_name)

                artist = ArtistSearchResult(
                    name=clean_name,
                    image_url=thumb,
                    genres=genres,
                    mbid=None
                )
                artists.append(artist)

                # Stop when we have enough unique artists
                if len(artists) >= limit:
                    break

            elapsed = time.time() - start_time
            return artists, elapsed

        except Exception as e:
            logger.warning(f"Discogs search failed: {e}, falling back to Last.fm")

        return self._search_artists_lastfm(query.strip(), limit=limit, start_time=start_time)

    def _get_genres_from_lastfm(self, artist_name: str) -> List[str]:
        try:
            params = {
                "method": "artist.getTopTags",
                "artist": artist_name,
                "api_key": self.api_key,
                "format": "json",
            }

            with httpx.Client(timeout=5.0) as client:
                resp = client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            tags = data.get("toptags", {}).get("tag", [])
            if isinstance(tags, dict):
                tags = [tags]

            genres = []
            for tag in tags[:3]:
                tag_name = tag.get("name", "")
                if tag_name:
                    genres.append(tag_name)

            return genres
        except Exception as e:
            logger.debug(f"Failed to get genres for {artist_name}: {e}")
            return []

    def _search_artists_lastfm(self, query: str, limit: int, start_time: float) -> Tuple[List[ArtistSearchResult], float]:
        try:
            params = {
                "method": "artist.search",
                "artist": query,
                "api_key": self.api_key,
                "format": "json",
                "limit": str(limit),
            }

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            results_node = data.get("results", {}).get("artistmatches", {}).get("artist", [])
            if isinstance(results_node, dict):
                results_node = [results_node]

            artists: List[ArtistSearchResult] = []
            for res in results_node[:limit]:
                name = res.get("name")
                if not name:
                    continue

                mbid = res.get("mbid")
                if mbid == "":
                    mbid = None

                genres = self._get_genres_from_lastfm(name)

                artist = ArtistSearchResult(
                    name=name,
                    image_url=None,
                    genres=genres,
                    mbid=mbid
                )
                artists.append(artist)

            elapsed = time.time() - start_time
            return artists, elapsed

        except Exception as e:
            logger.error(f"Last.fm search failed: {e}")
            elapsed = time.time() - start_time
            return [], elapsed


client = LastFMClient(
    api_key=LASTFM_API_KEY or "",
    discogs_key=DISCOGS_KEY,
    discogs_secret=DISCOGS_SECRET
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lastfm"}


@app.get("/search", response_model=SearchResponse)
async def search_artists(q: str = Query(..., min_length=4, description="Search query (min 4 characters)")):
    if not LASTFM_API_KEY:
        raise HTTPException(status_code=500, detail="LASTFM_API_KEY not configured")

    artists, search_time = client.search_artists_discogs(q, limit=5)

    return SearchResponse(
        artists=artists,
        search_time_ms=search_time * 1000
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3004)