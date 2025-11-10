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
# --- SPOTIFY INTEGRATION ------------------------------------------------------

import base64
from urllib.parse import urlencode

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# ⚠️ Para demo: guardamos tokens en memoria (1 usuario).
# En producción: guarda por usuario en DB (+ estado/CSRF).
spotify_tokens: dict[str, str] = {}  # {"access_token": "...", "refresh_token": "..."}


def _spotify_basic_auth_header() -> dict[str, str]:
    creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    encoded = base64.b64encode(creds).decode()
    return {"Authorization": f"Basic {encoded}"}


def _spotify_auth_header() -> dict[str, str]:
    if not spotify_tokens.get("access_token"):
        return {}
    return {"Authorization": f"Bearer {spotify_tokens['access_token']}"}


async def _refresh_spotify_token():
    if not spotify_tokens.get("refresh_token"):
        return
    if not client:
        return
    data = {
        "grant_type": "refresh_token",
        "refresh_token": spotify_tokens["refresh_token"],
    }
    headers = _spotify_basic_auth_header()
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    resp = await client.post(SPOTIFY_TOKEN_URL, data=data, headers=headers)
    j = resp.json()
    if "access_token" in j:
        spotify_tokens["access_token"] = j["access_token"]
        if "refresh_token" in j:  # a veces no lo devuelven
            spotify_tokens["refresh_token"] = j["refresh_token"]


@app.get("/spotify/login")
async def spotify_login():
    """
    Redirige al login de Spotify (Authorization Code Flow).
    """
    if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI]):
        return JSONResponse(
            status_code=500,
            content={"error": "Faltan SPOTIFY_CLIENT_ID/SECRET/REDIRECT_URI"},
        )

    scopes = ["user-top-read", "user-read-email"]
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(scopes),
        # Opcional: añade un state aleatorio para CSRF
    }
    url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    return JSONResponse({"authorize_url": url})


@app.get("/spotify/callback")
async def spotify_callback(code: str = Query(...)):
    """
    Intercambia el 'code' por access_token + refresh_token.
    """
    if not client:
        return JSONResponse(
            status_code=500,
            content={"error": "Cliente HTTP no inicializado"},
        )
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }
    headers = _spotify_basic_auth_header()
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    resp = await client.post(SPOTIFY_TOKEN_URL, data=data, headers=headers)
    j = resp.json()
    if "access_token" not in j:
        return JSONResponse(status_code=400, content={"error": "No token", "raw": j})

    spotify_tokens["access_token"] = j["access_token"]
    spotify_tokens["refresh_token"] = j.get("refresh_token", spotify_tokens.get("refresh_token"))

    return {"status": "ok", "message": "Spotify conectado ✅"}


async def _spotify_get(path: str, params: dict | None = None):
    """
    GET a la API de Spotify con auto-refresh si hace falta.
    """
    if not client:
        raise ValueError("Cliente HTTP no inicializado")
    
    url = f"{SPOTIFY_API_BASE}{path}"
    # 1º intento
    r = await client.get(url, headers=_spotify_auth_header(), params=params or {})
    if r.status_code == 401:
        # Refresh y reintento
        await _refresh_spotify_token()
        r = await client.get(url, headers=_spotify_auth_header(), params=params or {})
    return r


@app.get("/spotify/me")
async def spotify_me():
    r = await _spotify_get("/me")
    return r.json()


@app.get("/spotify/top-tracks")
async def spotify_top_tracks(limit: int = 50, time_range: str = "medium_term"):
    """
    Top tracks del usuario (short_term, medium_term, long_term).
    """
    params = {"limit": min(limit, 50), "time_range": time_range}
    r = await _spotify_get("/me/top/tracks", params)
    return r.json()


@app.get("/spotify/top-artists")
async def spotify_top_artists(limit: int = 50, time_range: str = "medium_term"):
    params = {"limit": min(limit, 50), "time_range": time_range}
    r = await _spotify_get("/me/top/artists", params)
    return r.json()


# Utilidades para tus casos
@app.get("/spotify/album-from-track/{track_id}")
async def spotify_album_from_track(track_id: str):
    """
    Dado un track, devuelve su álbum (con UPC si está disponible).
    """
    r = await _spotify_get(f"/tracks/{track_id}")
    track = r.json()
    album_id = track.get("album", {}).get("id")
    if not album_id:
        return JSONResponse(status_code=404, content={"error": "Álbum no encontrado"})
    r2 = await _spotify_get(f"/albums/{album_id}")
    return r2.json()
