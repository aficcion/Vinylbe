#!/usr/bin/env python3
"""
Script para importar artistas desde un archivo CSV a la base de datos.

Formato del CSV:
--------------
name
Radiohead
Blur
Pink Floyd
The Beatles

O con encabezado opcional:
name
Artist Name 1
Artist Name 2

El script:
- Lee el CSV línea por línea
- Consulta cada artista a través de la API para obtener álbumes con ratings
- Guarda automáticamente en PostgreSQL con imagen y ratings
- Maneja errores por artista (si uno falla, continúa con los demás)
- Respeta rate limiting de APIs externas
"""

import csv
import httpx
import time
import sys
from pathlib import Path


def import_artists_from_csv(csv_file_path: str, top_albums_per_artist: int = 10):
    """Import artists from CSV file"""
    
    csv_path = Path(csv_file_path)
    if not csv_path.exists():
        print(f"✗ ERROR: Archivo no encontrado: {csv_file_path}")
        print(f"\nUso: python scripts/import_artists_from_csv.py <archivo.csv>")
        return
    
    print("\n" + "="*60)
    print("IMPORTACIÓN DE ARTISTAS DESDE CSV")
    print("="*60 + "\n")
    print(f"📁 Archivo: {csv_file_path}")
    print(f"📀 Álbumes por artista: {top_albums_per_artist}\n")
    
    # Read CSV
    artists = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Check if header exists
        if not reader.fieldnames or 'name' not in reader.fieldnames:
            print("✗ ERROR: El CSV debe tener una columna 'name'")
            print("\nFormato esperado:")
            print("name")
            print("Radiohead")
            print("Blur")
            return
        
        for row in reader:
            artist_name = row.get('name', '').strip()
            if artist_name:
                artists.append(artist_name)
    
    if not artists:
        print("✗ ERROR: No se encontraron artistas en el CSV")
        return
    
    print(f"📋 Encontrados {len(artists)} artistas para importar")
    print(f"⏱️  Tiempo estimado: ~{len(artists) * 6 / 60:.1f} minutos (primera carga)\n")
    
    # Import each artist
    successful = 0
    failed = 0
    already_cached = 0
    
    client = httpx.Client(timeout=120.0)
    
    for i, artist_name in enumerate(artists, 1):
        print(f"[{i}/{len(artists)}] {artist_name}")
        
        try:
            start = time.time()
            response = client.post(
                'http://localhost:5000/api/recommendations/artist-single',
                json={
                    'artist_name': artist_name,
                    'top_albums': top_albums_per_artist
                }
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                total_albums = data.get('total', 0)
                
                if elapsed < 1.0:
                    print(f"  ✓ Cargado desde caché ({elapsed:.2f}s) - {total_albums} álbumes")
                    already_cached += 1
                else:
                    print(f"  ✓ Importado exitosamente ({elapsed:.2f}s) - {total_albums} álbumes con ratings")
                    successful += 1
                
                # Show top album
                if data.get('recommendations'):
                    top = data['recommendations'][0]
                    rating = top.get('rating', 'N/A')
                    print(f"    Top: \"{top.get('album_name')}\" ({top.get('year')}) - Rating: {rating}/5")
            
            elif response.status_code == 404:
                print(f"  ⚠ No se encontraron álbumes")
                failed += 1
            
            else:
                print(f"  ✗ Error HTTP {response.status_code}: {response.text[:100]}")
                failed += 1
        
        except httpx.TimeoutException:
            print(f"  ✗ Timeout (>120s) - artista muy lento, saltando...")
            failed += 1
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1
        
        # Small delay between artists to avoid overwhelming the system
        if i < len(artists):
            time.sleep(0.5)
    
    client.close()
    
    # Summary
    print("\n" + "="*60)
    print("IMPORTACIÓN COMPLETA")
    print("="*60)
    print(f"✓ Importados nuevos: {successful}")
    print(f"⚡ Ya en caché: {already_cached}")
    print(f"✗ Fallidos: {failed}")
    print(f"📊 Total procesados: {len(artists)}")
    print("="*60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n" + "="*60)
        print("USO DEL SCRIPT")
        print("="*60)
        print("\nFormato del CSV:")
        print("-" * 60)
        print("name")
        print("Radiohead")
        print("Blur")
        print("Pink Floyd")
        print("The Beatles")
        print("-" * 60)
        print("\nEjemplo de uso:")
        print("  python scripts/import_artists_from_csv.py artists.csv")
        print("\nNotas importantes:")
        print("  • La columna 'name' es obligatoria")
        print("  • Cada artista se consultará en APIs externas (~5-7s por artista)")
        print("  • Los artistas se guardan automáticamente con ratings e imágenes")
        print("  • Consultas futuras serán ~30x más rápidas (desde caché PostgreSQL)")
        print("  • El script maneja errores por artista (si uno falla, continúa)")
        print("="*60 + "\n")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    import_artists_from_csv(csv_file)
