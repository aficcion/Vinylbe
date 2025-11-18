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
        showLoading(true);
        await loadRecommendations();
    } else if (auth === 'error') {
        window.history.replaceState({}, document.title, '/');
        alert('Error al autenticar con Spotify. Por favor, intenta de nuevo.');
    }
}

// Show/hide loading state
function showLoading(show) {
    document.getElementById('loading').classList.toggle('active', show);
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

// Render recommendations grid (fast, no pricing calls)
function renderRecommendations(recommendations) {
    document.getElementById('landing-view').style.display = 'none';
    document.getElementById('album-detail-view').style.display = 'none';
    document.getElementById('recommendations-view').classList.add('active');
    
    updateLastUpdatedText();
    
    const container = document.getElementById('albums-container');
    container.innerHTML = '';
    
    recommendations.forEach(rec => {
        const card = createAlbumCard(rec);
        container.appendChild(card);
    });
    
    showLoading(false);
}

// Create album card (no pricing data yet)
function createAlbumCard(rec) {
    const albumInfo = rec.album_info || {};
    const artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
    const album = albumInfo.name || 'Unknown Album';
    const cover = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300x300?text=No+Cover';
    
    const card = document.createElement('div');
    card.className = 'album-card';
    card.innerHTML = `
        <img src="${cover}" alt="${album}" class="album-cover" loading="lazy">
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
    const albumInfo = rec.album_info || {};
    const artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
    const album = albumInfo.name || 'Unknown Album';
    const cover = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300x300?text=No+Cover';
    const spotifyUrl = albumInfo.external_urls?.spotify || null;
    
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
    
    // Tracklist section
    if (pricing.tracklist && pricing.tracklist.length > 0) {
        html += '<div class="tracklist-section"><h3>Lista de Canciones</h3><ol class="tracklist">';
        pricing.tracklist.forEach(track => {
            const duration = track.duration ? ` <span class="duration">(${track.duration})</span>` : '';
            html += `<li>${track.title}${duration}</li>`;
        });
        html += '</ol></div>';
    }
    
    // eBay price section
    if (pricing.ebay_offer) {
        const url = pricing.ebay_offer.url || '#';
        const totalPrice = pricing.ebay_offer.total_price || 'N/A';
        
        html += `
            <div class="price-highlight">
                <div class="price-label">Mejor precio eBay</div>
                <div class="price-value">${totalPrice} EUR</div>
                <a href="${url}" target="_blank" class="btn-primary">
                    🛒 Comprar en eBay
                </a>
            </div>
        `;
    }
    
    // Discogs link
    if (pricing.discogs_sell_url) {
        html += `
            <a href="${pricing.discogs_sell_url}" target="_blank" class="btn-secondary">
                🎵 Ver en Discogs
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
            html += '<div class="stores-section"><h3>Tiendas Locales</h3>';
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
    
    if (!spotifyUrl && !pricing.tracklist?.length && !pricing.ebay_offer && !pricing.discogs_sell_url && (!pricing.local_stores || Object.keys(pricing.local_stores).length === 0)) {
        html = '<p class="no-pricing">No hay información disponible en este momento</p>';
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    handleSpotifyCallback();
    checkCachedRecommendations();
});
