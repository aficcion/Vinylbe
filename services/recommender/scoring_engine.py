from typing import List, Dict
from libs.shared.utils import log_event


class ScoringEngine:
    def __init__(self):
        self.time_range_boosts = {
            "short_term": 3.0,
            "medium_term": 2.0,
            "long_term": 1.0,
        }
    
    def score_tracks(self, tracks: List[dict]) -> List[dict]:
        scored_tracks = []
        
        for idx, track in enumerate(tracks):
            time_range = track.get("time_range", "medium_term")
            boost = self.time_range_boosts.get(time_range, 1.0)
            
            position_score = 300 - (idx % 300)
            
            total_score = position_score * boost
            
            scored_track = {
                **track,
                "position": idx % 300,
                "score": total_score,
            }
            scored_tracks.append(scored_track)
        
        return scored_tracks
    
    def score_artists(self, artists: List[dict]) -> List[dict]:
        scored_artists = []
        
        for idx, artist in enumerate(artists):
            position_score = 300 - idx
            
            scored_artist = {
                **artist,
                "position": idx,
                "score": position_score,
            }
            scored_artists.append(scored_artist)
        
        return scored_artists
    
    def score_lastfm_tracks(self, tracks: List[dict]) -> List[dict]:
        """
        Score Last.fm tracks using playcount instead of position
        Last.fm tracks have: playcount, time_range (mapped from period)
        """
        scored_tracks = []
        
        if not tracks:
            return scored_tracks
        
        max_playcount = max((int(t.get("playcount", 0)) for t in tracks), default=1)
        
        for idx, track in enumerate(tracks):
            time_range = track.get("time_range", "medium_term")
            boost = self.time_range_boosts.get(time_range, 1.0)
            
            playcount = int(track.get("playcount", 0))
            playcount_score = (playcount / max_playcount) * 300 if max_playcount > 0 else 0
            
            total_score = playcount_score * boost
            
            scored_track = {
                **track,
                "position": idx,
                "score": total_score,
                "playcount": playcount,
                "source": "lastfm"
            }
            scored_tracks.append(scored_track)
        
        return scored_tracks
    
    def score_lastfm_artists(self, artists: List[dict]) -> List[dict]:
        """
        Score Last.fm artists using playcount
        """
        scored_artists = []
        
        if not artists:
            return scored_artists
        
        max_playcount = max((int(a.get("playcount", 0)) for a in artists), default=1)
        
        for idx, artist in enumerate(artists):
            playcount = int(artist.get("playcount", 0))
            playcount_score = (playcount / max_playcount) * 300 if max_playcount > 0 else 0
            
            scored_artist = {
                **artist,
                "position": idx,
                "score": playcount_score,
                "playcount": playcount,
                "source": "lastfm"
            }
            scored_artists.append(scored_artist)
        
        return scored_artists
