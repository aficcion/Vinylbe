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
    
    async def get_marketplace_stats(self, release_id: int, currency: str = "EUR") -> dict:
        if not self.client:
            raise ValueError("Client not started")
        
        await self._rate_limit()
        
        params = self._get_auth_params(currency=currency)
        url = f"{self.api_base}/marketplace/stats/{release_id}"
        debug_url = self._build_debug_url(url, params)
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            sell_list_url = f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}"
            
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
            return {
                "release_id": release_id,
                "lowest_price_eur": None,
                "lowest_price": None,
                "currency": "EUR",
                "original_price": None,
                "original_currency": None,
                "num_for_sale": 0,
                "sell_list_url": f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}",
                "debug_info": {
                    "request_url": debug_url,
                    "error": str(e)
                }
            }
    
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
