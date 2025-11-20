# Vinyl Recommendation System

## Overview
This project is a comprehensive vinyl recommendation system that leverages Spotify listening data and Discogs marketplace information to provide personalized vinyl recommendations. Its main purpose is to help music enthusiasts discover vinyl records based on their digital listening habits, including pricing and local store availability. The business vision is to evolve into a robust, data-rich platform for collectors.

## User Preferences
I want to prioritize a clear, concise, and professional communication style. For development, I prefer an iterative approach, focusing on delivering core functionality first and then enhancing it. I value detailed explanations, especially for complex architectural decisions. Please ask for my approval before making any major changes to the system architecture or core functionalities.

## System Architecture

### UI/UX Decisions
The user interface features a clean, minimalist landing page with dark/light theme support, a "Conectar con Spotify" button, and an OAuth flow. Recommendations are displayed in a responsive grid. Album detail pages are 1400px wide, two-column layouts showing cover art, basic info, Spotify playback, Discogs tracklist, eBay pricing, Discogs marketplace links, and local store links. On-demand pricing and tracklist loading optimize user experience. A fixed progress banner provides non-blocking feedback during recommendation generation. An Admin Interface is available for monitoring, debugging, and real-time request logs, including a real-time CSV import progress panel.

### Technical Implementations
The system uses a microservices architecture built with FastAPI and Python 3.11, employing asynchronous communication with `httpx` and `asyncio.gather`. Shared models ensure data consistency, and structured logging is implemented.

-   **Spotify Integration**: Handles OAuth, retrieves user's top tracks and artists, refreshes tokens, and provides album streaming links.
-   **Discogs Integration**: Normalizes album titles, implements master/release fallback, retrieves tracklists with durations, provides marketplace statistics (prices in EUR), generates sales links, and includes robust rate limiting. It also fetches artist images.
-   **Recommendation Engine**: Scores tracks/artists, aggregates albums, filters by track count, and boosts scores for favorite artists. It supports background recommendation generation per artist, caching, and intelligent fallbacks, merging Spotify and artist-based recommendations while deduplicating results.
-   **Pricing Service**: Finds best prices on eBay (filtered by EU location, converted to EUR, with shipping to Spain) and provides links to specific local vinyl stores.
-   **API Gateway**: Acts as a single entry point, orchestrates workflows, proxies Spotify authentication, and performs microservice health checks.
-   **Optimized Detail Page Flow**: Achieves complete information load (Discogs links, eBay pricing, local stores, tracklists) in 1-2 seconds through parallel fetching.
-   **Last.fm Artist Explorer**: Uses a Discogs-first search for artist images and simplified similar artist retrieval via `artist.getInfo`.
-   **PostgreSQL Caching**: Implements a structured database (artists, albums, similar_artists) with a 7-day expiration for cached data, dramatically improving response times for existing artists. It supports bulk artist import from CSV with persistence of ratings and images.

### System Design Choices
The architecture comprises five independent microservices: `Spotify Service` (port 3000), `Discogs Service` (port 3001), `Recommender Service` (port 3002), `Pricing Service` (port 3003), and `API Gateway` (port 5000). This design promotes scalability, maintainability, and clear separation of concerns.

## External Dependencies

-   **Spotify API**: User authentication, top tracks, top artists.
-   **Discogs API**: Vinyl release search, marketplace statistics, sales link generation, artist images.
-   **Last.fm API**: Artist search, similar artists, artist information.
-   **MusicBrainz API**: Artist discographies, studio albums, metadata.
-   **eBay Browse API**: Vinyl record pricing, filtering, currency conversion.
-   **Local Store Integrations**: Direct website links for specific Madrid vinyl shops (Marilians, Bajo el Volcán, Bora Bora, Revolver).
-   **FastAPI**: Python web framework.
-   **httpx**: Asynchronous HTTP client.
-   **PostgreSQL**: Database for caching and persistence.