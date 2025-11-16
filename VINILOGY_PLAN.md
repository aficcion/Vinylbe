# 🎵 Plan de Implementación: Vinilogy v2.0

**Arquitectura**: Monolito Modular con PostgreSQL  
**Objetivo**: Base de datos como caché inteligente para reducir llamadas a APIs externas  
**Fecha**: Noviembre 2025

---

## 📊 Visión General

### Problema Actual
Tu sistema de microservicios actual (Spotify + Discogs) funciona en **tiempo real** sin persistencia:
- ❌ Cada recomendación = múltiples llamadas a APIs externas
- ❌ Sin caché de datos de artistas/álbumes
- ❌ Dependencia total de disponibilidad de APIs
- ❌ Costes de cuota acumulativos

### Solución Propuesta
**PostgreSQL como "caché inteligente"** y fuente única de verdad:
- ✅ ~10k artistas precargados con álbumes y **TODOS** los vinilos disponibles
- ✅ **Cache-miss behavior**: si algo no está en BD → fetch API → insert → return
- ✅ Precios actualizados periódicamente
- ✅ APIs externas solo para:
  - Cache misses (datos faltantes)
  - Sincronizar escuchas del usuario
  - Refresh periódico de catálogo
  - Actualización de precios
- ✅ Recomendaciones instantáneas (consulta a BD)

### 🎯 Principio de Cache-Miss (CRÍTICO)

**Comportamiento obligatorio en todo el sistema**:

```python
# Ejemplo: Buscar artista por nombre
def get_or_create_artist(name: str) -> Artist:
    # 1. Query DB first
    artist = db.query(Artist).filter(
        Artist.normalized_name == normalize(name)
    ).first()
    
    if artist:
        # Cache HIT → return immediately
        return artist
    
    # 2. Cache MISS → fetch from API
    lastfm_data = lastfm_client.artist_getInfo(artist=name)
    
    # 3. Insert into DB
    artist = Artist(
        name=lastfm_data['name'],
        mbid=lastfm_data['mbid'],
        image_url=extract_image(lastfm_data['image']),
        normalized_name=normalize(lastfm_data['name']),
        source='lastfm'
    )
    db.add(artist)
    db.commit()
    
    # 4. Return DB entity
    return artist
```

**Este patrón se aplica a**:
- `get_or_create_artist(name, mbid)`
- `get_or_create_album(artist_id, title, mbid)`
- `get_or_create_release(album_id, discogs_id)`
- `sync_artist_albums(artist_id)` → fetch if not in DB
- `sync_album_releases(album_id)` → fetch ALL missing releases

### 🎵 Fuentes de Recomendación

El motor de recomendaciones combina múltiples señales:

1. **Manual Seeds** (v1 - prioritario):
   - Usuario añade artistas manualmente
   - Tabla: `user_seed_artists`

2. **Discogs Collection/Wantlist** (v2 - cuando conecte):
   - Fetch collection via Discogs OAuth
   - Identificar releases → albums → artists
   - Usar como señal positiva fuerte

3. **Spotify/Last.fm Listening History** (v3):
   - Top albums/tracks por período
   - Playcounts como peso
   - Tabla: `listening_snapshots`

**Todos estos inputs se combinan en el scorer** para generar `recommendation_sets`

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────┐
│                     MONOLITO MODULAR                    │
│                                                         │
│  /app/core              # Config, DB session, utils    │
│  /app/modules/                                          │
│    ├─ identity          # Auth, usuarios               │
│    ├─ profiles          # Gustos, conexiones Last.fm   │
│    ├─ catalog           # Artistas, álbumes, vinilos   │
│    ├─ integrations      # Clientes API externos        │
│    ├─ prices            # Precios, best_price          │
│    ├─ recommender       # Motor de recomendaciones     │
│    ├─ collections       # Wantlist, locks, dismissals  │
│    └─ ops               # Health, jobs, métricas       │
│                                                         │
│  /migrations            # Alembic                       │
│  /scripts               # CLI jobs de ingestion        │
└─────────────────────────────────────────────────────────┘
           │
           │ Consultas frecuentes
           ▼
┌─────────────────────────────────────────────────────────┐
│                   POSTGRESQL DATABASE                   │
│                                                         │
│  artists (10k rows)                                     │
│  artist_similars (200k rows)                            │
│  albums (50k rows)                                      │
│  releases (500k+ rows) ← TODOS los vinilos de Discogs  │
│  prices (2M+ rows)                                      │
│  album_best_price (materialized view)                   │
│  user_profiles                                          │
│  user_seed_artists                                      │
│  user_discogs_collections                               │
│  listening_snapshots                                    │
│  recommendation_sets                                    │
└─────────────────────────────────────────────────────────┘
           │
           │ Updates periódicos (batch jobs)
           ▼
┌─────────────────────────────────────────────────────────┐
│                     APIs EXTERNAS                       │
│                                                         │
│  Last.fm        → Similares, tags, listening data      │
│  MusicBrainz    → Studio albums                        │
│  Discogs        → Vinyl editions, ratings              │
│  Price Providers → eBay, Amazon, tiendas indie         │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 FASES DE IMPLEMENTACIÓN

### FASE 0: Fundaciones (1 semana)

#### 0.1. Setup de Base de Datos
**Tareas**:
- [ ] Crear PostgreSQL database en Replit
- [ ] Configurar SQLAlchemy (async engine)
- [ ] Setup Alembic para migraciones
- [ ] Variables de entorno: `DATABASE_URL`, API keys

**Output**: DB vacía lista para recibir schema

---

