// Theme Management
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Spotify Authentication
async function loginSpotify() {
    try {
        const response = await fetch('/auth/login');
        const data = await response.json();
        
        if (data.authorize_url) {
            localStorage.setItem('vinilogy_auth_pending', 'true');
            window.location.href = data.authorize_url;
        }
    } catch (error) {
        console.error('Error initiating Spotify login:', error);
        alert('Error al conectar con Spotify. Por favor, intenta de nuevo.');
    }
}

// Handle Spotify callback
async function handleSpotifyCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const auth = urlParams.get('auth');
    
    if (auth === 'success') {
        window.history.replaceState({}, document.title, '/');
        localStorage.removeItem('vinilogy_auth_pending');
        
        const savedArtists = localStorage.getItem('selected_artist_names');
        if (savedArtists) {
            await loadMixedRecommendations(JSON.parse(savedArtists));
        } else {
            showLoading(true);
            await loadRecommendations();
        }
    } else if (auth === 'error') {
        window.history.replaceState({}, document.title, '/');
        alert('Error al autenticar con Spotify. Por favor, intenta de nuevo.');
    }
}

// Show/hide loading state (legacy, keep for simple loads)
function showLoading(show, message = 'Cargando tus recomendaciones...') {
    const loadingEl = document.getElementById('loading');
    loadingEl.classList.toggle('active', show);
    if (show) {
        loadingEl.querySelector('p').textContent = message;
    }
}

// Progress banner control
let progressStartTime = 0;

function showProgressModal(title = 'Generando Recomendaciones') {
    const banner = document.getElementById('progress-banner');
    const titleEl = document.getElementById('progress-title');
    
    showLoading(false);
    
    titleEl.textContent = title;
    banner.classList.add('active');
    progressStartTime = Date.now();
    
    updateProgressUI(0, 0, 'Iniciando...', '');
}

function hideProgressModal() {
    const banner = document.getElementById('progress-banner');
    banner.classList.remove('active');
    showLoading(false);
}

function updateProgressUI(current, total, status, currentArtist = '') {
    const progressBar = document.getElementById('progress-bar');
    const percentage = document.getElementById('progress-percentage');
    const statusEl = document.getElementById('progress-status');
    const artistEl = document.getElementById('progress-current-artist');
    const timeEl = document.getElementById('progress-time-estimate');
    
    const percent = total > 0 ? Math.round((current / total) * 100) : 0;
    
    if (total === 0 || percent === 0) {
        progressBar.classList.add('indeterminate');
        progressBar.style.width = '';
    } else {
        progressBar.classList.remove('indeterminate');
        progressBar.style.width = `${percent}%`;
    }
    
    percentage.textContent = `${percent}%`;
    statusEl.textContent = status;
    
    if (currentArtist) {
        artistEl.textContent = ` | 🔍 ${currentArtist}`;
    } else {
        artistEl.textContent = '';
    }
    
    if (current > 0 && total > 0 && current < total) {
        const elapsed = (Date.now() - progressStartTime) / 1000;
        const timePerItem = elapsed / current;
        const remaining = Math.round(timePerItem * (total - current));
        timeEl.textContent = ` | ⏱️ ~${remaining}s`;
    } else {
        timeEl.textContent = '';
    }
}

// Progress monitoring
let progressInterval = null;
let progressPollCount = 0;
const MAX_PROGRESS_POLLS = 120;

async function startProgressMonitoring(contextTitle = 'Generando Recomendaciones') {
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    showProgressModal(contextTitle);
    progressPollCount = 0;
    
    progressInterval = setInterval(async () => {
        try {
            progressPollCount++;
            
            if (progressPollCount > MAX_PROGRESS_POLLS) {
                console.warn('Progress monitoring timed out');
                stopProgressMonitoring();
                hideProgressModal();
                alert('La operación está tardando más de lo esperado. Por favor, intenta de nuevo.');
                return;
            }
            
            const response = await fetch('/api/recommendations/progress');
            if (!response.ok) {
                console.error('Progress fetch failed:', response.status);
                return;
            }
            
            const progress = await response.json();
            
            if (progress.status === 'processing' && progress.total > 0) {
                const statusMsg = `Procesando artista ${progress.current} de ${progress.total}`;
                updateProgressUI(
                    progress.current, 
                    progress.total, 
                    statusMsg,
                    progress.current_artist || ''
                );
            } else if (progress.status === 'completed' || progress.status === 'idle') {
                stopProgressMonitoring();
            } else if (progress.status === 'error') {
                stopProgressMonitoring();
                hideProgressModal();
                alert('Hubo un error al procesar las recomendaciones. Por favor, intenta de nuevo.');
            }
        } catch (error) {
            console.error('Error fetching progress:', error);
        }
    }, 500);
}

