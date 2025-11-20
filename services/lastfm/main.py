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


auth_manager = LastFMAuthManager()
lastfm_client = None


class TimeRangeRequest(BaseModel):
    time_range: str = "medium_term"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("lastfm-service", "INFO", "Starting Last.fm service")
    yield
    log_event("lastfm-service", "INFO", "Shutting down Last.fm service")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "lastfm"}


@app.get("/auth/url")
async def get_auth_url():
    try:
        token = await auth_manager.get_token()
        if not token:
            raise HTTPException(status_code=500, detail="Failed to get Last.fm token")
        
        auth_url = auth_manager.get_auth_url(token)
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
        success = await auth_manager.get_session(token)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to get session")
        
        username = auth_manager.get_username()
        log_event("lastfm-service", "INFO", f"User authenticated: {username}")
        
        global lastfm_client
        api_key = os.getenv("LASTFM_API_KEY")
        lastfm_client = LastFMClient(api_key, username)
        await lastfm_client.start()
        
        return {
            "status": "success",
            "username": username
        }
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Auth callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/status")
async def auth_status():
    return {
        "authenticated": auth_manager.is_authenticated(),
        "username": auth_manager.get_username()
    }


@app.post("/top-tracks")
async def get_top_tracks(request: TimeRangeRequest):
    if not auth_manager.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not lastfm_client:
        raise HTTPException(status_code=500, detail="Client not initialized")
    
    period_map = {
        "short_term": "7day",
        "medium_term": "3month",
        "long_term": "12month"
    }
    
    period = period_map.get(request.time_range, "3month")
    
    try:
        tracks = await lastfm_client.get_top_tracks(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(tracks)} top tracks for period={period}")
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top tracks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/top-artists")
async def get_top_artists(request: TimeRangeRequest):
    if not auth_manager.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not lastfm_client:
        raise HTTPException(status_code=500, detail="Client not initialized")
    
    period_map = {
        "short_term": "7day",
        "medium_term": "3month",
        "long_term": "12month"
    }
    
    period = period_map.get(request.time_range, "3month")
    
    try:
        artists = await lastfm_client.get_top_artists(period=period)
        log_event("lastfm-service", "INFO", f"Retrieved {len(artists)} top artists for period={period}")
        return {"artists": artists, "total": len(artists)}
    except Exception as e:
        log_event("lastfm-service", "ERROR", f"Failed to get top artists: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
