// Request Log
const requestLog = [];

function addRequestLog(method, endpoint, params, status, time, summary, discogsRequest = null) {
    const timestamp = new Date().toLocaleTimeString();
    requestLog.push({ timestamp, method, endpoint, params, status, time, summary, discogsRequest });
    updateRequestLogDisplay();
}

function updateRequestLogDisplay() {
    const logDiv = document.getElementById('request-log');
    if (!logDiv) return;
    
    const html = requestLog.map(log => {
        const statusColor = log.status >= 200 && log.status < 300 ? 'text-green-600' : 'text-red-600';
        
        let discogsHtml = '';
        if (log.discogsRequest && log.discogsRequest.request_url) {
            const url = log.discogsRequest.request_url;
            const params = log.discogsRequest.params_sent || {};
            const paramsHtml = Object.entries(params)
                .map(([k, v]) => `<div class="ml-4 text-purple-600">&${k}=${v}</div>`)
                .join('');
            
            discogsHtml = `
                <div class="mt-1 ml-4 text-xs bg-gray-100 p-2 rounded border border-gray-300">
                    <div class="font-semibold text-blue-700">→ ${url.split('?')[0]}</div>
                    ${paramsHtml}
                    ${log.discogsRequest.params_sent && log.discogsRequest.params_sent.key !== undefined ? '<div class="ml-4 text-gray-500">&key=[HIDDEN]</div>' : ''}
                    ${log.discogsRequest.params_sent && log.discogsRequest.params_sent.secret !== undefined ? '<div class="ml-4 text-gray-500">&secret=[HIDDEN]</div>' : ''}
                </div>
            `;
        }
        
        return `
            <div class="text-xs p-2 border-b border-gray-200 font-mono">
                <div>
                    <span class="text-gray-500">[${log.timestamp}]</span>
                    <span class="font-semibold">${log.method}</span>
                    <span class="text-blue-600">${log.endpoint}</span>
                    ${log.params ? `<span class="text-purple-600">${log.params}</span>` : ''}
                    → <span class="${statusColor}">${log.status}</span>
                    <span class="text-gray-600">(${log.time}s)</span>
                    ${log.summary ? `<span class="text-gray-700 ml-2">→ ${log.summary}</span>` : ''}
                </div>
                ${discogsHtml}
            </div>
        `;
    }).reverse().join('');
    
    logDiv.innerHTML = html || '<div class="text-sm text-gray-500 p-4">No hay peticiones registradas</div>';
}

// Service Status Check
async function checkServiceHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        updateServiceStatus('gateway', data.gateway);
        
        for (const [serviceName, serviceData] of Object.entries(data.services)) {
            updateServiceStatus(serviceName, serviceData.status);
        }
    } catch (error) {
        console.error('Health check failed:', error);
        updateServiceStatus('gateway', 'error');
    }
}

function updateServiceStatus(service, status) {
    const element = document.getElementById(`status-${service}`);
    if (!element) return;
    
    const isHealthy = status === 'healthy';
    const color = isHealthy ? 'bg-green-500' : 'bg-red-500';
    const text = isHealthy ? 'Healthy' : 'Unhealthy';
    
    element.innerHTML = `
        <span class="inline-block w-3 h-3 rounded-full ${color}"></span>
        <span class="ml-2 text-sm">${text}</span>
    `;
}

// Test Spotify Login
async function testSpotifyLogin() {
    const resultElement = document.getElementById('spotify-login-result');
    resultElement.textContent = 'Loading...';
    resultElement.className = 'ml-4 text-sm text-blue-600';
    
    try {
        const response = await fetch('/auth/login');
        const data = await response.json();
        
        if (data.authorize_url) {
            resultElement.textContent = 'Opening Spotify login...';
            resultElement.className = 'ml-4 text-sm text-green-600';
            window.open(data.authorize_url, '_blank');
        } else {
            resultElement.textContent = 'Failed to get login URL';
            resultElement.className = 'ml-4 text-sm text-red-600';
        }
    } catch (error) {
        resultElement.textContent = `Error: ${error.message}`;
        resultElement.className = 'ml-4 text-sm text-red-600';
    }
}

