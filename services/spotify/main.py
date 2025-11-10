from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from libs.shared.models import Track, Artist, ServiceHealth, LogEvent
from libs.shared.utils import create_http_client, log_event
from .auth import SpotifyAuthManager
from .spotify_client import SpotifyClient

auth_manager = SpotifyAuthManager()
spotify_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global spotify_client
    spotify_client = SpotifyClient(auth_manager)
    await spotify_client.start()
    log_event("spotify-service", "INFO", "Spotify Service started")
    yield
    await spotify_client.stop()
    log_event("spotify-service", "INFO", "Spotify Service stopped")


app = FastAPI(lifespan=lifespan, title="Spotify Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return ServiceHealth(
        service_name="spotify-service",
        status="healthy" if spotify_client and spotify_client.is_ready() else "unhealthy"
    ).dict()


@app.get("/auth/login")
async def spotify_login():
    log_event("spotify-service", "INFO", "Login request received")
    auth_url = auth_manager.get_auth_url()
    return {"authorize_url": auth_url}


@app.get("/auth/callback")
async def spotify_callback(code: str = Query(...)):
    log_event("spotify-service", "INFO", "Callback received", {"code_length": len(code)})
    success = await auth_manager.exchange_code_for_token(code)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to exchange code for token")
    log_event("spotify-service", "INFO", "Authentication successful")
    return {"status": "ok", "message": "Authenticated successfully"}


@app.get("/me")
async def get_user_profile():
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    profile = await spotify_client.get_user_profile()
    log_event("spotify-service", "INFO", "User profile retrieved", {"user_id": profile.get("id")})
    return profile


@app.get("/top-tracks")
async def get_all_top_tracks():
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    log_event("spotify-service", "INFO", "Starting to fetch 300 top tracks across all time ranges")
    
    all_tracks = []
    time_ranges = ["short_term", "medium_term", "long_term"]
    
    for time_range in time_ranges:
        log_event("spotify-service", "INFO", f"Fetching tracks for {time_range}")
        tracks = await spotify_client.get_top_tracks(time_range=time_range, limit=300)
        all_tracks.extend([{**track, "time_range": time_range} for track in tracks])
        log_event("spotify-service", "INFO", f"Fetched {len(tracks)} tracks for {time_range}")
    
    log_event("spotify-service", "INFO", f"Total tracks fetched: {len(all_tracks)}")
    return {"tracks": all_tracks, "total": len(all_tracks)}


@app.get("/top-artists")
async def get_all_top_artists():
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    log_event("spotify-service", "INFO", "Starting to fetch 300 top artists (long_term)")
    
    artists = await spotify_client.get_top_artists(time_range="long_term", limit=300)
    
    log_event("spotify-service", "INFO", f"Total artists fetched: {len(artists)}")
    return {"artists": artists, "total": len(artists)}


@app.get("/album/{album_id}")
async def get_album(album_id: str):
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    album = await spotify_client.get_album(album_id)
    log_event("spotify-service", "INFO", f"Album retrieved: {album.get('name')}")
    return album
