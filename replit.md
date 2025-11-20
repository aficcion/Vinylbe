# Vinyl Recommendation System

## Overview
This project is a comprehensive vinyl recommendation system that leverages Spotify listening data and Discogs marketplace information. It provides personalized vinyl recommendations, including pricing and local store availability. The business vision is to offer a unique platform for music enthusiasts to discover vinyl records based on their digital listening habits, with ambitions to expand into a robust, data-rich platform for collectors.

## User Preferences
I want to prioritize a clear, concise, and professional communication style. For development, I prefer an iterative approach, focusing on delivering core functionality first and then enhancing it. I value detailed explanations, especially for complex architectural decisions. Please ask for my approval before making any major changes to the system architecture or core functionalities.

## Recent Changes (November 20, 2025)
**Persistencia de Artistas y Manejo de Rate Limiting de Discogs (LATEST):**
- **Persistencia robusta**: Modal de artistas ahora restaura automáticamente artistas previamente seleccionados desde localStorage cuando se reabre
- **Restauración paralela**: Método `restoreArtists()` usa `Promise.all()` para buscar todos los artistas en Last.fm simultáneamente (en vez de secuencialmente)
- **Manejo de fallos parciales**: Si algunos artistas no se encuentran en Last.fm, los demás se restauran exitosamente sin bloquear el flujo
- **Logging detallado**: Registra cuántos artistas se restauraron exitosamente vs cuántos fallaron, con razones específicas para debugging
- **Background recommendations**: Cada artista restaurado activa automáticamente la generación de recomendaciones en background (cachea desde sesión anterior si están disponibles)
- **Discogs rate limiting**: Implementado retry con exponential backoff (5 intentos, 1s→2s→4s→8s→10s) para manejar errores 429 de Discogs
- **Retry inteligente**: Maneja tanto errores 429 (rate limiting) como otros errores transitorios (500, 502, 503, network failures)
- **Mensajes claros**: Logging específico para debugging de rate limiting, muestra qué intentos se están haciendo y cuándo se agota el backoff
- **UX mejorada**: Usuario puede volver a abrir el modal y ver todos sus artistas previamente seleccionados, con sus recomendaciones cacheadas
- **Architect aprobado**: Ambas implementaciones validadas como production-ready y robustas ante todos los edge cases

**Filtro de Recomendaciones Minimalista:**
- **Feature nueva**: Filtro visual arriba del grid de recomendaciones que permite al usuario ver solo Spotify, solo artistas, o todas
- **Diseño minimalista**: Pills/tabs compactos con background card, border radius, hover states y estado activo con color primary
- **Variables CSS**: Agregadas --hover-color (light/dark themes) para consistencia visual
- **Preservación de estado**: El filtro mantiene la selección del usuario al recargar recomendaciones (no resetea a "Todas")
- **Lógica robusta**: Filtrado basado en campo source ('artist_based' vs undefined/otros), con fallback para casos edge
- **UX pulida**: Transiciones suaves, estado activo visible, coherente con diseño existente
- **Architect aprobado**: Implementación production-ready, preserva estado, maneja edge cases correctamente


**Corrección de Duplicados en Merge y Optimización de Generación Spotify (LATEST):**
- **Bug 1 corregido**: Duplicados en merge de recomendaciones Spotify + artistas (ej: "Getting Killed" de Geese aparecía 2 veces)
- **Deduplicación híbrida robusta**: Sistema de múltiples claves que genera `artist::album` (siempre) + `master_id` (cuando existe)
- **Maneja estructuras diferentes**: Spotify usa `album_info.name/artists[0].name`, artistas usa `album_name/artist_name` - ambas convergen a clave canónica
- **Metadata mixta**: Si una rec tiene master_id y otra no, ambas convergen a la misma clave canónica `artist::album`
- **Elimina variantes**: Reissues y ediciones variantes del mismo álbum se deduplicán correctamente (usuario ve UN álbum único)
- **Bug 2 corregido**: Generación Spotify lenta (10-15s cuando antes tomaba 2-3s)
- **Paralelización optimizada**: Usa `asyncio.gather` para llamadas paralelas (top-tracks + top-artists simultáneos, score-tracks + score-artists simultáneos)
- **Mejora de performance**: Reducción de tiempo ~40-60% en generación Spotify (de 5 llamadas secuenciales a 3 rondas con paralelización)
- **Logging mejorado**: Registra duplicados removidos en merge para debugging
- **Architect aprobado**: Ambas soluciones validadas como production-ready y robustas ante todos los edge cases

