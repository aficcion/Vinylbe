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
**PostgreSQL como "caché inteligente"** poblado por ingestion jobs:
- ✅ ~10k artistas precargados con álbumes y vinilos
- ✅ Precios actualizados periódicamente
- ✅ APIs externas solo para:
  - Sincronizar escuchas del usuario
  - Refresh periódico de catálogo
  - Actualización de precios
- ✅ Recomendaciones instantáneas (consulta a BD)

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
│  vinyl_editions (150k rows)                             │
│  prices (500k rows)                                     │
│  album_best_price (materialized view)                   │
│  user_profiles                                          │
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
      /catalog/
        models.py        # Artist, Album, VinylEdition
        repository.py    # Query functions
        service.py       # Business logic
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
    seed_artists.py
    enrich_albums.py
    map_discogs.py
    compute_prices.py
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
    source VARCHAR(50),  -- 'lastfm_tag', 'manual', 'similar'
    popularity_score FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_artists_normalized ON artists(normalized_name);
CREATE INDEX idx_artists_mbid ON artists(mbid);
CREATE INDEX idx_artists_discogs ON artists(discogs_id);

-- artist_similars
CREATE TABLE artist_similars (
    artist_id INTEGER REFERENCES artists(id),
    similar_artist_id INTEGER REFERENCES artists(id),
    score FLOAT NOT NULL,  -- 0-1 from Last.fm
    source VARCHAR(50) DEFAULT 'lastfm',
    PRIMARY KEY (artist_id, similar_artist_id)
);

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

