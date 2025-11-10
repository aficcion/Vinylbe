from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event

SPOTIFY_SERVICE_URL = os.getenv("SPOTIFY_SERVICE_URL", "http://localhost:3000")
DISCOGS_SERVICE_URL = os.getenv("DISCOGS_SERVICE_URL", "http://localhost:3001")
RECOMMENDER_SERVICE_URL = os.getenv("RECOMMENDER_SERVICE_URL", "http://localhost:3002")

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=60.0)
    log_event("gateway", "INFO", "API Gateway started")
    yield
    await http_client.aclose()
    log_event("gateway", "INFO", "API Gateway stopped")


app = FastAPI(lifespan=lifespan, title="Vinyl Recommendation API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
async def root():
    return FileResponse(static_path / "index.html")


@app.get("/health")
async def health_check():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    services_health = {}
    
    for service_name, service_url in [
        ("spotify", SPOTIFY_SERVICE_URL),
        ("discogs", DISCOGS_SERVICE_URL),
        ("recommender", RECOMMENDER_SERVICE_URL),
    ]:
        try:
            resp = await http_client.get(f"{service_url}/health", timeout=5.0)
            services_health[service_name] = resp.json()
        except Exception as e:
            services_health[service_name] = {
                "service_name": service_name,
                "status": "unhealthy",
                "error": str(e)
            }
    
    all_healthy = all(s.get("status") == "healthy" for s in services_health.values())
    
    return {
        "gateway": "healthy",
        "services": services_health,
        "overall_status": "healthy" if all_healthy else "degraded"
    }


@app.get("/auth/login")
async def spotify_login():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    try:
        resp = await http_client.get(f"{SPOTIFY_SERVICE_URL}/auth/login")
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact Spotify service: {str(e)}")


@app.get("/auth/callback")
async def spotify_callback(code: str):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    try:
        resp = await http_client.get(f"{SPOTIFY_SERVICE_URL}/auth/callback?code={code}")
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to authenticate: {str(e)}")


@app.get("/spotify/callback")
async def spotify_callback_alias(code: str):
    """Alias for /auth/callback to maintain compatibility with configured redirect URIs"""
    return await spotify_callback(code)


@app.get("/recommend-vinyl")
async def recommend_vinyl():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    log_event("gateway", "INFO", "Starting vinyl recommendation flow")
    
    try:
        log_event("gateway", "INFO", "Step 1: Fetching top tracks from Spotify")
        tracks_resp = await http_client.get(f"{SPOTIFY_SERVICE_URL}/top-tracks")
        tracks_data = tracks_resp.json()
        all_tracks = tracks_data.get("tracks", [])
        log_event("gateway", "INFO", f"Fetched {len(all_tracks)} tracks")
        
        log_event("gateway", "INFO", "Step 2: Fetching top artists from Spotify")
        artists_resp = await http_client.get(f"{SPOTIFY_SERVICE_URL}/top-artists")
        artists_data = artists_resp.json()
        all_artists = artists_data.get("artists", [])
        log_event("gateway", "INFO", f"Fetched {len(all_artists)} artists")
        
        log_event("gateway", "INFO", "Step 3: Scoring tracks")
        scored_tracks_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/score-tracks",
            json=all_tracks
        )
        scored_tracks = scored_tracks_resp.json().get("scored_tracks", [])
        log_event("gateway", "INFO", f"Scored {len(scored_tracks)} tracks")
        
        log_event("gateway", "INFO", "Step 4: Scoring artists")
        scored_artists_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/score-artists",
            json=all_artists
        )
        scored_artists = scored_artists_resp.json().get("scored_artists", [])
        log_event("gateway", "INFO", f"Scored {len(scored_artists)} artists")
        
        log_event("gateway", "INFO", "Step 5: Aggregating and filtering albums")
        albums_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/aggregate-albums",
            json={"scored_tracks": scored_tracks, "scored_artists": scored_artists}
        )
        albums = albums_resp.json().get("albums", [])
        log_event("gateway", "INFO", f"Generated {len(albums)} album recommendations")
        
        log_event("gateway", "INFO", f"Step 6: Enriching top 20 albums with Discogs data (rate limited, ~45 seconds)")
        top_albums = albums[:20]
        enriched_albums = []
        
        for idx, album in enumerate(top_albums, 1):
            album_info = album.get("album_info", {})
            artist_name = album_info.get("artists", [{}])[0].get("name", "Unknown")
            album_name = album_info.get("name", "Unknown")
            
            log_event("gateway", "INFO", f"[{idx}/20] Processing: {artist_name} - {album_name}")
            
            try:
                search_resp = await http_client.get(
                    f"{DISCOGS_SERVICE_URL}/search",
                    params={"artist": artist_name, "title": album_name}
                )
                search_results = search_resp.json().get("results", [])
                
                if search_results:
                    release = search_results[0]
                    release_id = release.get("id")
                    
                    stats_resp = await http_client.get(
                        f"{DISCOGS_SERVICE_URL}/stats/{release_id}"
                    )
                    stats = stats_resp.json()
                    
                    album["discogs_release"] = release
                    album["discogs_stats"] = stats
                    
                    log_event("gateway", "INFO", f"[{idx}/20] ✓ Enriched: {album_name}")
                else:
                    album["discogs_release"] = None
                    album["discogs_stats"] = None
                    log_event("gateway", "INFO", f"[{idx}/20] ○ Not found on Discogs: {album_name}")
            except Exception as e:
                log_event("gateway", "WARNING", f"[{idx}/20] ✗ Failed: {album_name} - {str(e)}")
                album["discogs_release"] = None
                album["discogs_stats"] = None
            
            enriched_albums.append(album)
        
        log_event("gateway", "INFO", f"Recommendation flow complete: {len(enriched_albums)} albums")
        
        return {
            "albums": enriched_albums,
            "total": len(enriched_albums),
            "stats": {
                "tracks_analyzed": len(all_tracks),
                "artists_analyzed": len(all_artists),
                "albums_found": len(albums),
                "albums_with_discogs_data": len([a for a in enriched_albums if a.get("discogs_release")])
            }
        }
    
    except Exception as e:
        log_event("gateway", "ERROR", f"Recommendation flow failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")
