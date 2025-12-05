import os
from dotenv import load_dotenv
from pathlib import Path as PathLib

# Load environment variables FIRST - use absolute path to .env
env_path = PathLib(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
from pathlib import Path as PathLib

sys.path.insert(0, str(PathLib(__file__).parent.parent.parent))

from libs.shared.models import ServiceHealth
from libs.shared.utils import log_event
from .pricing_client import PricingClient

pricing_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pricing_client
    pricing_client = PricingClient()
    try:
        await pricing_client.start()
        log_event("pricing-service", "INFO", "Pricing Service started with eBay connection")
    except Exception as e:
        log_event("pricing-service", "ERROR", f"Failed to connect to eBay: {e}")
        log_event("pricing-service", "WARNING", "Pricing Service started WITHOUT eBay connection")
        # Continue running even if eBay fails
    
    yield
    await pricing_client.stop()
    log_event("pricing-service", "INFO", "Pricing Service stopped")


app = FastAPI(lifespan=lifespan, title="Pricing Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return ServiceHealth(
        service_name="pricing-service",
        status="healthy" if pricing_client and pricing_client.is_ready() else "unhealthy"
    ).dict()


@app.get("/")
async def root():
    return {"service": "pricing-service", "status": "running"}


@app.get("/ebay-price")
async def get_ebay_price(
    artist: str = Query(..., description="Artist name"),
    album: str = Query(..., description="Album name")
):
    """
    Obtiene el mejor precio de eBay para un vinilo específico.
    """
    if not pricing_client:
        raise HTTPException(status_code=500, detail="Pricing client not initialized")
    
    log_event("pricing-service", "INFO", f"Fetching eBay price for {artist} - {album}")
    
    try:
        result = await pricing_client.fetch_best_ebay_offer(artist, album)
        
        if not result:
            log_event("pricing-service", "INFO", f"No eBay offer found for {artist} - {album}")
            return {
                "artist": artist,
                "album": album,
                "offer": None,
                "message": "No suitable offer found on eBay"
            }
        
        log_event(
            "pricing-service",
            "INFO",
            f"eBay offer found for {artist} - {album}",
            {"price": result["total_price"]}
        )
        
        return {
            "artist": artist,
            "album": album,
            "offer": result
        }
    except Exception as e:
        log_event("pricing-service", "ERROR", f"Error fetching eBay price: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching eBay price: {str(e)}")


@app.get("/local-stores")
async def get_local_stores(
    artist: str = Query(..., description="Artist name"),
    album: str = Query(..., description="Album name"),
    exclude_fnac: bool = Query(False, description="Exclude FNAC from scraping"),
    only_fnac: bool = Query(False, description="Only scrape FNAC")
):
    """
    Devuelve enlaces a tiendas locales de vinilos en España con precios obtenidos mediante scraping.
    """
    if not pricing_client:
        raise HTTPException(status_code=500, detail="Pricing client not initialized")
    
    log_event("pricing-service", "INFO", f"Generating local store links with prices for {artist} - {album} (exclude_fnac={exclude_fnac}, only_fnac={only_fnac})")
    
    stores = await pricing_client.get_local_store_links_with_prices(
        artist, 
        album,
        exclude_fnac=exclude_fnac,
        only_fnac=only_fnac
    )
    
    return {
        "artist": artist,
        "album": album,
        "stores": stores
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PRICING_SERVICE_PORT", 3003))
    uvicorn.run(app, host="0.0.0.0", port=port)
