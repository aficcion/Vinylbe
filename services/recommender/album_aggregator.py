from typing import List, Dict, Set, Any
from collections import defaultdict
from libs.shared.utils import log_event


class AlbumData:
    def __init__(self):
        self.tracks: List[dict] = []
        self.total_score: float = 0
        self.artists: Set[str] = set()
        self.album_info: dict | None = None


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
            
            album_data[album_id].tracks.append(track)
            album_data[album_id].total_score += track.get("score", 0)
            
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
            
            score = data.total_score
            if artist_boost:
                score *= self.favorite_artist_boost
                log_event("album-aggregator", "INFO", f"Applied artist boost to album {album_id}")
            
            album_recommendation = {
                "album_id": album_id,
                "album_info": data.album_info,
                "track_count": track_count,
                "score": score,
                "artist_boost": artist_boost,
            }
            filtered_albums.append(album_recommendation)
        
        log_event("album-aggregator", "INFO", f"Filtered to {len(filtered_albums)} albums (>= 5 tracks)")
        
        filtered_albums.sort(key=lambda x: x["score"], reverse=True)
        
        log_event("album-aggregator", "INFO", "Albums sorted by score")
        
        return filtered_albums