// Test Recommendation
async function testRecommendation() {
    const resultElement = document.getElementById('recommend-result');
    const progressTracker = document.getElementById('progress-tracker');
    const resultsContainer = document.getElementById('results-container');
    const resultsDiv = document.getElementById('results');
    
    resultElement.textContent = 'Starting...';
    resultElement.className = 'ml-4 text-sm text-blue-600';
    progressTracker.classList.remove('hidden');
    resultsContainer.classList.add('hidden');
    resultsDiv.innerHTML = '';
    
    // Simulate progress (since we don't have SSE yet)
    const steps = [
        { id: 'step-1', delay: 1000 },
        { id: 'step-2', delay: 2000 },
        { id: 'step-3', delay: 1000 },
        { id: 'step-4', delay: 1000 },
        { id: 'step-5', delay: 2000 },
    ];
    
    let currentStep = 0;
    const progressInterval = setInterval(() => {
        if (currentStep < steps.length) {
            updateStepStatus(steps[currentStep].id, 'in-progress');
            if (currentStep > 0) {
                updateStepStatus(steps[currentStep - 1].id, 'completed');
            }
            currentStep++;
        }
    }, 2000);
    
    try {
        const response = await fetch('/recommend-vinyl');
        const data = await response.json();
        
        clearInterval(progressInterval);
        steps.forEach(step => updateStepStatus(step.id, 'completed'));
        
        resultElement.textContent = `Success! Found ${data.total} albums in ${data.total_time_seconds}s`;
        resultElement.className = 'ml-4 text-sm text-green-600';
        
        displayResults(data.albums, data.stats, data.total_time_seconds);
    } catch (error) {
        clearInterval(progressInterval);
        resultElement.textContent = `Error: ${error.message}`;
        resultElement.className = 'ml-4 text-sm text-red-600';
        
        steps.forEach(step => {
            const stepElement = document.getElementById(step.id);
            if (stepElement.querySelector('.bg-blue-500')) {
                stepElement.querySelector('span').className = 'inline-block w-6 h-6 rounded-full bg-red-500 mr-3';
            }
        });
    }
}

function updateStepStatus(stepId, status) {
    const stepElement = document.getElementById(stepId);
    if (!stepElement) return;
    
    const circle = stepElement.querySelector('span');
    const colorMap = {
        'pending': 'bg-gray-300',
        'in-progress': 'bg-blue-500',
        'completed': 'bg-green-500',
        'error': 'bg-red-500'
    };
    
    circle.className = `inline-block w-6 h-6 rounded-full ${colorMap[status]} mr-3`;
}

// Discogs Interactive Search
async function searchDiscogs(artist, album, buttonElement) {
    const albumCard = buttonElement.closest('.album-card');
    const releasesDiv = albumCard.querySelector('.discogs-releases');
    
    buttonElement.disabled = true;
    buttonElement.textContent = 'Searching...';
    
    try {
        const startTime = performance.now();
        const response = await fetch(`/discogs/search/${encodeURIComponent(artist)}/${encodeURIComponent(album)}`);
        const data = await response.json();
        const endTime = performance.now();
        const elapsed = ((endTime - startTime) / 1000).toFixed(2);
        
        addRequestLog('GET', `/discogs/search/${artist}/${album}`, '', response.status, elapsed, `${data.total} releases`, data.discogs_request);
        
        buttonElement.textContent = `✓ Found ${data.total} releases`;
        buttonElement.classList.remove('bg-blue-600', 'hover:bg-blue-700');
        buttonElement.classList.add('bg-green-600');
        
        displayReleases(releasesDiv, data.releases);
        
    } catch (error) {
        buttonElement.textContent = 'Error - Try Again';
        buttonElement.disabled = false;
        buttonElement.classList.add('bg-red-600');
        addRequestLog('GET', `/discogs/search/${artist}/${album}`, '', 500, '0', `Error: ${error.message}`);
    }
}

