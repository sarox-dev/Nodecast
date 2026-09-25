// web-search.js — Web Search → redirect to preferred search engine

window.addEventListener('DOMContentLoaded', () => {
    window.setWebMode = function(web) {
        window.graphMode = false;
        const pageShell = document.getElementById('page-shell');
        if (pageShell) pageShell.classList.toggle('web-search-mode', web);
        const graphArea = document.getElementById('graph-area');
        if (graphArea) graphArea.hidden = true;
        const contentView = document.getElementById('content-view');
        if (contentView) contentView.hidden = false;
        const queryInput = document.getElementById('query');
        if (queryInput) {
            queryInput.placeholder = web ? 'Search the web...' : 'Search your library...';
            if (!web) queryInput.value = '';
        }
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', !web);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', web);
        document.getElementById('sidebar-graph-nav')?.classList.toggle('active', false);
        if (!web && typeof loadLibrary === 'function') {
            loadLibrary();
        } else if (web) {
            currentQuery = '';
            allResults = [];
            const resultsContainer = document.getElementById('results-container');
            if (resultsContainer) {
                const preferredEngine = localStorage.getItem('preferredEngine') || 'https://duckduckgo.com/?q=';
                if (queryInput && queryInput.value.trim()) {
                    window.open(preferredEngine + encodeURIComponent(queryInput.value.trim()), '_blank');
                }
                resultsContainer.innerHTML = '<div class="empty-state" style="display:flex"><div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div><h3>Web Search</h3><p>Type a query and press Enter to search the web in your preferred engine.</p></div>';
            }
        }
    };
});