document.addEventListener('DOMContentLoaded', () => {
    // ─── DOM refs ────────────────────────────────────────────────
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const resultsContainer = document.getElementById('results-container');
    const sentinel = document.getElementById('results-sentinel');
    const emptyState = document.getElementById('empty-state');
    const statusBar = document.getElementById('status-bar');
    const resultCount = document.getElementById('result-count');
    const browseBtn = document.getElementById('browse-btn');
    const filterBar = document.getElementById('filter-bar');
    const settingsButton = document.getElementById('settings-button');

    // ─── State ──────────────────────────────────────────────────
    let currentMode = 'all';         // 'all' | 'web' | 'saved'
    let currentQuery = '';
    let currentPage = 1;
    let loading = false;
    let hasMore = false;
    let allResults = [];             // full merged result set for current query
    let browseMode = false;          // true when showing all saved (no search)

    // ─── Settings overlay (ported from original) ────────────────
    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const settingsList = document.getElementById('settings-list');
    const settingsSave = document.getElementById('settings-save');

    const settingsSchema = [
        {
            category: 'General',
            items: [
                {
                    key: 'theme',
                    label: 'Theme',
                    type: 'select',
                    options: [
                        { value: 'default', label: 'Default' },
                        { value: 'dark', label: 'Dark' }
                    ],
                    default: 'default'
                },
            ]
        },
        {
            category: 'Search Behavior',
            items: [
                {
                    key: 'resultsPerPage',
                    label: 'Results per page',
                    type: 'number',
                    min: 1,
                    max: 50,
                    default: 10
                },
                {
                    key: 'engines',
                    label: 'Search engines',
                    type: 'checkbox-group',
                    options: [
                        { value: 'duckduckgo', label: 'DuckDuckGo' },
                        { value: 'bing', label: 'Bing' },
                        { value: 'google', label: 'Google' },
                        { value: 'wikipedia', label: 'Wikipedia' },
                        { value: 'github', label: 'GitHub' }
                    ],
                    default: ['duckduckgo']
                },
                {
                    key: 'autoLoad',
                    label: 'Auto load more results on scroll',
                    type: 'checkbox',
                    default: true
                }
            ]
        }
    ];

    const settingsState = {};

    function getValue(item) {
        const persisted = localStorage.getItem(item.key);
        if (persisted === null) return item.default;
        if (item.type === 'checkbox') return persisted === 'true';
        if (item.type === 'number') return Number(persisted);
        if (item.type === 'checkbox-group') {
            try { return JSON.parse(persisted); } catch { return item.default; }
        }
        return persisted;
    }

    function setValue(key, value) {
        settingsState[key] = value;
        if (Array.isArray(value)) localStorage.setItem(key, JSON.stringify(value));
        else localStorage.setItem(key, String(value));
    }

    function createField(item) {
        const value = getValue(item);
        settingsState[item.key] = value;
        if (item.type === 'select') {
            return `<label class="settings-field"><span>${item.label}</span><select data-key="${item.key}">${item.options.map(o => `<option value="${o.value}" ${o.value === value ? 'selected' : ''}>${o.label}</option>`).join('')}</select></label>`;
        }
        if (item.type === 'checkbox') {
            return `<label class="settings-field checkbox-field"><span>${item.label}</span><input type="checkbox" data-key="${item.key}" ${value ? 'checked' : ''} /></label>`;
        }
        if (item.type === 'checkbox-group') {
            return `<div class="settings-field"><span>${item.label}</span><div class="checkbox-group">${item.options.map(opt => `<label class="checkbox-option"><input type="checkbox" data-key="${item.key}" value="${opt.value}" ${value.includes(opt.value) ? 'checked' : ''} /><span>${opt.label}</span></label>`).join('')}</div></div>`;
        }
        return `<label class="settings-field"><span>${item.label}</span><input type="${item.type}" data-key="${item.key}" value="${value}" min="${item.min || ''}" max="${item.max || ''}" /></label>`;
    }

    function renderSettings() {
        settingsList.innerHTML = settingsSchema.map(cat => cat.items.map(createField).join('')).join('');
    }

    function readSettings() {
        settingsSchema.forEach(cat => {
            cat.items.forEach(item => {
                if (item.type === 'checkbox-group') {
                    const inputs = settingsList.querySelectorAll(`input[data-key="${item.key}"]`);
                    setValue(item.key, [...inputs].filter(i => i.checked).map(i => i.value));
                    return;
                }
                const input = settingsList.querySelector(`[data-key="${item.key}"]`);
                if (!input) return;
                let value;
                if (item.type === 'checkbox') value = input.checked;
                else if (item.type === 'number') value = Number(input.value) || item.default;
                else value = input.value;
                setValue(item.key, value);
            });
        });
    }

    function openSettings() {
        renderSettings();
        settingsOverlay.hidden = false;
        settingsOverlay.inert = false;
    }

    function closeSettings() {
        document.activeElement?.blur();
        settingsOverlay.inert = true;
        settingsOverlay.hidden = true;
    }

    settingsButton.addEventListener('click', openSettings);
    settingsClose.addEventListener('click', closeSettings);
    settingsOverlay.addEventListener('click', (e) => { if (e.target === settingsOverlay) closeSettings(); });
    settingsSave.addEventListener('click', () => { readSettings(); applyTheme(); closeSettings(); });

    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !settingsOverlay.hidden) closeSettings(); });

    function initSettings() {
        settingsSchema.forEach(cat => cat.items.forEach(item => { settingsState[item.key] = getValue(item); }));
    }
    initSettings();

    function applyTheme() {
        if (settingsState.theme === 'dark') document.documentElement.dataset.theme = 'dark';
        else document.documentElement.dataset.theme = '';
    }
    applyTheme();

    function getEngines() {
        const e = settingsState.engines;
        return Array.isArray(e) ? e.join(',') : 'duckduckgo';
    }

    function getPageSize() {
        return Number(settingsState.resultsPerPage) || 10;
    }

    // ─── Filter tabs ─────────────────────────────────────────────
    function renderFilterTabs(mode) {
        filterBar.hidden = false;
        filterBar.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
    }

    function setFilter(mode) {
        currentMode = mode;
        renderFilterTabs(mode);
        renderResults();
    }

    filterBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-btn');
        if (btn) setFilter(btn.dataset.mode);
    });

    // ─── Rendering ────────────────────────────────────────────────
    function formatTime(isoStr) {
        if (!isoStr) return '';
        try {
            const d = new Date(isoStr);
            const days = Math.floor((Date.now() - d) / (1000 * 60 * 60 * 24));
            if (days === 0) return 'today';
            if (days === 1) return 'yesterday';
            if (days < 7) return `${days} days ago`;
            return d.toLocaleDateString();
        } catch { return ''; }
    }

    function highlightText(text, query) {
        if (!query || !text) return text;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const words = escaped.split(/\s+/).filter(Boolean);
        if (!words.length) return text;
        const pattern = new RegExp(`(${words.join('|')})`, 'gi');
        return text.replace(pattern, '<mark>$1</mark>');
    }

    function createCard(item) {
        const isSaved = item._type === 'saved';
        const ts = formatTime(item.saved_at);
        const title = item.title || item.url || 'Untitled';
        const content = item.content || '';
        const highlightedTitle = highlightText(title, currentQuery);
        const highlightedContent = highlightText(content.slice(0, 250), currentQuery);

        let metaBadge = isSaved
            ? `<span class="badge-saved">★ Saved</span>`
            : `<span class="badge-web">Web</span>`;

        let metaTime = isSaved && ts ? `<span class="card-time">${ts}</span>` : '';

        let sourceName = item.site_name || '';
        if (!sourceName && item.url) {
            try { sourceName = new URL(item.url).hostname.replace('www.', ''); } catch {}
        }

        let urlDisplay = item.url || '';

        return `
<article class="result-card ${isSaved ? 'card-saved' : 'card-web'}">
  <div class="card-header">
    ${metaBadge}
    ${metaTime}
  </div>
  <a class="card-title" href="${item.url || '#'}" target="_blank" rel="noopener">${highlightedTitle}</a>
  ${urlDisplay ? `<div class="card-url">${urlDisplay}</div>` : ''}
  ${sourceName ? `<div class="card-source">${sourceName}</div>` : ''}
  ${content ? `<p class="card-content">${highlightedContent}</p>` : ''}
</article>`;
    }

    function renderResults() {
        let items = allResults;
        if (currentMode === 'web') items = allResults.filter(r => r._type === 'web');
        else if (currentMode === 'saved') items = allResults.filter(r => r._type === 'saved');

        resultsContainer.innerHTML = items.map(createCard).join('');

        // Status
        statusBar.hidden = false;
        const total = allResults.length;
        const shown = items.length;
        if (browseMode) {
            resultCount.textContent = `${total} saved item${total !== 1 ? 's' : ''}`;
        } else if (currentQuery) {
            if (currentMode === 'all') {
                resultCount.textContent = `${total} result${total !== 1 ? 's' : ''} (${allResults.filter(r => r._type === 'saved').length} saved)`;
            } else if (currentMode === 'saved') {
                resultCount.textContent = `${shown} saved result${shown !== 1 ? 's' : ''}`;
            } else {
                resultCount.textContent = `${shown} web result${shown !== 1 ? 's' : ''}`;
            }
        } else {
            statusBar.hidden = true;
        }

        // Empty state
        if (total === 0 && currentQuery) {
            emptyState.hidden = false;
            emptyState.innerHTML = `
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                </div>
                <h3>No results for "${currentQuery}"</h3>
                ${currentMode !== 'web' ? '<p>Try different keywords, or switch to All to include web results.</p>' : ''}
            `;
        } else {
            emptyState.hidden = true;
        }

        // Sentinel for infinite scroll (only for web mode with pagination)
        if (hasMore && !browseMode) {
            sentinel.hidden = false;
        } else {
            sentinel.hidden = true;
        }
    }

    // ─── Fetching ────────────────────────────────────────────────
    async function doSearch(query, page) {
        if (loading) return;
        loading = true;

        const pageSize = getPageSize();
        const url = `/search?q=${encodeURIComponent(query)}&page=${page}&count=${pageSize}&mode=all&engines=${getEngines()}`;

        try {
            const resp = await fetch(url);
            const data = await resp.json();

            if (!Array.isArray(data)) {
                loading = false;
                return;
            }

            if (page === 1) {
                allResults = data;
            } else {
                // Append web results (local results are already all returned page 1)
                const existingUrls = new Set(allResults.map(r => r.url));
                const newWeb = data.filter(r => r._type === 'web' && !existingUrls.has(r.url));
                allResults = allResults.concat(newWeb);
            }

            // Determine if there might be more web results
            hasMore = data.length >= pageSize;
            currentPage = page;

            renderResults();
        } catch (err) {
            console.error('Search failed:', err);
            resultsContainer.innerHTML = `<div class="message error">Search request failed. Is the server running?</div>`;
        }

        loading = false;
    }

    async function loadBrowse() {
        loading = true;
        browseMode = true;
        currentQuery = '';

        try {
            const resp = await fetch('/search?q=&mode=all');
            const data = await resp.json();

            if (!Array.isArray(data)) {
                allResults = [];
            } else {
                // Only keep saved items for browse
                allResults = data.filter(r => r._type === 'saved');
            }

            hasMore = false;
            currentPage = 1;
            renderResults();

            if (allResults.length === 0) {
                emptyState.hidden = false;
                emptyState.innerHTML = `
                    <div class="empty-icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                    </div>
                    <h3>Nothing saved yet</h3>
                    <p>Use the Recollect browser extension to save content from the web.</p>
                `;
            }
        } catch (err) {
            console.error('Browse failed:', err);
            resultsContainer.innerHTML = `<div class="message error">Could not load saved content.</div>`;
        }

        loading = false;
    }

    // ─── Search submit ────────────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        browseMode = false;
        currentQuery = query;
        currentPage = 1;
        hasMore = true;
        allResults = [];
        filterBar.hidden = false;
        renderFilterTabs('all');

        await doSearch(query, 1);
        queryInput.blur();
    });

    // ─── Browse button ────────────────────────────────────────────
    browseBtn.addEventListener('click', () => {
        queryInput.value = '';
        currentQuery = '';
        currentMode = 'all';
        filterBar.hidden = true;
        loadBrowse();
    });

    // ─── Infinite scroll (observer) ──────────────────────────────
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);

    // ─── Init: show browse on load ───────────────────────────────
    loadBrowse();
});