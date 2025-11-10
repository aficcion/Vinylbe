from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path
import httpx
import asyncio
import time

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


def filter_best_release(releases: list) -> dict | None:
    """Filter releases to find the best LP to buy based on format and availability"""
    if not releases:
        return None
    
    preferred_formats = ["LP", "Album", "Vinyl"]
    excluded_formats = ["Box Set", "Compilation", "Single", "EP", "CD"]
    
    lp_releases = []
    for release in releases:
        format_value = release.get("format", "")
        
        if isinstance(format_value, list):
            format_str = " ".join(format_value).lower()
        else:
            format_str = str(format_value).lower()
        
        is_excluded = any(excl.lower() in format_str for excl in excluded_formats)
        if is_excluded:
            continue
        
        is_lp = any(pref.lower() in format_str for pref in preferred_formats)
        if is_lp:
            lp_releases.append(release)
    
    if not lp_releases:
        return None
    
    for release in lp_releases:
        format_value = release.get("format", "")
        if isinstance(format_value, list):
            format_str = " ".join(format_value).lower()
        else:
            format_str = str(format_value).lower()
            
        if "reissue" in format_str or "remaster" in format_str:
            continue
        return release
    
    return lp_releases[0]


async def enrich_album_with_discogs(album: dict, idx: int, total: int, semaphore: asyncio.Semaphore) -> dict:
    """Enrich a single album with Discogs data using controlled concurrency"""
    async with semaphore:
        album_info = album.get("album_info", {})
        artist_name = album_info.get("artists", [{}])[0].get("name", "Unknown")
        album_name = album_info.get("name", "Unknown")
        
        log_event("gateway", "INFO", f"[{idx}/{total}] Processing: {artist_name} - {album_name}")
        
        try:
            search_resp = await http_client.get(
                f"{DISCOGS_SERVICE_URL}/search",
                params={"artist": artist_name, "title": album_name}
            )
            search_results = search_resp.json().get("results", [])
            
            if search_results:
                release = filter_best_release(search_results)
                if not release:
                    album["discogs_release"] = None
                    album["discogs_stats"] = None
                    log_event("gateway", "INFO", f"[{idx}/{total}] ○ No suitable vinyl format found: {album_name}")
                    return album
                
                release_id = release.get("id")
                
                stats_resp = await http_client.get(
                    f"{DISCOGS_SERVICE_URL}/stats/{release_id}"
                )
                stats = stats_resp.json()
                
                album["discogs_release"] = release
                album["discogs_stats"] = stats
                
                log_event("gateway", "INFO", f"[{idx}/{total}] ✓ Enriched: {album_name}")
            else:
                album["discogs_release"] = None
                album["discogs_stats"] = None
                log_event("gateway", "INFO", f"[{idx}/{total}] ○ Not found on Discogs: {album_name}")
        except Exception as e:
            log_event("gateway", "WARNING", f"[{idx}/{total}] ✗ Failed: {album_name} - {str(e)}")
            album["discogs_release"] = None
            album["discogs_stats"] = None
        
        return album


@app.get("/recommend-vinyl")
async def recommend_vinyl():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    start_time = time.time()
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
        
        total_albums = len(albums)
        log_event("gateway", "INFO", f"Step 6: Enriching ALL {total_albums} albums with Discogs data (sequential with 2s rate limit)")
        
        semaphore = asyncio.Semaphore(1)
        
        tasks = [
            enrich_album_with_discogs(album, idx, total_albums, semaphore)
            for idx, album in enumerate(albums, 1)
        ]
        
        enriched_albums = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        log_event("gateway", "INFO", f"Recommendation flow complete: {len(enriched_albums)} albums in {total_time:.2f}s")
        
        return {
            "albums": enriched_albums,
            "total": len(enriched_albums),
            "total_time_seconds": round(total_time, 2),
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
