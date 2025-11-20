from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path
import httpx
import asyncio
import time
import csv
import json
from typing import AsyncGenerator

sys.path.insert(0, str(Path(__file__).parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event

SPOTIFY_SERVICE_URL = os.getenv("SPOTIFY_SERVICE_URL", "http://localhost:3000")
DISCOGS_SERVICE_URL = os.getenv("DISCOGS_SERVICE_URL", "http://localhost:3001")
RECOMMENDER_SERVICE_URL = os.getenv("RECOMMENDER_SERVICE_URL", "http://localhost:3002")
PRICING_SERVICE_URL = os.getenv("PRICING_SERVICE_URL", "http://localhost:3003")
LASTFM_SERVICE_URL = os.getenv("LASTFM_SERVICE_URL", "http://localhost:3004")

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


@app.get("/admin")
async def admin():
    return FileResponse(static_path / "admin.html")


@app.get("/health")
async def health_check():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    services_health = {}
    
    for service_name, service_url in [
        ("spotify", SPOTIFY_SERVICE_URL),
        ("discogs", DISCOGS_SERVICE_URL),
        ("recommender", RECOMMENDER_SERVICE_URL),
        ("pricing", PRICING_SERVICE_URL),
        ("lastfm", LASTFM_SERVICE_URL),
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
        data = resp.json()
        
        if data.get("status") == "ok":
            return RedirectResponse(url="/?auth=success")
        else:
            return RedirectResponse(url="/?auth=error")
    except Exception as e:
        log_event("gateway", "ERROR", f"Auth callback failed: {str(e)}")
        return RedirectResponse(url="/?auth=error")


@app.get("/spotify/callback")
async def spotify_callback_alias(code: str):
    """Alias for /auth/callback to maintain compatibility with configured redirect URIs"""
    return await spotify_callback(code)


@app.get("/auth/lastfm/login")
async def lastfm_login():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    try:
        resp = await http_client.get(f"{LASTFM_SERVICE_URL}/auth/url")
        data = resp.json()
        log_event("gateway", "INFO", f"Generated Last.fm auth URL with token: {data.get('token', '')[:10]}...")
        return data
    except Exception as e:
        log_event("gateway", "ERROR", f"Last.fm login failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to contact Last.fm service: {str(e)}")


@app.get("/auth/lastfm/callback")
async def lastfm_callback(token: str):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    try:
        resp = await http_client.post(f"{LASTFM_SERVICE_URL}/auth/callback?token={token}")
        data = resp.json()
        
        if data.get("status") == "success":
            log_event("gateway", "INFO", f"Last.fm authentication successful for user: {data.get('username')}")
            return {"status": "ok", "username": data.get("username")}
        else:
            raise HTTPException(status_code=400, detail="Last.fm authentication failed")
    except HTTPException:
        raise
    except Exception as e:
        log_event("gateway", "ERROR", f"Last.fm callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Callback failed: {str(e)}")


@app.get("/lastfm/callback")
async def lastfm_callback_alias(token: str):
    """Alias for /auth/lastfm/callback to maintain compatibility with configured redirect URIs"""
    return await lastfm_callback(token)


@app.get("/album-pricing/{artist}/{album}")
async def get_album_pricing(artist: str, album: str):
    """
    Get complete pricing information for an album with maximum speed optimization.
    Fetches in parallel:
    - Discogs master link
    - eBay best price
    - Local store links
    
    Returns all data in 1-2 seconds thanks to asyncio.gather parallelization.
    """
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    start_time = time.time()
    log_event("gateway", "INFO", f"Getting pricing for: {artist} - {album}")
    
    try:
        # Parallel execution of all 3 requests using asyncio.gather
        discogs_task = http_client.get(f"{DISCOGS_SERVICE_URL}/master-link/{artist}/{album}")
        ebay_task = http_client.get(f"{PRICING_SERVICE_URL}/ebay-price/{artist}/{album}")
        stores_task = http_client.get(f"{PRICING_SERVICE_URL}/local-stores/{artist}/{album}")
        
        discogs_resp, ebay_resp, stores_resp = await asyncio.gather(
            discogs_task, ebay_task, stores_task, return_exceptions=True
        )
        
        # Parse Discogs response
        if isinstance(discogs_resp, Exception):
            log_event("gateway", "WARNING", f"Discogs master link failed: {str(discogs_resp)}")
            discogs_data = {"master_id": None, "master_url": None, "message": str(discogs_resp)}
        else:
            discogs_data = discogs_resp.json()
        
        # Parse eBay response
        if isinstance(ebay_resp, Exception):
            log_event("gateway", "WARNING", f"eBay pricing failed: {str(ebay_resp)}")
            ebay_data = {"offer": None, "message": str(ebay_resp)}
        else:
            ebay_data = ebay_resp.json()
        
        # Parse local stores response
        if isinstance(stores_resp, Exception):
            log_event("gateway", "WARNING", f"Local stores failed: {str(stores_resp)}")
            stores_data = {"stores": {}}
        else:
            stores_data = stores_resp.json()
        
        # Fetch tracklist based on type (master or release)
        tracklist_data = {"tracklist": []}
        discogs_sell_url = None
        discogs_url = None
        discogs_type = discogs_data.get("type")
        discogs_id = discogs_data.get("id")
        
        if discogs_type == "master" and discogs_id:
            try:
                tracklist_resp = await http_client.get(f"{DISCOGS_SERVICE_URL}/master-tracklist/{discogs_id}")
                tracklist_data = tracklist_resp.json()
                log_event("gateway", "INFO", f"Tracklist fetched for master {discogs_id}: {len(tracklist_data.get('tracklist', []))} tracks")
            except Exception as e:
                log_event("gateway", "WARNING", f"Tracklist fetch failed for master: {str(e)}")
            
            discogs_sell_url = f"https://www.discogs.com/sell/list?master_id={discogs_id}&currency=EUR&format=Vinyl"
            discogs_url = discogs_data.get("url")
            
        elif discogs_type == "release" and discogs_id:
            try:
                tracklist_resp = await http_client.get(f"{DISCOGS_SERVICE_URL}/release-tracklist/{discogs_id}")
                tracklist_data = tracklist_resp.json()
                log_event("gateway", "INFO", f"Tracklist fetched for release {discogs_id}: {len(tracklist_data.get('tracklist', []))} tracks")
            except Exception as e:
                log_event("gateway", "WARNING", f"Tracklist fetch failed for release: {str(e)}")
            
            discogs_sell_url = f"https://www.discogs.com/sell/list?release_id={discogs_id}&currency=EUR&format=Vinyl"
            discogs_url = discogs_data.get("url")
        else:
            log_event("gateway", "INFO", f"No Discogs master or release found for {artist} - {album}")
        
        elapsed = time.time() - start_time
        log_event("gateway", "INFO", f"Album info fetched for {artist} - {album} in {elapsed:.2f}s (type: {discogs_type or 'none'})")
        
        return {
            "artist": artist,
            "album": album,
            "discogs_type": discogs_type,
            "discogs_id": discogs_id,
            "discogs_url": discogs_url,
            "discogs_sell_url": discogs_sell_url,
            "discogs_title": discogs_data.get("title"),
            "tracklist": tracklist_data.get("tracklist", []),
            "ebay_offer": ebay_data.get("offer"),
            "local_stores": stores_data.get("stores", {}),
            "request_time_seconds": round(elapsed, 2),
            "debug_info": {
                "discogs": discogs_data.get("debug_info"),
                "search_type": discogs_type,
                "parallelization": "3 concurrent requests (Discogs + eBay + Local Stores) + tracklist fetch"
            }
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        log_event("gateway", "ERROR", f"Album pricing failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get album pricing: {str(e)}"
        )


def get_vinyl_releases(releases: list) -> tuple[list, dict]:
    """Get all vinyl releases ordered by preference (originals first, then reissues)
    
    Returns:
        (list_of_releases, debug_info)
    """
    debug_info = {
        "total_releases_found": len(releases),
        "vinyl_releases_found": 0,
    }
    
    if not releases:
        return [], debug_info
    
    preferred_formats = ["LP", "Album", "Vinyl"]
    
    vinyl_releases = []
    for release in releases:
        format_value = release.get("format", "")
        
        if isinstance(format_value, list):
            format_str = " ".join(format_value).lower()
        else:
            format_str = str(format_value).lower()
        
        is_vinyl = any(pref.lower() in format_str for pref in preferred_formats)
        if is_vinyl:
            vinyl_releases.append(release)
    
    debug_info["vinyl_releases_found"] = len(vinyl_releases)
    
    # Sort: originals first, then reissues/remasters
    originals = []
    reissues = []
    
    for release in vinyl_releases:
        format_value = release.get("format", "")
        if isinstance(format_value, list):
            format_str = " ".join(format_value).lower()
        else:
            format_str = str(format_value).lower()
            
        if "reissue" in format_str or "remaster" in format_str:
            reissues.append(release)
        else:
            originals.append(release)
    
    # Return originals first, then reissues
    ordered_releases = originals + reissues
    
    return ordered_releases, debug_info


async def enrich_album_with_discogs(album: dict, idx: int, total: int, semaphore: asyncio.Semaphore) -> dict:
    """Enrich a single album with Discogs data by trying multiple releases until finding one with price"""
    async with semaphore:
        album_info = album.get("album_info", {})
        artist_name = album_info.get("artists", [{}])[0].get("name", "Unknown")
        album_name = album_info.get("name", "Unknown")
        
        log_event("gateway", "INFO", f"[{idx}/{total}] Processing: {artist_name} - {album_name}")
        
        debug_info = {
            "status": None,
            "message": None,
            "details": {}
        }
        
        try:
            search_resp = await http_client.get(
                f"{DISCOGS_SERVICE_URL}/search",
                params={"artist": artist_name, "title": album_name}
            )
            search_results = search_resp.json().get("results", [])
            
            if not search_results:
                album["discogs_release"] = None
                album["discogs_stats"] = None
                debug_info["status"] = "not_found"
                debug_info["message"] = "No se encontró en Discogs"
                debug_info["details"] = {"total_releases_found": 0}
                log_event("gateway", "INFO", f"[{idx}/{total}] ○ Not found on Discogs: {album_name}")
                album["discogs_debug_info"] = debug_info
                return album
            
            # Get all vinyl releases ordered by preference
            vinyl_releases, search_debug = get_vinyl_releases(search_results)
            debug_info["details"] = search_debug
            
            if not vinyl_releases:
                album["discogs_release"] = None
                album["discogs_stats"] = None
                debug_info["status"] = "not_found"
                debug_info["message"] = "No se encontraron vinilos"
                log_event("gateway", "INFO", f"[{idx}/{total}] ○ No vinyl: {album_name}")
                album["discogs_debug_info"] = debug_info
                return album
            
            # Try up to 5 releases to find one with price
            max_attempts = min(5, len(vinyl_releases))
            debug_info["details"]["releases_tried"] = 0
            debug_info["details"]["releases_with_price"] = 0
            
            selected_release = None
            selected_stats = None
            
            for attempt_idx, release in enumerate(vinyl_releases[:max_attempts], 1):
                release_id = release.get("id")
                format_value = release.get("format", "")
                if isinstance(format_value, list):
                    format_str = " ".join(format_value)
                else:
                    format_str = str(format_value)
                
                log_event("gateway", "INFO", f"[{idx}/{total}] Trying release {attempt_idx}/{max_attempts}: ID {release_id} ({format_str})")
                
                try:
                    stats_resp = await http_client.get(
                        f"{DISCOGS_SERVICE_URL}/stats/{release_id}"
                    )
                    stats = stats_resp.json()
                    debug_info["details"]["releases_tried"] = attempt_idx
                    
                    has_price = stats.get("lowest_price_eur") is not None and stats.get("lowest_price_eur") > 0
                    
                    if has_price:
                        debug_info["details"]["releases_with_price"] += 1
                        selected_release = release
                        selected_stats = stats
                        debug_info["details"]["selected_release_index"] = attempt_idx
                        debug_info["details"]["selected_format"] = format_str
                        log_event("gateway", "INFO", f"[{idx}/{total}] ✓ Found price on attempt {attempt_idx}: €{stats['lowest_price_eur']:.2f}")
                        break
                    else:
                        log_event("gateway", "INFO", f"[{idx}/{total}] ○ Release {release_id} has no price, trying next...")
                        
                except Exception as e:
                    log_event("gateway", "WARNING", f"[{idx}/{total}] Failed to get stats for release {release_id}: {str(e)}")
                    continue
            
            # If we didn't find any with price, use the first release anyway
            if not selected_release:
                selected_release = vinyl_releases[0]
                release_id = selected_release.get("id")
                
                # Set debug info for fallback selection
                debug_info["details"]["selected_release_index"] = 1
                format_value = selected_release.get("format", "")
                if isinstance(format_value, list):
                    debug_info["details"]["selected_format"] = " ".join(format_value)
                else:
                    debug_info["details"]["selected_format"] = str(format_value)
                
                try:
                    stats_resp = await http_client.get(
                        f"{DISCOGS_SERVICE_URL}/stats/{release_id}"
                    )
                    selected_stats = stats_resp.json()
                except Exception as e:
                    log_event("gateway", "WARNING", f"[{idx}/{total}] Failed to get stats for fallback release: {str(e)}")
                    
                    # Get sell list URL with master_id from Discogs service
                    sell_url = f"https://www.discogs.com/sell/list?release_id={release_id}&currency=EUR&format=Vinyl"
                    try:
                        url_resp = await http_client.get(f"{DISCOGS_SERVICE_URL}/sell-list-url/{release_id}")
                        sell_url = url_resp.json().get("url", sell_url)
                    except:
                        pass
                    
                    selected_stats = {
                        "release_id": release_id,
                        "lowest_price_eur": None,
                        "num_for_sale": 0,
                        "sell_list_url": sell_url
                    }
            
            album["discogs_release"] = selected_release
            album["discogs_stats"] = selected_stats
            
            has_price = selected_stats.get("lowest_price_eur") is not None and selected_stats.get("lowest_price_eur") > 0
            
            if has_price:
                debug_info["status"] = "success"
                format_val = selected_release.get("format", "")
                if isinstance(format_val, list):
                    fmt = " ".join(format_val)
                else:
                    fmt = str(format_val)
                debug_info["message"] = f"Vinilo disponible - {fmt}"
                log_event("gateway", "INFO", f"[{idx}/{total}] ✓ Enriched: {album_name}")
            else:
                debug_info["status"] = "no_price"
                debug_info["message"] = f"Probados {debug_info['details']['releases_tried']} releases, ninguno con precio"
                log_event("gateway", "INFO", f"[{idx}/{total}] ⚠ No price found after trying {debug_info['details']['releases_tried']} releases: {album_name}")
                
        except Exception as e:
            log_event("gateway", "WARNING", f"[{idx}/{total}] ✗ Failed: {album_name} - {str(e)}")
            album["discogs_release"] = None
            album["discogs_stats"] = None
            debug_info["status"] = "error"
            debug_info["message"] = f"Error: {str(e)}"
            debug_info["details"] = {}
        
        album["discogs_debug_info"] = debug_info
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
        
        end_time = time.time()
        total_time = end_time - start_time
        log_event("gateway", "INFO", f"Recommendation flow complete: {len(albums)} albums in {total_time:.2f}s")
        
        return {
            "albums": albums,
            "total": len(albums),
            "total_time_seconds": round(total_time, 2),
            "stats": {
                "tracks_analyzed": len(all_tracks),
                "artists_analyzed": len(all_artists),
                "albums_found": len(albums)
            }
        }
    
    except Exception as e:
        log_event("gateway", "ERROR", f"Recommendation flow failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")


@app.get("/api/lastfm/search")
async def search_artists(q: str):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    if len(q) < 4:
        raise HTTPException(status_code=400, detail="Query must be at least 4 characters")
    
    try:
        log_event("gateway", "INFO", f"Searching artists: {q}")
        resp = await http_client.get(f"{LASTFM_SERVICE_URL}/search?q={q}")
        data = resp.json()
        log_event("gateway", "INFO", f"Found {len(data.get('artists', []))} artists")
        return data
    except Exception as e:
        log_event("gateway", "ERROR", f"Artist search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/api/lastfm/recommendations")
async def get_lastfm_recommendations(request: dict):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    start_time = time.time()
    time_range = request.get("time_range", "medium_term")
    username = request.get("username")
    
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    
    log_event("gateway", "INFO", f"Starting Last.fm recommendation flow for {username} (time_range={time_range})")
    
    try:
        log_event("gateway", "INFO", "Step 1: Fetching top tracks from Last.fm")
        tracks_resp = await http_client.post(
            f"{LASTFM_SERVICE_URL}/top-tracks",
            json={"time_range": time_range, "username": username}
        )
        tracks_data = tracks_resp.json()
        all_tracks = tracks_data.get("tracks", [])
        
        for track in all_tracks:
            track["time_range"] = time_range
        
        log_event("gateway", "INFO", f"Fetched {len(all_tracks)} Last.fm tracks")
        
        log_event("gateway", "INFO", "Step 2: Fetching top artists from Last.fm")
        artists_resp = await http_client.post(
            f"{LASTFM_SERVICE_URL}/top-artists",
            json={"time_range": time_range, "username": username}
        )
        artists_data = artists_resp.json()
        all_artists = artists_data.get("artists", [])
        log_event("gateway", "INFO", f"Fetched {len(all_artists)} Last.fm artists")
        
        log_event("gateway", "INFO", "Step 3: Scoring Last.fm tracks")
        scored_tracks_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/score-lastfm-tracks",
            json=all_tracks
        )
        scored_tracks = scored_tracks_resp.json().get("scored_tracks", [])
        log_event("gateway", "INFO", f"Scored {len(scored_tracks)} Last.fm tracks")
        
        log_event("gateway", "INFO", "Step 4: Scoring Last.fm artists")
        scored_artists_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/score-lastfm-artists",
            json=all_artists
        )
        scored_artists = scored_artists_resp.json().get("scored_artists", [])
        log_event("gateway", "INFO", f"Scored {len(scored_artists)} Last.fm artists")
        
        log_event("gateway", "INFO", "Step 5: Aggregating albums from Last.fm data")
        albums_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/aggregate-albums",
            json={"scored_tracks": scored_tracks, "scored_artists": scored_artists}
        )
        albums = albums_resp.json().get("albums", [])
        log_event("gateway", "INFO", f"Generated {len(albums)} album recommendations from Last.fm")
        
        end_time = time.time()
        total_time = end_time - start_time
        log_event("gateway", "INFO", f"Last.fm recommendation flow complete: {len(albums)} albums in {total_time:.2f}s")
        
        return {
            "albums": albums,
            "total": len(albums),
            "total_time_seconds": round(total_time, 2),
            "stats": {
                "tracks_analyzed": len(all_tracks),
                "artists_analyzed": len(all_artists),
                "albums_found": len(albums)
            }
        }
    
    except Exception as e:
        log_event("gateway", "ERROR", f"Last.fm recommendation flow failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Last.fm recommendation failed: {str(e)}")


@app.get("/api/recommendations/progress")
async def get_recommendations_progress():
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    try:
        resp = await http_client.get(f"{RECOMMENDER_SERVICE_URL}/progress")
        return resp.json()
    except Exception as e:
        log_event("gateway", "ERROR", f"Failed to fetch progress: {str(e)}")
        return {"status": "idle", "current": 0, "total": 0, "current_artist": ""}


@app.post("/api/recommendations/artist-single")
async def get_single_artist_recommendations(request: dict):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    artist_name = request.get("artist_name")
    top_albums = request.get("top_albums", 3)
    csv_mode = request.get("csv_mode", False)
    
    if not artist_name:
        raise HTTPException(status_code=400, detail="artist_name is required")
    
    start_time = time.time()
    mode_label = " (CSV mode)" if csv_mode else ""
    log_event("gateway", "INFO", f"Getting recommendations for artist: {artist_name}{mode_label}")
    
    try:
        resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/artist-single-recommendation",
            json={"artist_name": artist_name, "top_albums": top_albums, "csv_mode": csv_mode}
        )
        resp.raise_for_status()
        result = resp.json()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        recommendations = result.get("recommendations", [])
        
        if not recommendations:
            log_event("gateway", "WARNING", f"No recommendations found for {artist_name}")
            raise HTTPException(status_code=404, detail=f"No albums found for artist: {artist_name}")
        
        log_event("gateway", "INFO", 
                 f"Got {len(recommendations)} recommendations for {artist_name} in {total_time:.2f}s")
        
        return {
            "recommendations": recommendations,
            "total": len(recommendations),
            "artist_name": artist_name,
            "total_time_seconds": round(total_time, 2),
            "status": "success"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log_event("gateway", "ERROR", f"Single artist recommendations failed for {artist_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Recommendations failed: {str(e)}")


@app.post("/api/recommendations/artists")
async def get_artist_recommendations(request: dict):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    artist_names = request.get("artist_names", [])
    spotify_token = request.get("spotify_token")
    
    if not artist_names:
        raise HTTPException(status_code=400, detail="artist_names is required")
    
    if len(artist_names) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 artists required")
    
    if len(artist_names) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 artists allowed")
    
    start_time = time.time()
    log_event("gateway", "INFO", f"Getting recommendations for {len(artist_names)} artists")
    
    try:
        artist_recs_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/artist-recommendations",
            json={"artist_names": artist_names, "top_per_artist": 3}
        )
        artist_recs = artist_recs_resp.json().get("recommendations", [])
        log_event("gateway", "INFO", f"Got {len(artist_recs)} artist-based recommendations")
        
        spotify_recs = []
        if spotify_token:
            try:
                log_event("gateway", "INFO", "Fetching Spotify recommendations")
                
                tracks_resp, artists_resp = await asyncio.gather(
                    http_client.get(f"{SPOTIFY_SERVICE_URL}/top-tracks"),
                    http_client.get(f"{SPOTIFY_SERVICE_URL}/top-artists")
                )
                
                tracks_data = tracks_resp.json()
                all_tracks = tracks_data.get("tracks", [])
                
                artists_data = artists_resp.json()
                all_artists = artists_data.get("artists", [])
                
                scored_tracks_resp, scored_artists_resp = await asyncio.gather(
                    http_client.post(f"{RECOMMENDER_SERVICE_URL}/score-tracks", json=all_tracks),
                    http_client.post(f"{RECOMMENDER_SERVICE_URL}/score-artists", json=all_artists)
                )
                
                scored_tracks = scored_tracks_resp.json().get("scored_tracks", [])
                scored_artists = scored_artists_resp.json().get("scored_artists", [])
                
                albums_resp = await http_client.post(
                    f"{RECOMMENDER_SERVICE_URL}/aggregate-albums",
                    json={"scored_tracks": scored_tracks, "scored_artists": scored_artists}
                )
                spotify_recs = albums_resp.json().get("albums", [])
                log_event("gateway", "INFO", f"Got {len(spotify_recs)} Spotify recommendations")
            except Exception as e:
                log_event("gateway", "WARNING", f"Failed to get Spotify recommendations: {str(e)}")
        
        merge_resp = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/merge-recommendations",
            json={
                "spotify_recommendations": spotify_recs,
                "artist_recommendations": artist_recs
            }
        )
        merged = merge_resp.json().get("recommendations", [])
        
        end_time = time.time()
        total_time = end_time - start_time
        log_event("gateway", "INFO", f"Artist recommendations complete: {len(merged)} total in {total_time:.2f}s")
        
        return {
            "recommendations": merged,
            "total": len(merged),
            "total_time_seconds": round(total_time, 2),
            "stats": {
                "artist_based": len(artist_recs),
                "spotify_based": len(spotify_recs),
                "total": len(merged)
            }
        }
    
    except Exception as e:
        log_event("gateway", "ERROR", f"Artist recommendations failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Recommendations failed: {str(e)}")


