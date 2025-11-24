import os
import time
import sqlite3
import httpx
from typing import Optional, Tuple

DISCOGS_BASE = "https://api.discogs.com"
DISCOGS_KEY = os.getenv("DISCOGS_CONSUMER_KEY", "")
DISCOGS_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET", "")

HEADERS = {"User-Agent": "VinylRecommendationSystem/1.0"}

CLIENT = httpx.Client(
    headers=HEADERS,
    http2=False,
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
    follow_redirects=True,
)


def dict_factory(cursor, row):
    """Convert SQLite row to dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_db_connection():
    """Get SQLite connection"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    return conn


def _discogs_get(path: str, params: dict, tries: int = 5):
    """Discogs API call with retry and rate limiting"""
    url = f"{DISCOGS_BASE}{path}"
    params = {**params, "key": DISCOGS_KEY, "secret": DISCOGS_SECRET}
    last_exc = None
    backoff = 1.0
    
    for attempt in range(1, tries + 1):
        try:
            r = CLIENT.get(url, params=params)
            if r.status_code == 429:
                if attempt < tries:
                    print(f"  [DISCOGS] Rate limit, retry in {backoff}s... ({attempt}/{tries})")
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 10.0)
                    continue
            r.raise_for_status()
            time.sleep(0.5)
            return r.json()
        except Exception as e:
            last_exc = e
            if attempt < tries:
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 10.0)
    
    raise RuntimeError(f"Discogs API failed: {last_exc}")


def get_discogs_master_rating(master_id: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """Get rating, votes, and cover from Discogs master"""
    if not master_id:
        return None, None, None
    
    try:
        data = _discogs_get(f"/masters/{master_id}", {})
        r = (data.get("community") or {}).get("rating") or {}
        
        cover_url = None
        images = data.get("images", [])
        if images and len(images) > 0:
            cover_url = images[0].get("uri")
        
        if r.get("average") is not None:
            rating = float(r["average"])
            votes = int(r.get("count", 0))
            return rating, votes, cover_url
        
        # Fallback to main_release if master has no rating
        main_rel = data.get("main_release")
        if not main_rel:
            return None, None, cover_url
        
        rel = _discogs_get(f"/releases/{main_rel}", {})
        rr = (rel.get("community") or {}).get("rating") or {}
        
        if not cover_url:
            rel_images = rel.get("images", [])
            if rel_images and len(rel_images) > 0:
                cover_url = rel_images[0].get("uri")
        
        if rr.get("average") is not None:
            rating = float(rr["average"])
            votes = int(rr.get("count", 0))
            return rating, votes, cover_url
        
        return None, None, cover_url
    
    except Exception as e:
        print(f"  [ERROR] Master {master_id}: {e}")
        return None, None, None


def main():
    print("\n" + "="*60)
    print("ACTUALIZACIÓN DE RATINGS FALTANTES")
    print("="*60 + "\n")
    
    if not DISCOGS_KEY or not DISCOGS_SECRET:
        print("✗ ERROR: DISCOGS credentials not found")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get albums without rating
    cursor.execute("""
        SELECT a.id, a.title, a.year, a.discogs_master_id, ar.name as artist_name
        FROM albums a
        JOIN artists ar ON a.artist_id = ar.id
        WHERE a.rating IS NULL AND a.discogs_master_id IS NOT NULL
        ORDER BY ar.name, a.year
    """)
    
    albums_to_update = cursor.fetchall()
    total = len(albums_to_update)
    
    if total == 0:
        print("✓ No hay álbumes sin rating para actualizar")
        conn.close()
        return
    
    print(f"📋 Encontrados {total} álbumes sin rating")
    print(f"⏱️  Tiempo estimado: ~{total * 0.6 / 60:.1f} minutos\n")
    
    updated = 0
    failed = 0
    no_rating = 0
    
    for i, album in enumerate(albums_to_update, 1):
        print(f"[{i}/{total}] {album['artist_name']} - {album['title']} ({album['year']})")
        
        try:
            rating, votes, cover_url = get_discogs_master_rating(album['discogs_master_id'])
            
            if rating is not None:
                cursor.execute("""
                    UPDATE albums 
                    SET rating = ?, votes = ?, cover_url = COALESCE(cover_url, ?)
                    WHERE id = ?
                """, (rating, votes, cover_url, album['id']))
                conn.commit()
                print(f"  ✓ Rating: {rating:.2f}/5 ({votes} votos)")
                updated += 1
            else:
                print(f"  ⚠ Sin rating en Discogs")
                no_rating += 1
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1
            conn.rollback()
    
    conn.close()
    
    print("\n" + "="*60)
    print("ACTUALIZACIÓN COMPLETA")
    print("="*60)
    print(f"✓ Actualizados: {updated}")
    print(f"⚠ Sin rating: {no_rating}")
    print(f"✗ Fallidos: {failed}")
    print(f"📊 Total: {total}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