#### 0.2. Estructura de Módulos
**Estructura**:
```
/vinilogy/
  /app/
    /core/
      __init__.py
      config.py          # Env vars, settings
      database.py        # Session, engine
      models.py          # Base model
    /modules/
      /artists/
        models.py        # Artist
        repository.py    # get_or_create, queries
        service.py       # Business logic
      /albums/
        models.py        # Album
        repository.py    # get_or_create, queries
        service.py       # Business logic
      /releases/
        models.py        # Release (vinyl editions)
        repository.py    # get_or_create, queries
        service.py       # Sync ALL releases logic
      /integrations/
        /lastfm/
          client.py      # Last.fm API wrapper
          rate_limiter.py
        /musicbrainz/
          client.py      # MusicBrainz wrapper
        /discogs/
          client.py      # Discogs wrapper
      /profiles/
        models.py        # UserProfile, ExternalAccount
      /prices/
        models.py        # PriceQuote, BestPrice
      /recommender/
        models.py        # RecommendationSet, Item
        scorer.py        # Scoring logic
  /migrations/           # Alembic migrations
  /scripts/
    seed_artists.py           # Seed initial artists from Last.fm tags
    enrich_albums.py          # Fetch studio albums from MusicBrainz
    sync_all_releases.py      # Map ALL vinyl releases from Discogs
    compute_prices.py         # Fetch prices for releases
    debug_lastfm_images.py    # Debug image URL extraction
  main.py               # FastAPI app (futuro)
  alembic.ini
```

**Output**: Estructura de carpetas + imports funcionando

---

#### 0.3. Rate Limiting & Retry Logic
**Componente genérico**:
```python
class APIClient:
    def __init__(self, rate_limit: float, max_retries: int):
        self.rate_limiter = RateLimiter(rate_limit)
        self.max_retries = max_retries
    
    async def request_with_retry(self, fn, *args):
        # Exponential backoff
        # Rate limiting
        # Error handling
```

**Configuración por API**:
- Last.fm: 5 req/s
- MusicBrainz: 1 req/s (respetar User-Agent)
- Discogs: 60 req/min (25 req/min autenticado)

**Output**: Wrapper reutilizable para todos los clientes

---

#### 0.4. Cache-Miss Helpers (CRÍTICO)
**Archivo**: `/app/core/cache_helpers.py`

**Concepto**: Todos los lookups deben seguir el patrón "query DB → if miss → fetch API → insert → return"

```python
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.artists.models import Artist
from app.modules.albums.models import Album
from app.modules.releases.models import Release
from app.modules.integrations.lastfm import LastFmClient
from app.modules.integrations.musicbrainz import MusicBrainzClient
from app.modules.integrations.discogs import DiscogsClient

# Artist helpers
async def get_or_create_artist(
    db: Session,
    name: str,
    mbid: Optional[str] = None,
    lastfm: LastFmClient = None
) -> Artist:
    """
    1. Query DB by normalized_name or mbid
    2. If found → return
    3. If not found → fetch from Last.fm → insert → return
    """
    normalized = normalize_name(name)
    
    # Query DB first
    query = db.query(Artist)
    if mbid:
        artist = query.filter(Artist.mbid == mbid).first()
    else:
        artist = query.filter(Artist.normalized_name == normalized).first()
    
    if artist:
        return artist  # Cache HIT
    
    # Cache MISS → fetch from API
    data = await lastfm.artist_getInfo(artist=name, mbid=mbid)
    
    artist = Artist(
        name=data['name'],
        mbid=data.get('mbid'),
        normalized_name=normalize_name(data['name']),
        image_url=extract_image_url(data.get('image', [])),
        source='lastfm'
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    
    return artist

# Album helpers
async def get_or_create_album(
    db: Session,
    artist_id: int,
    title: str,
    mbid: Optional[str] = None,
    musicbrainz: MusicBrainzClient = None
) -> Album:
    """
    Similar pattern for albums
    """
    normalized_title = normalize_name(title)
    
    # Query DB
    query = db.query(Album).filter(Album.artist_id == artist_id)
    if mbid:
        album = query.filter(Album.mbid == mbid).first()
    else:
        album = query.filter(Album.normalized_title == normalized_title).first()
    
    if album:
        return album  # Cache HIT
    
    # Cache MISS → fetch from MusicBrainz
    # ... fetch logic ...
    
    return album

# Release helpers
async def sync_album_releases(
    db: Session,
    album_id: int,
    discogs: DiscogsClient
) -> int:
    """
    Fetch ALL vinyl releases for an album from Discogs
    Returns count of NEW releases inserted
    """
    album = db.query(Album).get(album_id)
    
    if not album:
        raise ValueError(f"Album {album_id} not found")
    
    # Count existing releases
    existing_count = db.query(Release).filter(
        Release.album_id == album_id
    ).count()
    
    # Fetch ALL from Discogs
    if album.discogs_master_id:
        releases = await discogs.get_all_master_versions(
            album.discogs_master_id
        )
    else:
        releases = await discogs.search_vinyl_releases(
            artist=album.artist.name,
            title=album.title
        )
    
    # Insert missing releases
    new_count = 0
    for release_data in releases:
        existing = db.query(Release).filter(
            Release.discogs_id == release_data['id']
        ).first()
        
        if not existing:
            release = Release(
                discogs_id=release_data['id'],
                album_id=album_id,
                title=release_data['title'],
                country=release_data.get('country'),
                year=release_data.get('year'),
                format=release_data.get('format'),
                label=release_data.get('label'),
                # ... more fields
            )
            db.add(release)
            new_count += 1
    
    db.commit()
    return new_count
```

**Este módulo es el corazón del sistema de caché**. Todas las operaciones de ingestion y lookups deben usarlo.

---

### FASE 1: Catálogo Base (2-3 semanas)

#### 1.1. Schema de Catálogo
**Migración Alembic**: `001_create_catalog_tables.py`

