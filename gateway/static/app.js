const API_BASE = "";

// -------------------------------------------------
// Helpers
// -------------------------------------------------
function getUserId() {
    const id = localStorage.getItem('userId');
    if (!id && window.location.pathname !== '/login.html') {
        window.location.href = '/login.html';
        return null;
    }
    return id;
}

function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);

    try {
        const res = await fetch(API_BASE + endpoint, options);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || `Error ${res.status}`);
        }
        return await res.json();
    } catch (e) {
        showToast(e.message, 'error');
        throw e;
    }
}

// -------------------------------------------------
// Auth
// -------------------------------------------------
async function loginGoogle(email, displayName, googleSub) {
    try {
        const data = await apiCall('/auth/google', 'POST', { email, display_name: displayName, google_sub: googleSub });
        localStorage.setItem('userId', data.user_id);
        window.location.href = '/index.html';
    } catch (e) { console.error(e); }
}

/* Updated Last.fm login flow – opens popup immediately to avoid blocker */
/* Robust Last.fm login flow – Manual Confirmation Fallback */
async function loginLastfm() {
    // 1. Open popup immediately
    const popup = window.open('', 'lastfm-auth', 'width=600,height=700');
    if (!popup) {
        showToast('El navegador bloqueó la ventana emergente. Permite pop‑ups y vuelve a intentarlo.', 'error');
        return;
    }

    try {
        // 2. Get Auth URL
        const res = await apiCall('/auth/lastfm/login');
        if (!res.auth_url || !res.token) {
            showToast('Error de configuración con Last.fm', 'error');
            popup.close();
            return;
        }

        // 3. Navigate popup
        popup.location = res.auth_url;

        // 4. Show "I have authorized" button (Plan B for when callback fails)
        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = '✅ Ya autoricé en Last.fm';
        confirmBtn.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:10000;padding:20px 40px;background:#d51007;color:white;border:none;border-radius:12px;font-size:18px;font-weight:bold;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,0.5);';

        confirmBtn.onclick = async () => {
            console.log('Verificando token manualmente:', res.token);
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Verificando...';

            try {
                // Manually check the token
                const callbackRes = await apiCall(`/auth/lastfm/callback?token=${res.token}`);
                console.log('Respuesta callback:', callbackRes);

                if (callbackRes.status === 'ok' && callbackRes.username) {
                    console.log('Autenticación exitosa, creando usuario...');
                    const authRes = await apiCall('/auth/lastfm', 'POST', { lastfm_username: callbackRes.username });

                    localStorage.setItem('userId', authRes.user_id);
                    // Store username too for generation fallback
                    if (callbackRes.username) localStorage.setItem('lastfm_username', callbackRes.username);

                    console.log('Usuario guardado:', authRes.user_id);

                    if (!popup.closed) popup.close();
                    document.body.removeChild(confirmBtn);
                    window.location.href = '/index.html';
                } else {
                    throw new Error('La respuesta del servidor no fue OK');
                }
            } catch (e) {
                console.error('Error en verificación manual:', e);
                confirmBtn.disabled = false;
                confirmBtn.style.backgroundColor = '#dc3545'; // Rojo error
                confirmBtn.textContent = '❌ No detectado. Reintentar';
                setTimeout(() => {
                    confirmBtn.textContent = '✅ Ya autoricé en Last.fm';
                    confirmBtn.style.backgroundColor = '#d51007'; // Rojo original
                }, 3000);
            }
        };

        document.body.appendChild(confirmBtn);

        // Eliminamos el listener automático para evitar conflictos
        // window.addEventListener('message', ... ); 

    } catch (e) {
        console.error(e);
        showToast('Error al iniciar sesión', 'error');
        if (!popup.closed) popup.close();
    }
}

// Backward‑compatible alias (in case other code uses the old name)
const loginLastFm = loginLastfm;

