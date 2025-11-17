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
PRICING_SERVICE_URL = os.getenv("PRICING_SERVICE_URL", "http://localhost:3003")

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
        ("pricing", PRICING_SERVICE_URL),
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


@app.get("/discogs/search/{artist}/{album}")
async def search_discogs(artist: str, album: str):
    """Search for vinyl releases on Discogs for a specific artist/album"""
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    start_time = time.time()
    log_event("gateway", "INFO", f"Searching Discogs: {artist} - {album}")
    
    try:
        resp = await http_client.get(
            f"{DISCOGS_SERVICE_URL}/search",
            params={"artist": artist, "title": album}
        )
        data = resp.json()
        releases = data.get("releases", [])
        discogs_debug = data.get("debug_info", {})
        
        # Filter for vinyl only and sort by preference
        vinyl_releases, filter_debug_info = get_vinyl_releases(releases)
        
        elapsed = time.time() - start_time
        log_event("gateway", "INFO", f"Found {len(vinyl_releases)} vinyl releases in {elapsed:.2f}s")
        
        return {
            "artist": artist,
            "album": album,
            "releases": vinyl_releases,
            "total": len(vinyl_releases),
            "debug_info": filter_debug_info,
            "discogs_request": discogs_debug,
            "request_time_seconds": round(elapsed, 2)
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        log_event("gateway", "ERROR", f"Discogs search failed: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Discogs search failed: {str(e)}"
        )


@app.get("/discogs/stats/{release_id}")
async def get_discogs_stats(release_id: int):
    """Get marketplace stats (price, availability) for a specific Discogs release"""
    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized")
    
    start_time = time.time()
    log_event("gateway", "INFO", f"Getting stats for release {release_id}")
    
    try:
        resp = await http_client.get(f"{DISCOGS_SERVICE_URL}/stats/{release_id}")
        stats = resp.json()
        discogs_debug = stats.pop("debug_info", {})
        
        elapsed = time.time() - start_time
        log_event("gateway", "INFO", f"Got stats for release {release_id} in {elapsed:.2f}s")
        
        return {
            "release_id": release_id,
            "stats": stats,
            "discogs_request": discogs_debug,
            "request_time_seconds": round(elapsed, 2)
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        log_event("gateway", "ERROR", f"Failed to get stats for release {release_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


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
        
        elapsed = time.time() - start_time
        log_event("gateway", "INFO", f"Pricing fetched for {artist} - {album} in {elapsed:.2f}s")
        
        return {
            "artist": artist,
            "album": album,
            "discogs_master_url": discogs_data.get("master_url"),
            "discogs_master_id": discogs_data.get("master_id"),
            "discogs_title": discogs_data.get("title"),
            "ebay_offer": ebay_data.get("offer"),
            "local_stores": stores_data.get("stores", {}),
            "request_time_seconds": round(elapsed, 2),
            "debug_info": {
                "discogs": discogs_data.get("debug_info"),
                "parallelization": "3 concurrent requests (Discogs + eBay + Local Stores)"
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