function stopProgressMonitoring() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
        progressPollCount = 0;
    }
}

// Load recommendations (without pricing)
async function loadRecommendations() {
    showLoading(true);
    
    try {
        const response = await fetch('/recommend-vinyl');
        const data = await response.json();
        
        if (data.albums && data.albums.length > 0) {
            localStorage.setItem('last_recommendations', JSON.stringify(data.albums));
            localStorage.setItem('last_updated', new Date().toISOString());
            localStorage.setItem('has_spotify_connected', 'true');
            renderRecommendations(data.albums);
        } else {
            showLoading(false);
            alert('No se encontraron recomendaciones. Por favor, intenta de nuevo.');
        }
    } catch (error) {
        console.error('Error loading recommendations:', error);
        showLoading(false);
        alert('Error al cargar recomendaciones. Por favor, intenta de nuevo.');
    }
}

// Load mixed recommendations (artists + Spotify)
async function loadMixedRecommendations(artistNames) {
    startProgressMonitoring('Combinando Recomendaciones');
    
    try {
        const response = await fetch('/api/recommendations/artists', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_names: artistNames,
                spotify_token: true
            })
        });
        
        const data = await response.json();
        
        stopProgressMonitoring();
        hideProgressModal();
        
        if (data.recommendations && data.recommendations.length > 0) {
            const formattedRecs = formatArtistRecommendations(data.recommendations);
            localStorage.setItem('last_recommendations', JSON.stringify(formattedRecs));
            localStorage.setItem('last_updated', new Date().toISOString());
            localStorage.setItem('has_spotify_connected', 'true');
            renderRecommendations(formattedRecs);
        } else {
            alert('No se encontraron recomendaciones. Por favor, intenta de nuevo.');
        }
    } catch (error) {
        console.error('Error loading mixed recommendations:', error);
        stopProgressMonitoring();
        hideProgressModal();
        alert('Error al cargar recomendaciones. Por favor, intenta de nuevo.');
    }
}

let allRecommendations = [];
let currentFilter = 'all';

// Render recommendations grid (fast, no pricing calls)
function renderRecommendations(recommendations) {
    allRecommendations = recommendations;
    
    document.getElementById('landing-view').style.display = 'none';
    document.getElementById('album-detail-view').style.display = 'none';
    document.getElementById('recommendations-view').classList.add('active');
    
    const hasArtistBased = recommendations.some(rec => rec.source === 'artist_based');
    const hasSpotifyBased = recommendations.some(rec => rec.source !== 'artist_based');
    const hasSpotifyConnected = localStorage.getItem('has_spotify_connected') === 'true';
    
    const spotifyBtn = document.getElementById('spotify-connect-btn');
    const artistSearchBtn = document.getElementById('artist-search-header-btn');
    
    if (hasArtistBased && !hasSpotifyBased && !hasSpotifyConnected) {
        spotifyBtn.style.display = 'inline-flex';
        document.getElementById('last-updated').textContent = 'Basado en tus artistas seleccionados';
    } else {
        spotifyBtn.style.display = 'none';
        updateLastUpdatedText();
    }
    
    artistSearchBtn.style.display = 'inline-flex';
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.filter-btn[data-filter="${currentFilter}"]`).classList.add('active');
    
    let filtered;
    if (currentFilter === 'all') {
        filtered = allRecommendations;
    } else if (currentFilter === 'spotify') {
        filtered = allRecommendations.filter(rec => !rec.source || rec.source !== 'artist_based');
    } else if (currentFilter === 'artists') {
        filtered = allRecommendations.filter(rec => rec.source === 'artist_based');
    } else {
        filtered = allRecommendations;
    }
    
    displayFilteredRecommendations(filtered);
    
    showLoading(false);
}

function displayFilteredRecommendations(recommendations) {
    const container = document.getElementById('albums-container');
    container.innerHTML = '';
    
    recommendations.forEach(rec => {
        const card = createAlbumCard(rec);
        container.appendChild(card);
    });
}

function filterRecommendations(filter) {
    currentFilter = filter;
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.filter-btn[data-filter="${filter}"]`).classList.add('active');
    
    let filtered;
    if (filter === 'all') {
        filtered = allRecommendations;
    } else if (filter === 'spotify') {
        filtered = allRecommendations.filter(rec => !rec.source || rec.source !== 'artist_based');
    } else if (filter === 'artists') {
        filtered = allRecommendations.filter(rec => rec.source === 'artist_based');
    }
    
    displayFilteredRecommendations(filtered);
}