-- vinyl_editions
CREATE TABLE vinyl_editions (
    id SERIAL PRIMARY KEY,
    mbid UUID,
    discogs_release_id INTEGER UNIQUE,
    album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
    title VARCHAR(500),
    country VARCHAR(100),
    year INTEGER,
    format VARCHAR(100),  -- "LP", "2xLP", etc.
    is_vinyl BOOLEAN DEFAULT TRUE,
    is_official BOOLEAN DEFAULT TRUE,
    label VARCHAR(500),
    catalog_number VARCHAR(200),
    discogs_rating FLOAT,  -- 0-5
    discogs_votes INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_vinyl_album ON vinyl_editions(album_id);
CREATE INDEX idx_vinyl_discogs ON vinyl_editions(discogs_release_id);
```

**Output**: Schema creado, migraciones versionadas

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

#### 1.5. Script: Map Albums a Discogs Vinyl
**Archivo**: `/scripts/map_discogs.py`

**Inputs**: Álbumes en BD

**Proceso**:
```python
# Para cada album:

# OPCIÓN A: Si tiene discogs_master_id (60% de casos)
if album.discogs_master_id:
    # 1. GET /masters/{id}
    # 2. Obtener main_release y rating del master
    # 3. GET /masters/{id}/versions (limit=20, filter vinyl)
    # 4. Priorizar: official > unofficial, Europe/US > otros
    
# OPCIÓN B: Si NO tiene master_id (40% de casos)
else:
    # 1. Search /database/search
    #    params: artist=name, release_title=title, format=Vinyl
    # 2. Score results (exact match > partial)
    # 3. Seleccionar top 10-20 releases

# Para cada release encontrado:
# - Guardar en vinyl_editions
# - Fields: discogs_release_id, country, year, format, 
#           is_official, label, rating

# Rate limiting: 1 req/2s (Discogs)

# Total estimado:
# - 5,000 albums × (1 master + 20 versions) = ~100k requests
# - Pero muchos artists comparten masters → real ~30k requests
```

**Outputs**:
- ~15,000-20,000 vinyl editions en `vinyl_editions`

**Tiempo estimado**: 16-20 horas de ejecución

---

### FASE 2: Precios (1-2 semanas)

#### 2.1. Schema de Precios
**Migración**: `002_create_prices_tables.py`

```sql
-- prices
CREATE TABLE prices (
    id SERIAL PRIMARY KEY,
    vinyl_edition_id INTEGER REFERENCES vinyl_editions(id),
    provider VARCHAR(50) NOT NULL,  -- 'discogs_marketplace', 'ebay', 'amazon'
    country VARCHAR(10),
    currency VARCHAR(10),
    amount DECIMAL(10,2),
    shipping_cost DECIMAL(10,2),
    total_amount DECIMAL(10,2),  -- amount + shipping
    url TEXT,
    condition VARCHAR(50),  -- 'mint', 'near_mint', 'very_good'
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_prices_vinyl ON prices(vinyl_edition_id);
CREATE INDEX idx_prices_provider ON prices(provider);
CREATE INDEX idx_prices_country ON prices(country);

-- album_best_price (materialized view)
CREATE MATERIALIZED VIEW album_best_price AS
SELECT DISTINCT ON (a.id, p.country)
    a.id as album_id,
    ve.id as vinyl_edition_id,
    p.provider,
    p.country,
    p.currency,
    p.total_amount,
    p.url,
    p.condition,
    NOW() as computed_at
FROM albums a
JOIN vinyl_editions ve ON ve.album_id = a.id
JOIN prices p ON p.vinyl_edition_id = ve.id
WHERE p.total_amount IS NOT NULL
ORDER BY a.id, p.country, p.total_amount ASC;

CREATE INDEX idx_best_price_album ON album_best_price(album_id);
```

---

#### 2.2. Interface de Price Providers
**Archivo**: `/app/modules/prices/providers.py`

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from decimal import Decimal

class PriceQuote:
    vinyl_edition_id: int
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
# Para cada vinyl_edition (batch de 100):
# 1. Llamar a providers activos:
#    - DiscogsMarketplaceProvider (único implementado)
# 2. Para cada quote:
#    - Guardar en prices table
# 3. Refresh materialized view:
#    REFRESH MATERIALIZED VIEW CONCURRENTLY album_best_price

# Frecuencia: diaria o semanal
```

**Output**: Precios actualizados en `album_best_price`

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
CREATE TABLE recommendation_items (
    id SERIAL PRIMARY KEY,
    recommendation_set_id INTEGER REFERENCES recommendation_sets(id),
    position INTEGER NOT NULL,
    vinyl_edition_id INTEGER REFERENCES vinyl_editions(id),
    score FLOAT NOT NULL,
    explanation TEXT,  -- "Top album in your last 6 months"
    is_locked BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_rec_items_set ON recommendation_items(recommendation_set_id);

-- locked_recommendations
CREATE TABLE locked_recommendations (
    user_id INTEGER REFERENCES users(id),
    vinyl_edition_id INTEGER REFERENCES vinyl_editions(id),
    locked_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, vinyl_edition_id)
);

-- dismissed_recommendations
CREATE TABLE dismissed_recommendations (
    user_id INTEGER REFERENCES users(id),
    vinyl_edition_id INTEGER REFERENCES vinyl_editions(id),
    dismissed_at TIMESTAMP DEFAULT NOW(),
    reason VARCHAR(255),
    PRIMARY KEY (user_id, vinyl_edition_id)
);
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

**Issue**: 10k artistas × 50 similares × 10 álbumes × 20 vinilos = **100M operaciones**

**Impacto**:
- Last.fm: 5 req/s → **~555 horas** (23 días)
- MusicBrainz: 1 req/s → **~2777 horas** (115 días)
- Discogs: 60 req/min → **~27,000 horas** (!!)

**Soluciones**:
1. **Ingestion incremental**: 100 artistas/día, no 10k de golpe
2. **Priorización**: artistas más populares primero
3. **Deduplicación agresiva**: muchos artistas comparten álbumes
4. **Límites razonables**:
   - Máximo 50 similares por artista
   - Máximo 20 álbumes por artista
   - Máximo 20 vinyl editions por álbum
5. **Workers asíncronos**: Celery o Python asyncio
6. **Caching inteligente**: no refetch datos viejos (<30 días)

**Recomendación**: Empezar con **100 artistas** para validar todo el flujo

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

1. **Leer y validar este plan**
2. **Decidir**: ¿empezamos con PoC (50 artistas) o full (500)?
3. **Setup inicial**: PostgreSQL + estructura de carpetas
4. **Debug de imágenes**: resolver problema de Last.fm
5. **Primer script**: seed 10 artistas de prueba

---

**Fecha de actualización**: Noviembre 2025  
**Versión del documento**: 1.0  
**Autor**: Planificación para Vinilogy v2.0
