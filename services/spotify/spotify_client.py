import os
import time
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from libs.shared.utils import log_event


class SpotifyClient:
    """Client for Spotify Web API with OAuth 2.0 Client Credentials Flow"""
    
    BASE_URL = "https://api.spotify.com/v1"
    AUTH_URL = "https://accounts.spotify.com/api/token"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
    
    async def _get_access_token(self) -> str:
        """Get or refresh access token using Client Credentials Flow"""
        # Check if token is still valid
        if self.access_token and self.token_expires_at:
            if datetime.now() < self.token_expires_at - timedelta(minutes=5):
                return self.access_token
        
        # Request new token
        log_event("spotify-client", "INFO", "Requesting new access token")
        
        try:
            response = await self.http_client.post(
                self.AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            log_event("spotify-client", "INFO", f"Access token obtained, expires in {expires_in}s")
            return self.access_token
            
        except Exception as e:
            log_event("spotify-client", "ERROR", f"Failed to get access token: {str(e)}")
            raise
    
    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to Spotify API with retry logic"""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        max_retries = 3
        backoff = 1.0
        
        for attempt in range(1, max_retries + 1):
            try:
                if method == "GET":
                    response = await self.http_client.get(url, headers=headers, params=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    log_event("spotify-client", "WARNING", f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt < max_retries:
                    # Token might be invalid, refresh and retry
                    log_event("spotify-client", "WARNING", "Token invalid, refreshing...")
                    self.access_token = None
                    token = await self._get_access_token()
                    headers["Authorization"] = f"Bearer {token}"
                    continue
                    
                log_event("spotify-client", "ERROR", f"HTTP error: {e.response.status_code} - {e.response.text}")
                raise
                
            except Exception as e:
                if attempt < max_retries:
                    log_event("spotify-client", "WARNING", f"Request failed (attempt {attempt}/{max_retries}): {str(e)}")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    log_event("spotify-client", "ERROR", f"Request failed after {max_retries} attempts: {str(e)}")
                    raise
        
        raise RuntimeError("Max retries exceeded")
    
    async def search_artists(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for artists on Spotify
        
        Returns:
            List of artists with: id, name, image_url, genres, popularity
        """
        log_event("spotify-client", "INFO", f"Searching artists: {query}")
        
        params = {
            "q": query,
            "type": "artist",
            "limit": min(limit, 50)
        }
        
        data = await self._make_request("GET", "/search", params)
        artists_data = data.get("artists", {}).get("items", [])
        
        artists = []
        for artist in artists_data:
            images = artist.get("images", [])
            image_url = images[0]["url"] if images else None
            
            artists.append({
                "id": artist["id"],
                "name": artist["name"],
                "image_url": image_url,
                "genres": artist.get("genres", []),
                "popularity": artist.get("popularity", 0)
            })
        
        log_event("spotify-client", "INFO", f"Found {len(artists)} artists")
        return artists
    
    async def get_artist_albums(self, artist_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get albums for an artist
        
        Returns:
            List of albums with: id, name, artist_name, image_url, release_date, total_tracks
        """
        log_event("spotify-client", "INFO", f"Getting albums for artist: {artist_id}")
        
        params = {
            "include_groups": "album",  # Only albums, no singles/compilations
            "limit": min(limit, 50),
            "market": "ES"  # Filter by market to get available albums
        }
        
        data = await self._make_request("GET", f"/artists/{artist_id}/albums", params)
        albums_data = data.get("items", [])
        
        albums = []
        seen_names = set()  # Deduplicate albums with same name
        
        for album in albums_data:
            album_name = album["name"]
            
            # Skip duplicates (reissues, different markets)
            if album_name.lower() in seen_names:
                continue
            seen_names.add(album_name.lower())
            
            images = album.get("images", [])
            image_url = images[0]["url"] if images else None
            
            artists = album.get("artists", [])
            artist_name = artists[0]["name"] if artists else "Unknown"
            
            albums.append({
                "id": album["id"],
                "name": album_name,
                "artist_name": artist_name,
                "artist_id": artist_id,
                "image_url": image_url,
                "release_date": album.get("release_date"),
                "total_tracks": album.get("total_tracks", 0)
            })
        
        log_event("spotify-client", "INFO", f"Found {len(albums)} unique albums")
        return albums
    
    async def search_album(self, artist_name: str, album_name: str) -> Optional[Dict[str, Any]]:
        """Search for a specific album by artist and name
        
        Returns:
            Album data or None if not found
        """
        log_event("spotify-client", "INFO", f"Searching album: {artist_name} - {album_name}")
        
        query = f"artist:{artist_name} album:{album_name}"
        params = {
            "q": query,
            "type": "album",
            "limit": 5
        }
        
        data = await self._make_request("GET", "/search", params)
        albums_data = data.get("albums", {}).get("items", [])
        
        if not albums_data:
            log_event("spotify-client", "INFO", f"Album not found: {artist_name} - {album_name}")
            return None
        
        # Take first result (best match)
        album = albums_data[0]
        images = album.get("images", [])
        image_url = images[0]["url"] if images else None
        
        artists = album.get("artists", [])
        artist = artists[0] if artists else {}
        
        result = {
            "id": album["id"],
            "name": album["name"],
            "artist_name": artist.get("name", artist_name),
            "artist_id": artist.get("id"),
            "image_url": image_url,
            "release_date": album.get("release_date"),
            "total_tracks": album.get("total_tracks", 0)
        }
        
        log_event("spotify-client", "INFO", f"Album found: {result['name']}")
        return result