// Create album card (no pricing data yet)
function createAlbumCard(rec) {
    let artist, album, cover;
    
    if (rec.source === 'artist_based') {
        artist = rec.artist_name || 'Unknown Artist';
        album = rec.album_name || 'Unknown Album';
        cover = rec.image_url || 'https://via.placeholder.com/300x300?text=No+Cover';
    } else {
        const albumInfo = rec.album_info || {};
        artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        album = albumInfo.name || 'Unknown Album';
        cover = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300x300?text=No+Cover';
    }
    
    const card = document.createElement('div');
    card.className = 'album-card';
    card.innerHTML = `
        <img src="${cover}" alt="${album}" class="album-cover" loading="lazy" onerror="this.src='https://via.placeholder.com/300x300?text=No+Cover'">
        <div class="album-info">
            <div class="album-title">${album}</div>
            <div class="album-artist">${artist}</div>
        </div>
    `;
    
    card.addEventListener('click', () => {
        openAlbumDetail(rec);
    });
    
    return card;
}

// Open album detail page
async function openAlbumDetail(rec) {
    let artist, album, cover, spotifyUrl;
    
    if (rec.source === 'artist_based') {
        artist = rec.artist_name || 'Unknown Artist';
        album = rec.album_name || 'Unknown Album';
        cover = rec.image_url || 'https://via.placeholder.com/300x300?text=No+Cover';
        spotifyUrl = null;
    } else {
        const albumInfo = rec.album_info || {};
        artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        album = albumInfo.name || 'Unknown Album';
        cover = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300x300?text=No+Cover';
        spotifyUrl = albumInfo.external_urls?.spotify || null;
    }
    
    document.getElementById('recommendations-view').classList.remove('active');
    document.getElementById('album-detail-view').style.display = 'block';
    
    document.getElementById('detail-cover').src = cover;
    document.getElementById('detail-title').textContent = album;
    document.getElementById('detail-artist').textContent = artist;
    
    const pricingContainer = document.getElementById('detail-pricing');
    pricingContainer.innerHTML = `
        <div class="spinner-small"></div>
        <p style="text-align: center; color: var(--text-secondary); margin-top: 1rem;">Cargando información...</p>
    `;
    
    try {
        const pricingData = await fetchPricing(artist, album);
        pricingContainer.innerHTML = renderDetailPricing(pricingData, spotifyUrl);
    } catch (error) {
        console.error('Error fetching pricing:', error);
        pricingContainer.innerHTML = '<p class="error-text">No se pudo cargar la información</p>';
    }
}

// Go back to recommendations
function backToRecommendations() {
    document.getElementById('album-detail-view').style.display = 'none';
    document.getElementById('recommendations-view').classList.add('active');
}

