#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ebay_vinyl_price.py

Busca en eBay el vinilo "<artist> <album>" y devuelve:

- Mejor oferta en eBay (precio más barato en EUR con envío al país indicado).
- Enlaces a tiendas locales (sin hacer scraping):
    - Marilians
    - Bajo el Volcán
    - Discos Bora Bora
    - Revolver Records

Uso:

    python ebay_vinyl_price.py "Geese" "Getting Killed"
    python ebay_vinyl_price.py "Karavana" "Entre amores y errores" --debug

Requiere variables de entorno:
    EBAY_CLIENT_ID
    EBAY_CLIENT_SECRET
"""

from typing import Optional, Dict, Any, List
import os
import sys
import argparse

import httpx

# =========================
# Constantes
# =========================

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# Categoría "Vinyl Records" (eBay)
VINYL_CATEGORY_ID = "176985"


# =========================
# Helpers
# =========================

def normalize(text: str) -> str:
    """Normaliza strings para comparaciones simples."""
    return (
        text.lower()
        .replace(",", " ")
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )


# =========================
# OAuth eBay
# =========================

def get_ebay_access_token(debug: bool = False) -> str:
    """
    Obtiene un application access token de eBay usando client credentials.
    Requiere EBAY_CLIENT_ID y EBAY_CLIENT_SECRET en entorno.
    """
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "EBAY_CLIENT_ID y EBAY_CLIENT_SECRET deben estar en variables de entorno"
        )

    if debug:
        print("\n[DEBUG] Getting OAuth token from eBay…")
        print(f"[DEBUG] Client ID: {client_id}")
        print(
            f"[DEBUG] Client Secret length: "
            f"{len(client_secret) if client_secret else 'None'}"
        )

    auth = (client_id, client_secret)
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            EBAY_OAUTH_URL,
            auth=auth,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if debug:
            print("[DEBUG] OAuth response status:", resp.status_code)
            print("[DEBUG] OAuth response body:", resp.text)

        resp.raise_for_status()
        payload = resp.json()

        if debug:
            token_preview = payload["access_token"][:20] + "..."
            print("[DEBUG] Access token acquired:", token_preview)

        return payload["access_token"]


# =========================
# eBay: parsing y selección
# =========================

def pick_best_ebay_item(
    item_summaries: List[dict],
    artist: str,
    album: str,
    debug: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Dado itemSummaries de eBay, devuelve el mejor item:
      - título razonable (contenga artist y algo del álbum)
      - precio total más bajo (item + shipping)
      - en EUR
    """
    artist_n = normalize(artist)
    album_n = normalize(album)

    if debug:
        print(f"\n[DEBUG] Raw eBay returned {len(item_summaries)} items")

    candidates: List[Dict[str, Any]] = []

    for idx, item in enumerate(item_summaries):
        title = item.get("title", "")
        title_n = normalize(title)

        if debug:
            print(f"\n[DEBUG] Item #{idx}: {title}")
            # Si hay demasiado ruido, comenta la siguiente línea:
            print("[DEBUG] Raw item:", item)

        # Filtro 1: que aparezca al menos una palabra del nombre de artista
        if not any(w for w in artist_n.split() if w in title_n):
            if debug:
                print("[DEBUG] ❌ descartado: no contiene el artista")
            continue

        # Filtro 2: que contenga alguna palabra del título del álbum
        if all(word not in title_n for word in album_n.split() if word):
            if debug:
                print("[DEBUG] ❌ descartado: no contiene el nombre del álbum")
            continue

        # Ya estamos en categoría de vinilo, solo filtramos CDs/cassette raros
        if "cd" in title_n or "cassette" in title_n:
            if debug:
                print("[DEBUG] ❌ descartado: parece CD/cassette")
            continue

        price = item.get("price", {})
        ship_opts = item.get("shippingOptions", [])

        if not price or not ship_opts:
            if debug:
                print("[DEBUG] ❌ descartado: no tiene precio o envío")
            continue

        # Filtramos moneda en Python
        if price.get("currency") != "EUR":
            if debug:
                print(f"[DEBUG] ❌ descartado: moneda {price.get('currency')} != EUR")
            continue

        try:
            item_price = float(price.get("value", 0.0))
        except (TypeError, ValueError):
            if debug:
                print("[DEBUG] ❌ descartado: precio inválido")
            continue

        try:
            ship_cost = float(
                ship_opts[0].get("shippingCost", {}).get("value", 0.0)
            )
        except (TypeError, ValueError, IndexError):
            if debug:
                print("[DEBUG] ❌ descartado: envío inválido")
            continue

        total = item_price + ship_cost

        if debug:
            print(
                f"[DEBUG] ✓ candidato eBay: item={item_price}, "
                f"envío={ship_cost}, total={total}"
            )

        candidates.append(
            {
                "provider": "ebay",
                "title": title,
                "item_price": item_price,
                "shipping_cost": ship_cost,
                "total_price": total,
                "currency": price.get("currency"),
                "url": item.get("itemWebUrl"),
                "raw": item,
            }
        )

    if not candidates:
        if debug:
            print("[DEBUG] ❌ No hay candidatos eBay válidos después del filtro.")
        return None

    candidates.sort(key=lambda c: c["total_price"])
    best = candidates[0]

    if debug:
        print("\n[DEBUG] BEST EBAY ITEM SELECTED:")
        print(best)

    return best


