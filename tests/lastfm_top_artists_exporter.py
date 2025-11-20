#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
lastfm_top_artists_exporter.py

Pequeña UI para exportar CSVs de top artistas de Last.fm:
- Global
- Por país
- Por género/tag

Ejecutar con:

    streamlit run lastfm_top_artists_exporter.py --server.port 8000 --server.address 0.0.0.0
"""

import os
import csv
import io
import requests
import streamlit as st

API_KEY = os.getenv("LASTFM_API_KEY")
BASE_URL = "https://ws.audioscrobbler.com/2.0/"


def extract_best_image(image_list):
    """Devuelve la mejor imagen disponible según prioridad de tamaño."""
    priority = ["mega", "extralarge", "large", "medium", "small"]
    for size in priority:
        for img in image_list:
            if img.get("size") == size and img.get("#text"):
                return img["#text"]
    return ""


def fetch_artists(mode: str, limit: int, page: int = 1, country: str | None = None, tag: str | None = None):
    """Llama a la API de Last.fm y devuelve la lista de artistas ya normalizada."""
    if not API_KEY:
        raise RuntimeError("No se encontró LASTFM_API_KEY en los secrets/variables de entorno.")

    params = {
        "api_key": API_KEY,
        "format": "json",
        "limit": limit,
        "page": page,
    }

    if mode == "global":
        params["method"] = "chart.gettopartists"
    elif mode == "country":
        params["method"] = "geo.gettopartists"
        params["country"] = country
    elif mode == "tag":
        params["method"] = "tag.gettopartists"
        params["tag"] = tag
    else:
        raise ValueError(f"Modo no soportado: {mode}")

    resp = requests.get(BASE_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    # Estructuras de respuesta distintas según método
    if mode == "global":
        artists = data.get("artists", {}).get("artist", [])
    else:
        artists = data.get("topartists", {}).get("artist", [])

    return artists


def build_csv(artists):
    """Genera un CSV en memoria (StringIO) con las columnas deseadas."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["rank", "name", "mbid", "listeners", "playcount", "url", "image_url"])

    for i, a in enumerate(artists, start=1):
        image_url = extract_best_image(a.get("image", []))
        writer.writerow([
            i,
            a.get("name", ""),
            a.get("mbid", ""),
            a.get("listeners", ""),
            a.get("playcount", ""),
            a.get("url", ""),
            image_url,
        ])

    return output.getvalue()


# ----------------- UI con Streamlit -----------------

st.title("🎧 Last.fm Top Artists → CSV")
st.write("Exporta un CSV con los artistas top por **mundo**, **país** o **género (tag)**.")

if not API_KEY:
    st.error("❌ No se encontró `LASTFM_API_KEY` en las variables de entorno. Configúralo en Replit/entorno.")
    st.stop()

mode = st.selectbox(
    "¿Qué quieres exportar?",
    options=["Global (chart.gettopartists)", "Por país (geo.gettopartists)", "Por género/tag (tag.gettopartists)"],
)

limit = st.slider("Número de artistas", min_value=10, max_value=1000, value=200, step=10)

country = None
tag = None
suffix = "global"

if mode.startswith("Por país"):
    country = st.text_input("País (en inglés, p.ej. Spain, United States, Brazil)", value="Spain")
    suffix = f"country_{country.replace(' ', '_')}"
elif mode.startswith("Por género"):
    tag = st.text_input("Género/tag (p.ej. rock, indie, hip-hop)", value="rock")
    suffix = f"tag_{tag.replace(' ', '_')}"
else:
    suffix = "global"

if st.button("📡 Descargar datos y generar CSV"):
    try:
        with st.spinner("Llamando a la API de Last.fm..."):
            if mode.startswith("Global"):
                artists = fetch_artists("global", limit=limit)
            elif mode.startswith("Por país"):
                if not country.strip():
                    st.error("Por favor, introduce un país.")
                    st.stop()
                artists = fetch_artists("country", limit=limit, country=country.strip())
            else:  # género/tag
                if not tag.strip():
                    st.error("Por favor, introduce un género/tag.")
                    st.stop()
                artists = fetch_artists("tag", limit=limit, tag=tag.strip())

        st.success(f"✔ Recibidos {len(artists)} artistas")

        csv_str = build_csv(artists)
        file_name = f"lastfm_top_artists_{suffix}_{limit}.csv"

        st.download_button(
            label="💾 Descargar CSV",
            data=csv_str.encode("utf-8"),
            file_name=file_name,
            mime="text/csv",
        )

        # Vista previa rápida de los primeros 20
        preview = []
        for i, a in enumerate(artists[:20], start=1):
            preview.append({
                "rank": i,
                "name": a.get("name", ""),
                "listeners": a.get("listeners", ""),
                "playcount": a.get("playcount", ""),
            })

        if preview:
            st.subheader("Vista previa (primeros 20)")
            st.dataframe(preview)

    except Exception as e:
        st.error(f"❌ Error al obtener datos: {e}")
