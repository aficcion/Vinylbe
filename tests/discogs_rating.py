#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
discogs_rating_full.py

Uso desde terminal:

1) Por master id:
   python discogs_rating_full.py --master-id 606709

2) Por artista + álbum:
   python discogs_rating_full.py --artist "Arctic Monkeys" --album "AM"

El script:
- Si usas master-id, intenta rating del main_release del master.
- Si usas artista+álbum, busca en /database/search:
    - Si el resultado tiene master_id → usa master → main_release para rating.
    - Si no tiene master_id → usa directamente el release para rating.
"""

import argparse
import sys
from typing import Any, Dict, Optional, List

import httpx

# =========================
# CONFIG
# =========================

DISCOGS_KEY = "QiaraVlzXNSUJOpkdKdK"      # <-- pon aquí tu key de Discogs
DISCOGS_SECRET = "BssuhxnAECuSXYoFYPzIuSUixhVXRedG"   # <-- pon aquí tu secret de Discogs

BASE_URL = "https://api.discogs.com"
USER_AGENT = "Vinilogy/1.0 (+https://vinilogy.com)"  # cámbialo si quieres


# =========================
# Helpers HTTP y rating
# =========================

def discogs_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hace un GET a la API de Discogs añadiendo key/secret y User-Agent.
    Sale con código 1 si falta config o hay error HTTP.
    """
    if not DISCOGS_KEY or not DISCOGS_SECRET:
        print("ERROR: Configura DISCOGS_KEY y DISCOGS_SECRET en el script.", file=sys.stderr)
        sys.exit(1)

    url = f"{BASE_URL}{path}"
    full_params = dict(params)
    full_params["key"] = DISCOGS_KEY
    full_params["secret"] = DISCOGS_SECRET

    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        r = client.get(url, params=full_params)
        if r.status_code != 200:
            print(f"ERROR HTTP {r.status_code} para {url}: {r.text}", file=sys.stderr)
            sys.exit(1)
        return r.json()


