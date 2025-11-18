# Vinyl Recommendation System

## Overview
This project is a comprehensive vinyl recommendation system that leverages Spotify listening data and Discogs marketplace information. It is built with a scalable microservices architecture to provide personalized vinyl recommendations, including pricing and local store availability. The business vision is to offer a unique platform for music enthusiasts to discover vinyl records based on their digital listening habits, with ambitions to expand into a robust, data-rich platform for collectors.

## User Preferences
I want to prioritize a clear, concise, and professional communication style. For development, I prefer an iterative approach, focusing on delivering core functionality first and then enhancing it. I value detailed explanations, especially for complex architectural decisions. Please ask for my approval before making any major changes to the system architecture or core functionalities.

## Recent Changes (November 18, 2025)
**Modal de Progreso Visual Mejorado (LATEST):**
- **Modal overlay de pantalla completa**: Indicador de progreso visual moderno con barra animada, porcentaje, y mensajes detallados
- **Barra de progreso animada**: Gradiente verde Spotify con efecto shimmer, muestra porcentaje exacto (ej: "75%")
- **Información contextual detallada**: "Procesando artista 3 de 5" + nombre del artista actual que se está analizando
- **Estimación de tiempo**: Cálculo dinámico de tiempo restante basado en velocidad de procesamiento
- **Títulos contextuales**: "Generando Recomendaciones" para solo artistas, "Combinando Recomendaciones" para merge Spotify+artistas
- **Manejo robusto de estados**: Cierre automático en timeout (60s) con alert al usuario, manejo de errores con mensajes claros
- **Sin bloqueos de UI**: Eliminada interferencia con loading legacy, ambos sistemas coexisten correctamente
- **Animaciones suaves**: FadeIn/SlideUp para entrada, backdrop blur, icono con pulse animation
- **Polling optimizado**: 500ms de intervalo, actualización fluida de UI sin degradar performance
- **Arquitectura limpia**: Separación clara entre loading simple (Spotify solo) y modal de progreso (artistas/merge)

**Sistema de Fallback Triple a Discogs:**
- **Fallback automático a Discogs**: Cuando MusicBrainz no tiene discogs_master_id, el sistema busca automáticamente en Discogs API (primero masters por artista+título, luego releases si no encuentra master)
- **Soporte completo releases**: StudioAlbum ahora guarda tanto discogs_master_id como discogs_release_id, con campo discogs_type para diferenciar
- **Gateway proxy**: Endpoint `/api/recommendations/progress` que hace proxy al servicio de recommender de forma segura
- **Cobertura mejorada**: Ahora funciona con artistas como Los Fresones Rebeldes que carecen de enlaces MusicBrainz→Discogs
- **Nota técnica MVP**: Progress tracking usa estado global (single-flight), aceptable para MVP pero documentado para mejora futura con per-request IDs
- **Pendiente futuro**: Tests automatizados para fallbacks y monitoreo de timeouts en producción

**Unificación de Opciones de Recomendaciones y Sistema de Merge Automático:**
- **Sistema unificado**: Ambas opciones (Spotify y búsqueda de artistas) siempre disponibles y funcionan juntas
- **Merge automático**: Cuando usuario conecta Spotify después de seleccionar artistas, las recomendaciones se mezclan automáticamente 1:1
- **Persistencia de selección**: Los artistas seleccionados se guardan en localStorage y se mantienen al conectar Spotify
- **UI mejorada**: Botón "Buscar artistas" siempre visible en página de recomendaciones, botón de Spotify se oculta después de conectar
- **Flujos inteligentes**: 
  - Solo artistas → muestra botón "Conectar Spotify" para mezclar
  - Solo Spotify → muestra botón "Buscar artistas" para añadir artistas
  - Mixto → muestra solo "Buscar artistas" para ajustar selección
- **Imágenes de portada**: Recomendaciones basadas en artistas incluyen imágenes desde Discogs masters/releases
- **Backend optimizado**: Endpoint `/api/recommendations/artists` maneja merge automático de ambas fuentes
- **Performance**: Búsqueda <2s, merge completo 15-30s, recomendaciones mixtas con toda la metadata

