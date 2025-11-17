from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from libs.shared.models import DiscogsRelease, DiscogsStats, ServiceHealth
from libs.shared.utils import create_http_client, log_event
from .discogs_client import DiscogsClient

discogs_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global discogs_client
    discogs_key = os.getenv("DISCOGS_KEY", "")
    discogs_secret = os.getenv("DISCOGS_SECRET", "")
    discogs_client = DiscogsClient(discogs_key, discogs_secret)
    await discogs_client.start()
    log_event("discogs-service", "INFO", "Discogs Service started")
    yield
    await discogs_client.stop()
    log_event("discogs-service", "INFO", "Discogs Service stopped")


app = FastAPI(lifespan=lifespan, title="Discogs Service")

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
        service_name="discogs-service",
        status="healthy" if discogs_client and discogs_client.is_ready() else "unhealthy"
    ).dict()


@app.get("/search")
async def search_release(artist: str = Query(...), title: str = Query(...)):
    if not discogs_client:
        raise HTTPException(status_code=500, detail="Discogs client not initialized")
    
    log_event("discogs-service", "INFO", f"Searching for: {artist} - {title}")
    
    response = await discogs_client.search_release(artist, title)
    results = response.get("results", [])
    debug_info = response.get("debug_info", {})
    
    log_event("discogs-service", "INFO", f"Found {len(results)} results for {artist} - {title}")
    return {"releases": results, "total": len(results), "debug_info": debug_info}


@app.get("/stats/{release_id}")
async def get_marketplace_stats(release_id: int, currency: str = "EUR"):
    if not discogs_client:
        raise HTTPException(status_code=500, detail="Discogs client not initialized")
    
    log_event("discogs-service", "INFO", f"Getting stats for release {release_id}")
    
    stats = await discogs_client.get_marketplace_stats(release_id, currency)
    
    log_event("discogs-service", "INFO", f"Stats retrieved for release {release_id}: {stats.get('num_for_sale', 0)} items for sale")
    return stats


@app.get("/sell-list-url/{release_id}")
async def get_sell_list_url(release_id: int):
    if not discogs_client or not discogs_client.is_ready():
        raise HTTPException(status_code=503, detail="Discogs client not ready")
    
    # Get master_id from release_id
    master_id = await discogs_client._get_master_id_from_release(release_id)
    
    # Use master_id if available, otherwise fallback to release_id
    if master_id:
        url = f"https://www.discogs.com/sell/list?master_id={master_id}&currency=EUR&format=Vinyl"
        log_event("discogs-service", "INFO", f"Generated sell list URL for release {release_id} (master_id: {master_id})")
    else:
        url = f"https://www.discogs.com/sell/list?release_id={release_id}&currency=EUR&format=Vinyl"
        log_event("discogs-service", "WARNING", f"Generated sell list URL for release {release_id} (master_id not found)")
    
    return {"release_id": release_id, "url": url}


@app.get("/master-link/{artist}/{album}")
async def get_master_link(artist: str, album: str):
    if not discogs_client:
        raise HTTPException(status_code=500, detail="Discogs client not initialized")
    
    log_event("discogs-service", "INFO", f"Fetching master link for: {artist} - {album}")
    
    result = await discogs_client.get_master_link(artist, album)
    
    if result.get("master_id"):
        log_event("discogs-service", "INFO", f"Master found for {artist} - {album}: {result['master_id']}")
    else:
        log_event("discogs-service", "INFO", f"No master found for {artist} - {album}")
    
    return result