def fetch_best_ebay_offer(
    artist: str,
    album: str,
    country: str = "ES",
    marketplace_id: str = "EBAY_ES",
    debug: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Busca en eBay el vinilo de artist + album y devuelve la mejor oferta
    (precio más barato en EUR que se envíe al país indicado).
    """
    if debug:
        print("\n[DEBUG] Starting eBay search…")
        print(f"[DEBUG] Artist: {artist}")
        print(f"[DEBUG] Album: {album}")
        print(f"[DEBUG] Country: {country}")
        print(f"[DEBUG] Marketplace: {marketplace_id}")
        print(f"[DEBUG] Vinyl category ID: {VINYL_CATEGORY_ID}")

    token = get_ebay_access_token(debug=debug)

    query = f"{artist} {album}"
    params = {
        "q": query,
        "category_ids": VINYL_CATEGORY_ID,
        "filter": f"deliveryCountry:{country}",
        # Orden documentado: priceWithShipping (precio + envío, ascendente)
        "sort": "priceWithShipping",
        "limit": "20",
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        "Content-Type": "application/json",
    }

    if debug:
        print("\n[DEBUG] Requesting eBay…")
        print("[DEBUG] URL:", EBAY_BROWSE_URL)
        print("[DEBUG] Params:", params)
        safe_headers = {
            k: ("<hidden>" if k == "Authorization" else v)
            for k, v in headers.items()
        }
        print("[DEBUG] Headers:", safe_headers)

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(EBAY_BROWSE_URL, params=params, headers=headers)
        if debug:
            print("[DEBUG] eBay response code:", resp.status_code)
            print("[DEBUG] eBay response body (truncated):")
            print(resp.text[:2000])

        resp.raise_for_status()
        data = resp.json()

    items = data.get("itemSummaries", [])
    return pick_best_ebay_item(items, artist=artist, album=album, debug=debug)


# =========================
# Tiendas locales (sin scraping)
# =========================

def local_store_links(artist: str, album: str) -> dict:
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
        "bora_bora": (
            f"https://discosborabora.com/?s={query}"
        ),
        "revolver": (
            f"https://www.revolverrecords.es/?s={query}&post_type=product"
        ),
    }


# =========================
# CLI
# =========================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Busca el mejor precio en eBay para un vinilo (artist + album) y "
            "muestra enlaces a tiendas locales."
        )
    )
    parser.add_argument("artist", help="Nombre del artista (ej. 'Geese')")
    parser.add_argument(
        "album", nargs="+", help="Título del álbum (ej. 'Getting Killed')"
    )
    parser.add_argument(
        "--country",
        default="ES",
        help="País de entrega (deliveryCountry, por defecto ES)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa salida de debug detallada",
    )

    args = parser.parse_args()
    artist = args.artist
    album = " ".join(args.album)

    ebay_offer = None

    try:
        ebay_offer = fetch_best_ebay_offer(
            artist,
            album,
            country=args.country,
            debug=args.debug,
        )
    except Exception as e:
        print("Error calling eBay:", e, file=sys.stderr)

    print("\n=== Resultados ===")

    if ebay_offer:
        print("\n[EBAY]")
        print(f"  Title:       {ebay_offer['title']}")
        print(f"  Item price:  {ebay_offer['item_price']} {ebay_offer['currency']}")
        print(f"  Shipping:    {ebay_offer['shipping_cost']} {ebay_offer['currency']}")
        print(f"  Total price: {ebay_offer['total_price']} {ebay_offer['currency']}")
        print(f"  URL:         {ebay_offer['url']}")
    else:
        print("\n[EBAY]")
        print("  No suitable offer found on eBay.")

    # --- Tiendas locales ----------
    links = local_store_links(artist, album)

    print("\n[TIENDAS LOCALES — Compra local ❤️]")
    print("  Marilians:        ", links["marilians"])
    print("  Bajo el Volcán:   ", links["bajo_el_volcan"])
    print("  Discos Bora Bora: ", links["bora_bora"])
    print("  Revolver Records: ", links["revolver"])

    print()


if __name__ == "__main__":
    main()
