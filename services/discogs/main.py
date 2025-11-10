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
    
    results = await discogs_client.search_release(artist, title)
    
    log_event("discogs-service", "INFO", f"Found {len(results)} results for {artist} - {title}")
    return {"results": results, "total": len(results)}


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
    url = f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}"
    log_event("discogs-service", "INFO", f"Generated sell list URL for release {release_id}")
    return {"release_id": release_id, "url": url}
