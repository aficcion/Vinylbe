#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
lastfm_artist_explorer.py

App TODO-en-uno (frontend + lógica) para:

- Buscar artistas en Last.fm mientras escribes (artist.search).
- Añadir artistas seleccionados.
- Mostrar siempre hasta 10 artistas sugeridos, combinando los similares
  de todos los artistas seleccionados.
- Para cada artista seleccionado, ver sus discos de estudio
  (MusicBrainz) y rating de vinilo (Discogs) en paralelo.

Ejecutar con:

    streamlit run lastfm_artist_explorer.py --server.port 8000 --server.address 0.0.0.0
"""

import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pandas as pd
import streamlit as st

# =========================
# Configuración APIs
# =========================

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"

MB_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE = "https://api.discogs.com"

DISCOGS_KEY = os.getenv("DISCOGS_KEY")
DISCOGS_SECRET = os.getenv("DISCOGS_SECRET")

HEADERS = {
    "User-Agent": "Vinilogy/1.0 (+https://vinilogy.com; contact@vinilogy.com)"
}

_RE_DISCOGS_MASTER = re.compile(
    r"https?://(?:www\.)?discogs\.com/(?:[a-z]{2}/)?master/(\d+)", re.I
)


# =========================
# Cliente HTTP reutilizable (MB + Discogs)
# =========================

CLIENT = httpx.Client(
    headers=HEADERS,
    http2=False,
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
    follow_redirects=True,
)

# =========================
# Modelos internos
# =========================

@dataclass
class Artist:
    name: str
    mbid: Optional[str] = None
    image_url: Optional[str] = None


# =========================
# Cliente Last.fm
# =========================

class LastFMClient:
    def __init__(self, api_key: str, base_url: str = LASTFM_BASE_URL, 
                 discogs_key: Optional[str] = None, discogs_secret: Optional[str] = None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.discogs_key = discogs_key
        self.discogs_secret = discogs_secret

    def _build_params(self, method: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        params = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
        }
        if extra:
            params.update(extra)
        return params

    def search_artists_discogs(self, query: str, limit: int = 5) -> Tuple[List[Artist], float]:
        """
        Busca artistas en Discogs si hay credenciales (trae imágenes thumb).
        Fallback a Last.fm si no hay credenciales de Discogs.
        Devuelve (lista de artistas, tiempo en segundos).
        """
        start_time = time.time()
        
        if not query.strip():
            return [], 0.0

        if self.discogs_key and self.discogs_secret:
            try:
                params = {
                    "q": query.strip(),
                    "type": "artist",
                    "key": self.discogs_key,
                    "secret": self.discogs_secret,
                    "per_page": str(limit),
                }
                
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(f"{DISCOGS_BASE}/database/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                
                results = data.get("results", [])
                artists: List[Artist] = []
                
                for item in results[:limit]:
                    name = item.get("title")
                    if not name:
                        continue
                        
                    thumb_url = item.get("thumb")
                    if thumb_url and thumb_url.startswith("http"):
                        image_url = thumb_url
                    else:
                        image_url = None
                    
                    artists.append(Artist(name=name, mbid=None, image_url=image_url))
                
                elapsed = time.time() - start_time
                return artists, elapsed
                
            except httpx.HTTPError as e:
                st.warning(f"Error al consultar Discogs, usando Last.fm como fallback: {e}")
        
        params = self._build_params(
            "artist.search",
            {
                "artist": query,
                "limit": str(limit),
            },
        )

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(self.base_url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            st.error(f"Error al consultar Last.fm: {e}")
            return [], time.time() - start_time

        data = resp.json()
        results = data.get("results", {}).get("artistmatches", {}).get("artist", [])

        if isinstance(results, dict):
            results = [results]

        artists: List[Artist] = []
        for item in results:
            name = item.get("name")
            if not name:
                continue
            mbid = item.get("mbid") or None
            artists.append(Artist(name=name, mbid=mbid, image_url=None))
        
        elapsed = time.time() - start_time
        return artists, elapsed

    def get_artist_info(self, *, name: Optional[str] = None, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene información detallada del artista usando artist.getInfo (incluye 5 similares)."""
        extra: Dict[str, str] = {}
        if mbid:
            extra["mbid"] = mbid
        elif name:
            extra["artist"] = name
        else:
            return None

        params = self._build_params("artist.getInfo", extra)

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("artist")
        except httpx.HTTPError:
            return None

    def get_similar_artist_images_discogs(self, artist_names: List[str]) -> Dict[str, Optional[str]]:
        """
        Busca imágenes en Discogs para una lista de nombres de artistas.
        Devuelve diccionario {nombre_artista: url_imagen}
        """
        result = {}
        for name in artist_names:
            if not name or not self.discogs_key or not self.discogs_secret:
                result[name] = None
                continue
                
            try:
                params = {
                    "q": name,
                    "type": "artist",
                    "key": self.discogs_key,
                    "secret": self.discogs_secret,
                    "per_page": "1",
                }
                
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get(f"{DISCOGS_BASE}/database/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                
                results = data.get("results", [])
                if results and results[0].get("thumb"):
                    result[name] = results[0]["thumb"]
                else:
                    result[name] = None
                    
            except httpx.HTTPError:
                result[name] = None
                
        return result


# =========================
# Helpers MusicBrainz
# =========================

def _mb_get(path: str, params: Dict[str, Any], tries: int = 5,
            sleep_after_ok: float = 1.0, debug: bool = False) -> Dict[str, Any]:
    url = f"{MB_BASE}{path}"
    params = {**params, "fmt": "json"}
    last_exc = None
    backoff = 0.6

    for attempt in range(1, tries + 1):
        try:
            if debug:
                st.write(f"[MB] GET {url} params={params} (attempt {attempt})")
            r = CLIENT.get(url, params=params)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("Transient", r.request, r)
            r.raise_for_status()
            time.sleep(sleep_after_ok)
            return r.json()
        except Exception as e:
            last_exc = e
            if debug:
                st.write(f"[MB] error {e}; retrying in {backoff:.1f}s")
            time.sleep(backoff)
            backoff = min(backoff * 1.7, 5.0)

    raise RuntimeError(f"MB failed: {last_exc}")


def _find_artist_mbid(name: str, debug: bool = False) -> Optional[str]:
    data = _mb_get("/artist", {"query": f'artist:"{name}"', "limit": 10}, debug=debug)
    artists = data.get("artists", []) or []
    if not artists:
        return None
    exact = [a for a in artists if a.get("name", "").lower() == name.lower()]
    chosen = exact[0] if exact else artists[0]
    return chosen.get("id")


def _fetch_release_groups(artist_mbid: str, limit: int = 100, debug: bool = False):
    data = _mb_get(
        "/release-group",
        {
            "artist": artist_mbid,
            "primary-type": "Album",
            "inc": "artist-credits+url-rels",
            "limit": min(limit, 100),
        },
        debug=debug,
    )
    return data.get("release-groups", []) or []


def _is_studio_album(rg: Dict[str, Any], artist_mbid: str) -> bool:
    if rg.get("primary-type") != "Album":
        return False
    if rg.get("secondary-types"):
        return False
    ac = rg.get("artist-credit") or []
    if len(ac) != 1:
        return False
    return (ac[0].get("artist") or {}).get("id") == artist_mbid


def _year_from_date(item: Dict[str, Any]) -> str:
    d = item.get("first-release-date") or ""
    return d.split("-")[0] if d else ""


def _discogs_master_from_rels(relations: Any) -> str:
    if not relations:
        return ""
    for rel in relations:
        if rel.get("type") == "discogs":
            url = (rel.get("url") or {}).get("resource", "")
            m = _RE_DISCOGS_MASTER.search(url)
            if m:
                return m.group(1)
    return ""


# =========================
# Helpers Discogs
# =========================

def _discogs_get(path: str, params: Dict[str, Any],
                 key: str, secret: str,
                 sleep_after_ok: float = 0.25,
                 debug: bool = False):

    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": key, "secret": secret}

    if debug:
        st.write(f"[Discogs] GET {url} {params}")

    r = CLIENT.get(url, params=params)
    r.raise_for_status()
    time.sleep(sleep_after_ok)
    return r.json()


def _discogs_master_rating(master_id: str, key: str, secret: str, debug: bool = False):
    """
    Devuelve (rating, votes) usando master o main_release.
    """
    if not master_id:
        return None, None

    data = _discogs_get(f"/masters/{master_id}", {}, key, secret, debug=debug)
    r = (data.get("community") or {}).get("rating") or {}
    if r.get("average") is not None:
        return float(r["average"]), int(r.get("count", 0))

    main_rel = data.get("main_release")
    if not main_rel:
        return None, None

    rel = _discogs_get(f"/releases/{main_rel}", {}, key, secret, debug=debug)
    rr = (rel.get("community") or {}).get("rating") or {}
    if rr.get("average") is None:
        return None, None
    return float(rr["average"]), int(rr.get("count", 0))


# =========================
# Parallel rating fetcher
# =========================

def attach_discogs_ratings(df: pd.DataFrame, key: str, secret: str, debug: bool = False) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    master_ids = df["discogs_master_id"].tolist()

    def process_one(mid: str):
        if not mid:
            return (None, None)
        try:
            return _discogs_master_rating(mid, key, secret, debug)
        except Exception:
            return (None, None)

    batch_size = 5
    results: List[Tuple[Optional[float], Optional[int]]] = []

    for i in range(0, len(master_ids), batch_size):
        chunk = master_ids[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=batch_size) as exe:
            future_map = {exe.submit(process_one, mid): mid for mid in chunk}
            for fut in as_completed(future_map):
                results.append(fut.result())

        time.sleep(0.25)

    df["discogs_rating"] = [r[0] for r in results]
    df["discogs_votes"] = [r[1] for r in results]
    return df


# =========================
# API pública: MB + Discogs
# =========================

def mb_dataframe(
    artist: Optional[str] = None,
    artist_mbid: Optional[str] = None,
    discogs_key: Optional[str] = None,
    discogs_secret: Optional[str] = None,
    debug: bool = False,
) -> pd.DataFrame:
    """
    Devuelve los álbumes de estudio de un artista:
    - year, title, discogs_master_id, rg_mbid
    Y si hay Discogs key/secret:
    - discogs_rating, discogs_votes
    """
    if not artist_mbid:
        if not artist:
            return pd.DataFrame()
        artist_mbid = _find_artist_mbid(artist, debug=debug)

    if not artist_mbid:
        return pd.DataFrame()

    rgs = _fetch_release_groups(artist_mbid, debug=debug)
    filtered = [rg for rg in rgs if _is_studio_album(rg, artist_mbid)]

    rows: List[Dict[str, Any]] = []
    for rg in filtered:
        rows.append({
            "year": _year_from_date(rg),
            "title": rg.get("title", "").strip(),
            "discogs_master_id": _discogs_master_from_rels(rg.get("relations")),
            "rg_mbid": rg.get("id", "")
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df.sort_values("year", inplace=True, ignore_index=True)

    if discogs_key and discogs_secret:
        df = attach_discogs_ratings(df, discogs_key, discogs_secret, debug)

    return df


# =========================
# Lógica de sugerencias (Last.fm)
# =========================

def build_suggestions(
    client: LastFMClient,
    selected: List[Artist],
    limit: int = 5,
) -> Tuple[List[Artist], float]:
    """
    Genera sugerencias usando artist.getInfo de Last.fm (trae 5 similares incluidos).
    Busca imágenes en Discogs solo para los top artistas sugeridos.
    Devuelve (lista de artistas sugeridos, tiempo total en segundos).
    """
    start_time = time.time()
    
    if not selected or limit <= 0:
        return [], 0.0

    candidate_counts: Dict[str, int] = {}
    candidate_names: Dict[str, str] = {}

    for seed in selected:
        artist_info = client.get_artist_info(name=seed.name, mbid=seed.mbid)
        if not artist_info:
            continue
        
        similars = artist_info.get("similar", {}).get("artist", [])
        if isinstance(similars, dict):
            similars = [similars]
        
        for sim in similars:
            sim_name = sim.get("name")
            if not sim_name:
                continue
            
            sim_name_lower = sim_name.lower()
            
            if sim_name_lower == seed.name.lower():
                continue
            
            candidate_counts[sim_name_lower] = candidate_counts.get(sim_name_lower, 0) + 1
            if sim_name_lower not in candidate_names:
                candidate_names[sim_name_lower] = sim_name
    
    selected_keys_lower = {s.name.lower() for s in selected}
    for sel_key in selected_keys_lower:
        candidate_counts.pop(sel_key, None)
        candidate_names.pop(sel_key, None)
    
    sorted_candidates = sorted(
        candidate_counts.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    
    top_artist_names = [candidate_names[name_lower] for name_lower, _ in sorted_candidates[:limit]]
    
    images_map = client.get_similar_artist_images_discogs(top_artist_names)
    
    suggestions: List[Artist] = []
    for name in top_artist_names:
        image_url = images_map.get(name)
        suggestions.append(Artist(name=name, mbid=None, image_url=image_url))
    
    elapsed = time.time() - start_time
    return suggestions, elapsed


# =========================
# Helpers de estado (Streamlit)
# =========================

def init_state():
    if "selected_artists" not in st.session_state:
        st.session_state.selected_artists: List[Artist] = []
    if "suggested_artists" not in st.session_state:
        st.session_state.suggested_artists: List[Artist] = []
    if "last_search_time" not in st.session_state:
        st.session_state.last_search_time: float = 0.0
    if "last_suggestions_time" not in st.session_state:
        st.session_state.last_suggestions_time: float = 0.0


def add_selected(artist: Artist, client: LastFMClient, limit: int = 5):
    for a in st.session_state.selected_artists:
        if a.name.lower() == artist.name.lower() and (
            (not a.mbid and not artist.mbid) or (a.mbid == artist.mbid)
        ):
            return
    st.session_state.selected_artists.append(artist)
    suggestions, elapsed = build_suggestions(
        client, st.session_state.selected_artists, limit=limit
    )
    st.session_state.suggested_artists = suggestions
    st.session_state.last_suggestions_time = elapsed


def remove_selected(index: int, client: LastFMClient, limit: int = 5):
    if 0 <= index < len(st.session_state.selected_artists):
        st.session_state.selected_artists.pop(index)
        suggestions, elapsed = build_suggestions(
            client, st.session_state.selected_artists, limit=limit
        )
        st.session_state.suggested_artists = suggestions
        st.session_state.last_suggestions_time = elapsed


# =========================
# App Streamlit
# =========================

def main():
    st.set_page_config(page_title="Explorador de artistas (Last.fm)", layout="wide")
    st.title("🎧 Explorador de artistas basado en Last.fm + discos de estudio (MB/Discogs)")

    if not LASTFM_API_KEY:
        st.error(
            "No se ha encontrado `LASTFM_API_KEY`. "
            "Añádelo como variable de entorno/Secret."
        )
        st.stop()

    client = LastFMClient(
        api_key=LASTFM_API_KEY,
        discogs_key=DISCOGS_KEY,
        discogs_secret=DISCOGS_SECRET
    )
    init_state()

    if not DISCOGS_KEY or not DISCOGS_SECRET:
        st.warning(
            "⚠️ No se han encontrado `DISCOGS_KEY` y/o `DISCOGS_SECRET`. "
            "Se mostrarán los discos de estudio pero sin rating ni imágenes de Discogs."
        )

    st.markdown(
        "Escribe un nombre de artista, añádelo a la selección y el sistema "
        "te propondrá hasta **5 artistas similares** con imágenes reales de Discogs. "
        "Para cada artista seleccionado puedes ver sus **discos de estudio** con el rating de vinilo."
    )
    
    if st.session_state.last_search_time > 0 or st.session_state.last_suggestions_time > 0:
        metrics_cols = st.columns(3)
        if st.session_state.last_search_time > 0:
            with metrics_cols[0]:
                st.metric("⏱️ Última búsqueda", f"{st.session_state.last_search_time:.2f}s")
        if st.session_state.last_suggestions_time > 0:
            with metrics_cols[1]:
                st.metric("⏱️ Generación sugerencias", f"{st.session_state.last_suggestions_time:.2f}s")

    col_search, col_selected, col_suggestions = st.columns([2, 2, 3])

    # -------- BÚSQUEDA --------
    with col_search:
        st.subheader("🔍 Buscar artista")
        query = st.text_input(
            "Nombre del artista",
            placeholder="Arctic Monkeys, Metallica...",
            key="search_box",
        )

        search_results: List[Artist] = []
        if st.session_state.search_box and len(st.session_state.search_box.strip()) >= 2:
            search_results, search_time = client.search_artists_discogs(st.session_state.search_box.strip(), limit=5)
            st.session_state.last_search_time = search_time

        if query and not search_results:
            st.info("No se han encontrado artistas para esa búsqueda.")

        for i, artist in enumerate(search_results):
            with st.container():
                cols = st.columns([1, 3])
                with cols[0]:
                    if artist.image_url:
                        st.image(artist.image_url, use_container_width=True)
                    else:
                        st.write("🎵")
                with cols[1]:
                    st.markdown(f"**{artist.name}**")
                    if artist.mbid:
                        st.caption(f"mbid: {artist.mbid}")

                    if st.button("➕ Añadir", key=f"add_search_{artist.name}_{i}"):
                        add_selected(artist, client, limit=5)
                        st.rerun()

    # -------- SELECCIONADOS --------
    with col_selected:
        st.subheader("✅ Artistas seleccionados")
        if not st.session_state.selected_artists:
            st.caption("Todavía no has seleccionado ningún artista.")
        else:
            for idx, artist in enumerate(st.session_state.selected_artists):
                with st.container():
                    cols = st.columns([3, 2])
                    with cols[0]:
                        st.markdown(f"**{artist.name}**")
                        if artist.mbid:
                            st.caption(f"mbid: {artist.mbid}")
                    with cols[1]:
                        if st.button("❌ Quitar", key=f"remove_sel_{idx}"):
                            remove_selected(idx, client, limit=5)
                            st.rerun()

                    # Botón para ver discos de estudio
                    if st.button("📀 Ver discos de estudio", key=f"albums_{idx}"):
                        with st.spinner("Buscando discos de estudio..."):
                            df_albums = mb_dataframe(
                                artist=artist.name,
                                artist_mbid=artist.mbid,
                                discogs_key=DISCOGS_KEY,
                                discogs_secret=DISCOGS_SECRET,
                                debug=False,
                            )
                        if df_albums.empty:
                            st.info("No se han encontrado álbumes de estudio.")
                        else:
                            st.dataframe(df_albums, use_container_width=True)

    # -------- SUGERENCIAS --------
    with col_suggestions:
        st.subheader("✨ Sugerencias (hasta 5)")
        suggestions = st.session_state.suggested_artists

        if not st.session_state.selected_artists:
            st.caption("Añade al menos un artista para ver sugerencias.")
        elif not suggestions:
            st.caption("No hay sugerencias disponibles ahora mismo.")
        else:
            for i, artist in enumerate(suggestions):
                with st.container():
                    cols = st.columns([1, 3, 1])
                    with cols[0]:
                        if artist.image_url:
                            st.image(artist.image_url, use_container_width=True)
                        else:
                            st.write("🎵")
                    with cols[1]:
                        st.markdown(f"**{artist.name}**")
                        if artist.mbid:
                            st.caption(f"mbid: {artist.mbid}")
                    with cols[2]:
                        if st.button("➕ Añadir", key=f"add_sugg_{artist.name}_{i}"):
                            add_selected(artist, client, limit=5)
                            st.rerun()


if __name__ == "__main__":
    main()
