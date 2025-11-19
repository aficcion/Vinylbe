# Vinyl Recommendation System

## Overview
This project is a comprehensive vinyl recommendation system that leverages Spotify listening data and Discogs marketplace information. It provides personalized vinyl recommendations, including pricing and local store availability. The business vision is to offer a unique platform for music enthusiasts to discover vinyl records based on their digital listening habits, with ambitions to expand into a robust, data-rich platform for collectors.

## User Preferences
I want to prioritize a clear, concise, and professional communication style. For development, I prefer an iterative approach, focusing on delivering core functionality first and then enhancing it. I value detailed explanations, especially for complex architectural decisions. Please ask for my approval before making any major changes to the system architecture or core functionalities.

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