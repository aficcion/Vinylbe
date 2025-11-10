import httpx
from typing import List, Dict, Optional
from libs.shared.utils import log_event


class DiscogsClient:
    def __init__(self, key: str, secret: str):
        self.key = key
        self.secret = secret
        self.client: Optional[httpx.AsyncClient] = None
        self.api_base = "https://api.discogs.com"
    
    async def start(self):
        headers = {"User-Agent": "VinylRecommender/1.0"}
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)
    
    async def stop(self):
        if self.client:
            await self.client.aclose()
    
    def is_ready(self) -> bool:
        return self.client is not None and bool(self.key) and bool(self.secret)
    
    def _get_auth_params(self, **params) -> dict:
        return {
            **params,
            "key": self.key,
            "secret": self.secret,
        }
    
    async def search_release(self, artist: str, title: str) -> List[dict]:
        if not self.client:
            raise ValueError("Client not started")
        
        params = self._get_auth_params(
            artist=artist,
            release_title=title,
            format="Vinyl",
            type="release",
        )
        
        url = f"{self.api_base}/database/search"
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Search failed: {str(e)}")
            return []
    
    async def get_marketplace_stats(self, release_id: int, currency: str = "EUR") -> dict:
        if not self.client:
            raise ValueError("Client not started")
        
        params = self._get_auth_params(currency=currency)
        url = f"{self.api_base}/marketplace/stats/{release_id}"
        
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            sell_list_url = f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}"
            
            lowest_price_data = data.get("lowest_price", {})
            source_price = lowest_price_data.get("value")
            source_currency = lowest_price_data.get("currency", "EUR")
            
            if source_price is not None and source_currency != "EUR":
                price_in_eur = await self.convert_to_eur(source_price, source_currency)
                log_event("discogs-client", "INFO", f"Converted {source_price} {source_currency} to {price_in_eur:.2f} EUR")
            else:
                price_in_eur = source_price
            
            return {
                "release_id": release_id,
                "lowest_price": price_in_eur,
                "currency": "EUR",
                "original_price": source_price,
                "original_currency": source_currency,
                "num_for_sale": data.get("num_for_sale", 0),
                "sell_list_url": sell_list_url,
            }
        except Exception as e:
            log_event("discogs-client", "ERROR", f"Stats fetch failed for release {release_id}: {str(e)}")
            return {
                "release_id": release_id,
                "lowest_price": None,
                "currency": "EUR",
                "original_price": None,
                "original_currency": None,
                "num_for_sale": 0,
                "sell_list_url": f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}",
            }
    
    async def convert_to_eur(self, price: float, from_currency: str) -> float:
        if from_currency == "EUR":
            return price
        
        conversion_rates = {
            "USD": 0.92,
            "GBP": 1.17,
            "JPY": 0.0062,
            "CAD": 0.67,
            "AUD": 0.60,
        }
        
        rate = conversion_rates.get(from_currency, 1.0)
        return price * rate
