(async () => {
    const uid = localStorage.getItem('userId');
    if (uid) {
        try {
            const resp = await fetch(`/api/users/${uid}`);
            if (!resp.ok) {
                console.warn(`Usuario ${uid} no encontrado → limpiando localStorage`);
                localStorage.removeItem('userId');
                localStorage.removeItem('lastfm_username');
                // Recargar para iniciar flujo de creación de usuario
                location.reload();
            }
        } catch (e) {
            console.error('Error verificando usuario al iniciar:', e);
        }
    }
})();

const hasLastfm = true; // Last.fm integration enabled

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


// Last.fm Authentication - Simplified redirect flow
async function loginLastfm() {
    try {
        const response = await fetch('/auth/lastfm/login');
        const data = await response.json();

        if (data.auth_url && data.token) {
            // Save token and set auth pending flag
            localStorage.setItem('vinilogy_lastfm_token', data.token);
            localStorage.setItem('vinilogy_lastfm_auth_pending', 'true');

            // Redirect to Last.fm in the same window
            window.location.href = data.auth_url;
        }
    } catch (error) {
        console.error('Error initiating Last.fm login:', error);
        alert('Error al conectar con Last.fm. Por favor, intenta de nuevo.');
    }
}

// Check if we just returned from Last.fm authentication
function checkLastfmAuthReturn() {
    const authCompleted = localStorage.getItem('vinilogy_lastfm_auth_completed');
    const lastfmUsername = localStorage.getItem('lastfm_username');

    if (authCompleted === 'true' && lastfmUsername) {
        // Clear the flag
        localStorage.removeItem('vinilogy_lastfm_auth_completed');

        console.log('✓ Returned from Last.fm authentication:', lastfmUsername);

        // Show success message
        if (typeof showToast === 'function') {
            showToast(`¡Conectado con Last.fm como ${lastfmUsername}!`, 'success');
        }

        // Load recommendations for the user
        const userId = localStorage.getItem('userId');
        if (userId) {
            fetchUserRecommendations(userId);
        }
    }
}

// ---------------------------------------------------------------------
// Helper: fetch recommendations for a logged‑in user and sync status map
// ---------------------------------------------------------------------
async function fetchUserRecommendations(userId) {
    // Validate userId
    if (!userId || userId === 'undefined' || userId === 'null') {
        console.warn('fetchUserRecommendations called with invalid userId:', userId);
        return;
    }

    console.log(`Fetching recommendations for user: ${userId} at /api/users/${userId}/recommendations`);
    try {
        // Use the /api prefix which we explicitly aliased in the backend
        const resp = await fetch(`/api/users/${userId}/recommendations`);

        if (!resp.ok) {
            throw new Error(`Server responded with ${resp.status}: ${resp.statusText}`);
        }

        const data = await resp.json();
        console.log('Recommendations loaded:', data.length, 'items');

        // If no recommendations found and we have a Last.fm user, trigger generation
        // Check if we need to trigger initial Last.fm generation
        // We do this if:
        // 1. We have a Last.fm user connected
        // 2. We haven't synced with Last.fm yet (checked via a flag)
        const lastfmUser = localStorage.getItem('lastfm_username');
        const hasSyncedLastfm = localStorage.getItem('lastfm_synced_v2');

        if (lastfmUser && !hasSyncedLastfm) {
            console.log('Last.fm connected but not synced (v2). Triggering generation/merge for:', lastfmUser);
            // Mark as synced BEFORE calling to prevent loops if it fails or returns 0
            localStorage.setItem('lastfm_synced_v2', 'true');
            await generateAndSaveRecommendations(userId, lastfmUser);
            return; // Exit, the generation function will call fetch again
        }

        // Store in localStorage for offline fallback
        localStorage.setItem('last_recommendations', JSON.stringify(data));
        localStorage.setItem('last_updated', new Date().toISOString());

        // Sync album status map from the received recommendations
        syncAlbumStatusesFromRecs(data);
        renderRecommendations(data);
    } catch (e) {
        console.error('Error fetching user recommendations:', e);
        // Fallback to cached if any
        checkCachedRecommendations();
    }
}