```sql
-- artists
CREATE TABLE artists (
    id SERIAL PRIMARY KEY,
    mbid UUID UNIQUE,
    discogs_id INTEGER,
    spotify_id VARCHAR(50),
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    image_url TEXT,
    source VARCHAR(50),  -- 'lastfm_tag', 'manual', 'similar', 'seed'
    popularity_score FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_artists_normalized ON artists(normalized_name);
CREATE INDEX idx_artists_mbid ON artists(mbid);
CREATE INDEX idx_artists_discogs ON artists(discogs_id);
CREATE INDEX idx_artists_spotify ON artists(spotify_id);

-- artist_similars
CREATE TABLE artist_similars (
    artist_id INTEGER REFERENCES artists(id) ON DELETE CASCADE,
    similar_artist_id INTEGER REFERENCES artists(id) ON DELETE CASCADE,
    score FLOAT NOT NULL,  -- 0-1 from Last.fm
    source VARCHAR(50) DEFAULT 'lastfm',
    PRIMARY KEY (artist_id, similar_artist_id)
);

CREATE INDEX idx_similars_artist ON artist_similars(artist_id);

-- albums
CREATE TABLE albums (
    id SERIAL PRIMARY KEY,
    mbid UUID UNIQUE,
    discogs_master_id INTEGER,
    spotify_id VARCHAR(50),
    artist_id INTEGER REFERENCES artists(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    normalized_title VARCHAR(500) NOT NULL,
    first_release_year INTEGER,
    is_studio BOOLEAN DEFAULT TRUE,
    track_count INTEGER,
    source VARCHAR(50) DEFAULT 'musicbrainz',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_albums_artist ON albums(artist_id);
CREATE INDEX idx_albums_mbid ON albums(mbid);
CREATE INDEX idx_albums_master ON albums(discogs_master_id);
CREATE INDEX idx_albums_spotify ON albums(spotify_id);
CREATE INDEX idx_albums_normalized ON albums(normalized_title);

-- releases (TODOS LOS VINILOS - critical table)
-- ⚠️  IMPORTANT: Store ALL vinyl releases found on Discogs
-- Not just one per album, not just the cheapest
-- Every country, every year, every pressing, every variant
CREATE TABLE releases (
    id SERIAL PRIMARY KEY,
    mbid UUID,                           -- MusicBrainz release (if available)
    discogs_id INTEGER UNIQUE NOT NULL,  -- Discogs release ID
    spotify_id VARCHAR(50),
    album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    country VARCHAR(100),
    year INTEGER,
    format VARCHAR(100),                 -- "LP", "2xLP", "3xLP", etc.
    is_vinyl BOOLEAN DEFAULT TRUE,
    is_official BOOLEAN DEFAULT TRUE,
    label VARCHAR(500),
    catalog_number VARCHAR(200),
    discogs_rating FLOAT,                -- 0-5 community rating
    discogs_votes INTEGER,               -- number of ratings
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_releases_album ON releases(album_id);
CREATE INDEX idx_releases_discogs ON releases(discogs_id);
CREATE INDEX idx_releases_mbid ON releases(mbid);
CREATE INDEX idx_releases_country ON releases(country);
CREATE INDEX idx_releases_year ON releases(year);
```

**Output**: Schema creado, migraciones versionadas

**⚠️  CRÍTICO - Comportamiento "ALL RELEASES"**:
- La tabla `releases` contendrá **cientos de miles de registros**
- Un album popular puede tener 50-200 releases diferentes
- Ejemplo: "Dark Side of the Moon" → ~150 vinilos diferentes en Discogs
- **NO filtrar por precio** en ingestion
- **NO limitar a "top 20"** en ingestion
- **SÍ guardar todo**: UK 1973, Japan 1976, US reissue 2016, etc.
- La tabla `album_best_price` (materialized view) se encargará de encontrar el más barato

---

#### 1.2. Script: Seed Artists desde Last.fm
**Archivo**: `/scripts/seed_artists.py`

**Inputs**:
- Tags de Last.fm: `indie`, `rock`, `electronic`, `jazz`, `hip-hop`
- O CSV manual con nombres de artistas

**Proceso**:
```python
# Para cada tag (ej. "indie"):
# 1. tag.getTopArtists(tag='indie', limit=100)
# 2. Para cada artista:
#    - artist.getInfo(artist=name, mbid=mbid)
#    - Extraer: name, mbid, image_url
#    - NORMALIZAR nombre: lowercase, remove "the", etc.
#    - Guardar en artists table
#    - Obtener similares (hasta 50)
#    - Guardar en artist_similars
# 3. Rate limiting: 5 req/s

# Total estimado: 
# - 5 tags × 100 artists = 500 artistas únicos
# - 500 × 50 similares = 25,000 relaciones (después de dedup)
```

**Outputs**:
- ~500 artistas en `artists`
- ~10,000-15,000 relaciones en `artist_similars` (muchos duplicados)
- Log con errores/warnings

**Tiempo estimado**: 2-3 horas de ejecución

---

#### 1.3. DEBUG SCRIPT: Last.fm Image URLs
**Archivo**: `/scripts/debug_lastfm_images.py`

**PROBLEMA CRÍTICO**: Las URLs de imágenes de Last.fm no cargan

**Script de debugging**:
```python
import httpx
import json
import os

API_KEY = os.getenv("LASTFM_API_KEY")

# Test con artista conocido
artist = "Arctic Monkeys"

response = httpx.get(
    "https://ws.audioscrobbler.com/2.0/",
    params={
        "method": "artist.getInfo",
        "artist": artist,
        "api_key": API_KEY,
        "format": "json"
    }
)

data = response.json()

# LOG COMPLETO del array de imágenes
print("=== RAW IMAGE ARRAY ===")
print(json.dumps(data['artist']['image'], indent=2))

# Selección de URL
images = data['artist']['image']
# Prioridad: extralarge > large > medium
candidates = [
    img for img in images 
    if img['size'] in ['extralarge', 'mega']
]

if candidates:
    selected_url = candidates[0]['#text']
    print(f"\n✅ Selected URL: {selected_url}")
    
    # Validaciones
    if not selected_url.startswith('https://'):
        print("⚠️  WARNING: Not HTTPS - may fail in browser")
    
    if selected_url == "":
        print("⚠️  WARNING: Empty URL")
    
    # Test de accesibilidad
    try:
        test_response = httpx.get(selected_url, timeout=5)
        print(f"✅ URL accessible: {test_response.status_code}")
        print(f"Content-Type: {test_response.headers.get('content-type')}")
    except Exception as e:
        print(f"❌ URL NOT accessible: {e}")
else:
    print("❌ No suitable image found")

# Recomendación final
print("\n=== RECOMMENDATION ===")
print("Use size 'extralarge' or 'mega'")
print("Always validate HTTPS")
print("Consider downloading and hosting yourself if hotlinking fails")
```

