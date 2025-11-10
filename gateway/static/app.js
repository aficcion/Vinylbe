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
        { id: 'step-6', delay: 5000 },
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
        const discogsStats = album.discogs_stats || {};
        const debugInfo = album.discogs_debug_info || {};
        const albumName = albumInfo.name || 'Unknown Album';
        const artistName = albumInfo.artists?.[0]?.name || 'Unknown Artist';
        const imageUrl = albumInfo.images?.[0]?.url || 'https://via.placeholder.com/300';
        const price = discogsStats.lowest_price ? `€${discogsStats.lowest_price.toFixed(2)}` : 'N/A';
        const forSale = discogsStats.num_for_sale || 0;
        const discogsUrl = discogsStats.sell_list_url || '#';
        const score = album.score ? album.score.toFixed(0) : '0';
        const trackCount = album.track_count || 0;
        
        const breakdown = album.score_breakdown || {};
        const baseScore = breakdown.base_score || 0;
        const artistBoostApplied = breakdown.artist_boost_applied || false;
        const boostMultiplier = breakdown.artist_boost_multiplier || 1;
        const scoreByPeriod = breakdown.score_by_period || {};
        const tracksByPeriod = breakdown.tracks_by_period || {};
        
        // Discogs Debug Info Badge
        const debugStatus = debugInfo.status || 'unknown';
        const debugMessage = debugInfo.message || 'Sin información';
        const debugDetails = debugInfo.details || {};
        
        const statusConfig = {
            'success': { 
                icon: '✓', 
                color: 'bg-green-100 text-green-800 border-green-300',
                iconColor: 'text-green-600'
            },
            'no_price': { 
                icon: '⚠', 
                color: 'bg-yellow-100 text-yellow-800 border-yellow-300',
                iconColor: 'text-yellow-600'
            },
            'filtered': { 
                icon: '○', 
                color: 'bg-orange-100 text-orange-800 border-orange-300',
                iconColor: 'text-orange-600'
            },
            'not_found': { 
                icon: '✗', 
                color: 'bg-gray-100 text-gray-800 border-gray-300',
                iconColor: 'text-gray-600'
            },
            'error': { 
                icon: '!', 
                color: 'bg-red-100 text-red-800 border-red-300',
                iconColor: 'text-red-600'
            }
        };
        
        const config = statusConfig[debugStatus] || statusConfig['not_found'];
        
        const debugBadgeHtml = `
            <div class="border ${config.color} rounded-lg p-2 mb-3 text-xs">
                <div class="flex items-center">
                    <span class="font-bold ${config.iconColor} mr-2">${config.icon}</span>
                    <span class="font-medium">${debugMessage}</span>
                </div>
                ${debugDetails.total_releases_found !== undefined ? `
                    <details class="mt-1">
                        <summary class="cursor-pointer hover:underline">Detalles técnicos</summary>
                        <div class="mt-1 pl-4 text-xs opacity-75">
                            <div>Releases en Discogs: ${debugDetails.total_releases_found || 0}</div>
                            <div>Vinilos válidos: ${debugDetails.vinyl_releases_found || 0}</div>
                            ${debugDetails.releases_tried !== undefined ? `<div class="font-semibold text-blue-700">Probados: ${debugDetails.releases_tried || 0}</div>` : ''}
                            ${debugDetails.releases_with_price !== undefined ? `<div>Con precio: ${debugDetails.releases_with_price || 0}</div>` : ''}
                            ${debugDetails.selected_release_index !== undefined ? `<div class="text-green-700">✓ Seleccionado: #${debugDetails.selected_release_index}</div>` : ''}
                            ${debugDetails.selected_format ? `<div class="text-xs mt-1 italic">${debugDetails.selected_format}</div>` : ''}
                        </div>
                    </details>
                ` : ''}
            </div>
        `;
        
        return `
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <img src="${imageUrl}" alt="${albumName}" class="w-full h-48 object-cover">
                <div class="p-4">
                    <h3 class="font-bold text-lg mb-1">${albumName}</h3>
                    <p class="text-gray-600 text-sm mb-2">${artistName}</p>
                    <div class="flex justify-between text-sm mb-2">
                        <span class="text-gray-700">${trackCount} tracks</span>
                        <span class="text-purple-600 font-semibold">Score: ${score}</span>
                    </div>
                    ${artistBoostApplied ? '<span class="inline-block bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded mb-2">⭐ Favorite Artist (${boostMultiplier}x boost)</span>' : ''}
                    <details class="text-xs text-gray-600 mb-2">
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
                        ${debugBadgeHtml}
                        ${debugStatus === 'success' || debugStatus === 'no_price' ? `
                            <div class="flex justify-between items-center mb-2">
                                <span class="text-gray-700">Vinyl Price:</span>
                                <span class="font-bold text-green-600">${price}</span>
                            </div>
                            <div class="flex justify-between items-center mb-3">
                                <span class="text-gray-700">Available:</span>
                                <span class="text-gray-900">${forSale} listings</span>
                            </div>
                        ` : ''}
                        ${debugStatus === 'success' && forSale > 0 ? `<a href="${discogsUrl}" target="_blank" class="block w-full text-center bg-purple-600 hover:bg-purple-700 text-white font-bold py-2 px-4 rounded">View on Discogs</a>` : ''}
                        ${debugStatus === 'no_price' ? '<div class="text-center text-sm text-gray-500 italic py-2">LP encontrado en Discogs pero sin precio disponible actualmente</div>' : ''}
                        ${debugStatus === 'filtered' ? '<div class="text-center text-sm text-orange-600 italic py-2">Solo Box Sets/Compilaciones disponibles - no se muestran</div>' : ''}
                        ${debugStatus === 'not_found' ? '<div class="text-center text-sm text-gray-500 italic py-2">No encontrado en el catálogo de Discogs</div>' : ''}
                        ${debugStatus === 'error' ? '<div class="text-center text-sm text-red-600 italic py-2">Error al buscar en Discogs</div>' : ''}
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
                <div class="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                    <div><span class="text-gray-600">Total Time:</span> <span class="font-semibold text-green-600">${totalTime}s</span></div>
                    <div><span class="text-gray-600">Tracks Analyzed:</span> <span class="font-semibold">${stats.tracks_analyzed || 0}</span></div>
                    <div><span class="text-gray-600">Artists Analyzed:</span> <span class="font-semibold">${stats.artists_analyzed || 0}</span></div>
                    <div><span class="text-gray-600">Albums Found:</span> <span class="font-semibold">${stats.albums_found || 0}</span></div>
                    <div><span class="text-gray-600">With Discogs Data:</span> <span class="font-semibold">${stats.albums_with_discogs_data || 0}</span></div>
                </div>
            </div>
        `;
        resultsDiv.insertAdjacentHTML('afterbegin', statsHtml);
    }
}

// Initialize
checkServiceHealth();
setInterval(checkServiceHealth, 10000); // Check every 10 seconds