function displayReleases(container, releases) {
    if (!releases || releases.length === 0) {
        container.innerHTML = '<div class="text-sm text-gray-500 p-2">No vinyl releases found</div>';
        container.classList.remove('hidden');
        return;
    }
    
    const html = releases.map((release, idx) => {
        const releaseId = release.id;
        const title = release.title || 'Unknown';
        const year = release.year || 'N/A';
        const format = Array.isArray(release.format) ? release.format.join(', ') : release.format || 'Vinyl';
        const label = release.label ? release.label.join(', ') : 'Unknown Label';
        
        return `
            <div class="border border-gray-300 rounded p-3 mb-2 release-item" data-release-id="${releaseId}">
                <div class="flex justify-between items-start mb-2">
                    <div class="flex-1">
                        <div class="font-semibold text-sm">#${idx + 1} - ${title}</div>
                        <div class="text-xs text-gray-600">${format} · ${year} · ${label}</div>
                    </div>
                    <button 
                        onclick="getPriceForRelease(${releaseId}, this)"
                        class="ml-2 bg-purple-600 hover:bg-purple-700 text-white text-xs px-3 py-1 rounded"
                    >
                        Get Price
                    </button>
                </div>
                <div class="price-info hidden mt-2"></div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
    container.classList.remove('hidden');
}

async function getPricing(artist, album, buttonElement) {
    const albumCard = buttonElement.closest('.album-card');
    const pricingDiv = albumCard.querySelector('.pricing-info');
    
    buttonElement.disabled = true;
    buttonElement.textContent = 'Loading prices...';
    
    try {
        const startTime = performance.now();
        const response = await fetch(`/album-pricing/${encodeURIComponent(artist)}/${encodeURIComponent(album)}`);
        const data = await response.json();
        const endTime = performance.now();
        const elapsed = ((endTime - startTime) / 1000).toFixed(2);
        
        const ebayOffer = data.ebay_offer;
        const discogsUrl = data.discogs_master_url;
        const localStores = data.local_stores || {};
        
        let summary = `${elapsed}s - Discogs: ${discogsUrl ? 'found' : 'not found'}, eBay: ${ebayOffer ? 'found' : 'not found'}`;
        addRequestLog('GET', `/album-pricing/${artist}/${album}`, '', response.status, elapsed, summary, data.debug_info?.discogs);
        
        buttonElement.textContent = '✓ Prices Loaded';
        buttonElement.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
        buttonElement.classList.add('bg-green-600');
        
        let html = '<div class="space-y-3">';
        
        if (discogsUrl) {
            html += `
                <div class="bg-blue-50 border border-blue-200 rounded p-3">
                    <div class="text-sm font-semibold text-blue-900 mb-2">🎵 Discogs Master</div>
                    <a href="${discogsUrl}" target="_blank" class="block text-center bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-2 rounded">
                        View on Discogs
                    </a>
                </div>
            `;
        }
        
        if (ebayOffer) {
            const price = ebayOffer.total_price;
            const itemPrice = ebayOffer.item_price;
            const shipping = ebayOffer.shipping_cost;
            const currency = ebayOffer.currency;
            const url = ebayOffer.url;
            
            html += `
                <div class="bg-green-50 border border-green-200 rounded p-3">
                    <div class="text-sm font-semibold text-green-900 mb-2">💳 Best eBay Offer</div>
                    <div class="text-xs text-gray-700 mb-2">
                        <div>Item: ${itemPrice} ${currency}</div>
                        <div>Shipping: ${shipping} ${currency}</div>
                        <div class="font-bold mt-1 text-lg text-green-700">Total: ${price} ${currency}</div>
                    </div>
                    <a href="${url}" target="_blank" class="block text-center bg-green-600 hover:bg-green-700 text-white text-sm px-3 py-2 rounded">
                        Buy on eBay
                    </a>
                </div>
            `;
        } else {
            html += `
                <div class="bg-yellow-50 border border-yellow-200 rounded p-3">
                    <div class="text-sm font-semibold text-yellow-900 mb-1">💳 eBay</div>
                    <div class="text-xs text-yellow-800">No suitable vinyl offer found on eBay</div>
                </div>
            `;
        }
        
        if (Object.keys(localStores).length > 0) {
            html += `
                <div class="bg-purple-50 border border-purple-200 rounded p-3">
                    <div class="text-sm font-semibold text-purple-900 mb-2">🏪 Tiendas Locales</div>
                    <div class="grid grid-cols-2 gap-2">
            `;
            
            const storeNames = {
                'marilians': 'Marilians',
                'bajo_el_volcan': 'Bajo el Volcán',
                'bora_bora': 'Bora Bora',
                'revolver': 'Revolver'
            };
            
            for (const [key, url] of Object.entries(localStores)) {
                const name = storeNames[key] || key;
                html += `
                    <a href="${url}" target="_blank" class="text-xs bg-purple-600 hover:bg-purple-700 text-white px-2 py-1 rounded text-center">
                        ${name}
                    </a>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
        
        pricingDiv.innerHTML = html;
        pricingDiv.classList.remove('hidden');
        
    } catch (error) {
        buttonElement.textContent = 'Error - Try Again';
        buttonElement.disabled = false;
        buttonElement.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
        buttonElement.classList.add('bg-red-600');
        addRequestLog('GET', `/album-pricing/${artist}/${album}`, '', 500, '0', `Error: ${error.message}`);
        
        pricingDiv.innerHTML = `
            <div class="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-800">
                Error loading prices: ${error.message}
            </div>
        `;
        pricingDiv.classList.remove('hidden');
    }
}

async function getPriceForRelease(releaseId, buttonElement) {
    const releaseItem = buttonElement.closest('.release-item');
    const priceDiv = releaseItem.querySelector('.price-info');
    
    buttonElement.disabled = true;
    buttonElement.textContent = 'Loading...';
    
    try {
        const startTime = performance.now();
        const response = await fetch(`/discogs/stats/${releaseId}`);
        const data = await response.json();
        const endTime = performance.now();
        const elapsed = ((endTime - startTime) / 1000).toFixed(2);
        
        const stats = data.stats;
        const price = stats.lowest_price_eur;
        const forSale = stats.num_for_sale || 0;
        const url = stats.sell_list_url;
        
        let summary = price ? `€${price.toFixed(2)}, ${forSale} units` : 'No price';
        addRequestLog('GET', `/discogs/stats/${releaseId}`, '', response.status, elapsed, summary, data.discogs_request);
        
        buttonElement.textContent = '✓ Got Price';
        buttonElement.classList.remove('bg-purple-600', 'hover:bg-purple-700');
        buttonElement.classList.add('bg-green-600');
        
        if (price && price > 0) {
            priceDiv.innerHTML = `
                <div class="bg-green-50 border border-green-200 rounded p-2">
                    <div class="flex justify-between items-center text-sm">
                        <span class="font-semibold text-green-700">€${price.toFixed(2)}</span>
                        <span class="text-gray-600">${forSale} available</span>
                    </div>
                    <a href="${url}" target="_blank" class="block mt-2 text-center bg-green-600 hover:bg-green-700 text-white text-xs px-3 py-1 rounded">
                        Buy on Discogs
                    </a>
                </div>
            `;
        } else {
            priceDiv.innerHTML = `
                <div class="bg-yellow-50 border border-yellow-200 rounded p-2 text-sm text-yellow-800">
                    No price available (${forSale} listings found)
                </div>
            `;
        }
        
        priceDiv.classList.remove('hidden');
        
    } catch (error) {
        buttonElement.textContent = 'Error';
        buttonElement.disabled = false;
        buttonElement.classList.add('bg-red-600');
        addRequestLog('GET', `/discogs/stats/${releaseId}`, '', 500, '0', `Error: ${error.message}`);
    }
}

function displayResults(albums, stats, totalTime) {
    const resultsContainer = document.getElementById('results-container');
    const resultsDiv = document.getElementById('results');
    
    resultsContainer.classList.remove('hidden');
    
    if (!albums || albums.length === 0) {
        resultsDiv.innerHTML = '<p class="text-gray-600">No albums found</p>';
        return;
    }
    
    resultsDiv.innerHTML = albums.map(album => {
        const albumInfo = album.album_info || {};
        const albumName = albumInfo.name || 'Unknown Album';
        const artistName = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        const imageUrl = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300';
        const score = album.score ? album.score.toFixed(0) : '0';
        const trackCount = album.track_count || 0;
        
        const breakdown = album.score_breakdown || {};
        const baseScore = breakdown.base_score || 0;
        const artistBoostApplied = breakdown.artist_boost_applied || false;
        const boostMultiplier = breakdown.artist_boost_multiplier || 1;
        const scoreByPeriod = breakdown.score_by_period || {};
        const tracksByPeriod = breakdown.tracks_by_period || {};
        
        return `
            <div class="bg-white rounded-lg shadow-md overflow-hidden album-card">
                <img src="${imageUrl}" alt="${albumName}" class="w-full h-48 object-cover">
                <div class="p-4">
                    <h3 class="font-bold text-lg mb-1">${albumName}</h3>
                    <p class="text-gray-600 text-sm mb-2">${artistName}</p>
                    <div class="flex justify-between text-sm mb-2">
                        <span class="text-gray-700">${trackCount} tracks</span>
                        <span class="text-purple-600 font-semibold">Score: ${score}</span>
                    </div>
                    ${artistBoostApplied ? `<span class="inline-block bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded mb-2">⭐ Favorite Artist (${boostMultiplier}x boost)</span>` : ''}
                    <details class="text-xs text-gray-600 mb-3">
                        <summary class="cursor-pointer hover:text-purple-600 font-medium">Score Breakdown</summary>
                        <div class="mt-2 p-2 bg-gray-50 rounded">
                            <div>Base Score: ${baseScore}</div>
                            ${artistBoostApplied ? `<div>Artist Boost: ${boostMultiplier}x</div>` : ''}
                            <div class="mt-1 border-t pt-1">
                                <div>Short term: ${scoreByPeriod.short_term || 0} (${tracksByPeriod.short_term || 0} tracks, 3x boost)</div>
                                <div>Medium term: ${scoreByPeriod.medium_term || 0} (${tracksByPeriod.medium_term || 0} tracks, 2x boost)</div>
                                <div>Long term: ${scoreByPeriod.long_term || 0} (${tracksByPeriod.long_term || 0} tracks, 1x boost)</div>
                            </div>
                        </div>
                    </details>
                    
                    <div class="border-t pt-3 mt-3">
                        <button 
                            onclick="getPricing('${artistName.replace(/'/g, "\\'")}', '${albumName.replace(/'/g, "\\'")}', this)"
                            class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded mb-2"
                        >
                            💰 Get Prices
                        </button>
                        <div class="pricing-info hidden mt-3"></div>
                        <button 
                            onclick="searchDiscogs('${artistName.replace(/'/g, "\\'")}', '${albumName.replace(/'/g, "\\'")}', this)"
                            class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded mb-2 mt-2"
                        >
                            🔍 Search Discogs Releases
                        </button>
                        <div class="discogs-releases hidden mt-3"></div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    // Show stats with total time
    if (stats) {
        const statsHtml = `
            <div class="col-span-full bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                <h3 class="font-bold text-lg mb-2">Statistics</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div><span class="text-gray-600">Total Time:</span> <span class="font-semibold text-green-600">${totalTime}s</span></div>
                    <div><span class="text-gray-600">Tracks Analyzed:</span> <span class="font-semibold">${stats.tracks_analyzed || 0}</span></div>
                    <div><span class="text-gray-600">Artists Analyzed:</span> <span class="font-semibold">${stats.artists_analyzed || 0}</span></div>
                    <div><span class="text-gray-600">Albums Found:</span> <span class="font-semibold">${stats.albums_found || 0}</span></div>
                </div>
            </div>
        `;
        resultsDiv.insertAdjacentHTML('afterbegin', statsHtml);
    }
}

// Initialize
checkServiceHealth();
setInterval(checkServiceHealth, 10000);
