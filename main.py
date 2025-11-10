from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import httpx
from contextlib import asynccontextmanager

DISCOGS_KEY = os.getenv("DISCOGS_KEY")
DISCOGS_SECRET = os.getenv("DISCOGS_SECRET")


def discogs_headers():
    return {"User-Agent": "MiApp/1.0"}


def discogs_auth_params(**params):
    return {
        **params,
        "key": DISCOGS_KEY,
        "secret": DISCOGS_SECRET,
    }


client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    # Startup
    client = httpx.AsyncClient(timeout=15.0, headers=discogs_headers())

    # Mostrar rutas registradas
    try:
        from fastapi.routing import APIRoute
        print("Rutas registradas:")
        for r in app.routes:
            if isinstance(r, APIRoute):
                print(r.path, r.methods)
    except Exception as e:
        print("Error listando rutas:", e)

    yield

    # Shutdown
    if client:
        await client.aclose()


app = FastAPI(lifespan=lifespan)

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Backend funcionando 🎧"}


@app.get("/discogs/search")
async def discogs_search(
    artist: str = Query(...),
    title: str = Query(...),
):
    """
    Busca un vinilo por artista y título.
    """
    if not DISCOGS_KEY or not DISCOGS_SECRET:
        return JSONResponse(
            status_code=500,
            content={"error": "Faltan DISCOGS_KEY o DISCOGS_SECRET"},
        )

    if not client:
        return JSONResponse(
            status_code=500,
            content={"error": "Cliente HTTP no inicializado"},
        )

    base = "https://api.discogs.com/database/search"
    params = discogs_auth_params(
        artist=artist,
        release_title=title,
        format="Vinyl",
        type="release",
    )

    resp = await client.get(base, params=params)
    return resp.json()


@app.get("/discogs/stats/{release_id}")
async def discogs_stats(release_id: int, currency: str = "EUR"):
    """
    Obtiene stats del marketplace (precio más bajo, cantidad, etc.)
    """
    if not DISCOGS_KEY or not DISCOGS_SECRET:
        return JSONResponse(
            status_code=500,
            content={"error": "Faltan DISCOGS_KEY o DISCOGS_SECRET"},
        )

    if not client:
        return JSONResponse(
            status_code=500,
            content={"error": "Cliente HTTP no inicializado"},
        )

    url = f"https://api.discogs.com/marketplace/stats/{release_id}"
    params = discogs_auth_params(currency=currency)

    resp = await client.get(url, params=params)
    return resp.json()


@app.get("/discogs/sell-list-url/{release_id}")
async def discogs_sell_list_url(release_id: int):
    """
    Devuelve la URL pública de listados de venta.
    """
    url = f"https://www.discogs.com/sell/list?format=Vinyl&release_id={release_id}"
    return {"release_id": release_id, "url": url}
