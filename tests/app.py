#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd

# === IMPORTA TU LÓGICA SIN DUPLICAR ===
from discogs_studio_masters import (
    search_master,
    collect_releases_from_master,
    search_releases,
    discogs_dataframe,
)
from mb_studio_vinyl import mb_dataframe

# =========================
# Config
# =========================
DEFAULT_DISCOGS_KEY = "QiaraVlzXNSUJOpkdKdK"
DEFAULT_DISCOGS_SECRET = "BssuhxnAECuSXYoFYPzIuSUixhVXRedG"

st.set_page_config(page_title="Vinilogy – Discogs & MusicBrainz", page_icon="💿", layout="wide")

with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    discogs_key = st.text_input("Discogs Consumer Key", value=DEFAULT_DISCOGS_KEY, type="password")
    discogs_secret = st.text_input("Discogs Consumer Secret", value=DEFAULT_DISCOGS_SECRET, type="password")
    st.caption("Usa tus claves de Discogs. (Guardadas solo en esta sesión)")

st.title("💿 Vinilogy – Búsqueda de ediciones en vinilo")
tab1, tab2 = st.tabs(["Discogs Releases", "MusicBrainz Studio Albums"])

# =========================
# Discogs UI
# =========================
with tab1:
    st.subheader("Discogs – Releases (por Master ID o por Artista + Álbum)")

    modo = st.radio(
        "¿Cómo quieres buscar?",
        ["Master ID", "Artista + Álbum"],
        index=0,
        horizontal=True
    )

    with st.form("discogs_form", clear_on_submit=False):
        if modo == "Master ID":
            master_id_input = st.text_input("Master ID", placeholder="Ejemplo: 123456")
        else:
            colA, colB = st.columns(2)
            with colA:
                artist = st.text_input("Artista", placeholder="JW Francis")
            with colB:
                title = st.text_input("Álbum (título)", placeholder="Sunshine")
            usar_master_si_existe = st.checkbox("Usar master si existe (recomendado)", value=True)

        colf1, colf2 = st.columns(2)
        with colf1:
            official_only = st.checkbox("Solo ediciones oficiales (excluir Unofficial)", value=True)
        with colf2:
            es_europe_only = st.checkbox("Solo Spain o 'Europe'", value=False)

        submitted = st.form_submit_button("🔎 Buscar")
        st.divider()

        if submitted:
            try:
                rows = []

                if modo == "Master ID":
                    mid = (master_id_input or "").strip()
                    if not mid:
                        st.warning("Introduce un Master ID.")
                        st.stop()
                    if not mid.isdigit():
                        st.error("El Master ID debe ser numérico (p. ej. 123456).")
                        st.stop()

                    # releases (versions) del master
                    rows = collect_releases_from_master(int(mid), discogs_key, discogs_secret)

                else:  # Artista + Álbum
                    if not (artist and title):
                        st.warning("Indica Artista y Álbum.")
                        st.stop()

                    m = None
                    if usar_master_si_existe:
                        m = search_master(artist, title, discogs_key, discogs_secret)

                    if m:
                        rows = collect_releases_from_master(int(m.get("id")), discogs_key, discogs_secret)
                    else:
                        rows = search_releases(artist, title, discogs_key, discogs_secret)

                # dataframe + filtros (lo hace tu módulo)
                df = discogs_dataframe(rows, official_only=official_only, es_europe_only=es_europe_only)

                if df.empty:
                    # Fallback para no dejar vacío: muestra sin filtrar por vinilo
                    df_all = pd.DataFrame(rows, columns=["release_id","year","format","country","label","catno","title","source"])
                    if df_all.empty:
                        st.info("Sin resultados.")
                    else:
                        st.warning("No he encontrado ediciones de vinilo tras filtrar. Muestro todas las releases encontradas.")
                        st.dataframe(df_all, use_container_width=True)
                        csv = df_all.to_csv(index=False).encode("utf-8")
                        st.download_button("⬇️ Descargar CSV", data=csv, file_name="discogs_releases_all.csv", mime="text/csv")
                else:
                    st.success(f"{len(df)} release(s) encontradas.")
                    st.dataframe(df, use_container_width=True)
                    csv = df.to_csv(index=False).encode("utf-8")
                    fname = "discogs_releases.csv" if modo == "Artista + Álbum" else f"discogs_master_{(master_id_input or '').strip()}.csv"
                    st.download_button("⬇️ Descargar CSV", data=csv, file_name=fname, mime="text/csv")

            except Exception as e:
                st.error(f"Error: {e}")

# =========================
# MusicBrainz UI
# =========================
with tab2:
    st.subheader("MusicBrainz – Álbumes de estudio (RG)")
    col1, col2 = st.columns([2,1])
    with col1:
        mb_artist = st.text_input("Artista (MB)", placeholder="The Rolling Stones")
    with col2:
        mb_limit = st.number_input("Límite (1–100)", min_value=1, max_value=100, value=100, step=1)

    run_mb = st.button("🎼 Buscar en MusicBrainz")
    st.caption("Trae release-groups de tipo Album, sin secondary-types y con único artista. Si MB enlaza un master de Discogs, lo muestra.")
    st.divider()

    if run_mb:
        try:
            df_mb = mb_dataframe(mb_artist, limit=int(mb_limit))
            if df_mb.empty:
                st.info("Sin resultados.")
            else:
                st.dataframe(df_mb, use_container_width=True)
                csv = df_mb.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Descargar CSV", data=csv, file_name="musicbrainz_albums.csv", mime="text/csv")
        except Exception as e:
            st.error(f"Error: {e}")