// New helper to generate and save recommendations
async function generateAndSaveRecommendations(userId, lastfmUsername) {
    showLoading(true, 'Generando recomendaciones personalizadas...');
    try {
        // 1. Get recommendations from Last.fm
        console.log('Step 1: Fetching Last.fm recommendations...');
        const genResp = await fetch('/api/lastfm/recommendations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: lastfmUsername,
                time_range: 'medium_term'
            })
        });

        if (!genResp.ok) throw new Error('Failed to generate recommendations');
        const genData = await genResp.json();
        const newLastfmRecs = genData.albums || [];
        console.log(`✓ Generated ${newLastfmRecs.length} recommendations from Last.fm`);

        // 2. Get recommendations for Selected Artists (Manual)
        console.log('Step 2: Fetching Manual Artist recommendations...');
        let manualRecs = [];
        try {
            // 2a. Get selected artists
            const artistsResp = await fetch(`/api/users/${userId}/selected-artists`);
            if (artistsResp.ok) {
                const selectedArtists = await artistsResp.json();
                const artistNames = selectedArtists.map(a => a.artist_name);

                if (artistNames.length > 0) {
                    console.log(`Found ${artistNames.length} selected artists:`, artistNames);
                    // 2b. Generate recommendations for them
                    const recsResp = await fetch('/api/recommendations/artists', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ artist_names: artistNames })
                    });

                    if (recsResp.ok) {
                        const recsData = await recsResp.json();
                        if (recsData.recommendations) {
                            manualRecs = formatArtistRecommendations(recsData.recommendations);
                            console.log(`✓ Generated ${manualRecs.length} recommendations from selected artists`);
                        }
                    }
                }
            }
        } catch (e) {
            console.warn('Error fetching manual artist recommendations:', e);
        }

        // 3. Load existing recommendations to merge (preserve status)
        console.log('Step 3: Merging with existing recommendations...');
        let finalRecs = [...newLastfmRecs, ...manualRecs];

        try {
            const existingResp = await fetch(`/api/users/${userId}/recommendations`);
            if (existingResp.ok) {
                const existingRecs = await existingResp.json();
                if (existingRecs.length > 0) {
                    console.log(`✓ Found ${existingRecs.length} existing recommendations`);

                    // Create a map of existing recs by key for easy lookup
                    const existingMap = new Map();
                    existingRecs.forEach(r => {
                        const key = `${r.artist_name}::${r.album_title || r.album_name}`;
                        existingMap.set(key, r);
                    });

                    // Filter new recs: 
                    // - If it exists in DB, keep the DB version (preserves status/id)
                    // - If it doesn't exist, keep the new version
                    const mergedRecs = [];
                    const processedKeys = new Set();

                    // Add existing recs first (they are the source of truth for status)
                    existingRecs.forEach(r => {
                        const key = `${r.artist_name}::${r.album_title || r.album_name}`;
                        mergedRecs.push(r);
                        processedKeys.add(key);
                    });

                    // Add new recs if they don't exist
                    finalRecs.forEach(r => {
                        const key = `${r.artist_name}::${r.album_name || r.album_title}`;
                        if (!processedKeys.has(key)) {
                            mergedRecs.push(r);
                            processedKeys.add(key);
                        }
                    });

                    finalRecs = mergedRecs;
                    console.log(`✓ Final merge count: ${finalRecs.length}`);
                }
            }
        } catch (e) {
            console.warn('Could not load existing recommendations for merge:', e);
        }

        // 4. Save merged recommendations to the database
        console.log('Step 4: Saving to database...');
        const saveResp = await fetch(`/users/${userId}/recommendations/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_recs: finalRecs })
        });

        if (!saveResp.ok) throw new Error('Failed to save recommendations');

        console.log('✓ Recommendations saved successfully');

        // 5. Save Last.fm profile (top artists)
        try {
            const profileResp = await fetch(`/api/lastfm/top-artists`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: lastfmUsername,
                    time_range: 'medium_term'
                })
            });

            if (profileResp.ok) {
                const profileData = await profileResp.json();
                const topArtists = profileData.artists || [];

                if (topArtists.length > 0) {
                    await fetch(`/api/users/${userId}/profile/lastfm`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            lastfm_username: lastfmUsername,
                            top_artists: topArtists.slice(0, 50)
                        })
                    });
                    console.log('✓ Last.fm profile saved');
                }
            }
        } catch (e) {
            console.warn('Could not save Last.fm profile:', e);
        }

        // 6. Fetch again to display
        showLoading(false);
        await fetchUserRecommendations(userId);

        if (typeof showToast === 'function') {
            showToast('Recomendaciones actualizadas correctamente', 'success');
        }

    } catch (e) {
        console.error('Error generating recommendations:', e);
        showLoading(false);
        alert('Hubo un error generando tus recomendaciones. Por favor intenta más tarde.');
    }
}

function syncAlbumStatusesFromRecs(recommendations) {
    // Clear current map
    albumStatuses.clear();
    recommendations.forEach(rec => {
        const artist = rec.artist_name || rec.album_info?.artists?.[0]?.name || 'Unknown';
        const album = rec.album_name || rec.album_info?.name || 'Unknown';
        if (rec.status && rec.status !== 'pending') {
            const key = `${artist}|${album}`;
            albumStatuses.set(key, rec.status);
        }
    });
}





// Legacy callback handler - no longer needed as callback.html handles everything
// Kept as no-op for backwards compatibility
async function handleLastfmCallback() {
    // All callback logic now handled in callback.html
    // This function is kept to avoid breaking existing code that calls it
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


// Load all recommendations from Last.fm
async function loadAllRecommendations() {
    showLoading(true, 'Cargando recomendaciones desde todas las fuentes...');

    try {
        const promises = [];

        if (hasLastfm) {
            const lastfmUsername = localStorage.getItem('lastfm_username');
            if (lastfmUsername) {
                promises.push(
                    fetch('/api/lastfm/recommendations', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ time_range: 'medium_term', username: lastfmUsername })
                    })
                        .then(res => res.json())
                        .then(data => {
                            const albums = data.albums || [];
                            albums.forEach(album => {
                                album.source = 'lastfm';
                            });
                            return { albums };
                        })
                        .catch(err => {
                            console.error('Last.fm recommendations failed:', err);
                            return { albums: [] };
                        })
                );
            } else {
                promises.push(Promise.resolve({ albums: [] }));
            }
        } else {
            promises.push(Promise.resolve({ albums: [] }));
        }

        const [lastfmData] = await Promise.all(promises);
        const lastfmAlbums = lastfmData.albums || [];

        if (lastfmAlbums.length === 0) {
            showLoading(false);
            alert('No se encontraron recomendaciones. Por favor, conecta al menos una fuente.');
            return;
        }

        // Merge with existing artist recommendations if they exist
        const existingRecs = localStorage.getItem('last_recommendations');
        let finalRecs = lastfmAlbums;

        if (existingRecs) {
            try {
                const existing = JSON.parse(existingRecs);
                const artistRecs = existing.filter(rec => rec.source === 'artist_based');
                if (artistRecs.length > 0) {
                    console.log(`✓ Merging ${lastfmAlbums.length} Last.fm recs with ${artistRecs.length} existing artist recs`);
                    finalRecs = [...lastfmAlbums, ...artistRecs];
                }
            } catch (e) {
                console.error('Error parsing existing recommendations:', e);
            }
        }

        localStorage.setItem('last_recommendations', JSON.stringify(finalRecs));
        localStorage.setItem('last_updated', new Date().toISOString());

        // Save to database if user is logged in
        const userId = localStorage.getItem('userId');
        const lastfmUsername = localStorage.getItem('lastfm_username');

        if (userId && lastfmUsername) {
            try {
                // Save Last.fm profile snapshot (top artists)
                const topArtistsRes = await fetch('/api/lastfm/top-artists', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ time_range: 'medium_term', username: lastfmUsername })
                });

                if (topArtistsRes.ok) {
                    const topArtistsData = await topArtistsRes.json();
                    const topArtists = (topArtistsData.artists || []).slice(0, 20).map(a => ({
                        name: a.name,
                        playcount: a.playcount || 0
                    }));

                    // Save profile to DB
                    await fetch(`/users/${userId}/profile/lastfm`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            lastfm_username: lastfmUsername,
                            top_artists: topArtists
                        })
                    });
                    console.log('✓ Last.fm profile saved to database');
                }

                // Save recommendations to DB
                const recsToSave = lastfmAlbums.slice(0, 50).map(rec => ({
                    artist_name: rec.artist_name || rec.artist,
                    album_title: rec.album_name || rec.album,
                    album_mbid: rec.mbid || null,
                    source: 'lastfm'
                }));

                if (recsToSave.length > 0) {
                    await fetch(`/users/${userId}/recommendations/regenerate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ new_recs: recsToSave })
                    });
                    console.log(`✓ ${recsToSave.length} recommendations saved to database`);
                }
            } catch (e) {
                console.error('Error saving to database:', e);
                // Don't fail the whole flow if DB save fails
            }
        }

        renderRecommendations(finalRecs);

    } catch (error) {
        console.error('Error loading all recommendations:', error);
        showLoading(false);
        alert('Error al cargar recomendaciones. Por favor, intenta de nuevo.');
    }
}

