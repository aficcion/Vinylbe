from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import os
from pathlib import Path
from typing import List
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event
from .scoring_engine import ScoringEngine
from .album_aggregator import AlbumAggregator
from .artist_recommendations import get_artist_based_recommendations

scoring_engine = None
album_aggregator = None


class ArtistRecommendationRequest(BaseModel):
    artist_names: List[str]
    top_per_artist: int = 3


class MergeRecommendationsRequest(BaseModel):
    spotify_recommendations: List[dict]
    artist_recommendations: List[dict]


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


@app.post("/artist-recommendations")
async def artist_recommendations(request: ArtistRecommendationRequest):
    discogs_key = os.getenv("DISCOGS_KEY")
    discogs_secret = os.getenv("DISCOGS_SECRET")
    
    if not discogs_key or not discogs_secret:
        raise HTTPException(status_code=500, detail="Discogs credentials not configured")
    
    if len(request.artist_names) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 artists required")
    
    if len(request.artist_names) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 artists allowed")
    
    log_event("recommender-service", "INFO", f"Generating recommendations for {len(request.artist_names)} artists")
    
    recommendations = get_artist_based_recommendations(
        request.artist_names,
        discogs_key,
        discogs_secret,
        top_per_artist=request.top_per_artist
    )
    
    log_event("recommender-service", "INFO", f"Generated {len(recommendations)} artist-based recommendations")
    return {"recommendations": recommendations, "total": len(recommendations)}


@app.post("/merge-recommendations")
async def merge_recommendations(request: MergeRecommendationsRequest):
    spotify_recs = request.spotify_recommendations
    artist_recs = request.artist_recommendations
    
    log_event("recommender-service", "INFO", 
              f"Merging {len(spotify_recs)} Spotify + {len(artist_recs)} artist recommendations")
    
    merged: List[dict] = []
    max_len = max(len(spotify_recs), len(artist_recs))
    
    for i in range(max_len):
        if i < len(spotify_recs):
            merged.append(spotify_recs[i])
        if i < len(artist_recs):
            merged.append(artist_recs[i])
    
    log_event("recommender-service", "INFO", f"Merged into {len(merged)} total recommendations")
    return {"recommendations": merged, "total": len(merged)}
