import httpx
from typing import List, Dict, Optional
from libs.shared.utils import log_event


class SpotifyClient:
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.client: Optional[httpx.AsyncClient] = None
        self.api_base = "https://api.spotify.com/v1"
    
    async def start(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def stop(self):
        if self.client:
            await self.client.aclose()
    
    def is_ready(self) -> bool:
        return self.client is not None and self.auth_manager.is_authenticated()
    
    def _get_auth_header(self) -> dict:
        token = self.auth_manager.get_access_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}
    
    async def _request(self, method: str, path: str, **kwargs):
        if not self.client:
            raise ValueError("Client not started")
        
        url = f"{self.api_base}{path}"
        headers = self._get_auth_header()
        
        resp = await self.client.request(method, url, headers=headers, **kwargs)
        
        if resp.status_code == 401:
            log_event("spotify-client", "INFO", "Token expired, refreshing...")
            await self.auth_manager.refresh_access_token()
            headers = self._get_auth_header()
            resp = await self.client.request(method, url, headers=headers, **kwargs)
        
        resp.raise_for_status()
        return resp.json()
    
    async def get_user_profile(self) -> dict:
        return await self._request("GET", "/me")
    
    async def get_top_tracks(self, time_range: str = "medium_term", limit: int = 300) -> List[dict]:
        all_tracks = []
        offset = 0
        batch_size = 50
        
        while len(all_tracks) < limit:
            log_event("spotify-client", "INFO", f"Fetching tracks batch: offset={offset}, time_range={time_range}")
            
            params = {
                "time_range": time_range,
                "limit": batch_size,
                "offset": offset
            }
            
            data = await self._request("GET", "/me/top/tracks", params=params)
            items = data.get("items", [])
            
            if not items:
                break
            
            all_tracks.extend(items)
            offset += batch_size
            
            if len(items) < batch_size:
                break
        
        return all_tracks[:limit]
    
    async def get_top_artists(self, time_range: str = "medium_term", limit: int = 300) -> List[dict]:
        all_artists = []
        offset = 0
        batch_size = 50
        
        while len(all_artists) < limit:
            log_event("spotify-client", "INFO", f"Fetching artists batch: offset={offset}, time_range={time_range}")
            
            params = {
                "time_range": time_range,
                "limit": batch_size,
                "offset": offset
            }
            
            data = await self._request("GET", "/me/top/artists", params=params)
            items = data.get("items", [])
            
            if not items:
                break
            
            all_artists.extend(items)
            offset += batch_size
            
            if len(items) < batch_size:
                break
        
        return all_artists[:limit]
    
    async def get_album(self, album_id: str) -> dict:
        return await self._request("GET", f"/albums/{album_id}")
