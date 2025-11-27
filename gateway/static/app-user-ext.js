// Extensions for unified UX - Profile sidebar and action buttons
console.log('app-user-ext.js loaded');

// Album status tracking
const albumStatuses = new Map(); // key: "artist|album", value: "favorite"|"owned"|"disliked"

// Load album statuses from localStorage
function loadAlbumStatuses() {
    // localStorage loading removed
    console.log('loadAlbumStatuses: skipping localStorage load, relying on backend sync');
}

// Save album statuses to localStorage and DB
async function saveAlbumStatuses() {
    // localStorage saving removed
    // const data = Object.fromEntries(albumStatuses);
    // localStorage.setItem('album_statuses', JSON.stringify(data));

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
    return albumStatuses.get(getAlbumKey(artist, album));
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
                if (profile.top_artists && profile.top_artists.length > 0) {
                    const list = document.getElementById('lastfm-artists-list');
                    list.innerHTML = '';

                    profile.top_artists.slice(0, 10).forEach(artist => {
                        const li = document.createElement('li');
                        li.innerHTML = `
                            <span>${artist.name}</span>
                            <span class="artist-playcount">${artist.playcount || 0} plays</span>
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
    // Load selected artists
    if (userId) {
        try {
            const res = await fetch(`/api/users/${userId}/selected-artists`);
            if (res.ok) {
                const artists = await res.json();
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
                }
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