// Merge recommendation lists from multiple sources with deduplication
async function mergeRecommendationLists(lastfmAlbums, artistAlbums = []) {
    try {
        const response = await fetch('/api/recommendations/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                lastfm_recommendations: lastfmAlbums,
                artist_recommendations: artistAlbums
            })
        });

        const data = await response.json();
        return data.recommendations || [];
    } catch (error) {
        console.error('Error merging recommendations:', error);
        return [...lastfmAlbums, ...artistAlbums];
    }
}

// Load mixed recommendations (artists only)
async function loadMixedRecommendations(artistNames) {
    startProgressMonitoring('Combinando Recomendaciones');

    try {
        const response = await fetch('/api/recommendations/artists', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_names: artistNames
            })
        });

        const data = await response.json();

        stopProgressMonitoring();
        hideProgressModal();

        if (data.recommendations && data.recommendations.length > 0) {
            const formattedRecs = formatArtistRecommendations(data.recommendations);
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
    // Keep album status map in sync (useful when recommendations are loaded from DB)
    syncAlbumStatusesFromRecs(recommendations);

    document.getElementById('landing-view').style.display = 'none';
    document.getElementById('album-detail-view').style.display = 'none';
    document.getElementById('recommendations-view').classList.add('active');

    const hasArtistBased = recommendations.some(rec => rec.source === 'artist_based');
    const hasLastfmBased = recommendations.some(rec => rec.source === 'lastfm');

    const artistSearchBtn = document.getElementById('artist-search-header-btn');
    const lastfmHeaderBtn = document.getElementById('lastfm-header-btn');
    const lastfmFilterBtn = document.querySelector('.filter-btn[data-filter="lastfm"]');

    if (lastfmFilterBtn) {
        lastfmFilterBtn.style.display = hasLastfmBased ? 'inline-block' : 'none';
    }

    if (hasArtistBased) {
        document.getElementById('last-updated').textContent = 'Basado en tus artistas seleccionados';
    } else {
        updateLastUpdatedText();
    }

    // Show artist search button always
    artistSearchBtn.style.display = 'inline-flex';

    // Show Last.fm button only if not connected
    const lastfmUsername = localStorage.getItem('lastfm_username');
    if (lastfmHeaderBtn) {
        lastfmHeaderBtn.style.display = lastfmUsername ? 'none' : 'inline-flex';
    }

    const filterButtons = document.querySelectorAll('.filter-btn');
    if (filterButtons.length > 0) {
        filterButtons.forEach(btn => {
            btn.classList.remove('active');
        });
        const activeBtn = document.querySelector(`.filter-btn[data-filter="${currentFilter}"]`);
        if (activeBtn) {
            activeBtn.classList.add('active');
        }
    }

    let filtered;
    if (currentFilter === 'all') {
        filtered = allRecommendations;
    } else if (currentFilter === 'favorites') {
        // Filter only favorites
        filtered = allRecommendations.filter(rec => {
            const artist = rec.artist_name || rec.album_info?.artists?.[0]?.name || 'Unknown';
            const album = rec.album_name || rec.album_info?.name || 'Unknown';
            return typeof window.getAlbumStatus === 'function' && window.getAlbumStatus(artist, album) === 'favorite';
        });
    } else if (currentFilter === 'lastfm') {
        filtered = allRecommendations.filter(rec => rec.source === 'lastfm');
    } else if (currentFilter === 'artists') {
        filtered = allRecommendations.filter(rec => rec.source === 'artist_based');
    } else {
        filtered = allRecommendations;
    }

    displayFilteredRecommendations(filtered);

    // Load profile sidebar
    if (typeof loadProfileSidebar === 'function') {
        loadProfileSidebar();
    }

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
    } else if (filter === 'lastfm') {
        filtered = allRecommendations.filter(rec => rec.source === 'lastfm');
    } else if (filter === 'artists') {
        filtered = allRecommendations.filter(rec => rec.source === 'manual');
    } else if (filter === 'favorites') {
        filtered = allRecommendations.filter(rec => {
            const artist = rec.artist_name || rec.album_info?.artists?.[0]?.name || 'Unknown';
            const album = rec.album_name || rec.album_info?.name || 'Unknown';
            return typeof window.getAlbumStatus === 'function' &&
                window.getAlbumStatus(artist, album) === 'favorite';
        });
    }

    displayFilteredRecommendations(filtered);
}