// Handle callback from Last.fm (check URL params on load)
async function handleLastFmCallback() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
        try {
            // Exchange token for session/user
            const res = await apiCall(`/auth/lastfm/callback?token=${token}`);
            if (res.status === 'ok' && res.username) {
                // Now create/get user in our DB
                const authRes = await apiCall('/auth/lastfm', 'POST', { lastfm_username: res.username });
                localStorage.setItem('userId', authRes.user_id);

                // Clean URL
                window.history.replaceState({}, document.title, "/index.html");
                window.location.href = '/index.html';
            }
        } catch (e) {
            console.error(e);
            showToast('Last.fm authentication failed', 'error');
        }
    }
}

// Call on load if we are on login page or index
if (window.location.pathname.includes('login') || window.location.pathname === '/' || window.location.pathname.includes('index')) {
    handleLastFmCallback();
}

async function handleManualLogin() {
    const username = document.getElementById('manual-username').value.trim();
    if (!username) return;

    try {
        // Directly create/get user with this username
        const authRes = await apiCall('/auth/lastfm', 'POST', { lastfm_username: username });
        localStorage.setItem('userId', authRes.user_id);
        window.location.href = '/index.html';
    } catch (e) {
        console.error(e);
        showToast('Login failed', 'error');
    }
}

async function linkLastFm(username) {
    const uid = getUserId();
    if (!uid) return;
    try {
        await apiCall('/auth/lastfm/link', 'POST', { user_id: parseInt(uid), lastfm_username: username });
        showToast('Account linked successfully', 'success');
        setTimeout(() => window.location.reload(), 1000);
    } catch (e) { console.error(e); }
}