**Integración de Búsqueda de Artistas y Recomendaciones Basadas en Artistas Manuales:**
- **Microservicio Last.fm**: Nuevo servicio (puerto 3004) con búsqueda Discogs-first para imágenes + Last.fm para géneros usando `artist.getTopTags`
- **Recomendaciones basadas en artistas**: Sistema que obtiene discografía de estudio vía MusicBrainz, ratings de Discogs, selecciona top 3 discos por artista
- **Algoritmo de mezclado**: Intercala recomendaciones 1:1 (1 Spotify, 1 artistas) para lista unificada
- **UI de búsqueda**: Componente JavaScript modular con búsqueda incremental (≥4 caracteres), grid 2 columnas, pills de selección, validación 3-10 artistas
- **Home page actualizada**: Dos opciones minimalistas - "Conectar con Spotify" o "Buscar artistas" con modal elegante
- **Arquitectura**: Separación completa backend/frontend, código modular y reutilizable


**Last.fm Artist Explorer - Major API Optimization (LATEST):**
- **Discogs-first search strategy**: Search now uses Discogs API directly (type=artist) for instant results with real thumbnails; falls back to Last.fm if credentials unavailable
- **Simplified similar artists flow**: Uses Last.fm `artist.getInfo` which includes 5 similar artists in response, eliminating need for separate `artist.getSimilar` calls
- **Targeted image fetching**: Only fetches Discogs images for top 5 suggested artists (not all 50 similar artists)
- **Eliminated cascade fallbacks**: Removed expensive multi-tier image fallback system (Last.fm getInfo → Discogs search per artist)
- **Performance breakthrough**: Reduced from ~112 API calls to ~7 calls per complete flow (94% reduction)
- **Speed improvement**: Full search + suggestions now completes in <2s vs 20-60s before (90% faster)
- **Graceful degradation**: Works with or without Discogs credentials (with/without images)
- **Hybrid suggestion algorithm**: Shows 2 from last added artist + 3 globally most voted, ensuring immediate feedback when adding new artists
- **Maintained functionality**: Shows up to 5 suggested artists with performance metrics in UI

**Enhanced Discogs Integration:**
- **Title normalization**: Album titles are now normalized before searching in Discogs by removing suffixes like "(Deluxe Version)", "(Remastered)", "(Anniversary Edition)", etc. This significantly improves match rate for albums with multiple editions.
- **Master/Release fallback system**: The system now attempts to find a Discogs master first; if not found, it falls back to searching for releases. This ensures better coverage for albums that only exist as releases without masters.
- **Release tracklist support**: Added new endpoint to fetch tracklists from releases (not only masters), providing comprehensive track information for all types of vinyl entries.
- **Smart URL generation**: URLs to Discogs marketplace are generated correctly based on type (master_id or release_id).

**Improved Detail Page UI:**
- **Wider layout**: Expanded from 900px to 1400px for better use of screen space on desktop
- **Optimized 2-column grid**: Left column (400px) shows album cover and basic info; right column displays tracklist, pricing, and store links
- **Scrollable tracklist**: Tracklist has max-height with overflow for albums with many tracks, preventing page scroll
- **Informative messages**: Clear messages when data is unavailable (e.g., "No se encontró tracklist en Discogs", "No hay ofertas de eBay disponibles")
- **Type indicator**: Shows whether the album was found as "Master" or "Release" in Discogs

## System Architecture

### UI/UX Decisions

**User Interface (/):**
The main user interface is a clean, minimalista landing page with dark/light theme support. Features include:
- Hero section with clear value proposition and prominent "Conectar con Spotify" button
- **OAuth flow**: Standard redirect-based flow (Spotify → callback → auto-redirect to homepage with recommendations)
- Automatic flow: login → auto-fetch recommendations → display grid (fast 2-3s loading, no pricing)
- Grid layout: 4 columns (desktop), 3 columns (tablet), 2 columns (mobile), 1 column (small mobile)
- Album cards with high-quality Spotify cover art, clickable to open full detail page
- **Album detail page**: Full page (1400px wide) with 2-column layout (cover + info | tracklist + pricing):
  - **Spotify playback link**: Direct "Escuchar en Spotify" button for instant streaming
  - **Tracklist**: Complete track listing from Discogs (master or release) with durations, scrollable for long albums
  - **eBay pricing**: Best EU-filtered price with direct purchase link
  - **Discogs marketplace**: Direct link to vinyl marketplace (master_id or release_id based)
  - **Discogs details**: Link to full album information page
  - **Local stores**: Links to Madrid vinyl shops (Marilians, Bajo el Volcán, Bora Bora, Revolver)
  - **Status messages**: Clear informative messages when data is unavailable