**Posibles causas del problema**:
1. **Campo incorrecto**: usar `size: "medium"` en vez de `"extralarge"`
2. **HTTP vs HTTPS**: mixed content blocked por navegador
3. **Hotlink protection**: Last.fm bloquea acceso directo
4. **URLs vacías**: algunos artistas no tienen imágenes

**Soluciones**:
- Siempre elegir `size: "extralarge"` o `"mega"`
- Verificar que sea HTTPS
- **Considerar**: descargar imagen y hostearla tú mismo (Replit Object Storage)
- Fallback: imagen placeholder genérica

**Implementación recomendada**:
```python
def extract_image_url(images):
    # Buscar extralarge o mega
    for img in reversed(images):
        url = img.get('#text', '')
        if url and url.startswith('https://') and img['size'] in ['extralarge', 'mega']:
            return url
    
    # Fallback: placeholder
    return "https://via.placeholder.com/300x300?text=No+Image"
```

---

#### 1.4. Script: Enrich Albums desde MusicBrainz
**Archivo**: `/scripts/enrich_albums.py`

**Inputs**: Artistas en BD con `mbid` no nulo

**Proceso**:
```python
# Para cada artist con mbid:
# 1. GET /release-group?artist={mbid}&type=Album&limit=100
# 2. Filtrar:
#    - primary-type = "Album"
#    - NO secondary-types (excluir Live, Compilation)
#    - Solo si artist-credit tiene 1 artista (no colaboraciones)
# 3. Para cada release-group:
#    - Extraer: title, mbid, first-release-date
#    - NORMALIZAR título
#    - Buscar Discogs master_id en relations (si existe)
#    - Guardar en albums table
# 4. Rate limiting: 1 req/s

# Total estimado:
# - 500 artists × ~10 albums promedio = 5,000 albums
```

**Outputs**:
- ~5,000 álbumes en `albums`
- ~60% con `discogs_master_id` (vía MusicBrainz relations)

**Tiempo estimado**: 8-10 horas de ejecución

---

#### 1.5. Script: Sync ALL Discogs Releases
**Archivo**: `/scripts/sync_all_releases.py`

**⚠️  CRITICAL BEHAVIOR**: Guardar **TODOS** los vinilos, sin límites

**Inputs**: Álbumes en BD

**Proceso**:
```python
# Para cada album:

# OPCIÓN A: Si tiene discogs_master_id (60% de casos)
if album.discogs_master_id:
    # 1. GET /masters/{id}
    #    - Obtener main_release y rating del master
    
    # 2. GET /masters/{id}/versions
    #    ⚠️  CRITICAL: NO usar limit, paginar TODO
    #    - page=1, per_page=100
    #    - page=2, per_page=100
    #    - ... hasta que pages = 0
    #    - Filtrar solo format=Vinyl en el loop
    
    # 3. Para CADA release en TODAS las páginas:
    #    - Verificar si ya existe en DB (by discogs_id)
    #    - Si NO existe → INSERT
    #    - Si existe → UPDATE rating/votes
    
# OPCIÓN B: Si NO tiene master_id (40% de casos)
else:
    # 1. Search /database/search
    #    params: artist=name, release_title=title, format=Vinyl
    #    ⚠️  CRITICAL: paginar TODO, no limitar resultados
    
    # 2. Para CADA resultado:
    #    - Match confidence score (artist + title)
    #    - Si confidence > 0.7 → INSERT release

# Para cada release guardado:
# - Fields: discogs_id, album_id, title, country, year,
#           format, is_official, label, catalog_number,
#           discogs_rating, discogs_votes

# Rate limiting: 1 req/2s (Discogs)

# Total estimado (escenario real):
# - 5,000 albums × 50 releases promedio = 250,000 releases
# - Discogs API calls:
#   - Con master_id: ~5,000 masters + ~25,000 versions calls = ~30k calls
#   - Sin master_id: ~2,000 searches × 3 pages promedio = ~6k calls
#   - Total: ~36,000 API calls
# - Tiempo: 36k calls × 2s = 72,000s = 20 horas
```

**Outputs**:
- **250,000-500,000 releases** en tabla `releases`
- Log detallado: releases nuevos, duplicados, errores

**Tiempo estimado**: 20-30 horas de ejecución

**Ejemplo de output esperado**:
```
Album: Dark Side of the Moon (album_id=123)
  → Found 147 vinyl releases on Discogs
  → Inserted: 147 (0 duplicates)
  → Countries: UK (23), US (45), Japan (12), Germany (18), ...
  → Years: 1973-2023
  → Formats: LP (98), 2xLP (15), Picture Disc (8), ...
```

---

### FASE 2: Precios (1-2 semanas)

#### 2.1. Schema de Precios
**Migración**: `002_create_prices_tables.py`

```sql
-- prices
CREATE TABLE prices (
    id SERIAL PRIMARY KEY,
    release_id INTEGER REFERENCES releases(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,  -- 'discogs_marketplace', 'ebay', 'amazon'
    country VARCHAR(10),
    currency VARCHAR(10),
    amount DECIMAL(10,2),
    shipping_cost DECIMAL(10,2),
    total_amount DECIMAL(10,2),  -- amount + shipping
    url TEXT,
    condition VARCHAR(50),  -- 'mint', 'near_mint', 'very_good', 'good'
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_prices_release ON prices(release_id);
CREATE INDEX idx_prices_provider ON prices(provider);
CREATE INDEX idx_prices_country ON prices(country);
CREATE INDEX idx_prices_total ON prices(total_amount);
CREATE INDEX idx_prices_fetched ON prices(fetched_at);

-- album_best_price (materialized view)
-- Encuentra el release más barato por (album, country)
-- entre TODOS los releases y TODOS los providers
CREATE MATERIALIZED VIEW album_best_price AS
SELECT DISTINCT ON (a.id, p.country)
    a.id as album_id,
    r.id as release_id,
    r.discogs_id,
    r.title as release_title,
    r.country as release_country,
    r.year as release_year,
    r.format,
    r.label,
    p.provider,
    p.country as shipping_to_country,
    p.currency,
    p.total_amount,
    p.url,
    p.condition,
    NOW() as computed_at
FROM albums a
JOIN releases r ON r.album_id = a.id
JOIN prices p ON p.release_id = r.id
WHERE p.total_amount IS NOT NULL
  AND p.total_amount > 0
ORDER BY a.id, p.country, p.total_amount ASC;

CREATE INDEX idx_best_price_album ON album_best_price(album_id);
CREATE INDEX idx_best_price_country ON album_best_price(shipping_to_country);

-- Refresh automático (opcional, con pg_cron)
-- SELECT cron.schedule('refresh-best-prices', '0 2 * * *', 
--   'REFRESH MATERIALIZED VIEW CONCURRENTLY album_best_price');
```