// Create album card (no pricing data yet)
function createAlbumCard(rec) {
    let artist, album, cover;

    // Generic property mapping to handle various sources (manual, lastfm, artist_based)
    artist = rec.artist_name || rec.artist || 'Unknown Artist';
    album = rec.album_name || rec.album_title || rec.name || 'Unknown Album';

    // Handle cover images
    // Check for various image properties and ensure it's not an empty string
    cover = rec.cover_url || rec.image_url || rec.image;

    // If cover is missing or is a generic Last.fm placeholder (often empty or just a star), use our SVG
    if (!cover || cover.includes('2a96cbd8b46e442fc41c2b86b821562f')) {
        cover = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="300" height="300"%3E%3Crect fill="%23f0f0f0" width="300" height="300"/%3E%3Ctext fill="%23888" font-family="sans-serif" font-size="24" dy="8" font-weight="bold" x="50%25" y="50%25" text-anchor="middle"%3EVinylbe%3C/text%3E%3C/svg%3E';
    }

    const card = document.createElement('div');
    card.className = 'album-card';

    // Check status
    let currentStatus = null;
    if (typeof window.getAlbumStatus === 'function') {
        currentStatus = window.getAlbumStatus(artist, album);
    }

    // Hide if disliked or owned unless in specific view
    if ((currentStatus === 'disliked' || currentStatus === 'owned') && window.currentFilter !== 'all') {
        // We might want to hide them, but for now let's just mark them
        // card.classList.add('hidden-card'); 
    }

    card.innerHTML = `
        <div class="album-cover">
            <img src="${cover}" alt="${album}" loading="lazy">
            <div class="album-actions">
                <button class="action-btn favorite ${currentStatus === 'favorite' ? 'active' : ''}" title="Guardar en favoritos" data-action="favorite">★</button>
                <button class="action-btn owned ${currentStatus === 'owned' ? 'active' : ''}" title="Ya lo tengo" data-action="owned">✓</button>
                <button class="action-btn disliked ${currentStatus === 'disliked' ? 'active' : ''}" title="No me interesa" data-action="disliked">✗</button>
            </div>
        </div>
        <div class="album-info">
            <h3>${album}</h3>
            <p>${artist}</p>
        </div>
    `;

    // Add event listeners to buttons
    card.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation(); // Prevent card click
            const action = btn.dataset.action;

            if (typeof window.setAlbumStatus === 'function') {
                // Optimistic UI update
                const isActive = btn.classList.contains('active');

                // Reset all buttons in this card
                card.querySelectorAll('.action-btn').forEach(b => b.classList.remove('active'));

                let newStatus = action;
                if (isActive) {
                    // Toggle off
                    newStatus = null;
                } else {
                    // Toggle on
                    btn.classList.add('active');
                }

                console.log(`Setting status: ${artist} - ${album} -> ${newStatus}`);

                // Call global handler
                await window.setAlbumStatus(artist, album, newStatus, rec.id);

                // Handle hiding logic if needed
                if ((newStatus === 'disliked' || newStatus === 'owned') && window.currentFilter !== 'favorites') {
                    card.style.opacity = '0.5'; // Visual feedback instead of hiding immediately
                } else {
                    card.style.opacity = '1';
                }

                // Refresh favorites filter if active
                if (window.currentFilter === 'favorites') {
                    window.filterRecommendations('favorites');
                }
            } else {
                console.error('setAlbumStatus function not available');
            }
        });
    });

    card.addEventListener('click', () => {
        openAlbumDetail(rec);
    });

    return card;
}

