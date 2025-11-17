from typing import Optional, Dict, Any, List
import os
import httpx

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
VINYL_CATEGORY_ID = "176985"

EU_COUNTRIES = "AT,BE,BG,HR,CY,CZ,DK,EE,FI,FR,DE,GR,HU,IE,IT,LV,LT,LU,MT,NL,PL,PT,RO,SK,SI,ES,SE"


def normalize(text: str) -> str:
    """Normaliza strings para comparaciones simples."""
    return (
        text.lower()
        .replace(",", " ")
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )


class PricingClient:
    def __init__(self):
        self.client_id = os.getenv("EBAY_CLIENT_ID")
        self.client_secret = os.getenv("EBAY_CLIENT_SECRET")
        
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "EBAY_CLIENT_ID y EBAY_CLIENT_SECRET deben estar en variables de entorno"
            )
        
        self.http_client: Optional[httpx.AsyncClient] = None
        self.access_token: Optional[str] = None

    async def start(self):
        """Inicializa el cliente HTTP asíncrono."""
        self.http_client = httpx.AsyncClient(timeout=20.0)
        await self._get_access_token()

    async def stop(self):
        """Cierra el cliente HTTP."""
        if self.http_client:
            await self.http_client.aclose()

    def is_ready(self) -> bool:
        """Verifica si el cliente está listo."""
        return self.http_client is not None and self.access_token is not None

    async def _get_access_token(self) -> str:
        """Obtiene un application access token de eBay usando client credentials."""
        auth = (self.client_id, self.client_secret)
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }

        resp = await self.http_client.post(
            EBAY_OAUTH_URL,
            auth=auth,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        payload = resp.json()
        self.access_token = payload["access_token"]
        return self.access_token

    def _pick_best_ebay_item(
        self,
        item_summaries: List[dict],
        artist: str,
        album: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Dado itemSummaries de eBay, devuelve el mejor item:
          - título razonable (contenga artist y algo del álbum)
          - precio total más bajo (item + shipping)
          - en EUR
        """
        artist_n = normalize(artist)
        album_n = normalize(album)

        candidates: List[Dict[str, Any]] = []

        for item in item_summaries:
            title = item.get("title", "")
            title_n = normalize(title)

            if not any(w for w in artist_n.split() if w in title_n):
                continue

            if all(word not in title_n for word in album_n.split() if word):
                continue

            if "cd" in title_n or "cassette" in title_n:
                continue

            price = item.get("price", {})
            ship_opts = item.get("shippingOptions", [])

            if not price or not ship_opts:
                continue

            if price.get("currency") != "EUR":
                continue

            try:
                item_price = float(price.get("value", 0.0))
            except (TypeError, ValueError):
                continue

            try:
                ship_cost = float(
                    ship_opts[0].get("shippingCost", {}).get("value", 0.0)
                )
            except (TypeError, ValueError, IndexError):
                continue

            total = item_price + ship_cost

            candidates.append(
                {
                    "provider": "ebay",
                    "title": title,
                    "item_price": item_price,
                    "shipping_cost": ship_cost,
                    "total_price": total,
                    "currency": price.get("currency"),
                    "url": item.get("itemWebUrl"),
                }
            )

        if not candidates:
            return None

        candidates.sort(key=lambda c: c["total_price"])
        return candidates[0]

    async def fetch_best_ebay_offer(
        self,
        artist: str,
        album: str,
        marketplace_id: str = "EBAY_ES",
    ) -> Optional[Dict[str, Any]]:
        """
        Busca en eBay el vinilo de artist + album y devuelve la mejor oferta
        (precio más barato en EUR ubicado en la Unión Europea).
        """
        if not self.access_token:
            await self._get_access_token()

        query = f"{artist} {album}"
        params = {
            "q": query,
            "category_ids": VINYL_CATEGORY_ID,
            "filter": f"itemLocationCountry:{{{EU_COUNTRIES}}}",
            "sort": "priceWithShipping",
            "limit": "20",
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Content-Type": "application/json",
        }

        resp = await self.http_client.get(
            EBAY_BROWSE_URL, params=params, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("itemSummaries", [])
        return self._pick_best_ebay_item(items, artist=artist, album=album)

    def get_local_store_links(self, artist: str, album: str) -> dict:
        """Devuelve enlaces preparados para tiendas locales sin scraping."""
        query = f"{artist} {album}".replace(" ", "+")

        return {
            "marilians": (
                f"https://www.marilians.com/busqueda?"
                f"controller=search&s={query}"
            ),
            "bajo_el_volcan": (
                "https://www.bajoelvolcan.es/busqueda/listaLibros.php?"
                f"tipoBus=full&palabrasBusqueda={query}"
            ),
            "bora_bora": f"https://discosborabora.com/?s={query}",
            "revolver": (
                f"https://www.revolverrecords.es/?s={query}&post_type=product"
            ),
        }
