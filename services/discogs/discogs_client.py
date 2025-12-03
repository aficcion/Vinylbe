import httpx
import asyncio
import time
from typing import List, Dict, Optional
from libs.shared.utils import log_event


class DiscogsClient:
    def __init__(self, key: str, secret: str):
        self.key = key
        self.secret = secret
        self.client: Optional[httpx.AsyncClient] = None
        self.api_base = "https://api.discogs.com"
        self.last_request_time = 0.0
        self.min_request_interval = 2.0
    
    async def start(self):
        headers = {"User-Agent": "VinylRecommender/1.0"}
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)
    
    async def stop(self):
        if self.client:
            await self.client.aclose()
    
    def is_ready(self) -> bool:
        return self.client is not None and bool(self.key) and bool(self.secret)
    
    async def _rate_limit(self):
        """Rate limiter: ensure we don't exceed 60 requests per minute"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last_request
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _get_auth_params(self, **params) -> dict:
        return {
            **params,
            "key": self.key,
            "secret": self.secret,
        }
    
    def _build_debug_url(self, url: str, params: dict) -> str:
        """Build URL for debugging with credentials hidden"""
        debug_params = params.copy()
        if "key" in debug_params:
            debug_params["key"] = "[HIDDEN]"
        if "secret" in debug_params:
            debug_params["secret"] = "[HIDDEN]"
        
        query_string = "&".join(f"{k}={v}" for k, v in debug_params.items())
        return f"{url}?{query_string}"
    
    def _normalize_album_title(self, title: str) -> str:
        """
        Normalize album title by removing common suffixes added by streaming platforms.
        This improves matching with Discogs database.
        
        Examples:
        - "Remain in Light (Deluxe Version)" -> "Remain in Light"
        - "Dark Side of the Moon (Remastered)" -> "Dark Side of the Moon"
        """
        import re
        
        # Common suffixes to remove (case-insensitive)
        suffixes = [
            r'\s*\(Deluxe(?:\s+(?:Edition|Version))?\)',
            r'\s*\(Remastered(?:\s+\d{4})?\)',
            r'\s*\(Anniversary(?:\s+Edition)?\)',
            r'\s*\(Expanded(?:\s+Edition)?\)',
            r'\s*\(Special(?:\s+Edition)?\)',
            r'\s*\(Limited(?:\s+Edition)?\)',
            r'\s*\(\d+(?:th|st|nd|rd)?\s+Anniversary(?:\s+Edition)?\)',
            r'\s*\(Bonus\s+Track(?:s)?(?:\s+Edition)?\)',
            r'\s*\(Platinum\s+Edition\)',
            r'\s*\(Standard\s+Edition\)',
            r'\s*\(Explicit\)',
            r'\s*\[Remastered\]',
            r'\s*-\s*Remastered(?:\s+\d{4})?',
        ]
        
        normalized = title
        for suffix_pattern in suffixes:
            normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    async def search_release(self, artist: str, title: str) -> List[dict]:
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        params = self._get_auth_params(
            artist=artist,
            release_title=title,
            format="Vinyl",
            type="release",
        )
        
        url = f"{self.api_base}/database/search"
        
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            
            # Return both results and debug info
            return {
                "results": results,
                "debug_info": {
                    "request_url": debug_url,
                    "params_sent": {k: v for k, v in params.items() if k not in ["key", "secret"]}
                }
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Search failed: {str(e)}")
            return {
                "results": [],
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }

    async def search_album(self, album_title: str) -> List[dict]:
        """Search for albums by title only"""
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        params = self._get_auth_params(
            release_title=album_title,
            format="Vinyl,LP,Album",
            per_page=20
        )
        
        url = f"{self.api_base}/database/search"
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            
            return {
                "results": results,
                "debug_info": {
                    "request_url": debug_url,
                    "params_sent": {k: v for k, v in params.items() if k not in ["key", "secret"]}
                }
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Album search failed: {str(e)}")
            return {
                "results": [],
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }
    
    async def get_marketplace_stats(self, release_id: int, currency: str = "EUR") -> dict:
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        # First, get the release details to extract master_id
        master_id = await self._get_master_id_from_release(release_id)
        
        params = self._get_auth_params(currency=currency)
        url = f"{self.api_base}/marketplace/stats/{release_id}"
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            # Use master_id in the sell list URL as per user's specification
            if master_id:
                sell_list_url = f"https://www.discogs.com/sell/list?master_id={master_id}&currency=EUR&format=Vinyl"
            else:
                # Fallback to release_id if master_id not found
                sell_list_url = f"https://www.discogs.com/sell/list?release_id={release_id}&currency=EUR&format=Vinyl"
            
            lowest_price_data = data.get("lowest_price")
            
            if lowest_price_data is None or not isinstance(lowest_price_data, dict):
                source_price = None
                source_currency = "EUR"
                price_in_eur = None
            else:
                source_price = lowest_price_data.get("value")
                source_currency = lowest_price_data.get("currency", "EUR")
                
                if source_price is not None and source_currency != "EUR":
                    price_in_eur = await self.convert_to_eur(source_price, source_currency)
                    log_event("discogs-client", "INFO", f"Converted {source_price} {source_currency} to {price_in_eur:.2f} EUR")
                else:
                    price_in_eur = source_price
            
            return {
                "release_id": release_id,
                "lowest_price_eur": price_in_eur,
                "lowest_price": price_in_eur,
                "currency": "EUR",
                "original_price": source_price,
                "original_currency": source_currency,
                "num_for_sale": data.get("num_for_sale", 0),
                "sell_list_url": sell_list_url,
                "debug_info": {
                    "request_url": debug_url,
                    "params_sent": {k: v for k, v in params.items() if k not in ["key", "secret"]}
                }
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Stats fetch failed for release {release_id}: {str(e)}")
            
            # Use master_id in error case too if available
            if master_id:
                sell_list_url = f"https://www.discogs.com/sell/list?master_id={master_id}&currency=EUR&format=Vinyl"
            else:
                sell_list_url = f"https://www.discogs.com/sell/list?release_id={release_id}&currency=EUR&format=Vinyl"
            
            return {
                "release_id": release_id,
                "lowest_price_eur": None,
                "lowest_price": None,
                "currency": "EUR",
                "original_price": None,
                "original_currency": None,
                "num_for_sale": 0,
                "sell_list_url": sell_list_url,
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }
    
    async def _get_master_id_from_release(self, release_id: int) -> Optional[int]:
        """Get the master_id from a release_id by fetching release details"""
        if not self.client:
            return None
        
        try:
            await self._rate_limit()
            params = self._get_auth_params()
            url = f"{self.api_base}/releases/{release_id}"
            
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            master_id = data.get("master_id")
            if master_id:
                log_event("discogs-client", "INFO", f"Found master_id {master_id} for release {release_id}")
            return master_id
        except Exception as e:
            log_event("discogs-client", "WARNING", f"Could not get master_id for release {release_id}: {str(e)}")
            return None
    
    async def convert_to_eur(self, price: float, from_currency: str) -> float:
        """Convert price from source currency to EUR using current exchange rates (Nov 2025)"""
        if from_currency == "EUR":
            return price
        
        conversion_rates = {
            "USD": 0.865,
            "GBP": 1.140,
            "JPY": 0.00573,
            "CAD": 0.617,
            "AUD": 0.562,
        }
        
        rate = conversion_rates.get(from_currency, 1.0)
        return price * rate
    
    async def get_master_link(self, artist: str, album: str) -> Optional[Dict]:
        """
        Busca un álbum en Discogs con fallback inteligente.
        
        Estrategia:
        1. Normaliza el título (elimina sufijos como "Deluxe", "Remastered", etc.)
        2. Busca primero tipo "master"
        3. Si no hay resultados, busca tipo "release"
        4. Retorna el primero que encuentre con su tipo correcto
        
        Returns dict con:
        - type: "master" o "release"
        - master_id o release_id
        - master_url o release_url  
        """
        if not self.client:
            raise ValueError("Client not started")
        
        # Normalizar el título del álbum
        normalized_album = self._normalize_album_title(album)
        log_event("discogs-client", "INFO", f"Normalized album title: '{album}' -> '{normalized_album}'")
        
        # Intentar buscar master primero
        await self._rate_limit()
        
        params_master = self._get_auth_params(
            artist=artist,
            release_title=normalized_album,
            type="master",
        )
        
        url = f"{self.api_base}/database/search"
        debug_url_master = self._build_debug_url(url, params_master)
        
        try:
            resp = await self.client.get(url, params=params_master)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            
            if results:
                first_result = results[0]
                master_id = first_result.get("master_id") or first_result.get("id")
                
                if master_id:
                    master_url = f"https://www.discogs.com/master/{master_id}"
                    log_event("discogs-client", "INFO", f"Found master {master_id} for '{album}'")
                    
                    return {
                        "type": "master",
                        "id": master_id,
                        "master_id": master_id,  # backward compatibility
                        "url": master_url,
                        "master_url": master_url,  # backward compatibility
                        "title": first_result.get("title", ""),
                        "debug_info": {
                            "request_url": debug_url_master,
                            "normalized_title": normalized_album,
                            "search_type": "master"
                        }
                    }
            
            # No master found, try release as fallback
            log_event("discogs-client", "INFO", f"No master found for '{album}', trying release fallback")
            
            await self._rate_limit()
            
            params_release = self._get_auth_params(
                artist=artist,
                release_title=normalized_album,
                format="Vinyl",
                type="release",
            )
            
            debug_url_release = self._build_debug_url(url, params_release)
            
            resp = await self.client.get(url, params=params_release)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            
            if results:
                first_result = results[0]
                release_id = first_result.get("id")
                
                if release_id:
                    release_url = f"https://www.discogs.com/release/{release_id}"
                    log_event("discogs-client", "INFO", f"Found release {release_id} for '{album}'")
                    
                    return {
                        "type": "release",
                        "id": release_id,
                        "release_id": release_id,
                        "url": release_url,
                        "release_url": release_url,
                        "title": first_result.get("title", ""),
                        "debug_info": {
                            "request_url": debug_url_release,
                            "normalized_title": normalized_album,
                            "search_type": "release (fallback)"
                        }
                    }
            
            # Neither master nor release found
            log_event("discogs-client", "WARNING", f"No master or release found for '{album}'")
            return {
                "type": None,
                "id": None,
                "url": None,
                "message": "No master or release found",
                "debug_info": {
                    "original_title": album,
                    "normalized_title": normalized_album,
                    "searches_attempted": ["master", "release"]
                }
            }
            
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Master/release link fetch failed: {str(e)}")
            return {
                "type": None,
                "id": None,
                "url": None,
                "message": f"Error: {str(e)}",
                "debug_info": {
                    "original_title": album,
                    "normalized_title": normalized_album,
                    "error": str(e)
                }
            }
    
    async def get_master_tracklist(self, master_id: int) -> Optional[Dict]:
        """
        Obtiene el tracklist de un master ID desde Discogs.
        """
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        params = self._get_auth_params()
        url = f"{self.api_base}/masters/{master_id}"
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            tracklist = data.get("tracklist", [])
            
            # Formatear el tracklist para devolver solo info relevante
            formatted_tracklist = []
            for track in tracklist:
                formatted_tracklist.append({
                    "position": track.get("position", ""),
                    "title": track.get("title", ""),
                    "duration": track.get("duration", "")
                })
            
            return {
                "master_id": master_id,
                "tracklist": formatted_tracklist,
                "title": data.get("title", ""),
                "year": data.get("year"),
                "debug_info": {
                    "request_url": debug_url,
                    "params_sent": {k: v for k, v in params.items() if k not in ["key", "secret"]}
                }
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Tracklist fetch failed for master {master_id}: {str(e)}")
            return {
                "master_id": master_id,
                "tracklist": [],
                "message": f"Error: {str(e)}",
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }
    
    async def get_release_tracklist(self, release_id: int) -> Optional[Dict]:
        """
        Obtiene el tracklist de un release ID desde Discogs.
        Usado como fallback cuando no hay master disponible.
        """
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        params = self._get_auth_params()
        url = f"{self.api_base}/releases/{release_id}"
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            tracklist = data.get("tracklist", [])
            
            # Formatear el tracklist igual que en master
            formatted_tracklist = []
            for track in tracklist:
                formatted_tracklist.append({
                    "position": track.get("position", ""),
                    "title": track.get("title", ""),
                    "duration": track.get("duration", "")
                })
            
            return {
                "release_id": release_id,
                "tracklist": formatted_tracklist,
                "title": data.get("title", ""),
                "year": data.get("year"),
                "debug_info": {
                    "request_url": debug_url,
                    "params_sent": {k: v for k, v in params.items() if k not in ["key", "secret"]}
                }
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Tracklist fetch failed for release {release_id}: {str(e)}")
            return {
                "release_id": release_id,
                "tracklist": [],
                "message": f"Error: {str(e)}",
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }
