# -*- coding: utf-8 -*-
"""
discogs_studio_masters.py (versión simplificada)

Helpers para trabajar con Discogs centrados en VINILO, usando la API
`/database/search` con:

- format=Vinyl
- type=release

API pensada para usar desde la UI / servicios:

- search_master(artist, title, key, secret) -> dict | None
    Busca un master por artista + título.

- collect_releases_from_master(master_id, key, secret) -> list[dict]
    Releases (en vinilo) asociadas a un master_id.

- search_releases(artist, title, key, secret) -> list[dict]
    Releases (en vinilo) por artista + título.

- discogs_dataframe(rows, official_only, es_europe_only) -> pd.DataFrame
    Aplica filtros ligeros (oficial / Spain+Europe) y devuelve un DataFrame.

También incluye un CLI opcional:
    python discogs_studio_masters.py --artist "JW Francis" --title "Sunshine"
"""

from typing import Any, Dict, List, Optional

import argparse
import time

import httpx
import pandas as pd

# =========================
# Config
# =========================

DISCOGS_KEY = "QiaraVlzXNSUJOpkdKdK"
DISCOGS_SECRET = "BssuhxnAECuSXYoFYPzIuSUixhVXRedG"
USER_AGENT = "Vinilogy/1.0 (+https://vinilogy.com)"
BASE_URL = "https://api.discogs.com"


# =========================
# HTTP helpers
# =========================

def _client() -> httpx.Client:
    """Cliente HTTP reutilizable."""
    timeout = httpx.Timeout(20.0, connect=20.0)
    headers = {"User-Agent": USER_AGENT}
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)


def _get_json(
    client: httpx.Client,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 4,
    sleep_between: float = 0.6,
) -> Dict[str, Any]:
    """Wrapper con reintentos para peticiones Discogs."""
    url = f"{BASE_URL}{path}"
    backoff = sleep_between
    last_exc: Optional[Exception] = None

    for _ in range(max_retries):
        try:
            r = client.get(url, params=params)
            if r.status_code == 429:
                # rate limit → esperamos y reintentamos
                time.sleep(backoff)
                backoff = min(backoff * 2, 6.0)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            last_exc = e
            time.sleep(backoff)
            backoff = min(backoff * 2, 6.0)

    if last_exc:
        raise last_exc
    return {}


