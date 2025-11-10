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
- Conversión automática de precios a EUR
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

```
1. Usuario se autentica en Spotify → Gateway → Spotify Service
2. Gateway solicita 300 tracks en 3 períodos → Spotify Service (18 peticiones)
3. Gateway solicita 300 artistas top → Spotify Service (6 peticiones)
4. Gateway envía tracks para puntuación → Recommender Service
5. Gateway envía artistas para puntuación → Recommender Service
6. Gateway solicita agregación de álbumes → Recommender Service
   - Filtra álbumes con < 5 tracks
   - Aplica boosts por período y artistas favoritos
7. Para cada álbum recomendado:
   - Gateway busca en Discogs → Discogs Service
   - Obtiene stats y precios (convertidos a EUR)
8. Retorna lista ordenada de álbumes con info de Spotify + Discogs
```

## Endpoints Principales (Gateway)

### Autenticación
- **GET** `/auth/login` - Inicia flujo OAuth de Spotify
- **GET** `/auth/callback?code={code}` - Callback OAuth

### Recomendación
- **GET** `/recommend-vinyl` - Flujo completo de recomendación

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

✅ Arquitectura de 4 microservicios independientes
✅ Obtención de 300 tracks y 300 artistas de Spotify
✅ Sistema de puntuación con boosts por período temporal
✅ Boost adicional para artistas favoritos
✅ Filtrado de álbumes (mínimo 5 tracks)
✅ Integración con Discogs para datos de vinilos
✅ Conversión automática de precios a EUR
✅ Health checks en todos los servicios
✅ Logging detallado en cada paso
✅ Gestión de errores robusta

## Frontend de Testing (Estado Actual)

✅ UI básica implementada en `gateway/static/`:
- Service Status: Monitoreo visual del estado de cada microservicio
- Test Panel: Botones para probar login de Spotify y obtener recomendaciones
- Progress Tracker: Visualización de pasos (actualmente simulado)
- Results View: Cards con álbumes recomendados, precios en EUR, y links a Discogs

⚠️ Limitaciones actuales:
- Progress tracking es simulado (no usa SSE real)
- No hay consola de logs en tiempo real
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
10 de noviembre de 2025 - Arquitectura de microservicios completamente funcional con conversión a EUR implementada