// Render pricing in detail view
function renderDetailPricing(pricing, spotifyUrl) {
    let html = '';
    
    // Spotify link
    if (spotifyUrl) {
        html += `
            <a href="${spotifyUrl}" target="_blank" class="btn-primary" style="background: #1DB954; margin-bottom: 1rem;">
                ▶️ Escuchar en Spotify
            </a>
        `;
    }
    
    // Discogs information section
    if (pricing.discogs_type) {
        const typeLabel = pricing.discogs_type === 'master' ? 'Master' : 'Release';
        html += `<div class="info-message">ℹ️ Encontrado en Discogs como ${typeLabel}</div>`;
    } else if (pricing.discogs_url === null && pricing.discogs_id === null) {
        html += `<div class="info-message warning">⚠️ No se encontró este álbum en Discogs</div>`;
    }
    
    // Tracklist section
    if (pricing.tracklist && pricing.tracklist.length > 0) {
        html += '<div class="tracklist-section"><h3>Lista de Canciones</h3><ol class="tracklist">';
        pricing.tracklist.forEach(track => {
            const duration = track.duration ? ` <span class="duration">${track.duration}</span>` : '';
            html += `<li><span>${track.title}</span>${duration}</li>`;
        });
        html += '</ol></div>';
    } else if (pricing.discogs_type) {
        html += `<div class="info-message warning">⚠️ No se encontró tracklist en Discogs</div>`;
    }
    
    // eBay price section
    if (pricing.ebay_offer) {
        const url = pricing.ebay_offer.url || '#';
        const totalPrice = pricing.ebay_offer.total_price || 'N/A';
        
        html += `
            <div class="price-highlight">
                <div class="price-label">Mejor precio eBay (EU)</div>
                <div class="price-value">${totalPrice} EUR</div>
                <a href="${url}" target="_blank" class="btn-primary">
                    🛒 Comprar en eBay
                </a>
            </div>
        `;
    } else {
        html += `<div class="info-message">ℹ️ No hay ofertas de eBay disponibles en este momento</div>`;
    }
    
    // Discogs marketplace link
    if (pricing.discogs_sell_url) {
        html += `
            <a href="${pricing.discogs_sell_url}" target="_blank" class="btn-secondary">
                🎵 Ver marketplace en Discogs
            </a>
        `;
    }
    
    // Discogs detail link
    if (pricing.discogs_url) {
        html += `
            <a href="${pricing.discogs_url}" target="_blank" class="btn-secondary">
                📖 Ver detalles en Discogs
            </a>
        `;
    }
    
    // Local stores section
    if (pricing.local_stores && typeof pricing.local_stores === 'object') {
        const storeNames = {
            'marilians': 'Marilians',
            'bajo_el_volcan': 'Bajo el Volcán',
            'bora_bora': 'Bora Bora',
            'revolver': 'Revolver Records'
        };
        
        const storeEntries = Object.entries(pricing.local_stores);
        if (storeEntries.length > 0) {
            html += '<div class="stores-section"><h3>Tiendas Locales en Madrid</h3>';
            storeEntries.forEach(([key, url]) => {
                const name = storeNames[key] || key;
                html += `
                    <a href="${url}" target="_blank" class="store-link">
                        🏪 ${name}
                    </a>
                `;
            });
            html += '</div>';
        }
    }
    
    return html;
}

// Fetch pricing for an album
async function fetchPricing(artist, album) {
    const response = await fetch(`/album-pricing/${encodeURIComponent(artist)}/${encodeURIComponent(album)}`);
    if (!response.ok) {
        throw new Error('Failed to fetch pricing');
    }
    return await response.json();
}

// Update last updated text
function updateLastUpdatedText() {
    const lastUpdated = localStorage.getItem('last_updated');
    if (lastUpdated) {
        const date = new Date(lastUpdated);
        const now = new Date();
        const diffMs = now - date;
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffMins = Math.floor(diffMs / (1000 * 60));
        
        let timeText = '';
        if (diffHours > 0) {
            timeText = `Actualizado hace ${diffHours} hora${diffHours > 1 ? 's' : ''}`;
        } else if (diffMins > 0) {
            timeText = `Actualizado hace ${diffMins} minuto${diffMins > 1 ? 's' : ''}`;
        } else {
            timeText = 'Actualizado hace un momento';
        }
        
        document.getElementById('last-updated').textContent = `Basado en tu escucha. ${timeText}`;
    }
}