// -------------------------------------------------
// Profile
// -------------------------------------------------
async function loadProfile() {
    const uid = getUserId();
    if (!uid) return;

    try {
        const profile = await apiCall(`/users/${uid}/profile/lastfm`);
        document.getElementById('profile-username').textContent = profile.lastfm_username;
        document.getElementById('profile-updated').textContent = new Date(profile.generated_at).toLocaleDateString();

        const container = document.getElementById('top-artists-grid');
        container.innerHTML = '';

        if (profile.top_artists && profile.top_artists.length) {
            profile.top_artists.forEach(artist => {
                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `
                    <h3>${artist.name}</h3>
                    <p>${artist.playcount || 0} plays</p>
                `;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">No top artists found.</p>';
        }
    } catch (e) {
        if (e.message.includes('404')) {
            document.getElementById('profile-content').innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <p>No Last.fm profile linked.</p>
                    <button class="btn" onclick="document.getElementById('link-modal').showModal()">Link Last.fm</button>
                </div>
            `;
        }
    }
}

// -------------------------------------------------
// Artists
// -------------------------------------------------
async function loadSelectedArtists() {
    const uid = getUserId();
    if (!uid) return;

    const artists = await apiCall(`/users/${uid}/selected-artists`);
    const tbody = document.getElementById('artists-table-body');
    tbody.innerHTML = '';

    artists.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${a.artist_name}</td>
            <td>${a.source}</td>
            <td>${new Date(a.created_at).toLocaleDateString()}</td>
            <td style="text-align: right;">
                <button class="btn btn-sm btn-danger" onclick="removeArtist(${a.id})">Remove</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function addArtist(name) {
    const uid = getUserId();
    if (!uid) return;
    try {
        await apiCall(`/users/${uid}/selected-artists`, 'POST', { artist_name: name, source: 'manual' });
        showToast(`Added ${name}`, 'success');
        loadSelectedArtists();
        return true;
    } catch (e) { return false; }
}

async function removeArtist(id) {
    const uid = getUserId();
    if (!uid) return;
    if (!confirm('Are you sure?')) return;

    try {
        await apiCall(`/users/${uid}/selected-artists/${id}`, 'DELETE');
        showToast('Artist removed', 'success');
        loadSelectedArtists();
    } catch (e) { console.error(e); }
}

// -------------------------------------------------
// Recommendations
// -------------------------------------------------
async function loadRecommendations(includeFav = true) {
    const uid = getUserId();
    if (!uid) return;

    const endpoint = includeFav ?
        `/users/${uid}/recommendations` :
        `/users/${uid}/recommendations?include_favorites=false`;

    const recs = await apiCall(endpoint);
    renderRecommendations(recs);
}

function renderRecommendations(recs) {
    const container = document.getElementById('albums-container');
    if (!container) {
        console.error('albums-container not found in DOM');
        return;
    }

    container.innerHTML = '';

    if (recs.length === 0) {
        container.innerHTML = '<p style="grid-column: 1/-1; text-align: center; padding: 2rem;">No recommendations yet. Try regenerating.</p>';
        return;
    }

    recs.forEach(r => {
        const card = document.createElement('div');
        card.className = `card rec-card ${r.status === 'favorite' ? 'fav-selected' : ''} ${r.status === 'disliked' ? 'disliked' : ''} ${r.status === 'owned' ? 'owned' : ''}`;
        card.dataset.id = r.id;

        card.innerHTML = `
            <h3>${r.artist_name}</h3>
            <p style="font-size: 1rem; color: #fff; margin-bottom: 0.5rem;">${r.album_title}</p>
            <p>Source: ${r.source}</p>
            <div class="actions">
                <button class="btn-sm ${r.status === 'favorite' ? 'active-fav' : ''}" onclick="updateRecStatus(${r.id}, 'favorite')">★</button>
                <button class="btn-sm ${r.status === 'disliked' ? 'active-dislike' : ''}" onclick="updateRecStatus(${r.id}, 'disliked')">✖</button>
                <button class="btn-sm ${r.status === 'owned' ? 'active-owned' : ''}" onclick="updateRecStatus(${r.id}, 'owned')">✅</button>
            </div>
        `;
        container.appendChild(card);
    });
}

async function updateRecStatus(recId, newStatus) {
    const uid = getUserId();
    if (!uid) return;

    try {
        await apiCall(`/users/${uid}/recommendations/${recId}`, 'PATCH', { new_status: newStatus });
        // Optimistic update or reload
        loadRecommendations(document.getElementById('show-favs')?.checked ?? true);
    } catch (e) { console.error(e); }
}

async function regenerateRecs() {
    const uid = getUserId();
    if (!uid) return;

    const btn = document.getElementById('regen-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Generating...';
    btn.disabled = true;

    try {
        // In a real app, this would call the recommender service to get new recs
        // For now, we'll simulate it or pass dummy data if the backend expects it
        // The backend endpoint expects 'new_recs' list.
        // We'll fetch from the *existing* recommender endpoints (e.g. /api/recommendations/artists) 
        // and then pass that to the persistence layer.
        // -------------------------------------------------
        // Artist Search
        // -------------------------------------------------
        async function searchArtists(query) {
            if (!query || query.length < 2) return [];
            try {
                const res = await apiCall(`/api/lastfm/search?q=${encodeURIComponent(query)}`);
                // The backend returns { artists: [...] } or just a list
                return res.artists || res || [];
            } catch (e) {
                console.error(e);
                return [];
            }
        }

        async function selectArtistFromSearch(artistName, mbid) {
            const uid = getUserId();
            if (!uid) return;
            try {
                await apiCall(`/users/${uid}/selected-artists`, 'POST', {
                    artist_name: artistName,
                    mbid: mbid,
                    source: 'manual'
                });
                showToast(`Added ${artistName}`, 'success');
                // Refresh lists if on relevant pages
                if (document.getElementById('artists-table-body')) loadSelectedArtists();
                return true;
            } catch (e) { return false; }
        }
        // 1. Get selected artists
        const artists = await apiCall(`/users/${uid}/selected-artists`);
        const artistNames = artists.map(a => a.artist_name);

        let newRecs = [];

        if (artistNames.length >= 3) {
            // Call the recommender service (proxied via gateway)
            const recResp = await apiCall('/api/recommendations/artists', 'POST', { artist_names: artistNames.slice(0, 5) });
            newRecs = recResp.recommendations.map(r => ({
                artist_name: r.artist,
                album_title: r.album,
                album_mbid: r.mbid,
                source: 'mixed'
            }));
        } else {
            // Fallback or error
            showToast('Select at least 3 artists first!', 'warning');
            btn.innerHTML = originalText;
            btn.disabled = false;
            return;
        }

        // 2. Save to DB
        await apiCall(`/users/${uid}/recommendations/regenerate`, 'POST', { new_recs: newRecs });

        showToast('Recommendations regenerated!', 'success');
        loadRecommendations();

    } catch (e) {
        console.error(e);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}