**Comportamiento**:
- La vista toma **TODOS** los releases del album
- Para cada país de destino, encuentra el precio total más bajo
- Incluye información del release (país de prensado, año, formato)
- Permite comparar: "UK 1973 original por €80" vs "2016 reissue por €25"

---

#### 2.2. Interface de Price Providers
**Archivo**: `/app/modules/prices/providers.py`

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from decimal import Decimal

class PriceQuote:
    release_id: int
    provider: str
    amount: Decimal
    shipping_cost: Decimal
    currency: str
    url: str
    condition: str

class PriceProvider(ABC):
    @abstractmethod
    async def search_prices(
        self, 
        artist: str, 
        album: str, 
        country: str
    ) -> List[PriceQuote]:
        pass

# Implementaciones

class DiscogsMarketplaceProvider(PriceProvider):
    """
    USA Discogs Marketplace API (GRATIS)
    GET /marketplace/search
    """
    async def search_prices(self, artist, album, country):
        # Buscar listings
        # Filtrar por country de shipping
        # Convertir a EUR si es necesario
        return quotes

class EbayProvider(PriceProvider):
    """
    USA eBay Finding API (limitado, requiere partner)
    """
    async def search_prices(self, artist, album, country):
        # TODO: implementar cuando tengas API key
        return []

class AmazonProvider(PriceProvider):
    """
    USA Amazon Product Advertising API (requiere Associates)
    """
    async def search_prices(self, artist, album, country):
        # TODO: implementar
        return []
```

---

#### 2.3. Script: Compute Best Prices
**Archivo**: `/scripts/compute_prices.py`

**Proceso**:
```python
# Para cada release (batch de 100):
# 1. Llamar a providers activos:
#    - DiscogsMarketplaceProvider (único implementado inicialmente)
#    - GET /marketplace/price_suggestions/{discogs_id}
#    - GET /marketplace/listings?release_id={discogs_id}
# 2. Para cada quote:
#    - Verificar si existe (release_id + provider + country)
#    - Si existe y price difiere → UPDATE
#    - Si no existe → INSERT
# 3. Refresh materialized view:
#    REFRESH MATERIALIZED VIEW CONCURRENTLY album_best_price

# Frecuencia: diaria o semanal
# Total releases: ~250k-500k
# Tiempo estimado: depende de rate limits de providers
```

**Output**: Precios actualizados en `prices` y `album_best_price`

**Consideraciones**:
- No todos los releases tendrán precio (pueden estar agotados)
- Priorizar releases con alta demanda (rating alto, años recientes)
- Batch processing para no saturar BD

---

### FASE 3: Profiles + Last.fm Sync (1 semana)

#### 3.1. Schema de Profiles
**Migración**: `003_create_profiles_tables.py`

```sql
-- users (simplificado por ahora)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),  -- futuro
    created_at TIMESTAMP DEFAULT NOW()
);

-- user_profiles
CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    lastfm_username VARCHAR(100),
    spotify_user_id VARCHAR(100),
    primary_source VARCHAR(50) DEFAULT 'lastfm',
    country VARCHAR(10) DEFAULT 'ES',
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- user_seed_artists (artistas añadidos manualmente)
CREATE TABLE user_seed_artists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    artist_id INTEGER REFERENCES artists(id),
    source VARCHAR(50) DEFAULT 'manual',  -- 'manual', 'lastfm_top'
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, artist_id)
);

-- listening_snapshots (cache de datos de Last.fm)
CREATE TABLE listening_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    source VARCHAR(50) DEFAULT 'lastfm',
    period VARCHAR(20),  -- 'overall', '12month', '6month'
    payload_hash VARCHAR(64),  -- MD5 del JSON
    payload JSONB,  -- datos crudos de Last.fm
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snapshots_user ON listening_snapshots(user_id);
```

---

#### 3.2. Script: Sync User Listening Data
**Archivo**: `/scripts/sync_user_lastfm.py`

```python
# Input: username de Last.fm
# 1. user.getTopAlbums(period='overall', limit=100)
# 2. user.getTopAlbums(period='12month', limit=100)
# 3. user.getTopAlbums(period='6month', limit=100)
# 4. Para cada álbum:
#    - Match con artists/albums en catalog
#    - Si no existe artista → añadirlo
#    - Si no existe album → añadirlo
# 5. Guardar snapshot con hash
# 6. Si hash != último snapshot → datos nuevos
```

---

### FASE 4: Recommender Engine (2 semanas)

#### 4.1. Schema de Recomendaciones
**Migración**: `004_create_recommender_tables.py`

```sql
-- recommendation_sets
CREATE TABLE recommendation_sets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    source_snapshot_hash VARCHAR(64),  -- link a listening_snapshot
    ttl_seconds INTEGER DEFAULT 86400,  -- 24h
    generated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- recommendation_items
-- Note: Recommendations point to ALBUMS, not specific releases
-- The user can then explore ALL releases of that album and choose
CREATE TABLE recommendation_items (
    id SERIAL PRIMARY KEY,
    recommendation_set_id INTEGER REFERENCES recommendation_sets(id),
    position INTEGER NOT NULL,
    album_id INTEGER REFERENCES albums(id),  -- Points to album, not release
    score FLOAT NOT NULL,
    explanation TEXT,  -- "Top album in your last 6 months"
    best_release_id INTEGER REFERENCES releases(id),  -- Suggested release (cheapest)
    is_locked BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_rec_items_set ON recommendation_items(recommendation_set_id);
CREATE INDEX idx_rec_items_album ON recommendation_items(album_id);

-- locked_recommendations (user saved an album to explore)
CREATE TABLE locked_recommendations (
    user_id INTEGER REFERENCES users(id),
    album_id INTEGER REFERENCES albums(id),
    locked_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, album_id)
);

