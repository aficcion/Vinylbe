from typing import List, Dict, Set, Any
from collections import defaultdict
from libs.shared.utils import log_event


class AlbumData:
    def __init__(self):
        self.tracks: List[dict] = []
        self.total_score: float = 0
        self.artists: Set[str] = set()
        self.album_info: dict | None = None
        self.score_by_period: Dict[str, float] = {"short_term": 0, "medium_term": 0, "long_term": 0}
        self.tracks_by_period: Dict[str, int] = {"short_term": 0, "medium_term": 0, "long_term": 0}


class AlbumAggregator:
    def __init__(self):
        self.favorite_artist_boost = 5.0
    
    def aggregate_albums(self, scored_tracks: List[dict], scored_artists: List[dict]) -> List[dict]:
        log_event("album-aggregator", "INFO", "Starting album aggregation")
        
        artist_scores = {artist["id"]: artist["score"] for artist in scored_artists}
        
        album_data: Dict[str, AlbumData] = {}
        
        for track in scored_tracks:
            album_id = track.get("album", {}).get("id")
            if not album_id:
                continue
            
            if album_id not in album_data:
                album_data[album_id] = AlbumData()
            
            track_score = track.get("score", 0)
            time_range = track.get("time_range", "unknown")
            
            album_data[album_id].tracks.append(track)
            album_data[album_id].total_score += track_score
            
            if time_range in album_data[album_id].score_by_period:
                album_data[album_id].score_by_period[time_range] += track_score
                album_data[album_id].tracks_by_period[time_range] += 1
            
            album_artists = track.get("album", {}).get("artists", [])
            for artist in album_artists:
                artist_id = artist.get("id")
                if artist_id:
                    album_data[album_id].artists.add(artist_id)
            
            if album_data[album_id].album_info is None:
                album_data[album_id].album_info = track.get("album", {})
        
        log_event("album-aggregator", "INFO", f"Found {len(album_data)} unique albums")
        
        filtered_albums = []
        for album_id, data in album_data.items():
            track_count = len(data.tracks)
            
            if track_count < 5:
                continue
            
            artist_boost = any(artist_id in artist_scores for artist_id in data.artists)
            
            base_score = data.total_score
            final_score = base_score
            if artist_boost:
                final_score *= self.favorite_artist_boost
                log_event("album-aggregator", "INFO", f"Applied artist boost to album {album_id}")
            
            album_recommendation = {
                "album_id": album_id,
                "album_info": data.album_info,
                "track_count": track_count,
                "score": final_score,
                "artist_boost": artist_boost,
                "score_breakdown": {
                    "base_score": round(base_score, 2),
                    "artist_boost_applied": artist_boost,
                    "artist_boost_multiplier": self.favorite_artist_boost if artist_boost else 1.0,
                    "final_score": round(final_score, 2),
                    "score_by_period": {
                        "short_term": round(data.score_by_period["short_term"], 2),
                        "medium_term": round(data.score_by_period["medium_term"], 2),
                        "long_term": round(data.score_by_period["long_term"], 2),
                    },
                    "tracks_by_period": data.tracks_by_period,
                },
            }
            filtered_albums.append(album_recommendation)
        
        log_event("album-aggregator", "INFO", f"Filtered to {len(filtered_albums)} albums (>= 5 tracks)")
        
        filtered_albums.sort(key=lambda x: x["score"], reverse=True)
        
        log_event("album-aggregator", "INFO", "Albums sorted by score")
        
        return filtered_albums
