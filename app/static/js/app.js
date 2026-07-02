window.addEventListener('DOMContentLoaded', async () => {
    const pageShell = document.getElementById('page-shell');
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const resultsContainer = document.getElementById('results-container');
    const sentinel = document.getElementById('results-sentinel');
    const loadMoreButton = document.getElementById('load-more-button');
    const bottomLoading = document.getElementById('bottom-loading');
    const endOfResults = document.getElementById('end-of-results');
    const emptyState = document.getElementById('empty-state');
    const statusBar = document.getElementById('status-bar');
    const resultCount = document.getElementById('result-count');
    const browseBtn = document.getElementById('browse-btn');
    const filterBar = document.getElementById('filter-bar');
    const settingsButton = document.getElementById('settings-button');
    const loadingIndicator = document.getElementById('loading-indicator');
    const previewPane = document.getElementById('preview-content');
    const previewHint = document.querySelector('.preview-hint');
    const previewEmptyState = document.getElementById('preview-empty');

    const scrollTopButton = document.createElement('button');
    scrollTopButton.id = 'scroll-top-button';
    scrollTopButton.className = 'scroll-top-button';
    scrollTopButton.type = 'button';
    scrollTopButton.hidden = true;
    scrollTopButton.textContent = '↑';
    document.body.appendChild(scrollTopButton);

    let currentMode = 'all';
    let currentQuery = '';
    let currentPage = 1;
    let loading = false;
    let hasMore = false;
    let allResults = [];
    let browseMode = false;
    let searchActive = false;
    let activeProject = '';
    let activeTag = '';
    let previewItem = null;
    let pinnedPreviewItem = null;
    let previewHoverTimer = null;
    let renderSequence = 0;
    let renderedIndices = new Set();

    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const settingsList = document.getElementById('settings-list');
    const settingsSave = document.getElementById('settings-save');
    const settingsCategories = document.getElementById('settings-categories');
    const settingsCategoryTitle = document.getElementById('settings-category-title');
    const settingsCategoryDescription = document.getElementById('settings-category-description');
    const settingsSearchInput = document.getElementById('settings-search-input');

    const searchEngineFields = [
        { key: 'engine_duckduckgo', engine: 'duckduckgo', label: 'DuckDuckGo', default: true },
        { key: 'engine_google', engine: 'google', label: 'Google', default: true },
        { key: 'engine_bing', engine: 'bing', label: 'Bing', default: true },
        { key: 'engine_wikipedia', engine: 'wikipedia', label: 'Wikipedia', default: true },
        { key: 'engine_github', engine: 'github', label: 'GitHub', default: true },
        { key: 'engine_startpage', engine: 'startpage', label: 'Startpage', default: true },
        { key: 'engine_brave', engine: 'brave', label: 'Brave', default: false },
        { key: 'engine_yahoo', engine: 'yahoo', label: 'Yahoo', default: false },
        { key: 'engine_yahoo_news', engine: 'yahoo_news', label: 'Yahoo News', default: false },
        { key: 'engine_google_news', engine: 'google_news', label: 'Google News', default: false },
        { key: 'engine_duckduckgo_extra', engine: 'duckduckgo_extra', label: 'DuckDuckGo Extra', default: false },
        { key: 'engine_google_images', engine: 'google_images', label: 'Google Images', default: false },
        { key: 'engine_bing_images', engine: 'bing_images', label: 'Bing Images', default: false },
        { key: 'engine_google_videos', engine: 'google_videos', label: 'Google Videos', default: false },
        { key: 'engine_duckduckgo_weather', engine: 'duckduckgo_weather', label: 'DuckDuckGo Weather', default: false },
        { key: 'engine_github_code', engine: 'github_code', label: 'GitHub Code', default: false },
        { key: 'engine_google_scholar', engine: 'google_scholar', label: 'Google Scholar', default: false },
        { key: 'engine_google_play', engine: 'google_play', label: 'Google Play', default: false },
        { key: 'engine_reddit', engine: 'reddit', label: 'Reddit', default: false }
    ];

    let activeSettingsCategory = 'Appearance';
    const settingsSchema = [
        {
            category: 'Appearance',
            description: 'Appearance and animation settings.',
            items: [
                { key: 'theme', label: 'Theme', type: 'select', options: [{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }], default: 'dark' },
                { key: 'animationSpeed', label: 'Reveal animation speed', type: 'select', options: [{ value: 'fast', label: 'Fast' }, { value: 'normal', label: 'Normal' }, { value: 'slow', label: 'Slow' }, { value: 'instant', label: 'Instant (no animation)' }], default: 'fast' }
            ]
        },
        {
            category: 'Search',
            description: 'Search behavior and web result display settings.',
            items: [
                { key: 'showEngines', label: 'Show search engine badges on web results', type: 'checkbox', default: true },
                { key: 'autoLoad', label: 'Auto load more results on scroll', type: 'checkbox', default: true },
                { key: 'hoverPreview', label: 'Enable hover preview in the right pane', type: 'checkbox', default: true }
            ]
        },
        {
            category: 'Search engines',
            description: 'Choose which search engines are included in your queries.',
            items: searchEngineFields.map(field => ({ key: field.key, label: field.label, type: 'checkbox', default: field.default }))
        }
    ];

    const settingsState = {};

    function getValue(item) {
        const stored = localStorage.getItem(item.key);
        if (stored === null) return item.default;
        if (item.type === 'checkbox') return stored === 'true';
        if (item.type === 'number') return Number(stored);
        return stored;
    }

    function setValue(key, value) {
        settingsState[key] = value;
        localStorage.setItem(key, Array.isArray(value) ? JSON.stringify(value) : String(value));
    }

    function createField(item) {
        const value = getValue(item);
        settingsState[item.key] = value;
        const categoryAttr = item.category ? ` data-category="${item.category}"` : '';
        if (item.type === 'select') {
            return `<label class="settings-field"${categoryAttr}><span>${item.label}</span><select data-key="${item.key}">${item.options.map(o => `<option value="${o.value}" ${o.value === value ? 'selected' : ''}>${o.label}</option>`).join('')}</select></label>`;
        }
        if (item.type === 'checkbox') {
            return `<label class="settings-field toggle-field"${categoryAttr}><span>${item.label}</span><input type="checkbox" data-key="${item.key}" ${value ? 'checked' : ''} /></label>`;
        }
        return `<label class="settings-field"${categoryAttr}><span>${item.label}</span><input type="${item.type}" data-key="${item.key}" value="${value}" min="${item.min || ''}" max="${item.max || ''}" /></label>`;
    }

    function renderCategoryNav() {
        settingsCategories.innerHTML = settingsSchema.map(cat => `
            <li class="settings-category-item">
              <button type="button" class="settings-category-button${cat.category === activeSettingsCategory ? ' active' : ''}" data-category="${cat.category}">${cat.category}</button>
            </li>
        `).join('');
    }

    function renderSettings() {
        const category = settingsSchema.find(cat => cat.category === activeSettingsCategory) || settingsSchema[0];
        settingsCategoryTitle.textContent = category.category;
        settingsCategoryDescription.textContent = category.description || '';
        settingsList.innerHTML = category.items.map(item => createField({ ...item, category: category.category })).join('');
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
    }

    function filterSettings(query) {
        const q = query.toLowerCase().trim();
        const fields = settingsList.querySelectorAll('.settings-field');
        fields.forEach(field => {
            const label = field.querySelector('span')?.textContent?.toLowerCase() || '';
            const catName = field.closest('[data-category]')?.dataset.category?.toLowerCase() || '';
            field.style.display = (!q || label.includes(q) || catName.includes(q)) ? '' : 'none';
        });
    }

    settingsSearchInput?.addEventListener('input', (e) => filterSettings(e.target.value));
    settingsCategories?.addEventListener('click', (e) => {
        const button = e.target.closest('.settings-category-button');
        if (!button) return;
        activeSettingsCategory = button.dataset.category;
        renderCategoryNav();
        renderSettings();
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
    });

    function readSettings() {
        settingsSchema.forEach(cat => {
            cat.items.forEach(item => {
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

    function openSettings() { renderCategoryNav(); renderSettings(); if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value); settingsOverlay.hidden = false; settingsOverlay.inert = false; }
    function closeSettings() { document.activeElement?.blur(); settingsOverlay.inert = true; settingsOverlay.hidden = true; }

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
        const theme = settingsState.theme || 'dark';
        document.documentElement.dataset.theme = theme === 'light' ? 'light' : '';
    }
    applyTheme();

    function getEngines() {
        const values = searchEngineFields.filter(field => settingsState[field.key] !== false).map(field => field.engine);
        return values.length ? values.join(',') : 'duckduckgo';
    }

    function getShowEngines() { return settingsState.showEngines !== false; }
    function getHoverPreviewEnabled() { return settingsState.hoverPreview !== false; }
    function getAnimationSpeedStr() { return settingsState.animationSpeed || 'fast'; }

    function setSearchActive(active) {
        searchActive = active;
        pageShell.classList.toggle('search-active', active);
    }

    function renderFilterTabs(mode) {
        filterBar.hidden = false;
        filterBar.querySelectorAll('.filter-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    }

    function setFilter(mode) {
        currentMode = mode;
        renderFilterTabs(mode);
        renderResults(false);
    }

    function clearSkeletons() {
        resultsContainer.querySelectorAll('.result-card.skeleton').forEach(card => card.remove());
    }

    function renderLoadingSkeletons(count = 4, append = false) {
        if (!append) resultsContainer.innerHTML = '';
        const skeletons = Array.from({ length: count }, () => `
            <article class="result-card skeleton">
              <div class="card-meta"><span class="skeleton-dot"></span><span class="skeleton-line skeleton-short"></span></div>
              <span class="card-title skeleton-line skeleton-title"></span>
              <p class="card-content skeleton-line skeleton-paragraph"></p>
            </article>
        `).join('');
        resultsContainer.insertAdjacentHTML('beforeend', skeletons);
    }

    function showLoading(show, page) {
        if (show) {
            loadingIndicator.hidden = false;
            if (page === 1) renderLoadingSkeletons(5, false);
            else renderLoadingSkeletons(3, true);
            bottomLoading.hidden = page === 1;
        } else {
            loadingIndicator.hidden = true;
            clearSkeletons();
            bottomLoading.hidden = true;
        }
    }

    filterBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-btn');
        if (btn) setFilter(btn.dataset.mode);
    });

    function parseDate(isoStr) {
        if (!isoStr) return null;
        const cleaned = isoStr.replace('+00:00Z', 'Z').replace('+00:00', 'Z').replace('+0000', '');
        const d = new Date(cleaned);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatTime(isoStr) {
        const d = parseDate(isoStr);
        if (!d) return '';
        const days = Math.floor((Date.now() - d) / (1000 * 60 * 60 * 24));
        if (days === 0) return 'today';
        if (days === 1) return 'yesterday';
        return days < 7 ? `${days} days ago` : d.toLocaleDateString();
    }

    function formatRelative(isoStr) {
        const d = parseDate(isoStr);
        if (!d) return '';
        const diffSec = Math.floor((Date.now() - d) / 1000);
        if (diffSec < 60) return 'just now';
        const minutes = Math.floor(diffSec / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        if (days < 30) return `${Math.floor(days / 7)}w ago`;
        return d.toLocaleDateString();
    }

    function formatTimeLong(isoStr) {
        const d = parseDate(isoStr);
        if (!d) return 'Unknown date';
        return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value || '';
        return div.innerHTML;
    }

    function highlightText(text, query) {
        if (!query || !text) return text;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const words = escaped.split(/\s+/).filter(Boolean);
        if (!words.length) return text;
        const pattern = new RegExp(`(${words.join('|')})`, 'gi');
        return text.replace(pattern, '<mark>$1</mark>');
    }

    function getDomain(item) {
        if (!item.url) return 'web';
        try {
            return new URL(item.url).hostname.replace('www.', '');
        } catch {
            return item.site_name || 'web';
        }
    }

    function getFaviconHtml(item, domain) {
        if (domain) {
            const faviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
            return `<img class="card-favicon" src="${faviconUrl}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
        }
        return `<span class="card-favicon-fallback">${(domain || 'W').charAt(0).toUpperCase()}</span>`;
    }

    function getResultMeta(item) {
        const isSaved = item._type === 'saved';
        const ts = formatTime(item.saved_at);
        const domain = getDomain(item);
        const siteName = (item.site_name || '').trim();
        const chips = [];
        if (item.project) chips.push(item.project);
        if (Array.isArray(item.tags)) item.tags.filter(Boolean).forEach(tag => chips.push(tag));
        return { isSaved, ts, domain, siteName, chips };
    }

    function createCard(item) {
        const { isSaved, ts, domain, siteName, chips } = getResultMeta(item);
        const title = item.title || item.url || 'Untitled';
        const content = item.content || '';
        const highlightedTitle = highlightText(title, currentQuery);
        const highlightedContent = highlightText(content, currentQuery);
        const badgeClass = isSaved ? 'saved' : 'web';
        const badgeLabel = isSaved ? 'Saved' : 'Web';
        const enginesHtml = !isSaved && getShowEngines() && Array.isArray(item.engines) && item.engines.length > 0
            ? `<span class="card-engines">${item.engines.map(e => `<span class="card-engine-badge">${escapeHtml(e)}</span>`).join('')}</span>`
            : '';
        const chipHtml = chips.slice(0, 2).map(ch => `<span class="card-chip">${escapeHtml(ch)}</span>`).join('');
        const globalIndex = allResults.findIndex(r => r === item);
        return `
          <article class="result-card ${isSaved ? 'card-saved' : 'card-web'}" data-type="${isSaved ? 'saved' : 'web'}" data-index="${globalIndex}">
            <div class="card-meta">
              ${getFaviconHtml(item, domain)}
              <span class="card-domain">${escapeHtml(siteName || domain)}</span>
              <span class="card-badge ${badgeClass}">${badgeLabel}</span>
              ${enginesHtml}
              ${isSaved && ts ? `<span class="card-time">${ts}</span>` : ''}
            </div>
            <span class="card-title" data-url="${item.url || '#'}">${highlightedTitle}</span>
            ${content ? `<p class="card-content">${highlightedContent}</p>` : ''}
            ${chipHtml ? `<div class="card-footer">${chipHtml}</div>` : ''}
          </article>`;
    }

    function getFilteredItems(items = allResults) {
        let filtered = items;
        if (activeProject) {
            if (activeProject === '__uncategorized__') {
                filtered = filtered.filter(item => !item.project || item.project.trim() === '');
            } else {
                filtered = filtered.filter(item => (item.project || '').trim() === activeProject);
            }
        }
        if (activeTag) {
            filtered = filtered.filter(item => Array.isArray(item.tags) && item.tags.includes(activeTag));
        }
        if (currentMode === 'saved') {
            filtered = filtered.filter(item => item._type === 'saved');
        } else if (currentMode === 'web') {
            filtered = filtered.filter(item => item._type === 'web');
        }
        return filtered;
    }

    function updateStatusBar(items) {
        statusBar.hidden = false;
        const total = allResults._total || allResults.length;
        const visible = items.length;
        if (browseMode) {
            resultCount.textContent = `${total} saved item${total !== 1 ? 's' : ''}`;
        } else if (currentQuery) {
            if (currentMode === 'all') {
                resultCount.textContent = `${visible} result${visible !== 1 ? 's' : ''} (${allResults.filter(r => r._type === 'saved').length} saved)`;
            } else if (currentMode === 'saved') {
                resultCount.textContent = `${visible} saved result${visible !== 1 ? 's' : ''}`;
            } else {
                resultCount.textContent = `${visible} web result${visible !== 1 ? 's' : ''}`;
            }
        } else {
            statusBar.hidden = true;
        }
    }

    function updatePaginationControls() {
        const autoLoad = settingsState.autoLoad !== false;
        const showLoadMore = !autoLoad && hasMore && !browseMode && currentQuery;
        const showSentinel = autoLoad && hasMore && !browseMode && currentQuery;
        const showEndMessage = !hasMore && !browseMode && currentQuery && allResults.length > 0;
        sentinel.hidden = !showSentinel;
        loadMoreButton.hidden = !showLoadMore;
        endOfResults.hidden = !showEndMessage;
        if (showEndMessage) bottomLoading.hidden = true;
    }

    function attachCardHandlers() {
        resultsContainer.querySelectorAll('.result-card').forEach(card => {
            if (card._bound) return;
            card._bound = true;
            card.addEventListener('mouseenter', () => {
                if (!getHoverPreviewEnabled() || pinnedPreviewItem) return;
                const index = Number(card.dataset.index);
                const item = allResults[index];
                if (item) {
                    clearTimeout(previewHoverTimer);
                    previewHoverTimer = setTimeout(() => showPreview(item), 180);
                }
            });
            card.addEventListener('mouseleave', () => {
                clearTimeout(previewHoverTimer);
            });
            card.addEventListener('click', (e) => {
                const titleEl = e.target.closest('.card-title');
                if (titleEl) {
                    const url = titleEl.dataset.url;
                    if (url && url !== '#') window.open(url, '_blank', 'noopener');
                    return;
                }
                const index = Number(card.dataset.index);
                const item = allResults[index];
                if (!item) return;
                pinnedPreviewItem = item;
                showPreview(item, true);
            });
        });
    }

    function renderResults(append = false) {
        const items = getFilteredItems(allResults);
        if (!append) {
            renderedIndices = new Set();
            resultsContainer.innerHTML = '';
            const sections = [];
            const savedItems = items.filter(item => item._type === 'saved');
            const webItems = items.filter(item => item._type === 'web');
            if (currentMode === 'all') {
                if (savedItems.length > 0) sections.push(`<div class="results-group"><div class="results-group-header">Your Library</div>${savedItems.map(createCard).join('')}</div>`);
                if (webItems.length > 0) sections.push(`<div class="results-group"><div class="results-group-header">Web Results</div>${webItems.map(createCard).join('')}</div>`);
            } else {
                const header = currentMode === 'saved' ? 'Saved Results' : 'Web Results';
                sections.push(`<div class="results-group"><div class="results-group-header">${header}</div>${items.map(createCard).join('')}</div>`);
            }
            resultsContainer.innerHTML = sections.join('');
            attachCardHandlers();
            resultsContainer.querySelectorAll('.result-card').forEach((card, idx) => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => card.classList.add('visible'));
                });
            });
        } else {
            const newItems = items.filter(item => !renderedIndices.has(allResults.findIndex(r => r === item)));
            if (!newItems.length) return;
            const html = newItems.map(createCard).join('');
            resultsContainer.insertAdjacentHTML('beforeend', html);
            newItems.forEach(item => renderedIndices.add(allResults.findIndex(r => r === item)));
            attachCardHandlers();
            resultsContainer.querySelectorAll('.result-card').forEach(card => { if (!card.classList.contains('visible')) card.classList.add('visible'); });
        }

        updateStatusBar(items);
        const total = allResults._total || allResults.length;
        if (total === 0 && currentQuery) {
            emptyState.hidden = false;
            emptyState.innerHTML = `
                <div class="empty-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
                </div>
                <h3>No results for "${escapeHtml(currentQuery)}"</h3>
                <p>Try different keywords. Saved content stays in your workspace while web results are layered beneath.</p>`;
        } else {
            emptyState.hidden = true;
        }
        updatePaginationControls();
    }

    async function doSearch(query, page) {
        if (loading) return;
        loading = true;
        showLoading(true, page);
        const url = `/search?q=${encodeURIComponent(query)}&page=${page}&engines=${getEngines()}${activeProject ? `&project=${encodeURIComponent(activeProject)}` : ''}`;
        try {
            const resp = await fetch(url);
            const data = await resp.json();
            if (!data || !Array.isArray(data.results)) {
                showLoading(false, page);
                loading = false;
                return;
            }
            const fetched = data.results;
            const total = data.total || 0;
            if (page === 1) {
                allResults = fetched;
                allResults._total = total;
                showLoading(false, page);
                renderResults(false);
            } else {
                const existingUrls = new Set(allResults.map(r => r.url));
                const newWeb = fetched.filter(r => r._type === 'web' && !existingUrls.has(r.url));
                allResults = allResults.concat(newWeb);
                allResults._total = total;
                showLoading(false, page);
                renderResults(true);
            }
            hasMore = fetched.length > 0;
            currentPage = page;
            if (!hasMore && allResults.length > 0) endOfResults.hidden = false;
        } catch (err) {
            console.error('Search failed:', err);
            showLoading(false, page);
            resultsContainer.innerHTML = '<div class="message error">Search request failed. Is the server running?</div>';
            hasMore = false;
        } finally {
            loading = false;
            updatePaginationControls();
        }
    }

    async function loadBrowse() {
        loading = true;
        browseMode = true;
        currentQuery = '';
        setSearchActive(false);
        try {
            const url = activeProject ? `/browse?project=${encodeURIComponent(activeProject)}` : '/browse';
            const resp = await fetch(url);
            const data = await resp.json();
            allResults = Array.isArray(data) ? data.filter(r => r._type === 'saved') : [];
            hasMore = false;
            currentPage = 1;
            renderResults(false);
        } catch (err) {
            console.error('Browse failed:', err);
            resultsContainer.innerHTML = '<div class="message error">Could not load saved content.</div>';
        }
        loading = false;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;
        browseMode = false;
        currentQuery = query;
        currentPage = 1;
        hasMore = true;
        allResults = [];
        emptyState.hidden = true;
        setSearchActive(true);
        filterBar.hidden = false;
        renderFilterTabs('all');
        await doSearch(query, 1);
        queryInput.blur();
    });

    browseBtn.addEventListener('click', () => {
        queryInput.value = '';
        currentQuery = '';
        currentMode = 'all';
        filterBar.hidden = true;
        setSearchActive(false);
        loadBrowse();
    });

    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad !== false) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);

    loadMoreButton?.addEventListener('click', () => {
        if (!loading && hasMore && currentQuery) doSearch(currentQuery, currentPage + 1);
    });

    scrollTopButton.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    function handleScrollTopVisibility() { scrollTopButton.hidden = window.scrollY <= window.innerHeight; }
    window.addEventListener('scroll', handleScrollTopVisibility, { passive: true });
    handleScrollTopVisibility();

    function renderMarkdown(markdown) {
        const text = markdown || '';
        if (!text.trim()) return '<p class="preview-placeholder">No content yet.</p>';
        const lines = text.split(/\n/);
        let html = '';
        let paragraph = [];
        let inList = false;
        const flushParagraph = () => {
            if (!paragraph.length) return;
            const joined = paragraph.join(' ').trim();
            if (joined) html += `<p>${formatInline(joined)}</p>`;
            paragraph = [];
        };
        const flushList = () => {
            if (!inList) return;
            html += '</ul>';
            inList = false;
        };
        lines.forEach(line => {
            const trimmed = line.trim();
            if (/^#{1,6}\s/.test(trimmed)) {
                flushParagraph();
                flushList();
                const level = trimmed.match(/^#+/)[0].length;
                const content = trimmed.replace(/^#{1,6}\s/, '');
                html += `<h${Math.min(level, 3)}>${formatInline(content)}</h${Math.min(level, 3)}>`;
            } else if (/^[-*]\s+/.test(trimmed)) {
                flushParagraph();
                if (!inList) {
                    html += '<ul>';
                    inList = true;
                }
                html += `<li>${formatInline(trimmed.replace(/^[-*]\s+/, ''))}</li>`;
            } else if (/^```/.test(trimmed)) {
                flushParagraph();
                flushList();
                html += '<pre><code>' + escapeHtml(text) + '</code></pre>';
            } else if (!trimmed) {
                flushParagraph();
                flushList();
            } else {
                paragraph.push(trimmed);
            }
        });
        flushParagraph();
        flushList();
        return html || `<pre>${escapeHtml(text)}</pre>`;
    }

    function formatInline(text) {
        return escapeHtml(text)
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    }

    function showPreview(item, pin = false) {
        if (!item) {
            previewPane.innerHTML = '<div class="preview-empty"><div class="preview-title">Select a result</div><p>Hover to preview notes and saved items here.</p></div>';
            previewHint.textContent = 'Hover • click to pin';
            return;
        }
        if (!pin) previewItem = item;
        else previewItem = item;
        const isSaved = item._type === 'saved';
        const { domain, siteName, chips } = getResultMeta(item);
        const previewTitle = item.title || item.url || 'Untitled';
        const previewDate = formatTimeLong(item.saved_at);
        const previewBody = item.content || item.description || item.snippet || '';
        const previewMeta = [
            ['Title', previewTitle],
            ['Website', siteName || domain || item.url || '—'],
            ['Saved', previewDate || '—'],
            ['Project', item.project || '—'],
            ['Tags', Array.isArray(item.tags) && item.tags.length ? item.tags.join(', ') : '—']
        ];
        const actions = `
          <div class="preview-actions">
            <button class="preview-action-btn" data-action="open" type="button">Open website</button>
            <button class="preview-action-btn" data-action="copy" type="button">Copy</button>
            <button class="preview-action-btn" data-action="edit" type="button">Edit</button>
            <button class="preview-action-btn" data-action="delete" type="button">Delete</button>
            <button class="preview-action-btn" data-action="move" type="button">Move to project</button>
          </div>`;
        previewPane.innerHTML = `
          <div class="preview-card">
            <div class="preview-meta-list">
              ${previewMeta.map(([label, value]) => `<div class="preview-meta-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`).join('')}
            </div>
            ${actions}
            <div class="preview-content">${renderMarkdown(previewBody)}</div>
          </div>`;
        previewHint.textContent = pin ? 'Pinned preview' : 'Hover • click to pin';
        const actionButtons = previewPane.querySelectorAll('.preview-action-btn');
        actionButtons.forEach(btn => btn.addEventListener('click', () => handlePreviewAction(btn.dataset.action, item)));
        if (isSaved && item.url) {
            previewPane.querySelector('.preview-content').dataset.url = item.url;
        }
    }

    async function handlePreviewAction(action, item) {
        if (!item) return;
        if (action === 'open') {
            if (item.url) window.open(item.url, '_blank', 'noopener');
            return;
        }
        if (action === 'copy') {
            const text = `${item.title || ''}\n\n${item.content || ''}`.trim();
            navigator.clipboard.writeText(text).catch(() => {});
            return;
        }
        if (action === 'edit') {
            openEditModal(item);
            return;
        }
        if (action === 'move') {
            openEditModal(item);
            return;
        }
        if (action === 'delete') {
            if (!confirm('Delete this saved item?')) return;
            try {
                const resp = await fetch(`/api/capture/${item.id || item.capture_id}`, { method: 'DELETE' });
                const data = await resp.json();
                if (data.success) {
                    allResults = allResults.filter(r => (r.id || r.capture_id) !== (item.id || item.capture_id));
                    renderResults(false);
                    if (previewItem && (previewItem.id || previewItem.capture_id) === (item.id || item.capture_id)) {
                        previewItem = null;
                        pinnedPreviewItem = null;
                        showPreview(null);
                    }
                }
            } catch (err) {
                console.error('Delete failed', err);
            }
        }
    }

    function updatePreviewFromSelection() {
        if (pinnedPreviewItem) {
            showPreview(pinnedPreviewItem, true);
        } else if (previewItem) {
            showPreview(previewItem, false);
        } else {
            showPreview(null);
        }
    }

    function setPinnedPreview(item) {
        pinnedPreviewItem = item;
        showPreview(item, true);
    }

    const sidebarProjectList = document.getElementById('sidebar-project-list');
    const sidebarTags = document.getElementById('sidebar-tags');
    const sidebarNewProject = document.getElementById('sidebar-new-project');
    const sidebarAddBtn = document.getElementById('sidebar-add-btn');

    function loadProjects() {
        fetch('/api/tags').then(r => r.json()).then(data => {
            const projects = data.projects || [];
            sidebarProjectList.innerHTML = '';
            const allBtn = document.createElement('button');
            allBtn.className = 'sidebar-item' + (!activeProject ? ' active' : '');
            allBtn.innerHTML = '<span class="sidebar-item-icon">⌘</span><span class="sidebar-item-label">All items</span><span class="sidebar-item-count">' + (data.total_items || 0) + '</span>';
            allBtn.addEventListener('click', () => selectProject(''));
            sidebarProjectList.appendChild(allBtn);
            const uncatBtn = document.createElement('button');
            uncatBtn.className = 'sidebar-item sidebar-item-uncat' + (activeProject === '__uncategorized__' ? ' active' : '');
            uncatBtn.innerHTML = '<span class="sidebar-item-icon">?</span><span class="sidebar-item-label">Uncategorized</span><span class="sidebar-item-count">' + (data.uncategorized || 0) + '</span>';
            uncatBtn.addEventListener('click', () => selectProject('__uncategorized__'));
            sidebarProjectList.appendChild(uncatBtn);
            projects.forEach(project => {
                const button = document.createElement('button');
                button.className = 'sidebar-item' + (activeProject === project.name ? ' active' : '');
                button.innerHTML = `<span class="sidebar-item-icon">▣</span><span class="sidebar-item-label">${escapeHtml(project.name)}</span><span class="sidebar-item-count">${project.count}</span>`;
                button.addEventListener('click', () => selectProject(project.name));
                sidebarProjectList.appendChild(button);
            });
            sidebarTags.innerHTML = '';
            (data.tags || []).forEach(tag => {
                const btn = document.createElement('button');
                btn.className = 'sidebar-tag-btn' + (activeTag === tag ? ' active' : '');
                btn.textContent = tag;
                btn.addEventListener('click', () => {
                    activeTag = activeTag === tag ? '' : tag;
                    loadProjects();
                    renderResults(false);
                });
                sidebarTags.appendChild(btn);
            });
            ['note-project', 'edit-project'].forEach(id => {
                const select = document.getElementById(id);
                if (!select) return;
                const currentValue = select.value;
                select.innerHTML = '<option value="">— None —</option>';
                projects.forEach(project => {
                    const option = document.createElement('option');
                    option.value = project.name;
                    option.textContent = project.name;
                    if (project.name === currentValue) option.selected = true;
                    select.appendChild(option);
                });
            });
        });
    }

    function selectProject(project) {
        activeProject = project;
        loadProjects();
        if (!currentQuery) {
            loadBrowse();
        } else {
            doSearch(currentQuery, 1);
        }
        renderResults(false);
    }

    sidebarAddBtn.addEventListener('click', async () => {
        const name = sidebarNewProject.value.trim();
        if (!name) return;
        sidebarNewProject.value = '';
        try {
            await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
        } catch (err) {
            console.error('Create project failed', err);
        }
        loadProjects();
        setTimeout(() => selectProject(name), 120);
    });

    sidebarNewProject.addEventListener('keydown', (e) => { if (e.key === 'Enter') sidebarAddBtn.click(); });
    document.getElementById('sidebar-search-nav')?.addEventListener('click', () => queryInput.focus());

    const noteModal = document.getElementById('note-modal');
    const noteClose = document.getElementById('note-close');
    const noteCancel = document.getElementById('note-cancel');
    const noteSave = document.getElementById('note-save');
    const noteTitle = document.getElementById('note-title');
    const noteContent = document.getElementById('note-content');
    const noteStatus = document.getElementById('note-status');
    const newNoteBtn = document.getElementById('new-note-btn');

    function openNoteModal() {
        noteTitle.value = '';
        noteContent.value = '';
        noteStatus.hidden = true;
        noteModal.hidden = false;
        noteModal.inert = false;
        setTimeout(() => noteTitle.focus(), 120);
    }
    function closeNoteModal() { noteModal.hidden = true; noteModal.inert = true; }
    if (newNoteBtn) newNoteBtn.addEventListener('click', openNoteModal);
    noteClose.addEventListener('click', closeNoteModal);
    noteCancel.addEventListener('click', closeNoteModal);
    noteModal.addEventListener('click', (e) => { if (e.target === noteModal) closeNoteModal(); });

    noteSave.addEventListener('click', async () => {
        const title = noteTitle.value.trim();
        const content = noteContent.value.trim();
        if (!title || !content) {
            noteStatus.textContent = title ? 'Content is required' : 'Title is required';
            noteStatus.className = 'note-status error';
            noteStatus.hidden = false;
            return;
        }
        noteStatus.textContent = 'Saving...';
        noteStatus.className = 'note-status';
        noteStatus.hidden = false;
        noteSave.disabled = true;
        try {
            const resp = await fetch('/api/capture', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'manual', content, source: { url: '', title, site_name: 'Manual' }, project: document.getElementById('note-project').value || '', tags: [] })
            });
            const data = await resp.json();
            if (data.success) {
                noteStatus.textContent = 'Saved ✓';
                noteStatus.className = 'note-status success';
                setTimeout(() => { closeNoteModal(); loadBrowse(); }, 600);
            } else {
                noteStatus.textContent = 'Save failed';
                noteStatus.className = 'note-status error';
            }
        } catch (err) {
            noteStatus.textContent = 'Server error';
            noteStatus.className = 'note-status error';
        }
        noteSave.disabled = false;
    });

    const importModal = document.getElementById('import-modal');
    const importModalClose = document.getElementById('import-modal-close');
    const importDropzone = document.getElementById('import-dropzone');
    const importFileInput = document.getElementById('import-file-input');
    const importBrowseLink = document.getElementById('import-browse-link');
    const importProgress = document.getElementById('import-progress');
    const importStatusText = document.getElementById('import-status-text');
    const importResult = document.getElementById('import-result');
    const importDoneBtn = document.getElementById('import-done-btn');
    const importBtn = document.getElementById('import-btn');

    if (importBtn) importBtn.addEventListener('click', () => {
        importResult.hidden = true; importProgress.hidden = true; importDoneBtn.hidden = true; importModal.hidden = false; importModal.inert = false;
    });
    function closeImportModal() { importModal.hidden = true; importModal.inert = true; }
    importModalClose.addEventListener('click', closeImportModal);
    importModal.addEventListener('click', (e) => { if (e.target === importModal) closeImportModal(); });
    importDoneBtn.addEventListener('click', closeImportModal);
    importBrowseLink.addEventListener('click', () => importFileInput.click());
    importDropzone.addEventListener('click', () => importFileInput.click());
    importDropzone.addEventListener('dragover', (e) => { e.preventDefault(); importDropzone.classList.add('drag-over'); });
    importDropzone.addEventListener('dragleave', () => importDropzone.classList.remove('drag-over'));
    importDropzone.addEventListener('drop', (e) => { e.preventDefault(); importDropzone.classList.remove('drag-over'); if (e.dataTransfer.files.length) handleImportFile(e.dataTransfer.files[0]); });
    importFileInput.addEventListener('change', () => { if (importFileInput.files.length) handleImportFile(importFileInput.files[0]); });

    async function handleImportFile(file) {
        if (!file.name.endsWith('.html')) {
            importResult.textContent = 'Please select an .html bookmark file.';
            importResult.className = 'import-result error';
            importResult.hidden = false;
            return;
        }
        importProgress.hidden = false; importResult.hidden = true; importDoneBtn.hidden = true; importStatusText.textContent = `Importing ${file.name}...`;
        const formData = new FormData(); formData.append('file', file);
        try {
            const resp = await fetch('/api/import/bookmarks', { method: 'POST', body: formData });
            const data = await resp.json();
            importProgress.hidden = true;
            if (data.success) {
                importResult.innerHTML = `<div class="import-result success"><strong>${data.saved} / ${data.total}</strong> bookmarks imported</div>`;
                importResult.className = 'import-result';
                importResult.hidden = false;
                importDoneBtn.hidden = false;
                loadBrowse();
            } else {
                importResult.textContent = data.detail || 'Import failed';
                importResult.className = 'import-result error';
                importResult.hidden = false;
            }
        } catch (err) {
            importProgress.hidden = true;
            importResult.textContent = 'Server error — is Recollect running?';
            importResult.className = 'import-result error';
            importResult.hidden = false;
        }
    }

    const editModal = document.getElementById('edit-modal');
    const editClose = document.getElementById('edit-close');
    const editCancel = document.getElementById('edit-cancel');
    const editSave = document.getElementById('edit-save');
    const editProject = document.getElementById('edit-project');
    const editTagsList = document.getElementById('edit-tags-list');
    const editTagsInput = document.getElementById('edit-tags-input');
    const editTagsAdd = document.getElementById('edit-tags-add');
    const editStatus = document.getElementById('edit-status');
    let editingItem = null;

    function openEditModal(item) {
        editingItem = item;
        editProject.value = item.project || '';
        renderEditTags(item.tags || []);
        editStatus.hidden = true;
        editModal.hidden = false;
        editModal.inert = false;
        loadProjects();
    }
    function closeEditModal() { editModal.hidden = true; editModal.inert = true; editingItem = null; }
    function renderEditTags(tags) {
        editTagsList.innerHTML = '';
        (tags || []).forEach(tag => {
            const chip = document.createElement('span');
            chip.className = 'edit-tag-chip';
            chip.innerHTML = `${escapeHtml(tag)} <button class="edit-tag-remove" data-tag="${escapeHtml(tag)}">&times;</button>`;
            chip.querySelector('.edit-tag-remove').addEventListener('click', () => removeEditTag(tag));
            editTagsList.appendChild(chip);
        });
    }
    function getEditTags() { return [...editTagsList.querySelectorAll('.edit-tag-chip')].map(chip => chip.querySelector('.edit-tag-remove')?.dataset.tag).filter(Boolean); }
    function addEditTag(tag) { const t = tag.trim(); if (!t) return; const current = getEditTags(); if (current.includes(t)) return; renderEditTags([...current, t]); editTagsInput.value = ''; editTagsInput.focus(); }
    function removeEditTag(tag) { renderEditTags(getEditTags().filter(t => t !== tag)); }
    editClose.addEventListener('click', closeEditModal); editCancel.addEventListener('click', closeEditModal); editModal.addEventListener('click', (e) => { if (e.target === editModal) closeEditModal(); });
    editTagsAdd.addEventListener('click', () => addEditTag(editTagsInput.value)); editTagsInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addEditTag(editTagsInput.value); });
    editSave.addEventListener('click', async () => {
        if (!editingItem) return;
        const project = editProject.value || '';
        const tags = getEditTags();
        editStatus.textContent = 'Saving...'; editStatus.className = 'note-status'; editStatus.hidden = false; editSave.disabled = true;
        try {
            const resp = await fetch(`/api/capture/${editingItem.id || editingItem.capture_id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project, tags }) });
            const data = await resp.json();
            if (data.success) {
                editingItem.project = data.project; editingItem.tags = data.tags;
                const idx = allResults.findIndex(item => (item.id || item.capture_id) === (editingItem.id || editingItem.capture_id));
                if (idx >= 0) { allResults[idx].project = data.project; allResults[idx].tags = data.tags; }
                editStatus.textContent = 'Saved ✓'; editStatus.className = 'note-status success';
                loadProjects(); setTimeout(closeEditModal, 600); renderResults(false); if (pinnedPreviewItem && (pinnedPreviewItem.id || pinnedPreviewItem.capture_id) === (editingItem.id || editingItem.capture_id)) showPreview(pinnedPreviewItem, true);
            } else {
                editStatus.textContent = 'Save failed'; editStatus.className = 'note-status error';
            }
        } catch (err) {
            editStatus.textContent = 'Server error'; editStatus.className = 'note-status error';
        }
        editSave.disabled = false;
    });

    const extBanner = document.getElementById('extension-banner');
    const bannerClose = document.getElementById('banner-close');
    const bannerInstallLink = document.getElementById('banner-install-link');
    const installModal = document.getElementById('install-modal');
    const installClose = document.getElementById('install-close');
    function checkExtensionInstalled() { if (localStorage.getItem('bannerDismissed') === 'true') return; const sentinel = document.querySelector('meta[name="recollect-extension"]'); if (!sentinel || sentinel.content !== 'installed') extBanner.hidden = false; }
    bannerClose.addEventListener('click', () => { extBanner.hidden = true; localStorage.setItem('bannerDismissed', 'true'); });
    bannerInstallLink.addEventListener('click', () => { extBanner.hidden = true; installModal.hidden = false; installModal.inert = false; });
    installClose.addEventListener('click', () => { installModal.hidden = true; installModal.inert = true; });
    installModal.addEventListener('click', (e) => { if (e.target === installModal) { installModal.hidden = true; installModal.inert = true; } });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !installModal.hidden) { installModal.hidden = true; installModal.inert = true; } });
    setTimeout(checkExtensionInstalled, 300);

    const sidebarResizer = document.getElementById('sidebar-resizer');
    const previewResizer = document.getElementById('preview-resizer');
    const workspaceSidebar = document.getElementById('workspace-sidebar');
    const workspacePreview = document.getElementById('workspace-preview');
    function applyPanelWidths() {
        document.documentElement.style.setProperty('--sidebar-width', `${sidebarWidth}px`);
        document.documentElement.style.setProperty('--preview-width', `${previewWidth}px`);
        workspaceSidebar.style.width = `${sidebarWidth}px`;
        workspacePreview.style.width = `${previewWidth}px`;
    }

    let sidebarWidth = Number(localStorage.getItem('recollect.sidebarWidth') || 280);
    let previewWidth = Number(localStorage.getItem('recollect.previewWidth') || 360);
    applyPanelWidths();

    function startResize(side, startEvent) {
        const startX = startEvent.clientX;
        const startSidebar = sidebarWidth;
        const startPreview = previewWidth;
        const onMove = (e) => {
            if (side === 'left') {
                const next = Math.min(Math.max(220, startSidebar + (e.clientX - startX)), 360);
                sidebarWidth = next;
            } else {
                const next = Math.min(Math.max(320, startPreview - (e.clientX - startX)), 520);
                previewWidth = next;
            }
            applyPanelWidths();
        };
        const onUp = () => {
            localStorage.setItem('recollect.sidebarWidth', String(sidebarWidth));
            localStorage.setItem('recollect.previewWidth', String(previewWidth));
            document.body.classList.remove('resizing');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.body.classList.add('resizing');
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    sidebarResizer.addEventListener('mousedown', (e) => { e.preventDefault(); startResize('left', e); });
    previewResizer.addEventListener('mousedown', (e) => { e.preventDefault(); startResize('right', e); });

    document.addEventListener('click', (e) => {
        const card = e.target.closest('.result-card');
        if (!card) return;
        const index = Number(card.dataset.index);
        const item = allResults[index];
        if (item) {
            pinnedPreviewItem = item;
            showPreview(item, true);
        }
    });

    showPreview(null);
    renderSettings();
    loadBrowse();
    loadProjects();
    renderResults(false);
    updatePaginationControls();
});
