import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from typing import List
from pydantic import BaseModel
from libs.shared.utils import log_event
from .auth import LastFMAuthManager
from .lastfm_client import LastFMClient


from typing import Dict
import time
import asyncio

auth_managers: Dict[str, tuple[LastFMAuthManager, float]] = {}
lastfm_clients: Dict[str, LastFMClient] = {}
AUTH_TOKEN_TTL = 600


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
        token = await temp_auth.get_token()
        if not token:
            raise HTTPException(status_code=500, detail="Failed to get Last.fm token")
        
        auth_url = temp_auth.get_auth_url(token)
        auth_managers[token] = (temp_auth, time.time())
        log_event("lastfm-service", "INFO", f"Generated auth URL with token: {token[:10]}...")
        
        return {
            "auth_url": auth_url,
            "token": token
        }
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to generate auth URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/callback")
async def auth_callback(token: str):
    try:
        if token not in auth_managers:
            raise HTTPException(status_code=400, detail="Invalid token")
        
        auth_manager, created_time = auth_managers[token]
        
        if time.time() - created_time > AUTH_TOKEN_TTL:
            del auth_managers[token]
            raise HTTPException(status_code=400, detail="Token expired")
        
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
        
        del auth_managers[token]
        
        return {
            "status": "success",
            "username": username
        }
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Auth callback failed: {str(e)}")
        if token in auth_managers:
            del auth_managers[token]
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
        albums = await client.get_top_albums(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(albums)} top albums for {request.username}, period={period}")
        return {"albums": albums, "total": len(albums)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top albums: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
