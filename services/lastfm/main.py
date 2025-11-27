import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
from typing import List, Optional, Tuple
from pydantic import BaseModel
from libs.shared.utils import log_event
from .auth import LastFMAuthManager
from .lastfm_client import LastFMClient

from typing import Dict
import time
import asyncio
import httpx
import re

auth_managers: Dict[str, tuple[LastFMAuthManager, float]] = {}
lastfm_clients: Dict[str, LastFMClient] = {}
AUTH_TOKEN_TTL = 600

DISCOGS_BASE = "https://api.discogs.com"


class ArtistSearchResult(BaseModel):
    name: str
    image_url: Optional[str] = None
    genres: List[str] = []


class SearchResponse(BaseModel):
    artists: List[ArtistSearchResult]


async def cleanup_expired_tokens():
    """Remove expired auth tokens (older than 10 minutes)"""
    while True:
        try:
            await asyncio.sleep(60)
            now = time.time()
            expired = [token for token, (_, created) in auth_managers.items() if now - created > AUTH_TOKEN_TTL]
            for token in expired:
                log_event("lastfm-service", "INFO", f"Removing expired auth token: {token[:10]}...")
                del auth_managers[token]
        except Exception as e:
            log_event("lastfm-service", "ERROR", f"Error cleaning tokens: {str(e)}")


class TimeRangeRequest(BaseModel):
    time_range: str = "medium_term"
    username: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("lastfm-service", "INFO", "Starting Last.fm service")
    cleanup_task = asyncio.create_task(cleanup_expired_tokens())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        for client in list(lastfm_clients.values()):
            await client.close()
        log_event("lastfm-service", "INFO", "Shutting down Last.fm service")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "lastfm"}


@app.get("/auth/url")
async def get_auth_url():
    try:
        temp_auth = LastFMAuthManager()
        # Web Flow: We don't pre-generate token. Last.fm generates it.
        auth_url = temp_auth.get_auth_url()
        
        log_event("lastfm-service", "INFO", "Generated auth URL (Web Flow)")
        
        return {
            "auth_url": auth_url
        }
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to generate auth URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/callback")
async def auth_callback(token: str):
    try:
        # Web Flow: We receive the token from Last.fm redirect
        # We don't have state in auth_managers, so we create a new manager
        auth_manager = LastFMAuthManager()
        
        success = await auth_manager.get_session(token)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to get session")
        
        username = auth_manager.get_username()
        log_event("lastfm-service", "INFO", f"User authenticated: {username}")
        
        if username in lastfm_clients:
            log_event("lastfm-service", "INFO", f"Closing existing client for {username}")
            old_client = lastfm_clients[username]
            await old_client.close()
            del lastfm_clients[username]
        
        api_key = os.getenv("LASTFM_API_KEY")
        client = LastFMClient(api_key, username)
        await client.start()
        lastfm_clients[username] = client
        
        return {
            "status": "success",
            "username": username
        }
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Auth callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/status")
async def auth_status(username: str = None):
    if username and username in lastfm_clients:
        return {
            "authenticated": True,
            "username": username
        }
    return {
        "authenticated": False,
        "username": None
    }


