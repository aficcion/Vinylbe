# API de Música - Discogs + Spotify

## Descripción General
API REST construida con FastAPI que integra dos servicios:
- **Discogs**: Búsqueda de vinilos e información del marketplace
- **Spotify**: Autenticación OAuth y acceso a datos del usuario (top tracks, top artists, etc.)

## Estado Actual
✅ API completamente funcional
✅ Servidor corriendo en puerto 5000
✅ Credenciales de Discogs configuradas
✅ Integración de Spotify lista (requiere configurar credenciales)
✅ Sin errores de código

## Endpoints Disponibles

### Estado de la API
- **GET** `/` - Verifica que el backend está funcionando

### Discogs
- **GET** `/discogs/search?artist={artista}&title={titulo}` - Busca vinilos por artista y título
- **GET** `/discogs/stats/{release_id}?currency=EUR` - Estadísticas de precios del marketplace
- **GET** `/discogs/sell-list-url/{release_id}` - URL de listados de venta

### Spotify (OAuth)
- **GET** `/spotify/login` - Devuelve URL para iniciar sesión con Spotify
- **GET** `/spotify/callback?code={code}` - Callback OAuth (intercambia código por token)
- **GET** `/spotify/me` - Información del perfil del usuario
- **GET** `/spotify/top-tracks?limit=50&time_range=medium_term` - Top tracks del usuario
- **GET** `/spotify/top-artists?limit=50&time_range=medium_term` - Top artistas del usuario
- **GET** `/spotify/album-from-track/{track_id}` - Obtiene álbum de un track (con UPC si está disponible)

## Tecnologías
- **FastAPI**: Framework web moderno
- **Uvicorn**: Servidor ASGI
- **httpx**: Cliente HTTP asíncrono
- **Python 3.11**

## Configuración

### Discogs
- `DISCOGS_KEY` ✅ Configurada
- `DISCOGS_SECRET` ✅ Configurada

### Spotify (OAuth)
- `SPOTIFY_CLIENT_ID` - ID de la aplicación de Spotify
- `SPOTIFY_CLIENT_SECRET` - Secret de la aplicación
- `SPOTIFY_REDIRECT_URI` - URL de callback (ej: https://tu-dominio.com/spotify/callback)

## Notas Técnicas
- Cliente HTTP reutilizable con timeout de 15 segundos
- CORS habilitado para todos los orígenes
- Tokens de Spotify se guardan en memoria (solo para demo, usar BD en producción)
- Auto-refresh de tokens de Spotify cuando expiran

## Última Actualización
10 de noviembre de 2025 - Integración de Spotify añadida, todos los errores corregidos
