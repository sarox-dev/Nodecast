// Web Search launcher: suggestions before Enter, configured redirect after Enter.

window.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const suggestions = document.getElementById('web-suggestions');
    let suggestionTimer = null;
    let suggestionRequest = null;
    let activeSuggestion = -1;

    function configuredEngineLabel() {
        const configured = localStorage.getItem('preferredEngine') || 'https://duckduckgo.com/?q=';
        if (configured === 'custom') return 'your custom provider';
        try { return new URL(configured).hostname.replace(/^www\./, ''); }
        catch { return 'your search provider'; }
    }

    function buildSearchUrl(rawQuery) {
        const encoded = encodeURIComponent(rawQuery);
        const configured = localStorage.getItem('preferredEngine') || 'https://duckduckgo.com/?q=';
        const template = configured === 'custom'
            ? (localStorage.getItem('customSearchUrl') || '')
            : configured;
        const candidate = template.includes('{query}')
            ? template.replaceAll('{query}', encoded)
            : `${template}${encoded}`;
        try {
            const url = new URL(candidate);
            if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported protocol');
            return url.toString();
        } catch {
            return `https://duckduckgo.com/?q=${encoded}`;
        }
    }

    function hideSuggestions() {
        suggestions.hidden = true;
        suggestions.innerHTML = '';
        activeSuggestion = -1;
    }

    function renderSuggestions(items, provider) {
        activeSuggestion = -1;
        if (!items.length || !webMode) {
            hideSuggestions();
            return;
        }
        suggestions.innerHTML = items.map((item, index) => `<button type="button" role="option" aria-selected="false" data-suggestion-index="${index}" data-suggestion="${escapeHtml(item)}"><span>⌕</span><span>${escapeHtml(item)}</span></button>`).join('') + `<div class="web-suggestions-provider">Suggestions from ${escapeHtml(provider)}</div>`;
        suggestions.hidden = false;
    }

    async function requestSuggestions(value) {
        const enabled = localStorage.getItem('suggestionsEnabled') !== 'false';
        const provider = localStorage.getItem('suggestionProvider') || 'duckduckgo';
        if (!enabled || provider === 'none' || value.trim().length < 2 || !webMode) {
            hideSuggestions();
            return;
        }
        suggestionRequest?.abort();
        suggestionRequest = new AbortController();
        try {
            const response = await fetch(`/api/web/suggestions?provider=${encodeURIComponent(provider)}&q=${encodeURIComponent(value.trim())}`, { signal: suggestionRequest.signal });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (queryInput.value.trim() === value.trim()) renderSuggestions(data.suggestions || [], provider);
        } catch (error) {
            if (error.name !== 'AbortError') hideSuggestions();
        }
    }

    function scheduleSuggestions() {
        window.clearTimeout(suggestionTimer);
        suggestionTimer = window.setTimeout(() => requestSuggestions(queryInput.value), 140);
    }

    function moveSuggestion(direction) {
        const options = [...suggestions.querySelectorAll('[data-suggestion]')];
        if (!options.length) return false;
        activeSuggestion = (activeSuggestion + direction + options.length) % options.length;
        options.forEach((option, index) => option.setAttribute('aria-selected', String(index === activeSuggestion)));
        queryInput.value = options[activeSuggestion].dataset.suggestion;
        return true;
    }

    function redirectToSearch(value) {
        const target = buildSearchUrl(value);
        hideSuggestions();
        if (localStorage.getItem('webSearchOpenMode') === 'new-tab') {
            window.open(target, '_blank', 'noopener');
        } else {
            window.location.assign(target);
        }
    }

    form?.addEventListener('submit', event => {
        if (!webMode) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const value = queryInput.value.trim();
        if (value) redirectToSearch(value);
    }, true);

    queryInput?.addEventListener('input', () => {
        if (webMode) scheduleSuggestions();
    });

    queryInput?.addEventListener('keydown', event => {
        if (!webMode || suggestions.hidden) return;
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            moveSuggestion(1);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            moveSuggestion(-1);
        } else if (event.key === 'Escape') {
            hideSuggestions();
        }
    });

    suggestions?.addEventListener('click', event => {
        const option = event.target.closest('[data-suggestion]');
        if (!option) return;
        queryInput.value = option.dataset.suggestion;
        hideSuggestions();
        queryInput.focus();
    });

    window.setWebMode = function(web) {
        window.graphMode = false;
        webMode = Boolean(web);
        document.getElementById('page-shell')?.classList.toggle('web-search-mode', webMode);
        const graphArea = document.getElementById('graph-area');
        if (graphArea) graphArea.hidden = true;
        const contentView = document.getElementById('content-view');
        if (contentView) contentView.hidden = false;
        if (queryInput) {
            queryInput.placeholder = webMode ? `Search ${configuredEngineLabel()}…` : 'Search your library...';
            queryInput.value = '';
        }
        hideSuggestions();
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', !webMode);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', webMode);
        document.getElementById('sidebar-graph-nav')?.classList.toggle('active', false);
        if (!webMode && typeof loadLibrary === 'function') {
            loadLibrary();
            return;
        }
        currentQuery = '';
        allResults = [];
        const resultsContainer = document.getElementById('results-container');
        if (resultsContainer) {
            resultsContainer.innerHTML = `<div class="web-search-launcher"><span class="web-search-launcher-icon">⌕</span><h2>Search the web</h2><p>Suggestions appear while you type. Enter opens ${escapeHtml(configuredEngineLabel())} with your query.</p><button type="button" id="web-search-settings">Search settings</button></div>`;
            document.getElementById('web-search-settings')?.addEventListener('click', () => openSettings('Search'));
        }
        window.setTimeout(() => queryInput?.focus(), 0);
    };
});