def _search_discogs(
    extra_params: Dict[str, Any],
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    """
    Helper genérico para /database/search con paginación.
    Devuelve la lista de 'results'.
    """
    out: List[Dict[str, Any]] = []
    page = 1

    with _client() as client:
        while True:
            params = {
                "per_page": per_page,
                "page": page,
                "key": DISCOGS_KEY,
                "secret": DISCOGS_SECRET,
                **extra_params,
            }
            data = _get_json(client, "/database/search", params)
            results = data.get("results", []) or []
            out.extend(results)

            pag = data.get("pagination") or {}
            pages = pag.get("pages", 1) or 1
            if page >= pages:
                break

            page += 1
            time.sleep(0.3)

    return out


def _normalize_year(raw) -> Optional[int]:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return int(raw[:4])
        except Exception:
            return None
    return None


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


# =========================
# Public helpers (para UI/servicios)
# =========================

def search_master(
    artist: str,
    title: str,
    key: str = None,
    secret: str = None,
) -> Optional[Dict[str, Any]]:
    """
    Devuelve el primer master que coincida (o None) para Artista + Título.

    No filtra por vinilo; solo sirve para obtener un master_id razonable.
    """
    params = {
        "type": "master",
        "artist": artist,
        "release_title": title,
        "per_page": 20,
        "page": 1,
        "key": key or DISCOGS_KEY,
        "secret": secret or DISCOGS_SECRET,
    }
    with _client() as client:
        data = _get_json(client, "/database/search", params)

    results = data.get("results", []) or []
    if not results:
        return None

    tnorm = (title or "").strip().lower()
    exact = [
        r for r in results
        if _safe_str(r.get("title", "")).lower().endswith(f" - {tnorm}")
    ]
    return exact[0] if exact else results[0]


def collect_releases_from_master(
    master_id: int,
    key: str = None,
    secret: str = None,
) -> List[Dict[str, Any]]:
    """
    Releases (en vinilo) asociadas a un master_id.

    Implementado mediante /database/search con:
      - type=release
      - master_id=...
      - format=Vinyl
    """
    params = {
        "type": "release",
        "master_id": master_id,
        "format": "Vinyl",
    }
    results = _search_discogs(params, per_page=100)

    rows: List[Dict[str, Any]] = []
    for r in results:
        year = _normalize_year(r.get("year"))
        fmt = r.get("format")
        if isinstance(fmt, list):
            fmt_str = ", ".join(str(x) for x in fmt)
        else:
            fmt_str = _safe_str(fmt)

        label = r.get("label")
        if isinstance(label, list):
            label_str = ", ".join(str(x) for x in label)
        else:
            label_str = _safe_str(label)

        rows.append(
            {
                "release_id": r.get("id"),
                "title": r.get("title"),
                "format": fmt_str,
                "country": r.get("country"),
                "label": label_str,
                "catno": r.get("catno"),
                "year": year,
                "source": "search.by_master",
            }
        )
    return rows


def search_releases(
    artist: str,
    title: str,
    key: str = None,
    secret: str = None,
) -> List[Dict[str, Any]]:
    """
    Releases (en vinilo) por artista + título, usando:

      type=release
      format=Vinyl

    Sirve tanto para la UI (Streamlit) como para un endpoint.
    """
    params = {
        "type": "release",
        "artist": artist,
        "release_title": title,
        "format": "Vinyl",
    }
    results = _search_discogs(params, per_page=100)

    tnorm = (title or "").strip().lower()
    rows: List[Dict[str, Any]] = []
    for r in results:
        year = _normalize_year(r.get("year"))
        fmt = r.get("format")
        if isinstance(fmt, list):
            fmt_str = ", ".join(str(x) for x in fmt)
        else:
            fmt_str = _safe_str(fmt)

        label = r.get("label")
        if isinstance(label, list):
            label_str = ", ".join(str(x) for x in label)
        else:
            label_str = _safe_str(label)

        rows.append(
            {
                "release_id": r.get("id"),
                "title": r.get("title"),
                "format": fmt_str,
                "country": r.get("country"),
                "label": label_str,
                "catno": r.get("catno"),
                "year": year,
                "source": "search.by_artist_title",
                "_exact_title": _safe_str(r.get("title", "")).lower().endswith(
                    f" - {tnorm}"
                ),
            }
        )

    # Orden: coincidencias exactas primero, luego por año / país
    rows.sort(
        key=lambda x: (
            0 if x.get("_exact_title") else 1,
            x.get("year") if x.get("year") is not None else 9999,
            _safe_str(x.get("country")),
        )
    )
    for r in rows:
        r.pop("_exact_title", None)
    return rows


# =========================
# Filtros + DataFrame para UI
# =========================

def _is_unofficial(fmt: Optional[str]) -> bool:
    if not fmt:
        return False
    f = fmt.lower()
    return "unofficial release" in f or "unofficial" in f


def _is_es_or_europe(country: Optional[str]) -> bool:
    if not country:
        return False
    c = country.strip().lower()
    return c == "spain" or "europe" in c


def discogs_dataframe(
    rows: List[Dict[str, Any]],
    official_only: bool,
    es_europe_only: bool,
) -> pd.DataFrame:
    """
    Aplica filtros ligeros sobre la lista de releases y devuelve un DataFrame:
      - official_only: excluye "Unofficial Release" en el campo format
      - es_europe_only: solo country = Spain o que contenga 'Europe'
    Ojo: ya asumimos que 'rows' solo contiene vinilos (format=Vinyl en la búsqueda).
    """
    filtered = list(rows)

    if official_only:
        filtered = [r for r in filtered if not _is_unofficial(r.get("format"))]

    if es_europe_only:
        filtered = [r for r in filtered if _is_es_or_europe(r.get("country"))]

    filtered.sort(
        key=lambda x: (
            x.get("year") if x.get("year") is not None else 9999,
            _safe_str(x.get("country")),
            _safe_str(x.get("catno")),
        )
    )

    cols = ["release_id", "year", "format", "country", "label", "catno", "title", "source"]
    return pd.DataFrame(filtered, columns=cols)


# =========================
# CLI opcional (para probar rápido)
# =========================

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Discogs helpers simplificados (solo vinilo) – CLI de prueba"
    )
    parser.add_argument("--artist", help="Nombre del artista")
    parser.add_argument("--title", help="Título del álbum")
    parser.add_argument("--master-id", type=int, help="Discogs master_id")
    args = parser.parse_args()

    if args.master_id:
        print(f"Buscando releases en vinilo para master_id={args.master_id}...\n")
        rows = collect_releases_from_master(args.master_id)
    else:
        if not (args.artist and args.title):
            parser.error("Debes indicar --artist y --title si no usas --master-id")
        print(f'Buscando releases en vinilo para "{args.artist}" – "{args.title}"...\n')
        rows = search_releases(args.artist, args.title)

    df = discogs_dataframe(rows, official_only=False, es_europe_only=False)
    if df.empty:
        print("Sin resultados.")
        return

    print(df.to_string(index=False))


if __name__ == "__main__":
    _cli()
