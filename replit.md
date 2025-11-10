# API de Búsqueda de Vinilos en Discogs

## Descripción General
API REST construida con FastAPI que permite buscar vinilos y obtener información del marketplace de Discogs.

## Estado Actual
✅ API completamente funcional
✅ Servidor corriendo en puerto 5000
✅ Credenciales de Discogs configuradas
✅ Sin errores de código

## Endpoints Disponibles

### 1. Estado de la API
- **GET** `/`
- Verifica que el backend está funcionando

### 2. Buscar Vinilos
- **GET** `/discogs/search?artist={artista}&title={titulo}`
- Busca vinilos por artista y título en la base de datos de Discogs
- Parámetros requeridos:
  - `artist`: Nombre del artista
  - `title`: Título del álbum o disco

### 3. Estadísticas del Marketplace
- **GET** `/discogs/stats/{release_id}?currency=EUR`
- Obtiene estadísticas de precios del marketplace
- Parámetros:
  - `release_id`: ID del lanzamiento en Discogs
  - `currency`: Moneda (por defecto EUR)

### 4. URL de Listados de Venta
- **GET** `/discogs/sell-list-url/{release_id}`
- Devuelve la URL pública donde ver los listados de venta del vinilo

## Tecnologías
- **FastAPI**: Framework web moderno
- **Uvicorn**: Servidor ASGI
- **httpx**: Cliente HTTP asíncrono
- **Python 3.11**

## Configuración
- Las credenciales `DISCOGS_KEY` y `DISCOGS_SECRET` están configuradas en las variables de entorno
- El servidor acepta peticiones CORS de cualquier origen
- Cliente HTTP reutilizable con timeout de 15 segundos

## Última Actualización
10 de noviembre de 2025 - Código arreglado y funcionando correctamente