-- dismissed_recommendations (user not interested in this album)
CREATE TABLE dismissed_recommendations (
    user_id INTEGER REFERENCES users(id),
    album_id INTEGER REFERENCES albums(id),
    dismissed_at TIMESTAMP DEFAULT NOW(),
    reason VARCHAR(255),
    PRIMARY KEY (user_id, album_id)
);

-- user_discogs_collections (when user connects Discogs OAuth)
CREATE TABLE user_discogs_collections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    discogs_user_id INTEGER NOT NULL,
    release_id INTEGER REFERENCES releases(id),
    folder VARCHAR(100),  -- 'collection', 'wantlist'
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, release_id, folder)
);

CREATE INDEX idx_discogs_collection_user ON user_discogs_collections(user_id);
```

---

#### 4.2. Scoring Logic
**Archivo**: `/app/modules/recommender/scorer.py`

**Algoritmo simplificado (v1)**:
```python
def score_album(album, user_data):
    score = 0
    
    # 1. Frecuencia de escucha (50 puntos máx)
    playcount = user_data.album_playcounts.get(album.id, 0)
    score += min(playcount / 10, 50)
    
    # 2. Artista en seeds (30 puntos)
    if album.artist_id in user_data.seed_artist_ids:
        score += 30
    
    # 3. Rating de Discogs (10 puntos)
    if album.avg_vinyl_rating:
        score += album.avg_vinyl_rating * 2  # 0-5 → 0-10
    
    # 4. Disponibilidad/precio (10 puntos)
    if album.best_price and album.best_price.total_amount < 30:
        score += 10
    elif album.best_price and album.best_price.total_amount < 50:
        score += 5
    
    return score

# Generar top 20
candidates = []
for album in eligible_albums:
    candidates.append({
        'album': album,
        'score': score_album(album, user_data),
        'explanation': build_explanation(album, user_data)
    })

candidates.sort(key=lambda x: x['score'], reverse=True)
top_20 = candidates[:20]
```

**Explicaciones**:
- "You've played this 127 times in the last year"
- "Top artist from your seeds"
- "Highly rated on Discogs (4.5★)"
- "Great price available (€22)"

---

#### 4.3. API Endpoint
**Archivo**: `/app/modules/recommender/routes.py`

```python
@router.get("/recs")
async def get_recommendations(user_id: int, db: Session):
    # 1. Buscar último RecommendationSet
    latest_set = db.query(RecommendationSet)\
        .filter_by(user_id=user_id)\
        .order_by(RecommendationSet.generated_at.desc())\
        .first()
    
    # 2. Verificar si está vigente
    if latest_set and not is_expired(latest_set):
        # Devolver cached
        return build_response(latest_set)
    
    # 3. Si expiró → recomputar
    new_set = await recompute_recommendations(user_id, db)
    return build_response(new_set)

@router.post("/recs/refresh")
async def force_refresh(user_id: int, db: Session):
    # Forzar recálculo (para testing)
    new_set = await recompute_recommendations(user_id, db)
    return build_response(new_set)
```

---

### FASE 5: Frontend Básico (1 semana)

#### UI Mínima
**Pantallas**:
1. **Artist Search**
   - Typeahead search
   - Botón "Add to seeds"
   - Lista de artistas seleccionados

2. **Recommendations**
   - Grid de vinyl cards (portada, título, artista, precio)
   - Score breakdown
   - Botones: Lock, Dismiss, Add to Wantlist

3. **Wantlist**
   - Lista simple de vinilos guardados

**Stack sugerido**:
- Frontend: React + Vite (reusar lo que ya tienes)
- Backend: FastAPI
- Comunicación: REST JSON

---

## ⚠️ PROBLEMAS CRÍTICOS Y SOLUCIONES

### 🔴 Problema 1: Escalabilidad de Ingestion

**Issue**: Con el requisito de guardar **TODOS** los releases:
- 10k artistas × 50 similares × 10 álbumes × **50 releases promedio** = **250M releases**

**⚠️  Actualizado con "ALL releases"**:
- Discogs API calls para 5,000 albums:
  - GET /masters/{id}: ~5,000 calls
  - GET /masters/{id}/versions (paginado): ~25,000 calls (5 páginas promedio)
  - Total: **~30,000 API calls** para albums con master_id
  - Tiempo: 30k × 2s = **16.6 horas** solo para Discogs

**Impacto REAL con 500 artistas iniciales**:
- Last.fm: 500 artists + similares → ~2,500 calls → **8 minutos**
- MusicBrainz: 500 artists × albums → ~5,000 calls → **1.4 horas**
- Discogs: 5,000 albums × ALL releases → ~30k calls → **16.6 horas**
- **Total: ~18 horas** para 500 artistas completos

**Soluciones**:
1. **Ingestion incremental**: 50-100 artistas/día, no 10k de golpe
2. **Priorización**: artistas más populares primero (Last.fm playcount)
3. **Deduplicación agresiva**: muchos artistas comparten álbumes/releases
4. **Rate limiting inteligente**:
   - Discogs: 1 req/2s (safe) vs 60/min (límite oficial)
   - MusicBrainz: 1 req/s estricto
   - Last.fm: 5 req/s
5. **Workers asíncronos**: Celery para background jobs largos
6. **Caching inteligente**: 
   - No refetch releases si `updated_at` < 30 días
   - Skip albums sin discogs_master_id en primera pasada
7. **Batch processing**: procesar en lotes de 10-20 albums
8. **Progress tracking**: logs detallados para monitorear avance

**Recomendación**: 
- **Fase 0**: 10 artistas para validación técnica (2-3 horas)
- **Fase 1**: 100 artistas para validación de datos (~2 días)
- **Fase 2**: 500-1000 artistas para MVP (~1-2 semanas)
- **Fase 3**: 10k artistas completo (incremental, background)

---

### 🔴 Problema 2: Imágenes de Last.fm No Cargan

**Síntomas**:
- URLs en respuesta de API pero no se muestran en UI
- Mixed content warnings
- 404 o timeout

**Causas probables**:
1. **Campo incorrecto**: usar `size: "small"` en vez de `"extralarge"`
2. **HTTP vs HTTPS**: navegador bloquea HTTP
3. **Hotlink protection**: Last.fm detecta origen
4. **URLs vacías**: algunos artistas sin imagen

**Debug**:
```python
# Script de debugging (ver Fase 1.3)
response = lastfm.artist.getInfo("Arctic Monkeys")
images = response['artist']['image']

