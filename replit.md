# Vinyl Recommendation System

## Overview
This project is a comprehensive vinyl recommendation system that leverages Spotify listening data and Discogs marketplace information. It is built with a scalable microservices architecture to provide personalized vinyl recommendations, including pricing and local store availability. The business vision is to offer a unique platform for music enthusiasts to discover vinyl records based on their digital listening habits, with ambitions to expand into a robust, data-rich platform for collectors.

## User Preferences
I want to prioritize a clear, concise, and professional communication style. For development, I prefer an iterative approach, focusing on delivering core functionality first and then enhancing it. I value detailed explanations, especially for complex architectural decisions. Please ask for my approval before making any major changes to the system architecture or core functionalities.

## System Architecture

### UI/UX Decisions
The user interface is interactive, featuring a service status monitor, a test panel for authentication and recommendations, a real-time request log for Discogs API calls, a progress tracker for Spotify processing, and a results view displaying recommended albums. Album cards provide detailed score breakdowns and interactive buttons for pricing and advanced Discogs searches. The UI prioritizes transparency, showing detailed request information and allowing users to control when external API quotas are consumed.

### Technical Implementations
The system is built on a microservices architecture using FastAPI and Python 3.11. Asynchronous communication between services is handled with `httpx`, and `asyncio.gather` is used for parallelizing API calls to minimize latency. Shared models are defined in `libs/shared/` to ensure data consistency across services. Structured logging with timestamps is implemented for detailed tracking and debugging.

### Feature Specifications
- **Spotify Integration**: Manages OAuth, retrieves user's top tracks and artists across different time periods, and refreshes tokens automatically.
- **Discogs Integration**: Searches for vinyl releases, provides marketplace statistics (prices, availability), converts prices to EUR, and generates sales links using master_id structure (`https://www.discogs.com/sell/list?master_id={id}&currency=EUR&format=Vinyl`), respecting rate limits.
- **Recommendation Engine**: Scores tracks and artists based on listening frequency and time periods, aggregates albums, filters by track count, and boosts scores for favorite artists.
- **Pricing Service**: Finds best prices on eBay filtered by EU location (27 countries) with dual-layer filtering (API + client-side validation), currency in EUR, and shipping to Spain. Automatically handles eBay API OAuth and provides links to local vinyl stores (Marilians, Bajo el Volcán, Bora Bora, Revolver).
- **API Gateway**: Acts as a single entry point, orchestrates the recommendation and pricing workflows, proxies Spotify authentication, and performs health checks on all microservices.
- **Optimized Pricing Flow**: Allows users to manually trigger pricing requests for recommended albums, executing Discogs, eBay, and local store lookups in parallel to achieve 0.5-0.7 second latency.
- **Advanced Discogs Search**: Enables users to search for all vinyl releases of a specific artist/album, sort by preference (originals first), and retrieve individual release prices and marketplace stats on demand.

### System Design Choices
The architecture comprises five independent microservices: `Spotify Service` (port 3000), `Discogs Service` (port 3001), `Recommender Service` (port 3002), `Pricing Service` (port 3003), and `API Gateway` (port 5000). This microservices approach ensures scalability, maintainability, and clear separation of concerns. The system is designed for a future evolution to a modular monolith with PostgreSQL for persistence and intelligent caching, supporting pre-loaded catalogs and advanced ingestion jobs.

## External Dependencies

- **Spotify API**: Used for user authentication, fetching top tracks, and top artists.
- **Discogs API**: Utilized for searching vinyl releases, retrieving marketplace statistics (prices, availability), and generating sales links.
- **eBay Browse API**: Integrated for finding the best prices for vinyl records, including filtering by currency and shipping location.
- **Local Store Integrations**: Direct links to specific local vinyl stores (Marilians, Bajo el Volcán, Bora Bora, Revolver) are provided, implying direct website integration rather than API.
- **FastAPI**: Python web framework used for building the microservices.
- **httpx**: Asynchronous HTTP client for inter-service communication.