// Check if user has cached recommendations
function checkCachedRecommendations() {
    const cached = localStorage.getItem('last_recommendations');
    
    if (cached) {
        const recommendations = JSON.parse(cached);
        renderRecommendations(recommendations);
    }
}

// Artist Search Modal
let artistSearchComponent = null;

function openArtistSearch() {
    const modal = document.getElementById('artist-search-modal');
    modal.classList.add('active');
    
    if (!artistSearchComponent) {
        artistSearchComponent = new ArtistSearch('artist-search-container', {
            minArtists: 3,
            maxArtists: 10,
            onContinue: handleArtistSelection
        });
    }
}

function closeArtistSearch() {
    const modal = document.getElementById('artist-search-modal');
    modal.classList.remove('active');
}

async function handleArtistSelection(selectedArtists) {
    const artistNames = selectedArtists.map(a => a.name);
    localStorage.setItem('selected_artist_names', JSON.stringify(artistNames));
    
    const hasSpotifyConnected = localStorage.getItem('has_spotify_connected') === 'true';
    
    if (!artistSearchComponent) {
        console.error('Artist search component not available');
        closeArtistSearch();
        alert('Error: el componente de búsqueda no está disponible. Por favor, intenta de nuevo.');
        return;
    }
    
    if (artistSearchComponent.pendingPromises.size > 0) {
        console.log(`⏳ Waiting for ${artistSearchComponent.pendingPromises.size} pending recommendations...`);
        showLoading(true, 'Finalizando recomendaciones...');
        await artistSearchComponent.waitForAllPendingRecommendations();
        showLoading(false);
    }
    
    closeArtistSearch();
    
    const loadingStatus = artistSearchComponent.getLoadingStatus();
    const cachedRecs = artistSearchComponent.getCachedRecommendations();
    
    console.log(`Cache status: ${cachedRecs.length} recommendations, ${loadingStatus.success}/${loadingStatus.total} successful, ${loadingStatus.error} errors, all successful: ${loadingStatus.hasAllSuccessful}`);
    
    if (!hasSpotifyConnected && loadingStatus.hasAllSuccessful && cachedRecs.length > 0) {
        console.log('✓ Using cached artist recommendations (no Spotify merge needed, all successful)');
        const formattedRecs = formatArtistRecommendations(cachedRecs);
        localStorage.setItem('last_recommendations', JSON.stringify(formattedRecs));
        localStorage.setItem('last_updated', new Date().toISOString());
        renderRecommendations(formattedRecs);
        return;
    }
    
    if (loadingStatus.error > 0) {
        console.log(`⚠ ${loadingStatus.error} artists failed to load, falling back to backend generation`);
    }
    
    const title = hasSpotifyConnected ? 'Combinando Recomendaciones' : 'Generando Recomendaciones';
    startProgressMonitoring(title);
    
    try {
        const response = await fetch('/api/recommendations/artists', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_names: artistNames,
                spotify_token: hasSpotifyConnected ? true : null
            })
        });
        
        const data = await response.json();
        
        stopProgressMonitoring();
        hideProgressModal();
        
        if (data.recommendations && data.recommendations.length > 0) {
            const formattedRecs = formatArtistRecommendations(data.recommendations);
            localStorage.setItem('last_recommendations', JSON.stringify(formattedRecs));
            localStorage.setItem('last_updated', new Date().toISOString());
            renderRecommendations(formattedRecs);
        } else {
            alert('No se encontraron recomendaciones para estos artistas.');
        }
    } catch (error) {
        console.error('Error loading artist recommendations:', error);
        stopProgressMonitoring();
        hideProgressModal();
        alert('Error al cargar recomendaciones. Por favor, intenta de nuevo.');
    }
}

function formatArtistRecommendations(recommendations) {
    return recommendations.map(rec => {
        if (rec.source === 'artist_based') {
            return {
                album_name: rec.album_name,
                artist_name: rec.artist_name,
                image_url: rec.image_url,
                discogs_master_id: rec.discogs_master_id,
                rating: rec.rating,
                votes: rec.votes,
                year: rec.year,
                source: 'artist_based'
            };
        }
        return rec;
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    handleSpotifyCallback();
    checkCachedRecommendations();
});