# Imprimir array completo
print(json.dumps(images, indent=2))

# Output esperado:
# [
#   {"#text": "", "size": "small"},
#   {"#text": "https://...", "size": "medium"},
#   {"#text": "https://...", "size": "large"},
#   {"#text": "https://...", "size": "extralarge"}
# ]
```

**Soluciones**:
1. **Siempre elegir** `size: "extralarge"` o `"mega"`
2. **Validar HTTPS**: `if not url.startswith('https://'): skip`
3. **Proxy/cache**: descargar imagen y hostear en Replit Object Storage
4. **Fallback**: imagen placeholder si falla

**Implementación recomendada**:
```python
def extract_image_url(images):
    # Buscar extralarge o mega
    for img in reversed(images):
        url = img.get('#text', '')
        if url and url.startswith('https://') and img['size'] in ['extralarge', 'mega']:
            return url
    
    # Fallback: placeholder
    return "https://via.placeholder.com/300x300?text=No+Image"
```

---

### 🔴 Problema 3: Matching Entre APIs

**Issue**: Mismo artista tiene nombres diferentes

**Ejemplos**:
- Last.fm: `"Arctic Monkeys"`
- MusicBrainz: `"The Arctic Monkeys"`
- Discogs: `"Arctic Monkeys, The"`

**Consecuencias**:
- Duplicados en BD
- Álbumes sin vincular
- Pérdida de datos

**Solución: Normalización agresiva**:
```python
import re
import unicodedata

def normalize_name(name: str) -> str:
    # 1. Lowercase
    name = name.lower()
    
    # 2. Remove accents
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    # 3. Remove articles (the, a, an)
    name = re.sub(r'\b(the|a|an)\b', '', name)
    
    # 4. Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    
    # 5. Collapse spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

# Examples:
# "The Arctic Monkeys" → "arctic monkeys"
# "Guns N' Roses" → "guns n roses"
# "Beyoncé" → "beyonce"
```

**Matching strategy**:
1. **Exacto por MBID** (cuando existe)
2. **Exacto por normalized_name**
3. **Fuzzy** con Levenshtein distance < 3
4. **Manual review** para casos dudosos

---

### 🔴 Problema 4: Datos Stale (Catálogo Desactualizado)

**Issue**: Artista saca álbum nuevo → no está en tu BD

**Impacto**: Recomendaciones incompletas para usuarios activos

**Soluciones**:
1. **Refresh jobs periódicos**:
   - Semanal: artistas con actividad reciente
   - Mensual: catálogo completo
2. **Trigger manual**: endpoint `/catalog/refresh/{artist_id}`
3. **Priorización**:
   - Artistas en seeds de usuarios activos
   - Artistas con alta popularidad
4. **TTL en registros**: campo `updated_at` + lógica de "refresh if older than 30 days"

**Implementación**:
```python
# Job semanal
@celery.task
def refresh_active_artists():
    # Artistas en seeds de usuarios activos (last 7 days)
    active_artist_ids = db.query(
        UserSeedArtist.artist_id
    ).join(User).filter(
        User.last_login > datetime.now() - timedelta(days=7)
    ).distinct()
    
    for artist_id in active_artist_ids:
        refresh_artist_albums(artist_id)
```

---

### 🔴 Problema 5: Costes de Price Providers

**Issue**: APIs de precios son caras o limitadas

**Proveedores**:
1. **eBay Finding API**:
   - ❌ Requiere eBay Partner Network (aprobación)
   - ❌ Límites de calls estrictos
   - ❌ Scraping = violación de ToS

2. **Amazon Product Advertising API**:
   - ❌ Requiere Amazon Associates (aprobación + ventas)
   - ❌ Solo funciona si generas ventas
   - ❌ Límites muy bajos

3. **Discogs Marketplace**:
   - ✅ API gratuita
   - ✅ Datos reales de vinilos
   - ⚠️  Rate limited (60 req/min)
   - ⚠️  Solo cubre marketplace de Discogs

**Recomendación**:
1. **Empezar SOLO con Discogs Marketplace** (gratis, legal, datos buenos)
2. **Futuro**: partnerships con tiendas indie (APIs privadas)
3. **Evitar**: web scraping (frágil, ilegal)

**Implementación prioritaria**:
```python
class DiscogsMarketplaceProvider:
    async def search_prices(self, vinyl_edition_id):
        # GET /marketplace/price_suggestions/{release_id}
        # GET /marketplace/listings (filtrar por release_id)
        # Ordenar por precio total (price + shipping)
        # Filtrar por país de envío
        return price_quotes