- On-demand pricing: Prices and tracklist load automatically when user opens album detail (0.5-2s)
- Skeleton loading states for progressive rendering
- Persistent theme preference with localStorage
- Timestamp showing "Actualizado hace X horas"

**Admin Interface (/admin):**
Technical dashboard for monitoring and debugging, featuring service status monitors, real-time request logs for Discogs API calls, progress tracker for Spotify processing, and detailed debugging information. The admin UI prioritizes transparency, showing detailed request information and allowing manual control of all workflows.

### Technical Implementations
The system is built on a microservices architecture using FastAPI and Python 3.11. Asynchronous communication between services is handled with `httpx`, and `asyncio.gather` is used for parallelizing API calls to minimize latency. Shared models are defined in `libs/shared/` to ensure data consistency across services. Structured logging with timestamps is implemented for detailed tracking and debugging.

### Feature Specifications
- **Spotify Integration**: Standard redirect-based OAuth flow (no popups), retrieves user's top tracks and artists across different time periods, refreshes tokens automatically, and provides album streaming links.
- **Discogs Integration**: 
  - Normalizes album titles by removing edition suffixes (Deluxe, Remastered, etc.) before searching
  - Implements master → release fallback: searches for master first, then release if master not found
  - Retrieves tracklists from both masters and releases with track positions and durations
  - Provides marketplace statistics (prices, availability), converts prices to EUR
  - Generates sales links using appropriate ID type: `https://www.discogs.com/sell/list?master_id={id}` or `release_id={id}`
  - Respects API rate limits with intelligent throttling
- **Recommendation Engine**: Scores tracks and artists based on listening frequency and time periods, aggregates albums, filters by track count, and boosts scores for favorite artists.
- **Pricing Service**: Finds best prices on eBay filtered by EU location (27 countries) with dual-layer filtering (API + client-side validation), currency in EUR, and shipping to Spain. Automatically handles eBay API OAuth and provides links to local vinyl stores (Marilians, Bajo el Volcán, Bora Bora, Revolver).
- **API Gateway**: Acts as a single entry point, orchestrates the recommendation and pricing workflows, proxies Spotify authentication, and performs health checks on all microservices.
- **Optimized Detail Page Flow**: When user clicks an album, the detail page loads instantly and then fetches in parallel: Discogs link (master or release), eBay pricing, local stores (0.5-1s for first three), followed by tracklist fetch using the appropriate ID type (additional 0.5-1s). Total load time for complete album information: 1-2 seconds. Returns Spotify streaming link, complete tracklist, eBay offer, Discogs marketplace link, Discogs detail link, local store links, and informative status messages.

### System Design Choices
The architecture comprises five independent microservices: `Spotify Service` (port 3000), `Discogs Service` (port 3001), `Recommender Service` (port 3002), `Pricing Service` (port 3003), and `API Gateway` (port 5000). This microservices approach ensures scalability, maintainability, and clear separation of concerns. The system is designed for a future evolution to a modular monolith with PostgreSQL for persistence and intelligent caching, supporting pre-loaded catalogs and advanced ingestion jobs.

## External Dependencies

- **Spotify API**: Used for user authentication, fetching top tracks, and top artists.
- **Discogs API**: Utilized for searching vinyl releases, retrieving marketplace statistics (prices, availability), generating sales links, and providing high-quality artist images as fallback.
- **Last.fm API**: Used in artist explorer for searching artists, getting similar artists, and artist information. Integrated with Discogs fallback for reliable artist images.
- **MusicBrainz API**: Used for fetching artist discographies and studio albums with release dates and metadata.
- **eBay Browse API**: Integrated for finding the best prices for vinyl records, including filtering by currency and shipping location.
- **Local Store Integrations**: Direct links to specific local vinyl stores (Marilians, Bajo el Volcán, Bora Bora, Revolver) are provided, implying direct website integration rather than API.
- **FastAPI**: Python web framework used for building the microservices.
- **httpx**: Asynchronous HTTP client for inter-service communication.
- **Streamlit**: Python framework used for the Last.fm artist explorer UI (tests/lastfm_artist_explorer.py).