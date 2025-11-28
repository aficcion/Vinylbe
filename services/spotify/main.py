import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event
from .spotify_client import SpotifyClient

spotify_client: Optional[SpotifyClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global spotify_client
    
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        log_event("spotify-service", "ERROR", "SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not configured")
        raise RuntimeError("Spotify credentials not configured")
    
    spotify_client = SpotifyClient(client_id, client_secret)
    log_event("spotify-service", "INFO", "Spotify Service started")
    
    yield
    
    await spotify_client.close()
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
        status="healthy"
    ).dict()


@app.get("/search/artists")
async def search_artists(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50)):
    """Search for artists on Spotify
    
    Args:
        q: Search query (minimum 2 characters)
        limit: Number of results to return (default 10, max 50)
    
    Returns:
        List of artists with id, name, image_url, genres, popularity
    """
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    try:
        artists = await spotify_client.search_artists(q, limit)
        return {
            "artists": artists,
            "total": len(artists)
        }
    except Exception as e:
        log_event("spotify-service", "ERROR", f"Artist search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/artist/{artist_id}/albums")
async def get_artist_albums(artist_id: str, limit: int = Query(20, ge=1, le=50)):
    """Get albums for an artist
    
    Args:
        artist_id: Spotify artist ID
        limit: Number of albums to return (default 20, max 50)
    
    Returns:
        List of albums with id, name, artist_name, image_url, release_date, total_tracks
    """
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    try:
        albums = await spotify_client.get_artist_albums(artist_id, limit)
        return {
            "albums": albums,
            "total": len(albums),
            "artist_id": artist_id
        }
    except Exception as e:
        log_event("spotify-service", "ERROR", f"Get albums failed for artist {artist_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get albums: {str(e)}")


@app.get("/search/album")
async def search_album(artist: str = Query(...), album: str = Query(...)):
    """Search for a specific album by artist and name
    
    Args:
        artist: Artist name
        album: Album name
    
    Returns:
        Album data or 404 if not found
    """
    if not spotify_client:
        raise HTTPException(status_code=500, detail="Spotify client not initialized")
    
    try:
        result = await spotify_client.search_album(artist, album)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Album not found: {artist} - {album}")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_event("spotify-service", "ERROR", f"Album search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
