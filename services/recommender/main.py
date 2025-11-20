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
from .artist_recommendations import get_artist_based_recommendations, get_artist_studio_albums

scoring_engine = None
album_aggregator = None

progress_state = {
    "current": 0,
    "total": 0,
    "status": "idle",
    "current_artist": ""
}


class ArtistRecommendationRequest(BaseModel):
    artist_names: List[str]
    top_per_artist: int = 3


class MergeRecommendationsRequest(BaseModel):
    spotify_recommendations: List[dict]
    artist_recommendations: List[dict]


class SingleArtistRequest(BaseModel):
    artist_name: str
    top_albums: int = 3


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
    import time
    start_time = time.time()
    
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(tracks)} tracks")
    
    scored_tracks = scoring_engine.score_tracks(tracks)
    
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", f"Scored {len(scored_tracks)} tracks in {elapsed:.2f}s")
    return {"scored_tracks": scored_tracks, "total": len(scored_tracks)}


@app.post("/score-artists")
async def score_artists(artists: List[dict]):
    import time
    start_time = time.time()
    
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(artists)} artists")
    
    scored_artists = scoring_engine.score_artists(artists)
    
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", f"Scored {len(scored_artists)} artists in {elapsed:.2f}s")
    return {"scored_artists": scored_artists, "total": len(scored_artists)}


@app.post("/aggregate-albums")
async def aggregate_albums(scored_tracks: List[dict], scored_artists: List[dict]):
    import time
    start_time = time.time()
    
    if not album_aggregator:
        raise HTTPException(status_code=500, detail="Album aggregator not initialized")
    
    log_event("recommender-service", "INFO", f"Aggregating albums from {len(scored_tracks)} tracks")
    
    albums = album_aggregator.aggregate_albums(scored_tracks, scored_artists)
    
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", f"Generated {len(albums)} album recommendations in {elapsed:.2f}s")
    return {"albums": albums, "total": len(albums)}


@app.get("/progress")
async def get_progress():
    return progress_state


@app.post("/artist-recommendations")
async def artist_recommendations(request: ArtistRecommendationRequest):
    import time
    start_time = time.time()
    global progress_state
    
    discogs_key = os.getenv("DISCOGS_KEY")
    discogs_secret = os.getenv("DISCOGS_SECRET")
    
    if not discogs_key or not discogs_secret:
        raise HTTPException(status_code=500, detail="Discogs credentials not configured")
    
    if len(request.artist_names) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 artists required")
    
    if len(request.artist_names) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 artists allowed")
    
    progress_state = {
        "current": 0,
        "total": len(request.artist_names),
        "status": "processing",
        "current_artist": ""
    }
    
    log_event("recommender-service", "INFO", f"Generating recommendations for {len(request.artist_names)} artists")
    
    def update_progress(current: int, artist_name: str):
        global progress_state
        progress_state["current"] = current
        progress_state["current_artist"] = artist_name
    
    try:
        recommendations = get_artist_based_recommendations(
            request.artist_names,
            discogs_key,
            discogs_secret,
            top_per_artist=request.top_per_artist,
            progress_callback=update_progress
        )
        
        progress_state["status"] = "completed"
        
        elapsed = time.time() - start_time
        log_event("recommender-service", "INFO", f"Generated {len(recommendations)} artist-based recommendations in {elapsed:.2f}s")
        return {"recommendations": recommendations, "total": len(recommendations)}
    except Exception as e:
        progress_state["status"] = "error"
        raise e


@app.post("/merge-recommendations")
async def merge_recommendations(request: MergeRecommendationsRequest):
    import time
    start_time = time.time()
    
    spotify_recs = request.spotify_recommendations
    artist_recs = request.artist_recommendations
    
    log_event("recommender-service", "INFO", 
              f"Merging {len(spotify_recs)} Spotify + {len(artist_recs)} artist recommendations")
    
    seen_albums = set()
    merged: List[dict] = []
    max_len = max(len(spotify_recs), len(artist_recs))
    
    def get_album_keys(rec: dict) -> list:
        """Returns all possible keys for this album to handle metadata variations"""
        keys = []
        
        album = rec.get("album_name", "").lower().strip()
        artist = rec.get("artist_name", "").lower().strip()
        fallback_key = f"{artist}::{album}"
        keys.append(fallback_key)
        
        discogs_master = rec.get("discogs_master_id")
        if discogs_master:
            keys.append(f"master::{discogs_master}")
        
        return keys
    
    def is_duplicate(rec: dict) -> bool:
        """Check if album is already seen using any of its keys"""
        rec_keys = get_album_keys(rec)
        return any(key in seen_albums for key in rec_keys)
    
    def mark_as_seen(rec: dict):
        """Mark all keys for this album as seen"""
        rec_keys = get_album_keys(rec)
        for key in rec_keys:
            seen_albums.add(key)
    
    for i in range(max_len):
        if i < len(spotify_recs):
            if not is_duplicate(spotify_recs[i]):
                mark_as_seen(spotify_recs[i])
                merged.append(spotify_recs[i])
        
        if i < len(artist_recs):
            if not is_duplicate(artist_recs[i]):
                mark_as_seen(artist_recs[i])
                merged.append(artist_recs[i])
    
    duplicates_removed = (len(spotify_recs) + len(artist_recs)) - len(merged)
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", 
              f"Merged into {len(merged)} total recommendations ({duplicates_removed} duplicates removed) in {elapsed:.2f}s")
    return {"recommendations": merged, "total": len(merged)}


@app.post("/artist-single-recommendation")
async def artist_single_recommendation(request: SingleArtistRequest):
    import time
    start_time = time.time()
    
    discogs_key = os.getenv("DISCOGS_KEY")
    discogs_secret = os.getenv("DISCOGS_SECRET")
    
    if not discogs_key or not discogs_secret:
        raise HTTPException(status_code=500, detail="Discogs credentials not configured")
    
    log_event("recommender-service", "INFO", f"Generating recommendations for artist: {request.artist_name}")
    
    try:
        albums = get_artist_studio_albums(
            request.artist_name,
            discogs_key,
            discogs_secret,
            top_n=request.top_albums
        )
        
        recommendations = []
        for album in albums:
            rec = {
                "album_name": album.title,
                "artist_name": album.artist_name,
                "year": album.year,
                "rating": album.rating,
                "votes": album.votes,
                "discogs_master_id": album.discogs_master_id or album.discogs_release_id,
                "discogs_type": album.discogs_type,
                "image_url": album.cover_image or "https://via.placeholder.com/300x300?text=No+Cover",
                "source": "artist_based"
            }
            recommendations.append(rec)
        
        elapsed = time.time() - start_time
        log_event("recommender-service", "INFO", 
                 f"Generated {len(recommendations)} recommendations for {request.artist_name} in {elapsed:.2f}s")
        return {"recommendations": recommendations, "total": len(recommendations), "artist_name": request.artist_name}
    except Exception as e:
        log_event("recommender-service", "ERROR", f"Failed to generate recommendations for {request.artist_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")