```

---

### 🟡 Problema 6: Complejidad del Scoring

**Issue**: Fórmula con muchas variables es difícil de balancear

**Riesgos**:
- Recomendaciones irrelevantes
- Usuario pierde confianza
- Difícil de debuggear

**Approach**:
1. **Empezar SIMPLE**: solo playcount
2. **Iterar**: añadir una variable, medir impacto
3. **A/B testing**: probar con usuarios reales
4. **Logging**: guardar score breakdown para debugging

**Versiones**:
- **v1**: Solo playcount de Last.fm
- **v2**: + artistas en seeds
- **v3**: + rating de Discogs
- **v4**: + precio/disponibilidad

---

### 🟡 Problema 7: Lock/Dismiss Vacía la Lista

**Issue**: Usuario dismissea 15 de 20 → solo quedan 5

**Solución**:
1. **Backfill automático**: si quedan <10, generar más candidatos
2. **Límite de dismissals**: máximo 100 en 30 días
3. **Reset button**: "Clear all dismissals"
4. **Sugerencia proactiva**: "You've dismissed many, want to reset?"

---

### 🟡 Problema 8: Dos Arquitecturas en Paralelo

**Issue**: Microservicios actuales + monolito nuevo = duplicación

**Opciones**:
1. **Migración completa**: deprecar microservicios
2. **Coexistencia**:
   - Microservicios = "real-time engine"
   - Monolito = "catalog backend"
3. **Híbrido**: monolito como único backend, exponer APIs

**Recomendación**: Decidir ANTES de empezar Fase 1

---

## 🎯 ROADMAP RECOMENDADO

### Semana 1-2: Validación de Concepto
- [ ] Setup BD + estructura
- [ ] Debug script de imágenes Last.fm (**PRIORITARIO**)
- [ ] Seed 50 artistas de prueba
- [ ] Validar matching entre APIs

### Semana 3-4: Catálogo Base
- [ ] Seed 500 artistas
- [ ] Enrich con MusicBrainz
- [ ] Map con Discogs
- [ ] Validar calidad de datos

### Semana 5-6: Precios
- [ ] Implementar Discogs Marketplace provider
- [ ] Compute best prices
- [ ] UI simple para ver precios

### Semana 7-8: Recommender
- [ ] Scoring v1 (solo playcount)
- [ ] Endpoint `/recs`
- [ ] Test con usuario real

### Semana 9-10: Polish
- [ ] Lock/dismiss
- [ ] Wantlist
- [ ] Frontend completo

---

## 📊 MÉTRICAS DE ÉXITO

### Técnicas
- ✅ 95% de artistas tienen `mbid`
- ✅ 80% de álbumes tienen vinyl edition
- ✅ 50% de vinilos tienen precio
- ✅ Matching accuracy >90%
- ✅ Response time <500ms para `/recs`

### Negocio
- ✅ Usuario encuentra al menos 5 vinilos relevantes
- ✅ Precio promedio <50€
- ✅ Lock rate >20% (usuarios guardan recomendaciones)
- ✅ Dismiss rate <50% (no todo es malo)

---

## 📝 DECISIONES PENDIENTES

1. **¿Migrar microservicios actuales o coexistencia?**
   - Impacta en deployment y arquitectura

2. **¿Cuántos artistas iniciales?**
   - 500 (rápido) vs 5000 (completo) vs 10k (ambicioso)

3. **¿Auth real desde inicio?**
   - Email/password vs OAuth vs hardcoded user

4. **¿Workers asíncronos?**
   - Celery/RQ vs simple cron jobs

5. **¿Frontend separado?**
   - Monorepo vs repos separados

---

## 🚀 PRÓXIMOS PASOS INMEDIATOS

### Paso 1: Validación del Plan (hoy)
- [ ] Revisar este documento completo
- [ ] Confirmar requisitos críticos:
  - ✅ Guardar **TODOS** los releases (sin límites)
  - ✅ Cache-miss behavior obligatorio
  - ✅ Combinación de fuentes (seeds + Discogs + Last.fm)
- [ ] Decidir arquitectura: ¿migrar microservicios o coexistir?
- [ ] Decidir scope inicial: 10 artistas (validación) vs 100 (MVP)

### Paso 2: Setup Técnico (Día 1-2)
- [ ] Crear PostgreSQL database en Replit
- [ ] Configurar SQLAlchemy + Alembic
- [ ] Crear estructura de carpetas (`/app/core`, `/app/modules`, `/scripts`)
- [ ] Variables de entorno: `DATABASE_URL`, API keys
- [ ] **CRÍTICO**: Ejecutar `/scripts/debug_lastfm_images.py` para resolver bug de imágenes

### Paso 3: Primer Script (Día 3)
- [ ] Implementar `cache_helpers.py` con `get_or_create_artist`
- [ ] Implementar `/scripts/seed_artists.py` (versión simplificada)
- [ ] Seed **10 artistas** de prueba con:
  - Artistas + similares (Last.fm)
  - Albums (MusicBrainz)
  - **ALL releases** (Discogs)
- [ ] Validar que se guardan TODOS los releases sin límites
- [ ] Tiempo estimado: 2-3 horas de ejecución

### Paso 4: Validación de Datos (Día 4)
- [ ] Inspeccionar BD manualmente:
  - ¿Cuántos releases por album?
  - ¿Imágenes de Last.fm cargan?
  - ¿Matching artist/album funciona?
- [ ] Ajustar scripts según problemas encontrados
- [ ] Documentar casos edge encontrados

### Paso 5: Escalar (Día 5+)
- [ ] Si validación exitosa → seed 100-500 artistas
- [ ] Implementar prices (Discogs Marketplace)
- [ ] Implementar recommender básico
- [ ] Frontend simple para explorar datos

---

## 📌 RESUMEN EJECUTIVO

**Requisitos no negociables**:
1. **ALL releases**: Guardar TODOS los vinilos de Discogs, sin límites ni filtros
2. **Cache-miss**: Siempre query DB first, fetch API on miss, insert, return
3. **Fuentes múltiples**: Seeds + Discogs collection + Last.fm/Spotify listening
4. **Normalización agresiva**: Matching entre APIs para evitar duplicados

**Números reales** (500 artistas):
- ~500 artists
- ~5,000 albums
- ~**250,000 releases** (TODOS los vinilos)
- ~18 horas de ingestion total

**Inicio recomendado**:
- 10 artistas para validación técnica (2-3 horas)
- Debug de Last.fm images **PRIORITARIO**
- Implementar cache-miss helpers como base

---

**Fecha de actualización**: 16 de Noviembre de 2025  
**Versión del documento**: 2.0  
**Cambios principales**:
- ✅ Enfatizado requisito "ALL releases" (no límites)
- ✅ Añadida sección explícita de cache-miss behavior
- ✅ Actualizado schema: `vinyl_editions` → `releases`
- ✅ Añadidas fuentes de recomendación (seeds + Discogs + listening)
- ✅ Actualizados números de escalabilidad con releases completos
- ✅ Añadido módulo `cache_helpers.py` como core del sistema
