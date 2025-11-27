import os
import hashlib
from urllib.parse import urlencode
import httpx
from typing import Optional


class LastFMAuthManager:
    def __init__(self):
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.api_secret = os.getenv("LASTFM_API_SECRET")
        
        self.redirect_uri = os.getenv("LASTFM_CALLBACK_URL", os.getenv("LASTFM_REDIRECT_URI", "http://127.0.0.1:5000/callback.html"))
        self.api_base = "http://ws.audioscrobbler.com/2.0/"
        self.auth_url_base = "http://www.last.fm/api/auth"
        self.session_key = None
        self.username = None

    def _generate_signature(self, params: dict) -> str:
        """Generate MD5 signature for Last.fm API calls"""
        params_without_format = {k: v for k, v in params.items() if k != "format"}
        sorted_params = sorted(params_without_format.items())
        sig_string = ''.join([f"{k}{v}" for k, v in sorted_params])
        sig_string += self.api_secret
        return hashlib.md5(sig_string.encode('utf-8')).hexdigest()

    async def get_token(self) -> Optional[str]:
        """Get temporary token from Last.fm"""
        params = {
            "method": "auth.getToken",
            "api_key": self.api_key,
            "format": "json"
        }
        params["api_sig"] = self._generate_signature(params)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.api_base, params=params)
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            return data.get("token")

    def get_auth_url(self) -> str:
        """Get authorization URL for user to approve"""
        if not all([self.api_key, self.api_secret]):
            raise ValueError("Missing Last.fm credentials")
        
        params = {
            "api_key": self.api_key,
            "cb": self.redirect_uri
        }
        return f"{self.auth_url_base}?{urlencode(params)}"

    async def get_session(self, token: str) -> bool:
        """Exchange token for session key after user authorization"""
        params = {
            "method": "auth.getSession",
            "api_key": self.api_key,
            "token": token,
            "format": "json"
        }
        params["api_sig"] = self._generate_signature(params)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.api_base, params=params)
            
            if resp.status_code != 200:
                print(f"Last.fm API error: status={resp.status_code}, body={resp.text}")
                return False
            
            data = resp.json()
            
            if "error" in data:
                error_msg = data.get("message", "Unknown error")
                print(f"Last.fm error response: {error_msg}")
                return False
            
            session = data.get("session", {})
            self.session_key = session.get("key")
            self.username = session.get("name")
            
            success = bool(self.session_key)
            print(f"Session key obtained: {success}, username: {self.username}")
            return success

    def get_session_key(self) -> Optional[str]:
        return self.session_key

    def get_username(self) -> Optional[str]:
        return self.username

    def is_authenticated(self) -> bool:
        return bool(self.session_key and self.username)
