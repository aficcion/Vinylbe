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
from . import db_utils
from .scoring_engine import ScoringEngine
from .album_aggregator import AlbumAggregator
from .artist_recommendations import get_artist_based_recommendations, get_artist_studio_albums

SPOTIFY_SERVICE_URL = os.getenv("SPOTIFY_SERVICE_URL", "http://127.0.0.1:3005")

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
    artist_recommendations: List[dict]
    lastfm_recommendations: List[dict] = []


class SingleArtistRequest(BaseModel):
    artist_name: str
    top_albums: int = 3
    csv_mode: bool = False
    cache_only: bool = False


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


@app.post("/lastfm-albums-recommendations")
async def lastfm_albums_recommendations(albums: List[dict]):
    """Simplified: user.gettopalbums → cache-first → fetch covers on-demand"""
    import time
    import asyncio
    import httpx
    from concurrent.futures import ThreadPoolExecutor
    from . import db_utils
    
    start_time = time.time()
    log_event("recommender-service", "INFO", f"Processing {len(albums)} Last.fm albums")
    
    all_recommendations = []
    cache_hits = 0
    cache_misses = 0
    covers_fetched = 0
    
    def fetch_from_db(artist_name, album_name, mbid=None):
        """Run DB lookup in thread pool to avoid blocking"""
        return db_utils.get_cached_album(artist_name, album_name, mbid)
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        with ThreadPoolExecutor(max_workers=3) as executor:
            loop = asyncio.get_event_loop()
            
            for album_data in albums[:50]:
                try:
                    album_name = album_data.get("name", "").strip()
                    mbid = album_data.get("mbid")
                    artist_data = album_data.get("artist", {})
                    
                    if isinstance(artist_data, str):
                        artist_name = artist_data.strip()
                    else:
                        artist_name = artist_data.get("name", "").strip()
                    
                    playcount = int(album_data.get("playcount", 0))
                    
                    if not album_name or not artist_name:
                        continue
                    
                    cached_album = await loop.run_in_executor(
                        executor, fetch_from_db, artist_name, album_name, mbid
                    )
                    
                    if cached_album:
                        cache_hits += 1
                        all_recommendations.append({
                            "artist_name": artist_name,
                            "album_name": cached_album["title"],
                            "year": cached_album.get("year"),
                            "discogs_master_id": cached_album.get("discogs_master_id"),
                            "discogs_release_id": cached_album.get("discogs_release_id"),
                            "rating": cached_album.get("rating"),
                            "votes": cached_album.get("votes"),
                            "cover_url": cached_album.get("cover_url"),
                            "lastfm_playcount": playcount,
                            "source": "lastfm"
                        })
                    else:
                        cache_misses += 1
                        
                        cover_url = None
                        spotify_album_id = None
                        spotify_artist_id = None
                        
                        try:
                            # Use Spotify for cover and IDs
                            resp = await client.get(
                                f"{SPOTIFY_SERVICE_URL}/search/album",
                                params={"artist": artist_name, "album": album_name}
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                cover_url = data.get("image_url")
                                spotify_album_id = data.get("id")
                                spotify_artist_id = data.get("artist_id")
                                
                                if cover_url:
                                    covers_fetched += 1
                                    log_event("recommender-service", "DEBUG", 
                                             f"✓ Spotify data fetched: {artist_name} - {album_name}")
                        except Exception as e:
                            log_event("recommender-service", "WARNING", 
                                     f"Spotify fetch failed: {artist_name} - {album_name}: {str(e)}")
                        
                        if cover_url:
                            await loop.run_in_executor(
                                executor, db_utils.create_basic_album_entry,
                                artist_name, album_name, cover_url, mbid, spotify_album_id, spotify_artist_id
                            )
                            
                            all_recommendations.append({
                                "artist_name": artist_name,
                                "album_name": album_name,
                                "year": None,
                                "discogs_master_id": None,
                                "discogs_release_id": None,
                                "rating": None,
                                "votes": None,
                                "cover_url": cover_url,
                                "spotify_id": spotify_album_id,
                                "lastfm_playcount": playcount,
                                "source": "lastfm"
                            })
                        else:
                            log_event("recommender-service", "INFO", 
                                     f"Skipped non-vinyl album: {artist_name} - {album_name}")
                        
                except Exception as e:
                    log_event("recommender-service", "ERROR", 
                             f"Album error: {str(e)}")
                    continue
    
    end_time = time.time()
    total_time = end_time - start_time
    
    log_event("recommender-service", "INFO", 
              f"✓ {len(all_recommendations)} albums processed in {total_time:.2f}s "
              f"(hits: {cache_hits}, new: {cache_misses}, covers: {covers_fetched})")
    
    return {
        "albums": all_recommendations,
        "total": len(all_recommendations),
        "stats": {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "covers_fetched": covers_fetched,
            "albums_processed": len(albums[:50]),
            "total_time_seconds": round(total_time, 2)
        }
    }


@app.post("/lastfm-recommendations")
async def lastfm_recommendations(artists: List[dict]):
    """
    LEGACY: Generate album recommendations from Last.fm artists using PostgreSQL cache
    Input: [{"name": "Artist Name", "score": 250.5, "playcount": 1234}, ...]
    """
    import time
    from . import artist_recommendations
    start_time = time.time()
    
    log_event("recommender-service", "INFO", f"Generating Last.fm recommendations for {len(artists)} artists")
    
    all_albums = []
    cache_hits = 0
    cache_misses = 0
    
    for artist in artists[:50]:
        artist_name = artist.get("name")
        lastfm_score = artist.get("score", 0)
        lastfm_playcount = artist.get("playcount", 0)
        
        if not artist_name:
            continue
        
        cached_albums = artist_recommendations._get_cached_artist_albums(artist_name)
        
        if cached_albums:
            cache_hits += 1
            for album in cached_albums[:2]:
                all_albums.append({
                    "artist_name": artist_name,
                    "album_name": album.get("title"),
                    "year": album.get("year"),
                    "discogs_master_id": album.get("discogs_master_id"),
                    "discogs_release_id": album.get("discogs_release_id"),
                    "rating": album.get("rating"),
                    "votes": album.get("votes"),
                    "cover_url": album.get("cover_url"),
                    "lastfm_score": lastfm_score,
                    "lastfm_playcount": lastfm_playcount,
                    "source": "lastfm"
                })
        else:
            cache_misses += 1
    
    end_time = time.time()
    total_time = end_time - start_time
    
    log_event("recommender-service", "INFO", 
              f"Generated {len(all_albums)} Last.fm recommendations in {total_time:.2f}s "
              f"(cache hits: {cache_hits}, misses: {cache_misses})")
    
    return {
        "albums": all_albums,
        "total": len(all_albums),
        "stats": {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "artists_processed": len(artists[:50]),
            "total_time_seconds": round(total_time, 2)
        }
    }


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


@app.post("/score-lastfm-tracks")
async def score_lastfm_tracks(tracks: List[dict]):
    import time
    start_time = time.time()
    
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(tracks)} Last.fm tracks")
    
    scored_tracks = scoring_engine.score_lastfm_tracks(tracks)
    
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", f"Scored {len(scored_tracks)} Last.fm tracks in {elapsed:.2f}s")
    return {"scored_tracks": scored_tracks, "total": len(scored_tracks)}