def extract_rating(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extrae el rating de community.rating.{average, count}.
    Devuelve dict {average, count} o None si no hay rating.
    """
    community = obj.get("community") or {}
    rating = community.get("rating") or {}
    average = rating.get("average")
    count = rating.get("count")

    if average is None or count is None:
        return None

    return {
        "average": float(average),
        "count": int(count),
    }


# =========================
# Rating por release
# =========================

def get_rating_by_release_id(release_id: int) -> Optional[Dict[str, Any]]:
    """
    Dado un release_id, obtiene el rating de /releases/{id}.
    """
    data = discogs_get(f"/releases/{release_id}", params={})
    rating = extract_rating(data)
    if rating:
        rating["source"] = "release"
        rating["release_id"] = int(release_id)
    return rating


# =========================
# Rating por master (usa main_release)
# =========================

def get_rating_by_master_id(master_id: int) -> Optional[Dict[str, Any]]:
    """
    Dado un master_id:
      1) Lee /masters/{id}
      2) Intenta rating del main_release (main_release_url)
      3) Si no hay, intenta rating directo del master
      4) (Opcional) aquí podrías hacer fallback a versiones si quisieras
    """
    master = discogs_get(f"/masters/{master_id}", params={})

    # 1) Intentar vía main_release
    main_release_id = master.get("main_release")
    if main_release_id:
        rel = discogs_get(f"/releases/{main_release_id}", params={})
        rating_rel = extract_rating(rel)
        if rating_rel is not None:
            rating_rel["source"] = "main_release"
            rating_rel["master_id"] = int(master_id)
            rating_rel["release_id"] = int(main_release_id)
            return rating_rel

    # 2) Intentar rating directo del master (no siempre existe)
    rating_master = extract_rating(master)
    if rating_master is not None:
        rating_master["source"] = "master"
        rating_master["master_id"] = int(master_id)
        return rating_master

    # 3) Aquí podrías llamar a aggregate_rating_from_master_versions(master_id)
    return None


# =========================
# Búsqueda por artista + álbum
# =========================

def score_search_result(r: Dict[str, Any], album: str) -> int:
    """
    Asigna un pequeño score a cada resultado para elegir el mejor.
    - Prioriza formato Vinyl
    - Prioriza que el título contenga el nombre del álbum
    """
    score = 0

    formats = r.get("format") or []
    if any("Vinyl" in f for f in formats):
        score += 10

    title = r.get("title") or ""
    if album.lower() in title.lower():
        score += 5

    # Si tiene master_id, sumamos un poco (suele estar bien agrupado)
    if r.get("master_id"):
        score += 2

    return score


def search_best_release_or_master(artist: str, album: str) -> Optional[Dict[str, Any]]:
    """
    Busca en /database/search usando artist + release_title sin 'type',
    para permitir que vengan tanto masters como releases.

    Devuelve el mejor resultado (dict de la lista 'results') o None.
    """
    params = {
        "artist": artist,
        "release_title": album,
        "per_page": 10,
        "page": 1,
    }
    data = discogs_get("/database/search", params=params)
    results: List[Dict[str, Any]] = data.get("results") or []

    if not results:
        return None

    # Elegimos el que tenga mayor score
    scored = sorted(results, key=lambda r: score_search_result(r, album), reverse=True)
    return scored[0]


def get_rating_by_artist_album(artist: str, album: str) -> Optional[Dict[str, Any]]:
    """
    1) Busca el mejor resultado en /database/search
    2) Si el resultado tiene master_id:
        - usa get_rating_by_master_id(master_id)
    3) Si no tiene master_id, usa el id como release_id y saca rating de /releases/{id}
    """
    best = search_best_release_or_master(artist, album)
    if best is None:
        print(f"No se encontraron resultados para '{artist}' - '{album}'", file=sys.stderr)
        return None

    master_id = best.get("master_id")
    release_id = best.get("id")

    if master_id:
        rating = get_rating_by_master_id(int(master_id))
        if rating is not None:
            # añadimos algo de contexto del search
            rating.setdefault("meta", {})
            rating["meta"]["search_title"] = best.get("title")
            rating["meta"]["search_type"] = best.get("type")
            rating["meta"]["search_formats"] = best.get("format")
            return rating

    if release_id:
        rating = get_rating_by_release_id(int(release_id))
        if rating is not None:
            rating.setdefault("meta", {})
            rating["meta"]["search_title"] = best.get("title")
            rating["meta"]["search_type"] = best.get("type")
            rating["meta"]["search_formats"] = best.get("format")
            return rating

    print(f"El mejor resultado para '{artist}' - '{album}' no tiene rating.", file=sys.stderr)
    return None


# =========================
# CLI
# =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lee el rating de un release/master de Discogs por master-id o por artista+álbum."
    )
    parser.add_argument("--master-id", type=int, help="ID del master de Discogs")
    parser.add_argument("--artist", type=str, help="Nombre del artista")
    parser.add_argument("--album", type=str, help="Título del álbum")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.master_id and (args.artist or args.album):
        print("ERROR: Usa o bien --master-id o bien --artist + --album, pero no ambos.", file=sys.stderr)
        sys.exit(1)

    if args.master_id:
        rating = get_rating_by_master_id(args.master_id)
        if rating is None:
            print(f"El master {args.master_id} no tiene rating.")
        else:
            src = rating.get("source", "desconocido")
            avg = rating["average"]
            cnt = rating["count"]
            rel_id = rating.get("release_id")
            extra = f" (release {rel_id})" if rel_id else ""
            print(f"[{src}] Rating master {args.master_id}{extra}: {avg:.2f} ({cnt} votos)")
        return

    if args.artist and args.album:
        rating = get_rating_by_artist_album(args.artist, args.album)
        if rating is None:
            print(f"No se obtuvo rating para '{args.artist}' - '{args.album}'.")
        else:
            src = rating.get("source", "desconocido")
            avg = rating["average"]
            cnt = rating["count"]
            rid = rating.get("release_id")
            mid = rating.get("master_id")
            print(f"[{src}] Rating para '{args.artist}' - '{args.album}': {avg:.2f} ({cnt} votos)")
            if mid:
                print(f"  master_id: {mid}")
            if rid:
                print(f"  release_id: {rid}")
        return

    print("ERROR: Debes usar --master-id o bien --artist y --album.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