@app.post("/api/recommendations/merge")
async def merge_recommendations(request: dict):
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    try:
        spotify_recs = request.get("spotify_recommendations", [])
        lastfm_recs = request.get("lastfm_recommendations", [])
        artist_recs = request.get("artist_recommendations", [])
        
        log_event("gateway", "INFO", 
                  f"Merging {len(spotify_recs)} Spotify + {len(lastfm_recs)} Last.fm + {len(artist_recs)} artist recommendations")
        
        response = await http_client.post(
            f"{RECOMMENDER_SERVICE_URL}/merge-recommendations",
            json={
                "spotify_recommendations": spotify_recs,
                "lastfm_recommendations": lastfm_recs,
                "artist_recommendations": artist_recs
            }
        )
        
        data = response.json()
        log_event("gateway", "INFO", f"Merged into {data.get('total', 0)} recommendations")
        return data
    
    except Exception as e:
        log_event("gateway", "ERROR", f"Merge recommendations failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")


@app.post("/api/admin/import-csv")
async def import_artists_csv(file: UploadFile = File(...)):
    """Import artists from CSV file with real-time progress updates via SSE"""
    
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    # Read file content before creating the stream
    content = await file.read()
    csv_text = content.decode('utf-8')
    csv_reader = csv.DictReader(csv_text.splitlines())
    
    if not csv_reader.fieldnames or 'name' not in csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must have a 'name' column")
    
    artists = [row['name'].strip() for row in csv_reader if row.get('name', '').strip()]
    
    if not artists:
        raise HTTPException(status_code=400, detail="No artists found in CSV")
    
    async def event_stream() -> AsyncGenerator[str, None]:
        """Server-Sent Events stream for progress updates"""
        try:
            total = len(artists)
            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
            
            successful = 0
            cached = 0
            failed = 0
            failed_artists = []
            
            for i, artist_name in enumerate(artists, 1):
                try:
                    start_time = time.time()
                    
                    response = await http_client.post(
                        "http://localhost:5000/api/recommendations/artist-single",
                        json={"artist_name": artist_name, "top_albums": 10, "csv_mode": True},
                        timeout=180.0
                    )
                    
                    elapsed = time.time() - start_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        total_albums = data.get('total', 0)
                        top_album = None
                        rating = None
                        
                        if data.get('recommendations'):
                            top_album = data['recommendations'][0].get('album_name')
                            rating = data['recommendations'][0].get('rating')
                        
                        if elapsed < 1.0:
                            cached += 1
                            status = 'cached'
                        else:
                            successful += 1
                            status = 'success'
                        
                        yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'artist': artist_name, 'status': status, 'albums': total_albums, 'time': round(elapsed, 2), 'top_album': top_album, 'rating': rating})}\n\n"
                    
                    elif response.status_code == 404:
                        failed += 1
                        failed_artists.append(artist_name)
                        yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'artist': artist_name, 'status': 'not_found', 'error': 'No albums found'})}\n\n"
                    
                    else:
                        failed += 1
                        failed_artists.append(artist_name)
                        error_msg = response.text[:100]
                        yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'artist': artist_name, 'status': 'error', 'error': error_msg})}\n\n"
                
                except asyncio.TimeoutError:
                    failed += 1
                    failed_artists.append(artist_name)
                    yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'artist': artist_name, 'status': 'timeout', 'error': 'Request timeout'})}\n\n"
                
                except Exception as e:
                    failed += 1
                    failed_artists.append(artist_name)
                    yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'artist': artist_name, 'status': 'error', 'error': str(e)})}\n\n"
                
                await asyncio.sleep(0.1)
            
            if failed_artists:
                yield f"data: {json.dumps({'type': 'retry_start', 'failed_count': len(failed_artists), 'artists': failed_artists})}\n\n"
                
                retry_successful = 0
                retry_failed = 0
                
                for i, artist_name in enumerate(failed_artists, 1):
                    try:
                        start_time = time.time()
                        
                        response = await http_client.post(
                            "http://localhost:5000/api/recommendations/artist-single",
                            json={"artist_name": artist_name, "top_albums": 10, "csv_mode": True},
                            timeout=180.0
                        )
                        
                        elapsed = time.time() - start_time
                        
                        if response.status_code == 200:
                            data = response.json()
                            total_albums = data.get('total', 0)
                            top_album = None
                            rating = None
                            
                            if data.get('recommendations'):
                                top_album = data['recommendations'][0].get('album_name')
                                rating = data['recommendations'][0].get('rating')
                            
                            retry_successful += 1
                            successful += 1
                            failed -= 1
                            
                            yield f"data: {json.dumps({'type': 'retry_progress', 'current': i, 'total': len(failed_artists), 'artist': artist_name, 'status': 'success', 'albums': total_albums, 'time': round(elapsed, 2), 'top_album': top_album, 'rating': rating})}\n\n"
                        else:
                            retry_failed += 1
                            error_msg = response.text[:100] if hasattr(response, 'text') else 'Unknown error'
                            yield f"data: {json.dumps({'type': 'retry_progress', 'current': i, 'total': len(failed_artists), 'artist': artist_name, 'status': 'error', 'error': error_msg})}\n\n"
                    
                    except Exception as e:
                        retry_failed += 1
                        yield f"data: {json.dumps({'type': 'retry_progress', 'current': i, 'total': len(failed_artists), 'artist': artist_name, 'status': 'error', 'error': str(e)})}\n\n"
                    
                    await asyncio.sleep(0.1)
                
                yield f"data: {json.dumps({'type': 'retry_complete', 'retry_successful': retry_successful, 'retry_failed': retry_failed})}\n\n"
            
            yield f"data: {json.dumps({'type': 'complete', 'successful': successful, 'cached': cached, 'failed': failed, 'total': total})}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")
