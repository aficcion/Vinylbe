import os
import base64
from urllib.parse import urlencode
import httpx
from typing import Optional


class SpotifyAuthManager:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
        self.auth_url = "https://accounts.spotify.com/authorize"
        self.token_url = "https://accounts.spotify.com/api/token"
        self.tokens = {}
    
    def get_auth_url(self) -> str:
        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            raise ValueError("Missing Spotify credentials")
        
        scopes = ["user-top-read", "user-read-email"]
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
    def _get_basic_auth_header(self) -> dict:
        creds = f"{self.client_id}:{self.client_secret}".encode()
        encoded = base64.b64encode(creds).decode()
        return {"Authorization": f"Basic {encoded}"}
    
    async def exchange_code_for_token(self, code: str) -> bool:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        headers = self._get_basic_auth_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                return False
            
            tokens = resp.json()
            self.tokens["access_token"] = tokens.get("access_token")
            self.tokens["refresh_token"] = tokens.get("refresh_token")
            return True
    
    async def refresh_access_token(self) -> bool:
        if not self.tokens.get("refresh_token"):
            return False
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.tokens["refresh_token"],
        }
        headers = self._get_basic_auth_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                return False
            
            tokens = resp.json()
            self.tokens["access_token"] = tokens.get("access_token")
            if "refresh_token" in tokens:
                self.tokens["refresh_token"] = tokens["refresh_token"]
            return True
    
    def get_access_token(self) -> Optional[str]:
        return self.tokens.get("access_token")
    
    def is_authenticated(self) -> bool:
        return bool(self.tokens.get("access_token"))
