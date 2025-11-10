from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event
from .scoring_engine import ScoringEngine
from .album_aggregator import AlbumAggregator

scoring_engine = None
album_aggregator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scoring_engine, album_aggregator
    scoring_engine = ScoringEngine()
    album_aggregator = AlbumAggregator()
    log_event("recommender-service", "INFO", "Recommendation Service started")
    yield
    log_event("recommender-service", "INFO", "Recommendation Service stopped")


app = FastAPI(lifespan=lifespan, title="Recommendation Service")

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
        service_name="recommender-service",
        status="healthy"
    ).dict()


@app.post("/score-tracks")
async def score_tracks(tracks: List[dict]):
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(tracks)} tracks")
    
    scored_tracks = scoring_engine.score_tracks(tracks)
    
    log_event("recommender-service", "INFO", f"Scored {len(scored_tracks)} tracks")
    return {"scored_tracks": scored_tracks, "total": len(scored_tracks)}


@app.post("/score-artists")
async def score_artists(artists: List[dict]):
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(artists)} artists")
    
    scored_artists = scoring_engine.score_artists(artists)
    
    log_event("recommender-service", "INFO", f"Scored {len(scored_artists)} artists")
    return {"scored_artists": scored_artists, "total": len(scored_artists)}


@app.post("/aggregate-albums")
async def aggregate_albums(scored_tracks: List[dict], scored_artists: List[dict]):
    if not album_aggregator:
        raise HTTPException(status_code=500, detail="Album aggregator not initialized")
    
    log_event("recommender-service", "INFO", f"Aggregating albums from {len(scored_tracks)} tracks")
    
    albums = album_aggregator.aggregate_albums(scored_tracks, scored_artists)
    
    log_event("recommender-service", "INFO", f"Generated {len(albums)} album recommendations")
    return {"albums": albums, "total": len(albums)}
