# Sistema de Recomendación de Vinilos - Arquitectura de Microservicios

## Descripción General
Sistema completo de recomendación de vinilos basado en tus gustos musicales de Spotify, con información del marketplace de Discogs. Implementado con arquitectura de microservicios escalable.

## Arquitectura

### Microservicios

#### 1. **Spotify Service** (puerto 3000)
- Gestión de OAuth y tokens de Spotify
- Obtención de 300 top tracks en 3 períodos temporales (18 peticiones paginadas)
- Obtención de 300 top artists (6 peticiones paginadas)
- Auto-refresh de tokens cuando expiran
- **Archivos**: `services/spotify/`

#### 2. **Discogs Service** (puerto 3001)
- Búsqueda de releases en el catálogo de Discogs
- Estadísticas del marketplace (precios, cantidad disponible)
- Conversión automática de precios a EUR con tasas actuales (Nov 2025)
- Rate limiting (2s entre peticiones para evitar 429s)
- Generación de links de venta
- **Archivos**: `services/discogs/`

#### 3. **Recommender Service** (puerto 3002)
- Motor de puntuación de tracks (con boost por período: short=3x, medium=2x, long=1x)
- Motor de puntuación de artistas
- Agregación de álbumes por tracks
- Filtrado de álbumes (mínimo 5 tracks)
- Boost adicional si el artista está en favoritos (5x)
- **Archivos**: `services/recommender/`

#### 4. **API Gateway** (puerto 5000)
- Punto de entrada único para clientes
- Orquestación del flujo completo de recomendación
- Proxying de autenticación de Spotify
- Health checks de todos los servicios
- **Archivos**: `gateway/`

### Flujo de Recomendación

#### Fase 1: Recomendaciones de Spotify (Automática)

```
1. Usuario se autentica en Spotify → Gateway → Spotify Service
2. Gateway solicita 300 tracks en 3 períodos → Spotify Service (18 peticiones)
3. Gateway solicita 300 artistas top → Spotify Service (6 peticiones)
4. Gateway envía tracks para puntuación → Recommender Service
5. Gateway envía artistas para puntuación → Recommender Service
6. Gateway solicita agregación de álbumes → Recommender Service
   - Filtra álbumes con < 5 tracks
   - Aplica boosts por período y artistas favoritos
7. Retorna lista de álbumes con scoring (SIN datos de Discogs)
```

#### Fase 2: Búsqueda en Discogs (Manual/Interactiva)

```
1. Usuario ve lista de álbumes recomendados con botón "Search Discogs"
2. Al hacer click → GET /discogs/search/{artist}/{album}
   - Gateway busca releases en Discogs Service
   - Filtra solo vinilos (LP format)
   - Ordena por preferencia: originales primero, luego reissues
   - Retorna lista de releases SIN precios
   - Request Log muestra: timestamp, endpoint, tiempo, # releases encontrados
3. UI muestra lista de releases (título, año, formato, label)
4. Por cada release, botón "Get Price"
5. Al hacer click → GET /discogs/stats/{release_id}
   - Gateway obtiene stats del marketplace → Discogs Service
   - Convierte precio a EUR
   - Request Log muestra: timestamp, endpoint, tiempo, precio/unidades
6. UI muestra precio, unidades disponibles, link de compra
```

**Ventajas del Flujo Interactivo:**
- ✅ Control total: Usuario decide cuándo consumir cuota de Discogs
- ✅ Transparencia: Cada petición HTTP visible en Request Log
- ✅ Exploración: Comparar múltiples releases manualmente
- ✅ Debug: Visibilidad completa de qué se pide y qué responde

## Endpoints Principales (Gateway)

### Autenticación
- **GET** `/auth/login` - Inicia flujo OAuth de Spotify
- **GET** `/auth/callback?code={code}` - Callback OAuth

### Recomendación
- **GET** `/recommend-vinyl` - Obtiene recomendaciones de Spotify (sin Discogs)

### Discogs Interactivo (NUEVO)
- **GET** `/discogs/search/{artist}/{album}` - Busca releases de vinilo en Discogs
  - Retorna lista de releases con: id, title, year, format, label
  - NO incluye precios (se obtienen por separado)