@app.post("/score-lastfm-artists")
async def score_lastfm_artists(artists: List[dict]):
    import time
    start_time = time.time()
    
    if not scoring_engine:
        raise HTTPException(status_code=500, detail="Scoring engine not initialized")
    
    log_event("recommender-service", "INFO", f"Scoring {len(artists)} Last.fm artists")
    
    scored_artists = scoring_engine.score_lastfm_artists(artists)
    
    elapsed = time.time() - start_time
    log_event("recommender-service", "INFO", f"Scored {len(scored_artists)} Last.fm artists in {elapsed:.2f}s")
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
    
    artist_recs = request.artist_recommendations
    lastfm_recs = request.lastfm_recommendations
    
    log_event("recommender-service", "INFO", 
              f"Merging {len(artist_recs)} artist + {len(lastfm_recs)} Last.fm recommendations")
    
    seen_albums = set()
    merged: List[dict] = []
    max_len = max(len(artist_recs), len(lastfm_recs))
    
    def get_album_keys(rec: dict) -> list:
        """Returns all possible keys for this album to handle metadata variations"""
        keys = []
        
        if "album_info" in rec:
            album_info = rec.get("album_info", {})
            album = album_info.get("name", "").lower().strip()
            artists_list = album_info.get("artists", [])
            artist = artists_list[0].get("name", "") if artists_list else ""
            artist = artist.lower().strip()
        else:
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
        if i < len(lastfm_recs):
            if not is_duplicate(lastfm_recs[i]):
                mark_as_seen(lastfm_recs[i])
                merged.append(lastfm_recs[i])
        
        if i < len(artist_recs):
            if not is_duplicate(artist_recs[i]):
                mark_as_seen(artist_recs[i])
                merged.append(artist_recs[i])
    
    duplicates_removed = (len(artist_recs) + len(lastfm_recs)) - len(merged)
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
        # 1. Try to get from DB (Cache Only)
        # This is FAST and checks if we already have quality data
        albums = get_artist_studio_albums(
            request.artist_name,
            discogs_key,
            discogs_secret,
            top_n=request.top_albums,
            csv_mode=request.csv_mode,
            cache_only=True  # FORCE CACHE ONLY - Do not go to Discogs yet
        )
        
        if albums:
            # CACHE HIT: We have data in DB, return it
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
                     f"✓ Cache HIT for {request.artist_name}: {len(recommendations)} albums in {elapsed:.2f}s")
            return {"recommendations": recommendations, "total": len(recommendations), "artist_name": request.artist_name}
            
        else:
            # CACHE MISS: Do NOT go to Discogs (too slow for interactive use)
            # Fallback immediately to Spotify (Fast, creates partial records)
            log_event("recommender-service", "INFO", 
                     f"○ Cache MISS for {request.artist_name}. Falling back to Spotify for speed.")
            
            return await _generate_spotify_recommendations(
                request.artist_name, 
                request.top_albums,
                user_id=None
            )

    except Exception as e:
        log_event("recommender-service", "ERROR", f"Failed to generate recommendations for {request.artist_name}: {str(e)}")
        # If Spotify fallback also fails, we return error
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


