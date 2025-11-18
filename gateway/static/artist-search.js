class ArtistSearch {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            minArtists: options.minArtists || 3,
            maxArtists: options.maxArtists || 10,
            onSelectionChange: options.onSelectionChange || (() => {}),
            onContinue: options.onContinue || null,
            ...options
        };
        
        this.selectedArtists = [];
        this.searchResults = [];
        this.searchTimeout = null;
        
        this.render();
        this.attachEventListeners();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="artist-search-modal">
                <div class="artist-search-header">
                    <h2>Selecciona entre ${this.options.minArtists} y ${this.options.maxArtists} artistas. Puedes buscar o elegir de los sugeridos.</h2>
                </div>
                
                <div class="artist-search-input-wrapper">
                    <input 
                        type="text" 
                        id="artist-search-input" 
                        placeholder="Escribe al menos 4 caracteres..." 
                        class="artist-search-input"
                        autocomplete="off"
                    />
                    <button id="clear-search-btn" class="clear-search-btn" style="display: none;">✕</button>
                </div>
                
                <div id="search-results-container" class="search-results-container">
                    <div class="search-results-label">Resultados de búsqueda</div>
                    <div id="search-results-grid" class="artist-grid"></div>
                </div>
                
                <div class="selected-artists-section">
                    <div class="selected-artists-header">
                        <span>Artistas seleccionados (mín. ${this.options.minArtists}, máx. ${this.options.maxArtists})</span>
                        <span id="artist-counter" class="artist-counter">0/${this.options.maxArtists} seleccionados</span>
                    </div>
                    <div id="selected-artists-pills" class="selected-artists-pills"></div>
                </div>
                
                ${this.options.onContinue ? `
                    <button id="continue-btn" class="continue-btn" disabled>
                        Continuar
                    </button>
                ` : ''}
            </div>
        `;
    }
    
    attachEventListeners() {
        const searchInput = document.getElementById('artist-search-input');
        const clearBtn = document.getElementById('clear-search-btn');
        const continueBtn = document.getElementById('continue-btn');
        
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            
            if (query.length > 0) {
                clearBtn.style.display = 'block';
            } else {
                clearBtn.style.display = 'none';
            }
            
            if (this.searchTimeout) {
                clearTimeout(this.searchTimeout);
            }
            
            if (query.length >= 4) {
                this.searchTimeout = setTimeout(() => {
                    this.performSearch(query);
                }, 300);
            } else {
                this.clearSearchResults();
            }
        });
        
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                searchInput.value = '';
                clearBtn.style.display = 'none';
                this.clearSearchResults();
            });
        }
        
        if (continueBtn) {
            continueBtn.addEventListener('click', () => {
                if (this.options.onContinue && this.isValidSelection()) {
                    this.options.onContinue(this.selectedArtists);
                }
            });
        }
    }
    
    async performSearch(query) {
        const resultsGrid = document.getElementById('search-results-grid');
        resultsGrid.innerHTML = '<div class="loading">Buscando...</div>';
        
        try {
            const response = await fetch(`/api/lastfm/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            
            this.searchResults = data.artists || [];
            this.renderSearchResults();
        } catch (error) {
            console.error('Search failed:', error);
            resultsGrid.innerHTML = '<div class="error">Error al buscar artistas</div>';
        }
    }
    
    renderSearchResults() {
        const resultsGrid = document.getElementById('search-results-grid');
        
        if (this.searchResults.length === 0) {
            resultsGrid.innerHTML = '<div class="no-results">No se encontraron artistas</div>';
            return;
        }
        
        resultsGrid.innerHTML = this.searchResults.map(artist => {
            const isSelected = this.selectedArtists.some(a => a.name === artist.name);
            const isDisabled = !isSelected && this.selectedArtists.length >= this.options.maxArtists;
            
            return `
                <div class="artist-card ${isSelected ? 'selected' : ''} ${isDisabled ? 'disabled' : ''}" 
                     data-artist-name="${artist.name}">
                    <div class="artist-card-content">
                        <div class="artist-image-wrapper">
                            ${artist.image_url 
                                ? `<img src="${artist.image_url}" alt="${artist.name}" class="artist-image" />`
                                : `<div class="artist-image-placeholder">🎵</div>`
                            }
                        </div>
                        <div class="artist-info">
                            <div class="artist-name">${artist.name}</div>
                            ${artist.genres && artist.genres.length > 0 
                                ? `<div class="artist-genres">${artist.genres.join(', ')}</div>`
                                : ''
                            }
                        </div>
                    </div>
                    <button class="add-artist-btn ${isSelected ? 'added' : ''}" 
                            ${isDisabled ? 'disabled' : ''}
                            data-artist='${JSON.stringify(artist)}'>
                        ${isSelected ? '✓' : '+'}
                    </button>
                </div>
            `;
        }).join('');
        
        this.attachArtistCardListeners();
    }
    
    attachArtistCardListeners() {
        const addButtons = document.querySelectorAll('.add-artist-btn');
        
        addButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const artist = JSON.parse(btn.dataset.artist);
                const isSelected = this.selectedArtists.some(a => a.name === artist.name);
                
                if (isSelected) {
                    this.removeArtist(artist.name);
                } else if (this.selectedArtists.length < this.options.maxArtists) {
                    this.addArtist(artist);
                }
            });
        });
    }
    
    addArtist(artist) {
        if (this.selectedArtists.length >= this.options.maxArtists) {
            return;
        }
        
        if (!this.selectedArtists.some(a => a.name === artist.name)) {
            this.selectedArtists.push(artist);
            this.updateUI();
        }
    }
    
    removeArtist(artistName) {
        this.selectedArtists = this.selectedArtists.filter(a => a.name !== artistName);
        this.updateUI();
    }
    
    updateUI() {
        this.renderSelectedArtists();
        this.renderSearchResults();
        this.updateCounter();
        this.updateContinueButton();
        this.options.onSelectionChange(this.selectedArtists);
    }
    
    renderSelectedArtists() {
        const pillsContainer = document.getElementById('selected-artists-pills');
        
        if (this.selectedArtists.length === 0) {
            pillsContainer.innerHTML = '<div class="no-selection">Aún no has seleccionado artistas</div>';
            return;
        }
        
        pillsContainer.innerHTML = this.selectedArtists.map(artist => `
            <div class="artist-pill">
                ${artist.image_url 
                    ? `<img src="${artist.image_url}" alt="${artist.name}" class="pill-image" />`
                    : ''
                }
                <span class="pill-name">${artist.name}</span>
                <button class="pill-remove-btn" data-artist-name="${artist.name}">✕</button>
            </div>
        `).join('');
        
        const removeButtons = pillsContainer.querySelectorAll('.pill-remove-btn');
        removeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                this.removeArtist(btn.dataset.artistName);
            });
        });
    }
    
    updateCounter() {
        const counter = document.getElementById('artist-counter');
        if (counter) {
            counter.textContent = `${this.selectedArtists.length}/${this.options.maxArtists} seleccionados`;
        }
    }
    
    updateContinueButton() {
        const continueBtn = document.getElementById('continue-btn');
        if (continueBtn) {
            continueBtn.disabled = !this.isValidSelection();
        }
    }
    
    isValidSelection() {
        return this.selectedArtists.length >= this.options.minArtists && 
               this.selectedArtists.length <= this.options.maxArtists;
    }
    
    clearSearchResults() {
        const resultsGrid = document.getElementById('search-results-grid');
        resultsGrid.innerHTML = '';
        this.searchResults = [];
    }
    
    getSelectedArtists() {
        return this.selectedArtists;
    }
    
    setSelectedArtists(artists) {
        this.selectedArtists = artists;
        this.updateUI();
    }
}
