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
        const response = await fetch('/spotify-auth-url');
        const data = await response.json();
        
        if (data.auth_url) {
            localStorage.setItem('vinilogy_flow', 'pending');
            window.location.href = data.auth_url;
        }
    } catch (error) {
        console.error('Error initiating Spotify login:', error);
        alert('Error al conectar con Spotify. Por favor, intenta de nuevo.');
    }
}

// Handle Spotify callback
async function handleSpotifyCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    
    if (code && localStorage.getItem('vinilogy_flow') === 'pending') {
        showLoading(true);
        localStorage.removeItem('vinilogy_flow');
        
        try {
            const response = await fetch(`/spotify-callback?code=${code}`);
            const data = await response.json();
            
            if (data.access_token) {
                localStorage.setItem('spotify_token', data.access_token);
                window.history.replaceState({}, document.title, '/');
                await loadRecommendations();
            }
        } catch (error) {
            console.error('Error handling Spotify callback:', error);
            showLoading(false);
            alert('Error al completar la autenticación. Por favor, intenta de nuevo.');
        }
    }
}

// Show/hide loading state
function showLoading(show) {
    document.getElementById('loading').classList.toggle('active', show);
}

// Load recommendations automatically
async function loadRecommendations() {
    showLoading(true);
    
    try {
        const response = await fetch('/recommend-vinyl');
        const data = await response.json();
        
        if (data.recommendations && data.recommendations.length > 0) {
            localStorage.setItem('last_recommendations', JSON.stringify(data.recommendations));
            localStorage.setItem('last_updated', new Date().toISOString());
            await renderRecommendations(data.recommendations);
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

// Render recommendations grid
async function renderRecommendations(recommendations) {
    document.getElementById('landing-view').style.display = 'none';
    document.getElementById('recommendations-view').classList.add('active');
    
    updateLastUpdatedText();
    
    const container = document.getElementById('albums-container');
    container.innerHTML = '';
    
    // Create skeleton cards first
    recommendations.forEach((_, index) => {
        const skeleton = createSkeletonCard();
        container.appendChild(skeleton);
    });
    
    // Load pricing in parallel for all albums
    const pricingPromises = recommendations.map(async (rec, index) => {
        const albumInfo = rec.album_info || {};
        const artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        const album = albumInfo.name || 'Unknown Album';
        
        try {
            const pricingData = await fetchPricing(artist, album);
            return { ...rec, pricing: pricingData, index };
        } catch (error) {
            console.error(`Error fetching pricing for ${artist} - ${album}:`, error);
            return { ...rec, pricing: null, index };
        }
    });
    
    const results = await Promise.all(pricingPromises);
    
    // Replace skeletons with actual cards
    results.forEach(result => {
        const card = createAlbumCard(result);
        const skeleton = container.children[result.index];
        if (skeleton) {
            container.replaceChild(card, skeleton);
        }
    });
    
    showLoading(false);
}

// Create skeleton card
function createSkeletonCard() {
    const card = document.createElement('div');
    card.className = 'album-card';
    card.innerHTML = `
        <div class="album-cover skeleton"></div>
        <div class="album-info">
            <div class="album-title skeleton" style="height: 1rem; width: 80%; margin-bottom: 0.5rem;"></div>
            <div class="album-artist skeleton" style="height: 0.9rem; width: 60%;"></div>
        </div>
    `;
    return card;
}

// Create album card
function createAlbumCard(rec) {
    const albumInfo = rec.album_info || {};
    const artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
    const album = albumInfo.name || 'Unknown Album';
    const cover = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300x300?text=No+Cover';
    const score = rec.combined_score?.toFixed(1) || '0.0';
    const pricing = rec.pricing;
    
    const card = document.createElement('div');
    card.className = 'album-card';
    card.innerHTML = `
        <img src="${cover}" alt="${album}" class="album-cover" loading="lazy">
        <div class="album-info">
            <div class="album-title">${album}</div>
            <div class="album-artist">${artist}</div>
        </div>
        <div class="album-details">
            <div class="album-details-content">
                ${pricing ? renderPricingSection(pricing) : '<p class="price-label">Precios no disponibles</p>'}
            </div>
        </div>
    `;
    
    card.addEventListener('click', () => {
        card.classList.toggle('expanded');
    });
    
    return card;
}

// Render pricing section
function renderPricingSection(pricing) {
    let html = '';
    
    // eBay price
    if (pricing.ebay_offer) {
        html += `
            <div class="price-section">
                <div class="price-label">Mejor precio eBay</div>
                <div class="price-value">${pricing.ebay_offer.total_price} EUR</div>
            </div>
        `;
    }
    
    // Links
    html += '<div class="links-section">';
    
    if (pricing.discogs_sell_url) {
        html += `<a href="${pricing.discogs_sell_url}" target="_blank" class="link-btn">🎵 Ver en Discogs</a>`;
    }
    
    if (pricing.ebay_offer?.item_web_url) {
        html += `<a href="${pricing.ebay_offer.item_web_url}" target="_blank" class="link-btn">🛒 Comprar en eBay</a>`;
    }
    
    // Local stores
    if (pricing.local_stores && pricing.local_stores.length > 0) {
        pricing.local_stores.forEach(store => {
            html += `<a href="${store.url}" target="_blank" class="link-btn">🏪 ${store.name}</a>`;
        });
    }
    
    html += '</div>';
    
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
    const token = localStorage.getItem('spotify_token');
    
    if (cached && token) {
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