- **GET** `/discogs/stats/{release_id}` - Obtiene stats de marketplace para un release
  - Retorna: precio EUR, unidades disponibles, link de compra

### Monitoreo
- **GET** `/health` - Estado de todos los servicios
- **GET** `/` - Estado del gateway

## Modelos Compartidos

En `libs/shared/`:
- `Track`, `Artist`, `Album` - Modelos de Spotify
- `DiscogsRelease`, `DiscogsStats` - Modelos de Discogs
- `ScoredTrack`, `ScoredArtist` - Modelos con puntuación
- `AlbumRecommendation` - Recomendación completa con Discogs
- `ServiceHealth`, `LogEvent` - Monitoreo y logging

## Configuración

### Variables de Entorno Requeridas

```bash
# Spotify OAuth
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_secret
SPOTIFY_REDIRECT_URI=https://tu-repl.repl.co/auth/callback

# Discogs API
DISCOGS_KEY=tu_key
DISCOGS_SECRET=tu_secret

# Service Discovery (opcional, defaults a localhost)
SPOTIFY_SERVICE_URL=http://localhost:3000
DISCOGS_SERVICE_URL=http://localhost:3001
RECOMMENDER_SERVICE_URL=http://localhost:3002
```

Ver `.env.example` para referencia completa.

## Ejecución

```bash
python start_services.py
```

Esto levanta todos los servicios en paralelo:
- Spotify Service → :3000
- Discogs Service → :3001
- Recommender Service → :3002
- API Gateway → :5000 (punto de entrada)

## Stack Tecnológico

- **Backend**: FastAPI + Python 3.11
- **HTTP Client**: httpx (asíncrono)
- **Proceso Manager**: subprocess (Python)
- **Comunicación**: HTTP asíncrono entre servicios
- **Logging**: Structured logging con timestamps

## Características Implementadas

### Backend
✅ Arquitectura de 4 microservicios independientes
✅ Obtención de 300 tracks y 300 artistas de Spotify
✅ Sistema de puntuación con boosts por período temporal
✅ Boost adicional para artistas favoritos (5x)
✅ Filtrado de álbumes (mínimo 5 tracks)
✅ Integración con Discogs para datos de vinilos
✅ **Búsqueda interactiva de Discogs controlada por usuario**
✅ **Endpoints separados**: /search y /stats para control granular
✅ **Permite todos los formatos** (Box Sets, Compilaciones, etc.) - ordena por preferencia
✅ Conversión automática de precios a EUR con tasas actuales (Nov 2025)
✅ Health checks en todos los servicios
✅ Logging detallado en cada paso
✅ Gestión de errores robusta

### Frontend
✅ **UI completamente interactiva** para búsqueda de Discogs
✅ **Request Log en tiempo real** - visibilidad de cada petición HTTP
✅ **Búsqueda controlada por usuario** - decide cuándo buscar en Discogs
✅ **Exploración de releases** - ve todos los releases antes de consultar precio
✅ **Breakdown detallado de scoring** por álbum (base score + periodo + boost)
✅ **Tracking de tiempo** de procesamiento Spotify
✅ Service status monitoring visual

## Frontend Interactivo (Estado Actual)

✅ UI completa implementada en `gateway/static/`:

### Secciones Principales
1. **Service Status**: Monitoreo visual del estado de cada microservicio
2. **Test Panel**: Botones para login y obtener recomendaciones
3. **📡 Discogs Request Log** (NUEVO): Panel que muestra todas las peticiones a Discogs
   - Timestamp de cada petición
   - Método y endpoint llamado
   - Parámetros (artist/album o release_id)
   - Status code (200/500)
   - Tiempo de respuesta en segundos
   - Resumen de datos (# releases, precio/unidades)
4. **Progress Tracker**: Visualización de pasos de recomendación Spotify
5. **Results View**: Cards con álbumes recomendados

### Cards de Álbumes (Interactivas)
- Imagen, nombre, artista, score
- **Score Breakdown**: Desglose detallado de puntuación
  - Base score (suma de tracks)
  - Boost de artista favorito (si aplica)
  - Distribución por período temporal (short/medium/long term)
- **🔍 Search Discogs** (botón): Busca releases en Discogs
  - Al hacer click: llama `/discogs/search/{artist}/{album}`
  - Muestra lista de releases encontrados
- **Lista de Releases** (expandible):
  - Por cada release: título, año, formato, label
  - **Get Price** (botón): Obtiene precio del marketplace
    - Al hacer click: llama `/discogs/stats/{release_id}`
    - Muestra precio EUR, unidades, link "Buy on Discogs"

### Request Log (MEJORADO ✨)
- Registra TODAS las peticiones a Discogs en tiempo real
- **Muestra URLs completas de la API de Discogs** con credenciales ofuscadas
- Formato multinivel:
  ```
  [HH:MM:SS] GET /discogs/search/Artist/Album → 200 (1.2s) → 5 releases
    → https://api.discogs.com/database/search
      &artist=Artist+Name
      &release_title=Album+Name
      &format=Vinyl
      &type=release
      &key=[HIDDEN]
      &secret=[HIDDEN]
  ```
- **Ventajas del nuevo formato:**
  - ✅ Debugging completo: Ve exactamente qué parámetros se enviaron
  - ✅ Seguridad: Credenciales automáticamente ofuscadas como `[HIDDEN]`
  - ✅ Transparencia total: Cada query parameter visible
  - ✅ Copiar/pegar: Puedes recrear la petición manualmente si es necesario
- Scroll automático para ver últimas peticiones
- Persistente durante la sesión

⚠️ Limitaciones actuales:
- Progress tracking de Spotify es simulado (no usa SSE real)
- Requiere credenciales de Spotify configuradas para funcionar

## Próximas Mejoras

- [ ] Server-Sent Events (SSE) para logs en tiempo real desde cada servicio
- [ ] Progress reporting real usando SSE del gateway
- [ ] Consola de logs con filtros por servicio y nivel
- [ ] Conversión de monedas completa para todas las divisas de Discogs
- [ ] Cache para peticiones a Discogs (rate limiting)
- [ ] Concurrencia en enrichment de álbumes (paralelo vs secuencial)
- [ ] Persistencia de tokens de Spotify en base de datos
- [ ] Métricas y observabilidad (Prometheus/Grafana)

## Última Actualización
11 de noviembre de 2025 - **Request Log Mejorado con URLs Completas**

### Cambios Principales:
- ✅ **NUEVO**: Request Log muestra URLs completas de la API de Discogs
- ✅ **NUEVO**: Credenciales automáticamente ofuscadas como `[HIDDEN]`
- ✅ **NUEVO**: Cada parámetro de query visible y formateado
- ✅ **Arquitectura**: Flujo de debug info end-to-end (client → service → gateway → UI)
- ✅ **Compatibilidad**: Ambos campos `lowest_price` y `lowest_price_eur` retornados

### Cambios Anteriores (11 Nov 2025):
- ❌ **Eliminado**: Enrichment automático de Discogs en `/recommend-vinyl`
- ✅ **Nuevo**: Endpoints interactivos `/discogs/search` y `/discogs/stats`
- ✅ **Nuevo**: Request Log en UI - visibilidad completa de peticiones HTTP
- ✅ **Nuevo**: Búsqueda controlada por usuario con botones "Search Discogs" y "Get Price"
- ✅ **Nuevo**: Exploración de múltiples releases antes de consultar precios

### Características Técnicas:
- **Tasas de conversión EUR actualizadas** (Nov 2025): USD 0.865, GBP 1.140, JPY 0.00573
- **Permite todos los formatos**: Box Sets, Compilaciones, etc. (ordena por preferencia)
- Tracking de tiempo total de procesamiento Spotify
- Breakdown detallado de scoring visible en UI
- Health checks en todos los servicios
- Gestión de errores robusta

### Ventajas del Nuevo Flujo:
- 🎯 **Control total**: Usuario decide cuándo consumir cuota de Discogs
- 📊 **Transparencia**: Cada petición HTTP visible con tiempo y resultado
- 🔍 **Exploración**: Ver todos los releases antes de consultar precios
- 🐛 **Debug**: Saber exactamente qué se pidió y qué respondió la API
