// Extensions for unified UX - Profile sidebar and action buttons
console.log('app-user-ext.js loaded');

// Album status tracking
const albumStatuses = new Map(); // key: "artist|album", value: "favorite"|"owned"|"disliked"
window.albumStatuses = albumStatuses; // Expose to other scripts

// Load album statuses from localStorage
function loadAlbumStatuses() {
    // localStorage loading removed
    console.log('loadAlbumStatuses: skipping localStorage load, relying on backend sync');
}

// Save album statuses to localStorage and DB
// Save album statuses to localStorage and DB
async function saveAlbumStatuses() {
    // Save to localStorage for guest persistence (using individual keys for callback.html compatibility)
    // First clear old keys to avoid stale data
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('album_status_')) {
            localStorage.removeItem(key);
        }
    }

    // Save current statuses
    albumStatuses.forEach((status, key) => {
        // key is "artist|album", convert to "artist::album" for storage safety
        const storageKey = `album_status_${key.replace('|', '::')}`;
        localStorage.setItem(storageKey, status);
    });

    // Also save to database if user is logged in
    const userId = localStorage.getItem('userId');
    if (userId) {
        // This will be handled by updating recommendation status in DB
    }
}

// Get album key
function getAlbumKey(artist, album) {
    return `${artist}|${album}`;
}

// Set album status
window.setAlbumStatus = async function (artist, album, status, recId = null, skipRender = false) {
    const key = getAlbumKey(artist, album);

    // Toggle off if clicking same status
    if (albumStatuses.get(key) === status) {
        albumStatuses.delete(key);
        status = null;
    } else {
        albumStatuses.set(key, status);
    }

    await saveAlbumStatuses();

    // Update in database if we have a rec ID
    const userId = localStorage.getItem('userId');
    if (userId && recId) {
        try {
            await fetch(`/users/${userId}/recommendations/${recId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_status: status || 'neutral' })
            });
        } catch (e) {
            console.error('Error updating recommendation status:', e);
        }
    }

    // Re-render current filter to update the view
    if (!skipRender && typeof window.filterRecommendations === 'function' && typeof window.currentFilter !== 'undefined') {
        window.filterRecommendations(window.currentFilter);
    }

    return status;
}

// Get album status
window.getAlbumStatus = function (artist, album) {
    const key = getAlbumKey(artist, album);
    const status = albumStatuses.get(key);
    console.log(`[DEBUG getAlbumStatus] artist="${artist}", album="${album}", key="${key}", status="${status}"`);
    return status;
}

// Load and display profile sidebar
window.loadProfileSidebar = async function () {
    const userId = localStorage.getItem('userId');
    const lastfmUsername = localStorage.getItem('lastfm_username');
    const selectedArtistNames = localStorage.getItem('selected_artist_names');

    const placeholder = document.getElementById('sidebar-placeholder');
    const lastfmSection = document.getElementById('lastfm-artists-section');
    const selectedSection = document.getElementById('selected-artists-section');

    let hasContent = false;

    // Load Last.fm top artists
    if (userId && lastfmUsername) {
        try {
            const res = await fetch(`/api/users/${userId}/profile/lastfm`);
            if (res.ok) {
                const profile = await res.json();
                console.log('[DEBUG] Last.fm profile response:', profile);

                let artists = profile.top_artists || [];

                // Robust handling for data structure
                if (!Array.isArray(artists)) {
                    console.warn('[DEBUG] top_artists is not an array, attempting to extract...', typeof artists);
                    if (artists.artist && Array.isArray(artists.artist)) {
                        artists = artists.artist;
                    } else if (artists.artists && Array.isArray(artists.artists)) {
                        artists = artists.artists;
                    } else {
                        // Fallback: try to convert object values if it looks like a list-as-object
                        const values = Object.values(artists);
                        if (values.length > 0 && (values[0].name || values[0].artist_name)) {
                            artists = values;
                        }
                    }
                }

                console.log(`Loaded ${artists ? artists.length : 0} Last.fm top artists for sidebar`);

                if (artists && artists.length > 0) {
                    const list = document.getElementById('lastfm-artists-list');
                    list.innerHTML = '';

                    artists.slice(0, 10).forEach(artist => {
                        const li = document.createElement('li');
                        const name = typeof artist === 'string' ? artist : artist.name;
                        const playcount = artist.playcount || 0;
                        li.innerHTML = `
                            <span>${name}</span>
                            <span class="artist-playcount">${playcount} plays</span>
                        `;
                        list.appendChild(li);
                    });

                    lastfmSection.style.display = 'block';
                    hasContent = true;
                }
            } else if (res.status === 404) {
                // Profile not found - this is normal for new users
                console.log('No Last.fm profile found for user (this is normal for new users)');
            } else {
                console.error('Error loading Last.fm profile:', res.status, res.statusText);
            }
        } catch (e) {
            console.error('Error loading Last.fm profile:', e);
        }
    }

    // Load selected artists
    if (userId) {
        try {
            console.log('[DEBUG] Fetching selected artists for sidebar...');
            const res = await fetch(`/api/users/${userId}/selected-artists`);
            if (res.ok) {
                const artists = await res.json();
                console.log('[DEBUG] Selected artists response:', artists);
                if (artists.length > 0) {
                    const list = document.getElementById('selected-artists-list');
                    list.innerHTML = '';

                    artists.forEach(artist => {
                        const li = document.createElement('li');
                        li.textContent = artist.artist_name;
                        list.appendChild(li);
                    });

                    selectedSection.style.display = 'block';
                    hasContent = true;
                } else {
                    console.log('[DEBUG] No selected artists found');
                }
            } else {
                console.error('[DEBUG] Failed to fetch selected artists:', res.status);
            }
        } catch (e) {
            console.error('Error loading selected artists:', e);
        }
    }

    // Show/hide placeholder
    placeholder.style.display = hasContent ? 'none' : 'block';
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadAlbumStatuses();
});