**Corrección de Bug: Promise Tracking para Carga Completa de Recomendaciones:**
- **Problema corregido**: Bug donde hacer clic en "Continuar" antes de que terminen de cargar artistas causaba que no se mostraran todas las recomendaciones
- **Promise tracking robusto**: Implementación de `pendingPromises` Map que rastrea promesas de fetch reales (no contadores síncronos)
- **Método waitForAllPendingRecommendations()**: Usa `Promise.allSettled()` para esperar a TODAS las promesas (exitosas o fallidas) antes de proceder
- **Event handler async**: Botón "Continuar" ahora es async y espera con `await onContinue()`, bloqueando hasta que se completen todas las promesas
- **UX mejorada**: Muestra "Finalizando recomendaciones..." mientras espera, mantiene modal abierto durante espera (usuario no pierde contexto)
- **Robustez completa**: Elimina condiciones de carrera, Map se limpia en finally y removeArtist, garantiza datos completos antes de proceder
- **Architect aprobado**: Solución validada como correcta y robusta ante todos los edge cases

**Generación Incremental de Recomendaciones por Artista:**
- **Background generation**: Cuando usuario selecciona artista, el sistema genera recomendaciones automáticamente en background (0-2s por artista)
- **Cache local robusto**: Frontend cachea recomendaciones con estructura `{status, recommendations/error, timestamp}` para diferenciar éxito de error
- **Indicadores visuales por artista**: Pills muestran ⏳ durante carga, ✓ cuando exitoso, ⚠ cuando error (con tooltip descriptivo)
- **Uso instantáneo de cache**: Si TODOS los artistas tienen recs exitosas y NO hay Spotify conectado, usa cache directamente (0s de espera)
- **Fallback inteligente**: Si algún artista falla, hace fallback automático al flujo tradicional de backend con mensaje claro en consola
- **Endpoints nuevos**: `/api/recommendations/artist-single` en Gateway y Recommender para generación por artista individual
- **Manejo de errores HTTP completo**: Gateway usa `raise_for_status()`, retorna 404 cuando no hay álbumes, propaga errores correctamente
- **Performance mejorada**: Reduce tiempo de espera de 15-30s a 0-2s cuando usuario ya seleccionó artistas previamente

## System Architecture

### UI/UX Decisions
The main user interface features a clean, minimalist landing page with dark/light theme support. It includes a hero section with a "Conectar con Spotify" button, an OAuth flow, and a responsive grid layout for album recommendations. Album cards display Spotify cover art and link to a detailed album page. The album detail page is a 1400px wide, two-column layout showing cover art, basic info, Spotify playback link, scrollable Discogs tracklist, eBay pricing, Discogs marketplace links, local store links, and informative messages for unavailable data. On-demand pricing and tracklist loading optimize user experience. A fixed progress banner provides non-blocking feedback during recommendation generation. The system also features an Admin Interface for monitoring, debugging, and real-time request logs.

### Technical Implementations
The system is built on a microservices architecture using FastAPI and Python 3.11. Asynchronous communication is handled with `httpx` and `asyncio.gather` for parallel API calls. Shared models ensure data consistency, and structured logging is implemented for debugging. Key features include:

-   **Spotify Integration**: Standard OAuth, retrieves user's top tracks and artists, refreshes tokens, provides album streaming links.
-   **Discogs Integration**: Normalizes album titles, implements master → release fallback for comprehensive searching, retrieves tracklists with durations, provides marketplace statistics (prices in EUR), generates sales links, and respects API rate limits.
-   **Recommendation Engine**: Scores tracks/artists based on listening data, aggregates albums, filters by track count, and boosts scores for favorite artists. It also supports generation of recommendations by artist, caching, and intelligent fallbacks.
-   **Pricing Service**: Finds best prices on eBay filtered by EU location, handles currency conversion to EUR, and provides shipping to Spain. Also includes links to specific local vinyl stores.
-   **API Gateway**: Acts as a single entry point, orchestrates workflows, proxies Spotify authentication, and performs microservice health checks.
-   **Optimized Detail Page Flow**: Instant loading of detail pages with parallel fetching of Discogs links, eBay pricing, local stores, and tracklists, achieving complete information load in 1-2 seconds.
-   **Last.fm Artist Explorer**: Implements a Discogs-first search strategy for artist images, simplified similar artist retrieval via `artist.getInfo`, and targeted image fetching, significantly reducing API calls and improving performance.
-   **Unified Recommendation System**: Automatically merges Spotify and manually selected artist recommendations, persists artist selections, and intelligently adjusts UI based on current selection state.

### System Design Choices
The architecture consists of five independent microservices: `Spotify Service` (port 3000), `Discogs Service` (port 3001), `Recommender Service` (port 3002), `Pricing Service` (port 3003), and `API Gateway` (port 5000). This microservices approach enhances scalability, maintainability, and separation of concerns.

## External Dependencies

-   **Spotify API**: User authentication, top tracks, top artists.
-   **Discogs API**: Vinyl release search, marketplace statistics (prices, availability), sales link generation, artist images.
-   **Last.fm API**: Artist search, similar artists, artist information.
-   **MusicBrainz API**: Artist discographies, studio albums, metadata.
-   **eBay Browse API**: Vinyl record pricing, filtering by currency and shipping location.
-   **Local Store Integrations**: Direct website links for specific Madrid vinyl shops (Marilians, Bajo el Volcán, Bora Bora, Revolver).
-   **FastAPI**: Python web framework for microservices.
-   **httpx**: Asynchronous HTTP client for inter-service communication.