// Open album detail page
async function openAlbumDetail(rec) {
    let artist, album, cover;

    if (rec.source === 'artist_based' || rec.source === 'lastfm') {
        artist = rec.artist_name || 'Unknown Artist';
        album = rec.album_name || 'Unknown Album';
        cover = rec.cover_url || rec.image_url || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="300" height="300"%3E%3Crect fill="%23ddd" width="300" height="300"/%3E%3Ctext fill="%23999" font-family="sans-serif" font-size="18" dy="10.5" font-weight="bold" x="50%25" y="50%25" text-anchor="middle"%3ENo Cover%3C/text%3E%3C/svg%3E';

    } else {
        const albumInfo = rec.album_info || {};
        artist = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        album = albumInfo.name || 'Unknown Album';
        cover = albumInfo.images?.[0]?.url || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="300" height="300"%3E%3Crect fill="%23ddd" width="300" height="300"/%3E%3Ctext fill="%23999" font-family="sans-serif" font-size="18" dy="10.5" font-weight="bold" x="50%25" y="50%25" text-anchor="middle"%3ENo Cover%3C/text%3E%3C/svg%3E';
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
        pricingContainer.innerHTML = renderDetailPricing(pricingData);
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
function renderDetailPricing(pricing) {
    let html = '';


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

async function openArtistSearch() {
    const modal = document.getElementById('artist-search-modal');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    if (!artistSearchComponent) {
        artistSearchComponent = new ArtistSearch('artist-search-container', {
            minArtists: 3,
            maxArtists: 10,
            onContinue: handleArtistSelection
        });

        // Load selected artists from DB
        const userId = localStorage.getItem('userId');
        if (userId) {
            try {
                const res = await fetch(`/api/users/${userId}/selected-artists`);
                if (res.ok) {
                    const dbArtists = await res.json();
                    const artistNames = dbArtists.map(a => a.artist_name);
                    console.log(`✓ Restoring ${artistNames.length} artists from DB:`, artistNames);
                    artistSearchComponent.restoreArtists(artistNames);
                }
            } catch (e) {
                console.error('Error loading selected artists:', e);
            }
        }
    }
}

function closeArtistSearch() {
    const modal = document.getElementById('artist-search-modal');
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

async function handleArtistSelection(selectedArtists, searchComponent) {
    const userId = localStorage.getItem('userId');
    console.log('handleArtistSelection called with', selectedArtists.length, 'artists. User:', userId);

    // Use passed component or fallback to global (for backward compatibility)
    const component = searchComponent || artistSearchComponent;

    // Sync with database (artists)
    if (userId) {
        try {
            // 1. Get current DB artists
            const res = await fetch(`/api/users/${userId}/selected-artists`);
            if (res.ok) {
                const dbArtists = await res.json();
                const dbArtistNames = new Set(dbArtists.map(a => a.artist_name));
                const selectedNames = new Set(selectedArtists.map(a => a.name));

                // 2. Add new ones
                for (const artist of selectedArtists) {
                    if (!dbArtistNames.has(artist.name)) {
                        console.log(`Adding artist to DB: ${artist.name}`);
                        const addResp = await fetch(`/api/users/${userId}/selected-artists`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                artist_name: artist.name,
                                mbid: artist.mbid || null,
                                source: 'manual'
                            })
                        });

                        if (addResp.ok) {
                            console.log(`✓ Added artist to DB: ${artist.name}`);
                        } else {
                            console.error(`✗ Failed to add artist ${artist.name}:`, addResp.status);
                        }
                    }
                }

                // 3. Remove deleted ones
                for (const dbArtist of dbArtists) {
                    if (!selectedNames.has(dbArtist.artist_name)) {
                        console.log(`Removing artist from DB: ${dbArtist.artist_name}`);
                        const delResp = await fetch(`/api/users/${userId}/selected-artists/${dbArtist.id}`, {
                            method: 'DELETE'
                        });

                        if (delResp.ok) {
                            console.log(`✓ Removed artist from DB: ${dbArtist.artist_name}`);
                        } else {
                            console.error(`✗ Failed to remove artist ${dbArtist.artist_name}:`, delResp.status);
                        }
                    }
                }
            }
        } catch (e) {
            console.error('Error syncing artists with DB:', e);
        }

        // Refresh sidebar to show newly added artists
        if (typeof loadProfileSidebar === 'function') {
            loadProfileSidebar();
        }
    }

    const artistNames = selectedArtists.map(a => a.name);
    localStorage.setItem('selected_artist_names', JSON.stringify(artistNames));


    if (!component) {
        console.error('Artist search component not available');
        closeArtistSearch();
        alert('Error: el componente de búsqueda no está disponible. Por favor, intenta de nuevo.');
        return;
    }

    if (component.pendingPromises.size > 0) {
        console.log(`⏳ Waiting for ${component.pendingPromises.size} pending recommendations...`);
        showLoading(true, 'Finalizando recomendaciones...');
        await component.waitForAllPendingRecommendations();
        showLoading(false);
    }

    closeArtistSearch();

    const loadingStatus = component.getLoadingStatus();
    const cachedRecs = component.getCachedRecommendations();

    console.log(`Cache status: ${cachedRecs.length} recommendations, ${loadingStatus.success}/${loadingStatus.total} successful, ${loadingStatus.error} errors`);

    let finalRecs = [];

    // Strategy: Use cached recommendations if available, otherwise fetch from backend
    if (cachedRecs.length > 0) {
        console.log('✓ Using cached artist recommendations');
        finalRecs = formatArtistRecommendations(cachedRecs);
    } else {
        console.log('⚠ No cached recommendations, falling back to backend generation');
        const title = 'Generando Recomendaciones';
        startProgressMonitoring(title);

        try {
            const response = await fetch('/api/recommendations/artists', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist_names: artistNames })
            });
            const data = await response.json();
            stopProgressMonitoring();
            hideProgressModal();

            if (data.recommendations && data.recommendations.length > 0) {
                finalRecs = formatArtistRecommendations(data.recommendations);
            }
        } catch (error) {
            console.error('Error loading artist recommendations:', error);
            stopProgressMonitoring();
            hideProgressModal();
            alert('Error al cargar recomendaciones. Por favor, intenta de nuevo.');
            return;
        }
    }

    if (finalRecs.length === 0) {
        alert('No se encontraron recomendaciones para estos artistas.');
        return;
    }

    // Save recommendations to DB if user is logged in
    if (userId) {
        try {
            console.log(`Saving ${finalRecs.length} recommendations to database for user ${userId}...`);
            const saveResp = await fetch(`/users/${userId}/recommendations/regenerate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_recs: finalRecs })
            });

            if (saveResp.ok) {
                console.log('✓ Recommendations saved successfully to DB');
                if (typeof showToast === 'function') {
                    showToast('Recomendaciones guardadas correctamente', 'success');
                }
            } else {
                console.error('✗ Failed to save recommendations:', saveResp.status, await saveResp.text());
                if (typeof showToast === 'function') {
                    showToast('Error al guardar recomendaciones', 'error');
                }
            }

            // Reload from DB to ensure consistency (and get IDs, favorites, etc.)
            await fetchUserRecommendations(userId);

        } catch (e) {
            console.error('Error saving recommendations to DB:', e);
            // Fallback to local rendering if DB save fails
            localStorage.setItem('last_recommendations', JSON.stringify(finalRecs));
            localStorage.setItem('last_updated', new Date().toISOString());
            renderRecommendations(finalRecs);
        }
    } else {
        // Guest user: save to localStorage
        localStorage.setItem('last_recommendations', JSON.stringify(finalRecs));
        localStorage.setItem('last_updated', new Date().toISOString());
        renderRecommendations(finalRecs);
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
                source: 'manual'  // Map to 'manual' for DB constraint
            };
        }
        return rec;
    });
}

// Initialize
// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();

    // Check if we just returned from Last.fm authentication
    checkLastfmAuthReturn();

    handleLastfmCallback();


    // If user is logged in, load fresh recommendations from DB
    const userId = localStorage.getItem('userId');
    const lastfmUsername = localStorage.getItem('lastfm_username'); // Ensure we have this

    if (userId) {
        console.log(`🚀 Usuario detectado: ${userId}. Iniciando carga de recomendaciones...`);

        // 1. Try to fetch existing recommendations
        try {
            await fetchUserRecommendations(userId);

            // 2. Check if we actually got anything. If not, and we have a username, force generation.
            const container = document.getElementById('albums-container');
            if ((!container || container.children.length === 0) && lastfmUsername) {
                console.log('⚠️ No hay recomendaciones visibles. Forzando generación inicial...');
                await generateAndSaveRecommendations(userId, lastfmUsername);
            }
        } catch (e) {
            console.error('Error en carga inicial:', e);
        }
    } else {
        // No user yet, keep any cached recommendations
        checkCachedRecommendations();
    }
});
