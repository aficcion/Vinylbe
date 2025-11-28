// Database Explorer App
class DatabaseExplorer {
    constructor() {
        this.currentView = 'dashboard';
        this.currentPage = {
            artists: 1,
            albums: 1
        };
        this.searchTimers = {};

        this.init();
    }

    init() {
        this.setupNavigation();
        this.setupSearch();
        this.setupRefresh();
        this.loadDashboard();
    }

    // Navigation
    setupNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const view = item.dataset.view;
                this.switchView(view);
            });
        });
    }

    switchView(view) {
        // Update nav
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === view);
        });

        // Update views
        document.querySelectorAll('.view').forEach(v => {
            v.classList.toggle('active', v.id === `${view}View`);
        });

        this.currentView = view;

        // Load view data
        switch (view) {
            case 'dashboard':
                this.loadDashboard();
                break;
            case 'artists':
                this.loadArtists();
                break;
            case 'albums':
                this.loadAlbums();
                break;
            case 'users':
                this.loadUsers();
                break;
            case 'stats':
                this.loadStats();
                break;
        }
    }

    // Search
    setupSearch() {
        const globalSearch = document.getElementById('globalSearch');
        const artistSearch = document.getElementById('artistSearch');
        const albumSearch = document.getElementById('albumSearch');

        globalSearch.addEventListener('input', (e) => {
            this.debounce('global', () => this.globalSearch(e.target.value), 300);
        });

        artistSearch.addEventListener('input', (e) => {
            this.debounce('artists', () => this.loadArtists(1, e.target.value), 300);
        });

        albumSearch.addEventListener('input', (e) => {
            this.debounce('albums', () => this.loadAlbums(1, e.target.value), 300);
        });
    }

    debounce(key, func, wait) {
        clearTimeout(this.searchTimers[key]);
        this.searchTimers[key] = setTimeout(func, wait);
    }

    async globalSearch(query) {
        if (!query) return;

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            // Show results (you can implement a dropdown here)
            console.log('Search results:', data);
        } catch (error) {
            console.error('Search error:', error);
        }
    }

    // Refresh
    setupRefresh() {
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.switchView(this.currentView);
        });
    }

    // Dashboard
    async loadDashboard() {
        this.showLoading();

        try {
            const response = await fetch('/api/summary');
            const data = await response.json();

            this.renderStats(data.table_counts);
            this.renderMosaic(data.mosaic_albums);
            this.renderTopArtists(data.top_artists);
            this.renderTopAlbums(data.top_albums);
        } catch (error) {
            console.error('Error loading dashboard:', error);
        } finally {
            this.hideLoading();
        }
    }

    renderStats(counts) {
        const statsGrid = document.getElementById('statsGrid');

        const stats = [
            { label: 'Artistas', value: counts.artists || 0, icon: '🎤' },
            { label: 'Álbumes', value: counts.albums || 0, icon: '💿' },
            { label: 'Usuarios', value: counts.user || 0, icon: '👥' },
            { label: 'Recomendaciones', value: counts.recommendation || 0, icon: '⭐' }
        ];

        statsGrid.innerHTML = stats.map(stat => `
            <div class="stat-card">
                <div class="stat-label">${stat.icon} ${stat.label}</div>
                <div class="stat-value">${stat.value.toLocaleString()}</div>
            </div>
        `).join('');
    }

    renderMosaic(albums) {
        const grid = document.getElementById('mosaicGrid');
        if (!grid || !albums || albums.length === 0) return;

        // Shuffle array for randomness on frontend too
        const shuffled = [...albums].sort(() => 0.5 - Math.random());

        // Take enough to fill the grid (approx 50)
        const displayAlbums = shuffled.slice(0, 50);

        grid.innerHTML = displayAlbums.map(album => `
            <div class="mosaic-item" title="${this.escapeHtml(album.title)}">
                <img src="${album.cover_url}" 
                     loading="lazy"
                     alt="${this.escapeHtml(album.title)}"
                     onerror="this.style.display='none'">
            </div>
        `).join('');
    }

    renderTopArtists(artists) {
        const container = document.getElementById('topArtists');

        container.innerHTML = artists.map(artist => `
            <div class="list-item" onclick="app.showArtistDetail(${artist.id || 0})">
                <img src="${artist.image_url || 'https://via.placeholder.com/48?text=🎤'}" 
                     class="list-item-image" 
                     onerror="this.src='https://via.placeholder.com/48?text=🎤'">
                <div class="list-item-content">
                    <div class="list-item-title">${this.escapeHtml(artist.name)}</div>
                    <div class="list-item-subtitle">${artist.album_count} álbumes</div>
                </div>
                <div class="list-item-meta">
                    <div class="list-item-value">${artist.album_count}</div>
                    <div class="list-item-label">álbumes</div>
                </div>
            </div>
        `).join('');
    }

    renderTopAlbums(albums) {
        const container = document.getElementById('topAlbums');

        container.innerHTML = albums.map(album => `
            <div class="list-item">
                <img src="${album.cover_url || 'https://via.placeholder.com/48?text=💿'}" 
                     class="list-item-image"
                     onerror="this.src='https://via.placeholder.com/48?text=💿'">
                <div class="list-item-content">
                    <div class="list-item-title">${this.escapeHtml(album.title)}</div>
                    <div class="list-item-subtitle">${this.escapeHtml(album.artist)} • ${album.year}</div>
                </div>
                <div class="list-item-meta">
                    <div class="list-item-value">⭐ ${album.rating.toFixed(1)}</div>
                    <div class="list-item-label">${album.votes} votos</div>
                </div>
            </div>
        `).join('');
    }

    // Artists
    async loadArtists(page = 1, search = '') {
        this.showLoading();
        this.currentPage.artists = page;

        try {
            const response = await fetch(`/api/artists?page=${page}&per_page=20&search=${encodeURIComponent(search)}`);
            const data = await response.json();

            this.renderArtistsGrid(data.artists);
            this.renderPagination('artists', data);
        } catch (error) {
            console.error('Error loading artists:', error);
        } finally {
            this.hideLoading();
        }
    }

    renderArtistsGrid(artists) {
        const grid = document.getElementById('artistsGrid');

        if (artists.length === 0) {
            grid.innerHTML = '<p style="text-align: center; color: var(--text-tertiary); padding: 40px;">No se encontraron artistas</p>';
            return;
        }

        grid.innerHTML = artists.map(artist => `
            <div class="grid-item">
                <div class="grid-item-actions action-buttons">
                    <button class="btn-action edit" onclick="app.editArtist(${artist.id})" title="Editar">
                        ✏️
                    </button>
                    <button class="btn-action delete" onclick="app.confirmDeleteArtist(${artist.id}, '${this.escapeHtml(artist.name).replace(/'/g, "\\'")}')" title="Eliminar">
                        🗑️
                    </button>
                </div>
                <img src="${artist.image_url || 'https://via.placeholder.com/200?text=🎤'}" 
                     class="grid-item-image"
                     onerror="this.src='https://via.placeholder.com/200?text=🎤'"
                     onclick="app.showArtistDetail(${artist.id})">
                <div class="grid-item-content" onclick="app.showArtistDetail(${artist.id})">
                    <div class="grid-item-title">${this.escapeHtml(artist.name)}</div>
                    <div class="grid-item-subtitle">${artist.album_count} álbumes</div>
                    ${artist.mbid ? `<div class="grid-item-meta">
                        <span style="font-size: 11px; color: var(--text-tertiary);">MBID</span>
                    </div>` : ''}
                </div>
            </div>
        `).join('');
    }

    async editArtist(artistId) {
        this.showLoading();

        try {
            const response = await fetch(`/api/artist/${artistId}`);
            const data = await response.json();
            const artist = data.artist;

            const modal = document.getElementById('artistModal');
            const title = document.getElementById('artistModalTitle');
            const body = document.getElementById('artistModalBody');

            title.textContent = 'Editar Artista';

            body.innerHTML = `
                <form class="edit-form" onsubmit="app.saveArtist(event, ${artistId})">
                    <div class="form-group">
                        <label>Nombre del Artista</label>
                        <input type="text" id="artistName" value="${this.escapeHtml(artist.name)}" required>
                    </div>
                    
                    <div class="form-group">
                        <label>URL de Imagen</label>
                        <input type="url" id="artistImage" value="${artist.image_url || ''}" placeholder="https://...">
                    </div>
                    
                    <div class="form-group">
                        <label>MusicBrainz ID</label>
                        <input type="text" id="artistMbid" value="${artist.mbid || ''}" readonly>
                        <small style="color: var(--text-tertiary); font-size: 12px;">Este campo no se puede editar</small>
                    </div>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('artistModal').classList.remove('active')">
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-primary">
                            Guardar Cambios
                        </button>
                    </div>
                </form>
            `;

            modal.classList.add('active');

            // Close modal handlers
            modal.querySelector('.modal-close').onclick = () => modal.classList.remove('active');
            modal.onclick = (e) => {
                if (e.target === modal) modal.classList.remove('active');
            };

        } catch (error) {
            console.error('Error loading artist for edit:', error);
            this.showToast('Error', 'No se pudo cargar el artista', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async saveArtist(event, artistId) {
        event.preventDefault();
        this.showLoading();

        const name = document.getElementById('artistName').value;
        const image_url = document.getElementById('artistImage').value;

        try {
            const response = await fetch(`/api/update/artist/${artistId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name, image_url })
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Éxito!', 'Artista actualizado correctamente', 'success');
                document.getElementById('artistModal').classList.remove('active');
                this.loadArtists(this.currentPage.artists);
            } else {
                this.showToast('Error', 'No se pudo actualizar el artista', 'error');
            }
        } catch (error) {
            console.error('Error saving artist:', error);
            this.showToast('Error', 'No se pudo actualizar el artista', 'error');
        } finally {
            this.hideLoading();
        }
    }

    confirmDeleteArtist(artistId, artistName) {
        this.showConfirmDialog(
            '¿Eliminar Artista?',
            `¿Estás seguro de que quieres eliminar a "${artistName}" y todos sus álbumes? Esta acción no se puede deshacer.`,
            () => this.deleteArtist(artistId, artistName)
        );
    }

    async deleteArtist(artistId, artistName) {
        this.showLoading();

        try {
            const response = await fetch(`/api/delete/artist/${artistId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Eliminado!', `${artistName} ha sido eliminado`, 'success');
                this.loadArtists(this.currentPage.artists);
            } else {
                this.showToast('Error', 'No se pudo eliminar el artista', 'error');
            }
        } catch (error) {
            console.error('Error deleting artist:', error);
            this.showToast('Error', 'No se pudo eliminar el artista', 'error');
        } finally {
            this.hideLoading();
        }
    }


    async showArtistDetail(artistId) {
        this.showLoading();

        try {
            const response = await fetch(`/api/artist/${artistId}`);
            const data = await response.json();

            const modal = document.getElementById('artistModal');
            const title = document.getElementById('artistModalTitle');
            const body = document.getElementById('artistModalBody');

            title.textContent = data.artist.name;

            body.innerHTML = `
                <div style="display: flex; gap: 24px; margin-bottom: 24px;">
                    <img src="${data.artist.image_url || 'https://via.placeholder.com/150?text=🎤'}" 
                         style="width: 150px; height: 150px; border-radius: var(--radius-lg); object-fit: cover;"
                         onerror="this.src='https://via.placeholder.com/150?text=🎤'">
                    <div style="flex: 1;">
                        <h3 style="margin-bottom: 8px;">${this.escapeHtml(data.artist.name)}</h3>
                        <p style="color: var(--text-tertiary); margin-bottom: 16px;">${data.albums.length} álbumes en la colección</p>
                        ${data.artist.mbid ? `<p style="font-size: 12px; color: var(--text-tertiary); font-family: monospace;">MBID: ${data.artist.mbid}</p>` : ''}
                    </div>
                </div>
                
                <h4 style="margin-bottom: 16px;">Discografía</h4>
                <div style="display: grid; gap: 12px;">
                    ${data.albums.map(album => `
                        <div style="display: flex; gap: 16px; padding: 12px; background: var(--bg-tertiary); border-radius: var(--radius-md);">
                            <img src="${album.cover_url || 'https://via.placeholder.com/60?text=💿'}" 
                                 style="width: 60px; height: 60px; border-radius: var(--radius-md); object-fit: cover;"
                                 onerror="this.src='https://via.placeholder.com/60?text=💿'">
                            <div style="flex: 1;">
                                <div style="font-weight: 600; margin-bottom: 4px;">${this.escapeHtml(album.title)}</div>
                                <div style="font-size: 13px; color: var(--text-tertiary);">
                                    ${album.year || 'Unknown year'}
                                    ${album.rating ? ` • ⭐ ${album.rating.toFixed(1)} (${album.votes} votos)` : ''}
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;

            modal.classList.add('active');

            // Close modal handlers
            modal.querySelector('.modal-close').onclick = () => modal.classList.remove('active');
            modal.onclick = (e) => {
                if (e.target === modal) modal.classList.remove('active');
            };

        } catch (error) {
            console.error('Error loading artist detail:', error);
        } finally {
            this.hideLoading();
        }
    }

    // Albums
    async loadAlbums(page = 1, search = '') {
        this.showLoading();
        this.currentPage.albums = page;

        try {
            const response = await fetch(`/api/albums?page=${page}&per_page=20&search=${encodeURIComponent(search)}`);
            const data = await response.json();

            this.renderAlbumsGrid(data.albums);
            this.renderPagination('albums', data);
        } catch (error) {
            console.error('Error loading albums:', error);
        } finally {
            this.hideLoading();
        }
    }

    renderAlbumsGrid(albums) {
        const grid = document.getElementById('albumsGrid');

        if (albums.length === 0) {
            grid.innerHTML = '<p style="text-align: center; color: var(--text-tertiary); padding: 40px;">No se encontraron álbumes</p>';
            return;
        }

        grid.innerHTML = albums.map(album => `
            <div class="grid-item">
                <div class="grid-item-actions action-buttons">
                    <button class="btn-action edit" onclick="app.editAlbum(${album.id})" title="Editar">
                        ✏️
                    </button>
                    <button class="btn-action delete" onclick="app.confirmDeleteAlbum(${album.id}, '${this.escapeHtml(album.title).replace(/'/g, "\\'")}')" title="Eliminar">
                        🗑️
                    </button>
                </div>
                <img src="${album.cover_url || 'https://via.placeholder.com/200?text=💿'}" 
                     class="grid-item-image"
                     onerror="this.src='https://via.placeholder.com/200?text=💿'">
                <div class="grid-item-content">
                    <div class="grid-item-title">${this.escapeHtml(album.title)}</div>
                    <div class="grid-item-subtitle">${this.escapeHtml(album.artist_name)}</div>
                    <div class="grid-item-meta">
                        <span>${album.year || '—'}</span>
                        ${album.rating ? `<span class="rating">⭐ ${album.rating.toFixed(1)}</span>` : ''}
                    </div>
                </div>
            </div>
        `).join('');
    }

    async editAlbum(albumId) {
        this.showLoading();

        try {
            const response = await fetch(`/api/album/${albumId}`);
            const data = await response.json();
            const album = data.album;

            const modal = document.getElementById('artistModal');
            const title = document.getElementById('artistModalTitle');
            const body = document.getElementById('artistModalBody');

            title.textContent = 'Editar Álbum';

            body.innerHTML = `
                <form class="edit-form" onsubmit="app.saveAlbum(event, ${albumId})">
                    <div class="form-group">
                        <label>Título del Álbum</label>
                        <input type="text" id="albumTitle" value="${this.escapeHtml(album.title)}" required>
                    </div>
                    
                    <div class="form-group">
                        <label>Año</label>
                        <input type="text" id="albumYear" value="${album.year || ''}" placeholder="1973">
                    </div>
                    
                    <div class="form-group">
                        <label>URL de Portada</label>
                        <input type="url" id="albumCover" value="${album.cover_url || ''}" placeholder="https://...">
                    </div>
                    
                    <div class="form-group">
                        <label>Artista</label>
                        <input type="text" value="${this.escapeHtml(album.artist_name || '')}" readonly>
                        <small style="color: var(--text-tertiary); font-size: 12px;">El artista no se puede cambiar</small>
                    </div>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('artistModal').classList.remove('active')">
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-primary">
                            Guardar Cambios
                        </button>
                    </div>
                </form>
            `;

            modal.classList.add('active');

            modal.querySelector('.modal-close').onclick = () => modal.classList.remove('active');
            modal.onclick = (e) => {
                if (e.target === modal) modal.classList.remove('active');
            };

        } catch (error) {
            console.error('Error loading album for edit:', error);
            this.showToast('Error', 'No se pudo cargar el álbum', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async saveAlbum(event, albumId) {
        event.preventDefault();
        this.showLoading();

        const title = document.getElementById('albumTitle').value;
        const year = document.getElementById('albumYear').value;
        const cover_url = document.getElementById('albumCover').value;

        try {
            const response = await fetch(`/api/update/album/${albumId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ title, year, cover_url })
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Éxito!', 'Álbum actualizado correctamente', 'success');
                document.getElementById('artistModal').classList.remove('active');
                this.loadAlbums(this.currentPage.albums);
            } else {
                this.showToast('Error', 'No se pudo actualizar el álbum', 'error');
            }
        } catch (error) {
            console.error('Error saving album:', error);
            this.showToast('Error', 'No se pudo actualizar el álbum', 'error');
        } finally {
            this.hideLoading();
        }
    }

    confirmDeleteAlbum(albumId, albumTitle) {
        this.showConfirmDialog(
            '¿Eliminar Álbum?',
            `¿Estás seguro de que quieres eliminar "${albumTitle}"? Esta acción no se puede deshacer.`,
            () => this.deleteAlbum(albumId, albumTitle)
        );
    }

    async deleteAlbum(albumId, albumTitle) {
        this.showLoading();

        try {
            const response = await fetch(`/api/delete/album/${albumId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Eliminado!', `${albumTitle} ha sido eliminado`, 'success');
                this.loadAlbums(this.currentPage.albums);
            } else {
                this.showToast('Error', 'No se pudo eliminar el álbum', 'error');
            }
        } catch (error) {
            console.error('Error deleting album:', error);
            this.showToast('Error', 'No se pudo eliminar el álbum', 'error');
        } finally {
            this.hideLoading();
        }
    }


    // Users
    async loadUsers() {
        this.showLoading();

        try {
            const response = await fetch('/api/users');
            const data = await response.json();

            this.renderUsersTable(data.users);
        } catch (error) {
            console.error('Error loading users:', error);
        } finally {
            this.hideLoading();
        }
    }

    renderUsersTable(users) {
        const container = document.getElementById('usersTable');

        if (users.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-tertiary); padding: 40px;">No hay usuarios</p>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Nombre</th>
                        <th>Email</th>
                        <th>Recomendaciones</th>
                        <th>Favoritos</th>
                        <th>Artistas</th>
                        <th>Creado</th>
                        <th>Último Login</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(user => `
                        <tr>
                            <td>${user.id}</td>
                            <td>${this.escapeHtml(user.display_name || 'Sin nombre')}</td>
                            <td>${this.escapeHtml(user.email || '—')}</td>
                            <td>${user.total_recommendations}</td>
                            <td>${user.favorites}</td>
                            <td>${user.selected_artists}</td>
                            <td>${this.formatDate(user.created_at)}</td>
                            <td>${this.formatDate(user.last_login_at)}</td>
                            <td>
                                <div style="display: flex; gap: 8px;">
                                    <button class="btn-action edit" onclick="app.editUser(${user.id})" title="Editar">
                                        ✏️
                                    </button>
                                    <button class="btn-action delete" onclick="app.confirmDeleteUser(${user.id}, '${this.escapeHtml(user.display_name || 'Usuario').replace(/'/g, "\\'")}')" title="Eliminar">
                                        🗑️
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>

        `;
    }

    async editUser(userId) {
        this.showLoading();

        try {
            const response = await fetch(`/api/user/${userId}`);
            const data = await response.json();
            const user = data.user;

            const modal = document.getElementById('artistModal');
            const title = document.getElementById('artistModalTitle');
            const body = document.getElementById('artistModalBody');

            title.textContent = 'Editar Usuario';

            body.innerHTML = `
                <form class="edit-form" onsubmit="app.saveUser(event, ${userId})">
                    <div class="form-group">
                        <label>Nombre para Mostrar</label>
                        <input type="text" id="userDisplayName" value="${this.escapeHtml(user.display_name || '')}" placeholder="Nombre del usuario">
                    </div>
                    
                    <div class="form-group">
                        <label>Email</label>
                        <input type="email" id="userEmail" value="${user.email || ''}" placeholder="usuario@ejemplo.com">
                    </div>
                    
                    <div class="form-group">
                        <label>ID de Usuario</label>
                        <input type="text" value="${user.id}" readonly>
                        <small style="color: var(--text-tertiary); font-size: 12px;">Este campo no se puede editar</small>
                    </div>
                    
                    <div class="form-group">
                        <label>Fecha de Creación</label>
                        <input type="text" value="${this.formatDate(user.created_at)}" readonly>
                        <small style="color: var(--text-tertiary); font-size: 12px;">Este campo no se puede editar</small>
                    </div>
                    
                    <div style="background: var(--bg-tertiary); padding: 16px; border-radius: var(--radius-md); margin-bottom: 16px;">
                        <h4 style="margin-bottom: 12px; font-size: 14px;">Estadísticas del Usuario</h4>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; font-size: 13px;">
                            <div>
                                <div style="color: var(--text-tertiary);">Recomendaciones</div>
                                <div style="font-weight: 600; color: var(--accent-primary);">${user.total_recommendations || 0}</div>
                            </div>
                            <div>
                                <div style="color: var(--text-tertiary);">Favoritos</div>
                                <div style="font-weight: 600; color: var(--accent-primary);">${user.favorites || 0}</div>
                            </div>
                            <div>
                                <div style="color: var(--text-tertiary);">Artistas</div>
                                <div style="font-weight: 600; color: var(--accent-primary);">${user.selected_artists || 0}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('artistModal').classList.remove('active')">
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-primary">
                            Guardar Cambios
                        </button>
                    </div>
                </form>
            `;

            modal.classList.add('active');

            modal.querySelector('.modal-close').onclick = () => modal.classList.remove('active');
            modal.onclick = (e) => {
                if (e.target === modal) modal.classList.remove('active');
            };

        } catch (error) {
            console.error('Error loading user for edit:', error);
            this.showToast('Error', 'No se pudo cargar el usuario', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async saveUser(event, userId) {
        event.preventDefault();
        this.showLoading();

        const display_name = document.getElementById('userDisplayName').value;
        const email = document.getElementById('userEmail').value;

        try {
            const response = await fetch(`/api/update/user/${userId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ display_name, email })
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Éxito!', 'Usuario actualizado correctamente', 'success');
                document.getElementById('artistModal').classList.remove('active');
                this.loadUsers();
            } else {
                this.showToast('Error', 'No se pudo actualizar el usuario', 'error');
            }
        } catch (error) {
            console.error('Error saving user:', error);
            this.showToast('Error', 'No se pudo actualizar el usuario', 'error');
        } finally {
            this.hideLoading();
        }
    }

    confirmDeleteUser(userId, userName) {
        this.showConfirmDialog(
            '¿Eliminar Usuario?',
            `¿Estás seguro de que quieres eliminar a "${userName}"? Se eliminarán todas sus recomendaciones, artistas seleccionados y datos asociados. Esta acción no se puede deshacer.`,
            () => this.deleteUser(userId, userName)
        );
    }

    async deleteUser(userId, userName) {
        this.showLoading();

        try {
            const response = await fetch(`/api/delete/user/${userId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('¡Eliminado!', `${userName} ha sido eliminado`, 'success');
                this.loadUsers();
            } else {
                this.showToast('Error', 'No se pudo eliminar el usuario', 'error');
            }
        } catch (error) {
            console.error('Error deleting user:', error);
            this.showToast('Error', 'No se pudo eliminar el usuario', 'error');
        } finally {
            this.hideLoading();
        }
    }


    // Stats
    async loadStats() {
        this.showLoading();

        try {
            const response = await fetch('/api/stats');
            const data = await response.json();

            this.renderDecadeChart(data.by_decade);
            this.renderRatingChart(data.by_rating);
        } catch (error) {
            console.error('Error loading stats:', error);
        } finally {
            this.hideLoading();
        }
    }

    renderDecadeChart(data) {
        const container = document.getElementById('decadeChart');

        if (data.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-tertiary);">No hay datos</p>';
            return;
        }

        const max = Math.max(...data.map(d => d.count));

        container.innerHTML = data.map(item => `
            <div class="chart-bar">
                <div class="chart-label">${item.decade}</div>
                <div class="chart-bar-container">
                    <div class="chart-bar-fill" style="width: ${(item.count / max * 100)}%">
                        ${item.count}
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderRatingChart(data) {
        const container = document.getElementById('ratingChart');

        if (data.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-tertiary);">No hay datos</p>';
            return;
        }

        const max = Math.max(...data.map(d => d.count));

        container.innerHTML = data.map(item => `
            <div class="chart-bar">
                <div class="chart-label">${item.rating_range}</div>
                <div class="chart-bar-container">
                    <div class="chart-bar-fill" style="width: ${(item.count / max * 100)}%">
                        ${item.count}
                    </div>
                </div>
            </div>
        `).join('');
    }

    // Pagination
    renderPagination(type, data) {
        const container = document.getElementById(`${type}Pagination`);

        if (data.total_pages <= 1) {
            container.innerHTML = '';
            return;
        }

        const pages = [];
        const current = data.page;
        const total = data.total_pages;

        // Previous button
        pages.push(`
            <button ${current === 1 ? 'disabled' : ''} 
                    onclick="app.loadPage('${type}', ${current - 1})">
                ← Anterior
            </button>
        `);

        // Page numbers
        for (let i = 1; i <= total; i++) {
            if (i === 1 || i === total || (i >= current - 2 && i <= current + 2)) {
                pages.push(`
                    <button class="${i === current ? 'active' : ''}" 
                            onclick="app.loadPage('${type}', ${i})">
                        ${i}
                    </button>
                `);
            } else if (i === current - 3 || i === current + 3) {
                pages.push('<span style="color: var(--text-tertiary);">...</span>');
            }
        }

        // Next button
        pages.push(`
            <button ${current === total ? 'disabled' : ''} 
                    onclick="app.loadPage('${type}', ${current + 1})">
                Siguiente →
            </button>
        `);

        container.innerHTML = pages.join('');
    }

    loadPage(type, page) {
        if (type === 'artists') {
            this.loadArtists(page);
        } else if (type === 'albums') {
            this.loadAlbums(page);
        }
    }

    // Utilities
    showLoading() {
        document.getElementById('loadingOverlay').classList.add('active');
    }

    hideLoading() {
        document.getElementById('loadingOverlay').classList.remove('active');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }


    showConfirmDialog(title, message, onConfirm) {
        // Remove any existing dialog
        const existing = document.querySelector('.confirm-dialog');
        if (existing) existing.remove();

        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'modal active';
        overlay.style.background = 'rgba(0, 0, 0, 0.8)';

        // Create dialog
        const dialog = document.createElement('div');
        dialog.className = 'confirm-dialog';
        dialog.innerHTML = `
            <h3>${title}</h3>
            <p>${message}</p>
            <div class="confirm-dialog-actions">
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">
                    Cancelar
                </button>
                <button class="btn btn-danger" id="confirmBtn">
                    Confirmar
                </button>
            </div>
        `;

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        // Handle confirm
        document.getElementById('confirmBtn').onclick = () => {
            overlay.remove();
            onConfirm();
        };

        // Handle overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) overlay.remove();
        };
    }

    showToast(title, message, type = 'success') {
        // Remove any existing toast
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div class="toast-icon">${icons[type] || '📢'}</div>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" onclick="this.closest('.toast').remove()">×</button>
        `;

        document.body.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.animation = 'slideOutRight 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }
        }, 5000);
    }

    formatDate(dateString) {

        if (!dateString) return '—';
        const date = new Date(dateString);
        return date.toLocaleDateString('es-ES', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
}

// Initialize app
const app = new DatabaseExplorer();
