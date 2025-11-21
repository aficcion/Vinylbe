import os
import hashlib
import httpx
from typing import List, Dict, Any, Optional
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from libs.shared.utils import log_event


class LastFMClient:
    def __init__(self, api_key: str, username: str):
        self.api_key = api_key
        self.username = username
        self.api_base = "http://ws.audioscrobbler.com/2.0/"
        self.client = None
    
    async def start(self):
        self.client = httpx.AsyncClient()
    
    async def close(self):
        if self.client:
            await self.client.aclose()
    
    async def _request(self, method: str, params: Dict[str, Any]) -> dict:
        if not self.client:
            raise ValueError("Client not started")
        
        params["api_key"] = self.api_key
        params["format"] = "json"
        
        resp = await self.client.get(self.api_base, params=params)
        resp.raise_for_status()
        return resp.json()
    
    async def get_top_tracks(self, period: str = "3month", limit: int = 300) -> List[dict]:
        """
        Get user's top tracks for a given period
        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        all_tracks = []
        page = 1
        per_page = 50
        
        while len(all_tracks) < limit:
            log_event("lastfm-client", "INFO", f"Fetching tracks page={page}, period={period}")
            
            params = {
                "method": "user.getTopTracks",
                "user": self.username,
                "period": period,
                "limit": per_page,
                "page": page
            }
            
            data = await self._request("GET", params)
            tracks_data = data.get("toptracks", {}).get("track", [])
            
            if not tracks_data:
                break
            
            if isinstance(tracks_data, dict):
                tracks_data = [tracks_data]
            
            all_tracks.extend(tracks_data)
            
            if len(tracks_data) < per_page:
                break
            
            page += 1
        
        return all_tracks[:limit]
    
    async def get_top_artists(self, period: str = "3month", limit: int = 300) -> List[dict]:
        """
        Get user's top artists for a given period
        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        all_artists = []
        page = 1
        per_page = 50
        
        while len(all_artists) < limit:
            log_event("lastfm-client", "INFO", f"Fetching artists page={page}, period={period}")
            
            params = {
                "method": "user.getTopArtists",
                "user": self.username,
                "period": period,
                "limit": per_page,
                "page": page
            }
            
            data = await self._request("GET", params)
            artists_data = data.get("topartists", {}).get("artist", [])
            
            if not artists_data:
                break
            
            if isinstance(artists_data, dict):
                artists_data = [artists_data]
            
            all_artists.extend(artists_data)
            
            if len(artists_data) < per_page:
                break
            
            page += 1
        
        return all_artists[:limit]
    
    async def get_top_albums(self, period: str = "3month", limit: int = 50) -> List[dict]:
        """
        Get user's top albums for a given period
        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        all_albums = []
        page = 1
        per_page = 50
        
        while len(all_albums) < limit:
            log_event("lastfm-client", "INFO", f"Fetching albums page={page}, period={period}")
            
            params = {
                "method": "user.getTopAlbums",
                "user": self.username,
                "period": period,
                "limit": per_page,
                "page": page
            }
            
            data = await self._request("GET", params)
            albums_data = data.get("topalbums", {}).get("album", [])
            
            if not albums_data:
                break
            
            if isinstance(albums_data, dict):
                albums_data = [albums_data]
            
            all_albums.extend(albums_data)
            
            if len(albums_data) < per_page:
                break
            
            page += 1
        
        return all_albums[:limit]
    
    async def get_user_info(self) -> dict:
        """Get user profile information"""
        params = {
            "method": "user.getInfo",
            "user": self.username
        }
        data = await self._request("GET", params)
        return data.get("user", {})