async def _generate_spotify_recommendations(artist_name: str, top_albums: int, user_id: int = None):
    """Helper to generate recommendations using Spotify (fast fallback)"""
    import time
    import httpx
    from . import db_utils
    
    start_time = time.time()
    log_event("recommender-service", "INFO", f"Generating Spotify recommendations for: {artist_name}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Search artist to get ID
        search_resp = await client.get(
            f"{SPOTIFY_SERVICE_URL}/search/artists",
            params={"q": artist_name, "limit": 1}
        )
        search_data = search_resp.json()
        artists = search_data.get("artists", [])
        
        if not artists:
            raise HTTPException(status_code=404, detail="Artist not found on Spotify")
        
        artist = artists[0]
        spotify_artist_id = artist["id"]
        artist_name = artist["name"]  # Use canonical name
        
        # 2. Get top albums
        albums_resp = await client.get(
            f"{SPOTIFY_SERVICE_URL}/artist/{spotify_artist_id}/albums",
            params={"limit": top_albums + 5}  # Fetch a few more to filter
        )
        albums_data = albums_resp.json()
        spotify_albums = albums_data.get("albums", [])
        
        recommendations = []
        
        # 3. Process albums (check cache or create partial)
        for album in spotify_albums[:top_albums]:
            # Check cache
            cached = db_utils.get_cached_album(
                artist_name, 
                album["name"], 
                spotify_id=album["id"]
            )
            
            if cached:
                # Use cached data (might be full or partial)
                rec = {
                    "album_name": cached["title"],
                    "artist_name": cached["artist_name"],
                    "year": cached.get("year"),
                    "rating": cached.get("rating"),
                    "votes": cached.get("votes"),
                    "discogs_master_id": cached.get("discogs_master_id"),
                    "image_url": cached.get("cover_url"),
                    "spotify_id": cached.get("spotify_id"),
                    "is_partial": cached.get("is_partial", 0),
                    "source": "spotify"
                }
            else:
                # Create partial entry
                db_utils.create_basic_album_entry(
                    artist_name,
                    album["name"],
                    cover_url=album["image_url"],
                    spotify_id=album["id"],
                    artist_spotify_id=spotify_artist_id
                )
                
                rec = {
                    "album_name": album["name"],
                    "artist_name": artist_name,
                    "year": album.get("release_date")[:4] if album.get("release_date") else None,
                    "rating": None,
                    "votes": None,
                    "image_url": album["image_url"],
                    "spotify_id": album["id"],
                    "is_partial": 1,
                    "source": "spotify"
                }
            
            recommendations.append(rec)
        
        elapsed = time.time() - start_time
        log_event("recommender-service", "INFO", 
                 f"Generated {len(recommendations)} Spotify recommendations for {artist_name} in {elapsed:.2f}s")
        
        return {
            "recommendations": recommendations, 
            "total": len(recommendations), 
            "artist_name": artist_name
        }


@app.post("/spotify-recommendations")
async def spotify_recommendations(request: SingleArtistRequest):
    """Generate recommendations using Spotify (fast fallback)"""
    try:
        return await _generate_spotify_recommendations(
            request.artist_name, 
            request.top_albums, 
            user_id=None
        )
    except Exception as e:
        log_event("recommender-service", "ERROR", f"Spotify recommendations failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")
