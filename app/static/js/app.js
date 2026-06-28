document.addEventListener('DOMContentLoaded', () => {
    // ─── DOM refs ────────────────────────────────────────────────
    const pageShell = document.getElementById('page-shell');
    const pageHeader = document.getElementById('page-header');
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
    const loadingIndicator = document.getElementById('loading-indicator');

    // ─── Modal DOM refs ──────────────────────────────────────────
    const snippetModal = document.getElementById('snippet-modal');
    const modalClose = document.getElementById('modal-close');
    const modalTitle = document.getElementById('modal-title');
    const modalSnippet = document.getElementById('modal-snippet');
    const modalContentText = document.getElementById('modal-content-text');
    const modalCtxBefore = document.getElementById('modal-context-before');
    const modalCtxAfter = document.getElementById('modal-context-after');
    const modalTime = document.getElementById('modal-time');
    const modalSource = document.getElementById('modal-source');
    const modalRelative = document.getElementById('modal-relative');
    const modalOpenUrl = document.getElementById('modal-open-url');

    // ─── State ──────────────────────────────────────────────────
    let currentMode = 'all';
    let currentQuery = '';
    let currentPage = 1;
    let loading = false;
    let hasMore = false;
    let allResults = [];
    let browseMode = false;
    let searchActive = false;

    // ─── Word reveal state ──────────────────────────────────────
    let revealTimer = null;

    // ─── Track rendered URLs for append-only rendering ─────────
    let renderedUrls = new Set();

    // ─── Settings overlay ───────────────────────────────────────
    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const settingsList = document.getElementById('settings-list');
    const settingsSave = document.getElementById('settings-save');

    const settingsSchema = [
        {
            category: 'General',
            items: [
                { key: 'theme', label: 'Theme', type: 'select',
                  options: [
                    { value: 'dark', label: 'Dark' },
                    { value: 'light', label: 'Light' }
                  ],
                  default: 'dark' },
            ]
        },
        {
            category: 'Search Behavior',
            items: [
                { key: 'resultsPerPage', label: 'Results per page', type: 'number', min: 1, max: 50, default: 10 },
                { key: 'showEngines', label: 'Show search engine badges on web results', type: 'checkbox', default: true },
                { key: 'engines', label: 'Search engines', type: 'checkbox-group',
                  options: [
                    { value: 'duckduckgo', label: 'DuckDuckGo' },
                    { value: 'bing', label: 'Bing' },
                    { value: 'google', label: 'Google' },
                    { value: 'wikipedia', label: 'Wikipedia' },
                    { value: 'github', label: 'GitHub' }
                  ],
                  default: ['duckduckgo'] },
                { key: 'autoLoad', label: 'Auto load more results on scroll', type: 'checkbox', default: true }
            ]
        },
        {
            category: 'Animations',
            items: [
                { key: 'animationSpeed', label: 'Reveal animation speed', type: 'select',
                  options: [
                    { value: 'fast', label: 'Fast' },
                    { value: 'normal', label: 'Normal' },
                    { value: 'slow', label: 'Slow' },
                    { value: 'instant', label: 'Instant (no animation)' }
                  ],
                  default: 'fast' },
            ]
        }
    ];

    const settingsState = {};

    function getValue(item) {
        const p = localStorage.getItem(item.key);
        if (p === null) return item.default;
        if (item.type === 'checkbox') return p === 'true';
        if (item.type === 'number') return Number(p);
        if (item.type === 'checkbox-group') { try { return JSON.parse(p); } catch { return item.default; } }
        return p;
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

    function openSettings() { renderSettings(); settingsOverlay.hidden = false; settingsOverlay.inert = false; }
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
        if (theme === 'light') {
            document.documentElement.dataset.theme = 'light';
        } else {
            document.documentElement.dataset.theme = '';
        }
    }
    applyTheme();

    function getEngines() {
        const e = settingsState.engines;
        return Array.isArray(e) ? e.join(',') : 'duckduckgo';
    }

    function getPageSize() { return Number(settingsState.resultsPerPage) || 10; }

    function getShowEngines() { return settingsState.showEngines !== false; }

    function getAnimationSpeedStr() { return settingsState.animationSpeed || 'fast'; }

    function getWordRevealDelayMs(totalWords) {
        const spd = getAnimationSpeedStr();
        let totalMs = 0;
        switch (spd) {
            case 'instant': totalMs = 0; break;
            case 'fast': totalMs = 500; break;
            case 'normal': totalMs = 1000; break;
            case 'slow': totalMs = 2500; break;
            default: totalMs = 500;
        }
        if (totalMs === 0 || !totalWords || totalWords === 0) return 0;
        return Math.max(10, totalMs / totalWords);
    }

    // ─── Header scroll effect ───────────────────────────────────
    function handleScroll() {
        const scrolled = window.scrollY > 15;
        pageHeader.classList.toggle('scrolled', scrolled);
    }
    window.addEventListener('scroll', handleScroll, { passive: true });

    // ─── Search active state ────────────────────────────────────
    function setSearchActive(active) {
        searchActive = active;
        pageShell.classList.toggle('search-active', active);
        pageHeader.classList.toggle('search-active', active);
    }

    // ─── Loading state ──────────────────────────────────────────
    function showLoading(show) {
        loadingIndicator.hidden = !show;
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
        renderedUrls = new Set();
        renderResults();
    }

    filterBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-btn');
        if (btn) setFilter(btn.dataset.mode);
    });

    // ─── Modal logic ──────────────────────────────────────────────

    function closeModal() {
        if (revealTimer) {
            clearInterval(revealTimer);
            revealTimer = null;
        }
        const panel = snippetModal.querySelector('.modal-panel');
        if (panel) panel.classList.add('closing');
        snippetModal.classList.add('closing');
        setTimeout(() => {
            snippetModal.hidden = true;
            snippetModal.inert = true;
            snippetModal.classList.remove('closing');
            if (panel) panel.classList.remove('closing');
            document.body.style.overflow = '';
        }, 200);
    }

    function openModal(item) {
        if (!item || item._type !== 'saved') return;

        modalTitle.textContent = item.title || 'Untitled';

        // Metadata
        const ts = item.saved_at || '';
        modalTime.textContent = formatTimeLong(ts);
        modalSource.textContent = item.url || '';
        modalSource.title = item.url || '';
        const rel = formatRelative(ts);
        modalRelative.textContent = rel ? `Saved ${rel}` : '';
        modalOpenUrl.href = item.url || '#';

        // Build structured word list: [{text, type}] where type='before'|'sep'|'main'|'after'
        const contentText = item.content || '';
        const ctxBeforeRaw = ((item.context && item.context.before) || '').trim();
        const ctxAfterRaw = ((item.context && item.context.after) || '').trim();

        const wordParts = [];

        // Before context words
        if (ctxBeforeRaw) {
            const beforeWords = ctxBeforeRaw.split(/\s+/);
            beforeWords.forEach((w, i) => {
                const total = beforeWords.length;
                const progress = (i + 1) / total;
                const opacity = Math.max(0.05, progress * 0.9 + 0.05);
                wordParts.push({ text: w, type: 'before', opacity });
            });
            wordParts.push({ text: '\n', type: 'sep' });
        }

        // Main selected text words
        if (contentText) {
            const mainWords = contentText.split(/\s+/);
            mainWords.forEach((w) => {
                wordParts.push({ text: w, type: 'main' });
            });
        }

        // After context words
        if (ctxAfterRaw) {
            wordParts.push({ text: '\n', type: 'sep' });
            const afterWords = ctxAfterRaw.split(/\s+/);
            afterWords.forEach((w, i) => {
                const total = afterWords.length;
                const progress = (i + 1) / total;
                const opacity = Math.max(0.05, (1 - progress) * 0.9 + 0.05);
                wordParts.push({ text: w, type: 'after', opacity });
            });
        }

        // Render all words as hidden spans, reveal one at a time via timer
        // Group main text into a single continuous span for the highlight sweep
        let fullHtml = '';
        let mainTextBuffer = [];
        let inMain = false;

        function flushMain() {
            if (mainTextBuffer.length > 0) {
                fullHtml += `<span class="sel-text" style="opacity:0">${mainTextBuffer.join(' ')} </span>`;
                mainTextBuffer = [];
            }
            inMain = false;
        }

        wordParts.forEach((part) => {
            if (part.type === 'sep') {
                flushMain();
                fullHtml += '<br>';
                return;
            }
            if (part.type === 'main') {
                mainTextBuffer.push(escapeHtml(part.text));
                inMain = true;
                return;
            }
            // before/after words
            if (inMain) flushMain();
            fullHtml += `<span class="ctx-word" style="opacity:0" data-opacity="${part.opacity.toFixed(2)}">${escapeHtml(part.text)} </span>`;
        });
        flushMain(); // flush any remaining main words

        modalContentText.innerHTML = fullHtml;
        // Remove CSS mask initially — we add it after all words are revealed
        modalContentText.parentElement.classList.remove('content-revealed');
        snippetModal.hidden = false;
        snippetModal.inert = false;
        document.body.style.overflow = 'hidden';

        // Word-by-word reveal
        const allSpans = modalContentText.querySelectorAll('span');
        const totalSpans = allSpans.length;
        const delayMs = getWordRevealDelayMs(totalSpans);

        // Set highlight animation delay — starts AFTER all words are revealed
        const totalRevealMs = totalSpans * delayMs;
        const selTexts = modalContentText.querySelectorAll('.sel-text');
        selTexts.forEach(el => {
            el.style.animationDelay = `${totalRevealMs}ms`;
        });

        if (delayMs === 0 || totalSpans === 0) {
            // Instant: show all
            allSpans.forEach((sp) => {
                const opacity = sp.dataset.opacity || '1';
                sp.style.opacity = opacity;
            });
            modalContentText.parentElement.classList.add('content-revealed');
            return;
        }

        if (revealTimer) clearInterval(revealTimer);
        let wordIdx = 0;
        revealTimer = setInterval(() => {
            if (wordIdx < totalSpans) {
                const sp = allSpans[wordIdx];
                const opacity = sp.dataset.opacity || '1';
                sp.style.opacity = opacity;
                wordIdx++;
            } else {
                clearInterval(revealTimer);
                revealTimer = null;
                // All words revealed — apply edge fade
                modalContentText.parentElement.classList.add('content-revealed');
            }
        }, delayMs);
    }

    modalClose.addEventListener('click', closeModal);
    snippetModal.addEventListener('click', (e) => {
        if (e.target === snippetModal) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !snippetModal.hidden) closeModal();
    });

    // ─── Card animation ──────────────────────────────────────────
    function animateCardsFrom(startIndex) {
        const cards = resultsContainer.querySelectorAll('.result-card');
        for (let i = startIndex; i < cards.length; i++) {
            const delay = 20 + (i * 35);
            setTimeout(() => {
                cards[i].classList.add('visible');
            }, delay);
        }
    }

    // ─── Formatters ───────────────────────────────────────────────
    function parseDate(isoStr) {
        if (!isoStr) return null;
        // Fix double timezone: "2026-06-28T18:29:16.909029+00:00Z" -> "2026-06-28T18:29:16.909029Z"
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
        if (days < 7) return `${days} days ago`;
        return d.toLocaleDateString();
    }

    function formatRelative(isoStr) {
        const d = parseDate(isoStr);
        if (!d) return '';
        const now = Date.now();
        const diffMs = now - d;
        const seconds = Math.floor(diffMs / 1000);
        if (seconds < 60) return 'just now';
        const minutes = Math.floor(seconds / 60);
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
        return d.toLocaleString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    }

    function highlightText(text, query) {
        if (!query || !text) return text;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const words = escaped.split(/\s+/).filter(Boolean);
        if (!words.length) return text;
        const pattern = new RegExp(`(${words.join('|')})`, 'gi');
        return text.replace(pattern, '<mark>$1</mark>');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ─── Card creation ────────────────────────────────────────────
    function createCard(item) {
        const isSaved = item._type === 'saved';
        const ts = formatTime(item.saved_at);
        const title = item.title || item.url || 'Untitled';
        const content = item.content || '';
        const highlightedTitle = highlightText(title, currentQuery);
        const highlightedContent = highlightText(content, currentQuery);

        let domain = '';
        if (item.url) {
            try {
                const u = new URL(item.url);
                domain = u.hostname.replace('www.', '');
            } catch {}
        }

        const siteName = (item.site_name || '').trim();
        const displayDomain = domain || siteName || 'web';

        let faviconHtml;
        if (domain) {
            const faviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
            faviconHtml = `<img class="card-favicon" src="${faviconUrl}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
        } else {
            faviconHtml = `<span class="card-favicon-fallback">${displayDomain.charAt(0).toUpperCase()}</span>`;
        }

        const badgeHtml = isSaved
            ? `<span class="card-type-badge saved">Saved</span>`
            : `<span class="card-type-badge web">Web</span>`;

        let enginesHtml = '';
        if (!isSaved && getShowEngines() && item.engines && item.engines.length > 0) {
            enginesHtml = `<span class="card-engines">${item.engines.map(e => `<span class="card-engine-badge">${escapeHtml(e)}</span>`).join('')}</span>`;
        }

        const timeHtml = isSaved && ts ? `<span class="card-time">${ts}</span>` : '';

        const globalIndex = allResults.indexOf(item);
        const cardAttrs = isSaved
            ? `data-type="saved" data-index="${globalIndex}"`
            : `data-type="web" data-index="${globalIndex}"`;

        return `
    <article class="result-card ${isSaved ? 'card-saved' : 'card-web'}" ${cardAttrs}>
      <div class="card-meta">
        ${faviconHtml}
        <span class="card-domain">${displayDomain}</span>
        ${badgeHtml}
        ${enginesHtml}
        ${timeHtml}
      </div>
      <span class="card-title" data-url="${item.url || '#'}">${highlightedTitle}</span>
      ${content ? `<p class="card-content">${highlightedContent}</p>` : ''}
    </article>`;
    }

    // ─── Attach click handlers to saved cards ────────────────────
    function attachCardHandlers() {
        resultsContainer.querySelectorAll('.result-card[data-type="saved"]').forEach((card) => {
            if (card._modalBound) return;
            card._modalBound = true;
            card.addEventListener('click', (e) => {
                const titleEl = e.target.closest('.card-title');
                if (titleEl) {
                    const url = titleEl.dataset.url;
                    if (url && url !== '#') window.open(url, '_blank', 'noopener');
                    return;
                }
                e.preventDefault();
                const index = parseInt(card.dataset.index, 10);
                if (!isNaN(index) && allResults[index]) {
                    openModal(allResults[index]);
                }
            });
        });
    }

    // ─── Rendering (append-aware) ─────────────────────────────────
    function renderResults(append) {
        let items = allResults;
        if (currentMode === 'web') items = allResults.filter(r => r._type === 'web');
        else if (currentMode === 'saved') items = allResults.filter(r => r._type === 'saved');

        if (append && resultsContainer.children.length > 0) {
            // ── APPEND MODE (infinite scroll) ──
            // Determine which items aren't yet rendered
            const renderedCount = resultsContainer.children.length;
            // Build a set of already-rendered data-index values
            const existingIndices = new Set();
            resultsContainer.querySelectorAll('.result-card').forEach(card => {
                const idx = parseInt(card.dataset.index, 10);
                if (!isNaN(idx)) existingIndices.add(idx);
            });

            let addedHtml = '';
            let addedCount = 0;
            items.forEach((item) => {
                const idx = allResults.indexOf(item);
                if (existingIndices.has(idx)) return;
                addedHtml += createCard(item);
                renderedUrls.add(item.url);
                addedCount++;
            });

            if (addedCount === 0) return; // nothing new

            resultsContainer.insertAdjacentHTML('beforeend', addedHtml);
            attachCardHandlers();

            // Animate only the newly added cards
            const totalBefore = renderedCount;
            animateCardsFrom(totalBefore);
        } else {
            // ── FULL REPLACE (new search, filter change, browse) ──
            renderedUrls = new Set();
            allResults.forEach(item => { if (item.url) renderedUrls.add(item.url); });

            resultsContainer.innerHTML = items.map(createCard).join('');
            attachCardHandlers();

            // Animate all cards
            if (items.length > 0) {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        animateCardsFrom(0);
                    });
                });
            }
        }

        // ── Status bar ──
        statusBar.hidden = false;
        const total = allResults._total || allResults.length;
        const shown = resultsContainer.children.length;
        if (browseMode) {
            resultCount.textContent = `${total} saved item${total !== 1 ? 's' : ''}`;
        } else if (currentQuery) {
            const savedCount = allResults.filter(r => r._type === 'saved').length;
            if (currentMode === 'all') {
                resultCount.textContent = `${total} result${total !== 1 ? 's' : ''} (${savedCount} saved)`;
            } else if (currentMode === 'saved') {
                resultCount.textContent = `${shown} saved result${shown !== 1 ? 's' : ''}`;
            } else {
                resultCount.textContent = `${shown} web result${shown !== 1 ? 's' : ''}`;
            }
        } else {
            statusBar.hidden = true;
        }

        // ── Empty state ──
        if (total === 0 && currentQuery) {
            emptyState.hidden = false;
            emptyState.innerHTML = `
                <div class="empty-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                </div>
                <h3>No results for "${currentQuery}"</h3>
                <p>Try different keywords. Saved content is searched alongside web results.</p>
            `;
        } else {
            emptyState.hidden = true;
        }

        // ── Sentinel ──
        sentinel.hidden = !(hasMore && !browseMode);
    }

    // ─── Fetching ────────────────────────────────────────────────
    async function doSearch(query, page) {
        if (loading) return;
        loading = true;
        showLoading(true);

        const pageSize = getPageSize();
        const url = `/search?q=${encodeURIComponent(query)}&page=${page}&count=${pageSize}&mode=all&engines=${getEngines()}`;

        try {
            const resp = await fetch(url);
            const data = await resp.json();

            if (!data || !Array.isArray(data.results)) {
                showLoading(false);
                loading = false;
                return;
            }

            const fetched = data.results;
            const total = data.total || 0;

            if (page === 1) {
                allResults = fetched;
                allResults._total = total;
                showLoading(false);
                renderResults(false);
            } else {
                const existingUrls = new Set(allResults.map(r => r.url));
                const newWeb = fetched.filter(r => r._type === 'web' && !existingUrls.has(r.url));
                allResults = allResults.concat(newWeb);
                showLoading(false);
                renderResults(true);
            }

            hasMore = fetched.length >= pageSize;
            currentPage = page;
        } catch (err) {
            console.error('Search failed:', err);
            showLoading(false);
            resultsContainer.innerHTML = `<div class="message error">Search request failed. Is the server running?</div>`;
        }

        loading = false;
    }

    async function loadBrowse() {
        loading = true;
        browseMode = true;
        currentQuery = '';
        setSearchActive(false);

        try {
            const resp = await fetch('/search?q=&mode=all');
            const data = await resp.json();

            if (!Array.isArray(data)) {
                allResults = [];
            } else {
                allResults = data.filter(r => r._type === 'saved');
            }

            hasMore = false;
            currentPage = 1;
            renderResults(false);

            if (allResults.length === 0) {
                emptyState.hidden = false;
                emptyState.innerHTML = `
                    <div class="empty-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
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
        emptyState.hidden = true;

        setSearchActive(true);

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
        setSearchActive(false);
        loadBrowse();
    });

    // ─── Infinite scroll ──────────────────────────────────────────
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);

    // ─── Init ──────────────────────────────────────────────────────
    loadBrowse();
    
    // ─── Extension detection banner ──────────────────────────────
    const extBanner = document.getElementById('extension-banner');
    const bannerClose = document.getElementById('banner-close');
    const bannerInstallLink = document.getElementById('banner-install-link');
    const installModal = document.getElementById('install-modal');
    const installClose = document.getElementById('install-close');

    function checkExtensionInstalled() {
        if (localStorage.getItem('bannerDismissed') === 'true') return;
        const sentinel = document.querySelector('meta[name="recollect-extension"]');
        if (!sentinel || sentinel.content !== 'installed') {
            extBanner.hidden = false;
        }
    }

    bannerClose.addEventListener('click', () => {
        extBanner.hidden = true;
        localStorage.setItem('bannerDismissed', 'true');
    });

    bannerInstallLink.addEventListener('click', () => {
        extBanner.hidden = true;
        installModal.hidden = false;
        installModal.inert = false;
    });

    installClose.addEventListener('click', () => {
        installModal.hidden = true;
        installModal.inert = true;
    });

    installModal.addEventListener('click', (e) => {
        if (e.target === installModal) {
            installModal.hidden = true;
            installModal.inert = true;
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !installModal.hidden) {
            installModal.hidden = true;
            installModal.inert = true;
        }
    });

    // Copy-to-clipboard for code blocks
    document.querySelectorAll('.step-copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const text = btn.dataset.copy;
            if (text) {
                navigator.clipboard.writeText(text).then(() => {
                    const orig = btn.textContent;
                    btn.textContent = '✓';
                    setTimeout(() => { btn.textContent = orig; }, 1500);
                }).catch(() => {});
            }
        });
    });

    // Check after a small delay to let extension inject sentinel
    setTimeout(checkExtensionInstalled, 300);
});