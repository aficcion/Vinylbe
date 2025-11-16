#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import requests

API_KEY = "cb606e8446da2c8e78ab03ecb7e600c1"
URL = "https://ws.audioscrobbler.com/2.0/"

params = {
    "method": "chart.gettopartists",
    "api_key": "cb606e8446da2c8e78ab03ecb7e600c1",
    "format": "json",
    "limit": 1000,
    "page": 1,
}

print("📡 Descargando top 1000 artistas de Last.fm...")
resp = requests.get(URL, params=params, timeout=20)
resp.raise_for_status()
data = resp.json()

artists = data["artists"]["artist"]
print(f"✔ Recibidos {len(artists)} artistas")

# Nombre del CSV
CSV_FILE = "top_artists_1000.csv"

# Escritura del CSV
with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["rank", "name", "mbid", "listeners", "playcount", "url"])

    for i, a in enumerate(artists, start=1):
        writer.writerow([
            i,
            a.get("name", ""),
            a.get("mbid", ""),
            a.get("listeners", ""),
            a.get("playcount", ""),
            a.get("url", "")
        ])

print(f"💾 Archivo CSV generado: {CSV_FILE}")
