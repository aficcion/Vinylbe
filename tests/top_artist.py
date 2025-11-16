import csv
import requests
import os

API_KEY = os.getenv("LASTFM_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ No se encontró LASTFM_API_KEY en los secrets.")

URL = "https://ws.audioscrobbler.com/2.0/"

params = {
    "method": "chart.gettopartists",
    "api_key": API_KEY,
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

CSV_FILE = "top_artists_1000.csv"

def extract_best_image(image_list):
    priority = ["mega", "extralarge", "large", "medium", "small"]
    for size in priority:
        for img in image_list:
            if img.get("size") == size and img.get("#text"):
                return img["#text"]
    return ""

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
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
            image_url
        ])

print(f"💾 Archivo CSV generado: {CSV_FILE}")