@app.post("/top-tracks")
async def get_top_tracks(request: TimeRangeRequest):
    if request.username not in lastfm_clients:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    client = lastfm_clients[request.username]
    
    period_map = {
        "short_term": "7day",
        "medium_term": "3month",
        "long_term": "12month"
    }
    
    period = period_map.get(request.time_range, "3month")
    
    try:
        tracks = await client.get_top_tracks(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(tracks)} top tracks for {request.username}, period={period}")
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top tracks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/top-artists")
async def get_top_artists(request: TimeRangeRequest):
    if request.username not in lastfm_clients:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    client = lastfm_clients[request.username]
    
    period_map = {
        "short_term": "7day",
        "medium_term": "3month",
        "long_term": "12month"
    }
    
    period = period_map.get(request.time_range, "3month")
    
    try:
        artists = await client.get_top_artists(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(artists)} top artists for {request.username}, period={period}")
        return {"artists": artists, "total": len(artists)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top artists: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/top-albums")
async def get_top_albums(request: TimeRangeRequest):
    client = lastfm_clients.get(request.username)
    if not client:
        # Fallback: Create a new client on the fly (Stateless mode)
        # This is crucial for serverless environments (Railway) where memory is not persistent across requests/restarts
        api_key = os.getenv("LASTFM_API_KEY")
        if not api_key:
             raise HTTPException(status_code=500, detail="LASTFM_API_KEY not configured")
        
        client = LastFMClient(api_key, request.username)
        await client.start()
        lastfm_clients[request.username] = client
        log_event("lastfm-service", "INFO", f"Created new client for {request.username} (stateless fallback)")
    
    period_map = {
        "short_term": "7day",
        "medium_term": "3month",
        "long_term": "12month"
    }
    
    period = period_map.get(request.time_range, "3month")
    
    try:
        albums = await client.get_top_albums(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(albums)} top albums for {request.username}, period={period}")
        return {"albums": albums, "total": len(albums)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top albums: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _clean_artist_name(name: str) -> str:
    """Remove Discogs ID numbers like (11), (3) from artist names"""
    cleaned = re.sub(r'\s*\(\d+\)\s*$', '', name)
    return cleaned.strip()


async def _get_genres_from_lastfm(artist_name: str) -> List[str]:
    """Get genres/tags from Last.fm for an artist"""
    try:
        api_key = os.getenv("LASTFM_API_KEY")
        async with httpx.AsyncClient(timeout=5.0) as client:
            params = {
                "method": "artist.getTopTags",
                "artist": artist_name,
                "api_key": api_key,
                "format": "json"
            }
            resp = await client.get("https://ws.audioscrobbler.com/2.0/", params=params)
            if resp.status_code == 200:
                data = resp.json()
                tags = data.get("toptags", {}).get("tag", [])
                if isinstance(tags, list):
                    return [tag.get("name", "") for tag in tags[:5]]
                elif isinstance(tags, dict):
                    return [tags.get("name", "")]
    except Exception as e:
        log_event("lastfm-service", "WARNING", f"Failed to get genres for {artist_name}: {str(e)}")
    return []


@app.get("/search", response_model=SearchResponse)
async def search_artists(q: str = Query(..., min_length=2)):
    """Search artists via Discogs, clean names, deduplicate, fetch Last.fm genres"""
    try:
        discogs_key = os.getenv("DISCOGS_CONSUMER_KEY") or os.getenv("DISCOGS_KEY")
        discogs_secret = os.getenv("DISCOGS_CONSUMER_SECRET") or os.getenv("DISCOGS_SECRET")
        
        if not discogs_key or not discogs_secret:
            raise HTTPException(status_code=500, detail="Discogs credentials not configured")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "q": q.strip(),
                "type": "artist",
                "key": discogs_key,
                "secret": discogs_secret,
                "per_page": "20"
            }
            
            resp = await client.get(f"{DISCOGS_BASE}/database/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            
            results = data.get("results", [])
            
            seen_names = {}
            artists: List[ArtistSearchResult] = []
            
            for res in results:
                raw_title = res.get("title", "")
                thumb = res.get("thumb")
                
                clean_name = _clean_artist_name(raw_title)
                
                if clean_name in seen_names:
                    continue
                
                seen_names[clean_name] = thumb
                
                genres = await _get_genres_from_lastfm(clean_name)
                
                artist = ArtistSearchResult(
                    name=clean_name,
                    image_url=thumb,
                    genres=genres
                )
                artists.append(artist)
                
                if len(artists) >= 10:
                    break
            
            log_event("lastfm-service", "INFO", f"Found {len(artists)} unique artists for query: {q}")
            return SearchResponse(artists=artists)
            
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Artist search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
