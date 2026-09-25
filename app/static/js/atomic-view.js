// ─── Atomic View — standalone module from app.js ────────────────
// State variables are declared in app.js (allResults, currentQuery, etc.)
// This module only assigns to them, does NOT redeclare with let.

// ─── Init: bind DOM refs and observer ──────────────────────────
function initAtomicView() {
    pageShell = document.getElementById('page-shell');
    form = document.getElementById('search-form');
    queryInput = document.getElementById('query');
    resultsContainer = document.getElementById('results-container');
    sentinel = document.getElementById('results-sentinel');
    loadMoreButton = document.getElementById('load-more-button');
    bottomLoading = document.getElementById('bottom-loading');
    endOfResults = document.getElementById('end-of-results');
    emptyState = document.getElementById('empty-state');
    statusBar = document.getElementById('status-bar');
    loadingIndicator = document.getElementById('loading-indicator');

    observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad !== false) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });

    if (observer && sentinel) {
        observer.observe(sentinel);
    }

    loadMoreButton?.addEventListener('click', () => {
        if (!loading && hasMore && currentQuery) doSearch(currentQuery, currentPage + 1);
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;
        currentQuery = query;
        currentPage = 1;
        hasMore = true;
        loading = false;
        allResults = [];
        emptyState.hidden = true;
        await routeQuery(query);
        queryInput.blur();
    });
}

// ─── Helpers ──────────────────────────────────────────────────
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
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
        bottomLoading.hidden = false;
        endOfResults.hidden = true;
    } else {
        loadingIndicator.hidden = true;
        clearSkeletons();
    }
}

function parseDate(isoStr) {
    if (!isoStr) return null;
    const cleaned = isoStr.replace('+00:00Z', 'Z').replace('+00:00', 'Z').replace('+0000', '');
    const d = new Date(cleaned);
    return isNaN(d.getTime()) ? null : d;
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

// ─── Card/Results ─────────────────────────────────────────────
function createCard(item) {
    const type = item.type || 'text';
    const content = item.content || '';
    const sourceUrl = item.source_url || '';
    const sourceTitle = item.source_site_name || item.source_title || '';
    const typeColors = { heading: '#1f6feb', text: '#64748b', code_block: '#238636', quote: '#8250df', link: '#9e6a03', image: '#da3633', entity: '#d29922', aggregate: '#22c55e' };
    const color = typeColors[type] || '#64748b';

    if (type === 'aggregate') {
        return `
          <article class="result-card card-aggregate" data-type="aggregate" data-id="${escapeHtml(item.id)}">
            <div class="card-meta">
              <span class="card-chip" style="background:${color};color:#fff;padding:0.15rem 0.4rem;border-radius:0.3rem;font-size:0.7rem;font-weight:600;text-transform:uppercase">📋 ${escapeHtml(content)}</span>
              <span class="card-domain">aggregate</span>
            </div>
            <div class="card-body">
              <div class="card-aggregate-children" id="agg-${escapeHtml(item.id)}">
                <span class="card-loading">${skeletonLoader(2)}</span>
              </div>
            </div>
          </article>`;
    }

    const shortContent = content.length > 200 ? content.slice(0, 200) + '…' : content;
    const sourceBadge = sourceUrl
        ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener" class="card-source-badge" title="${escapeHtml(sourceTitle || sourceUrl)}">${escapeHtml(sourceTitle || sourceUrl.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</a>`
        : '';

    return `
      <article class="result-card" data-type="atomic" data-index="${allResults.findIndex(r => r === item)}">
        <div class="card-meta">
          <span class="card-chip" style="background:${color};color:#fff;padding:0.15rem 0.4rem;border-radius:0.3rem;font-size:0.7rem;font-weight:600;text-transform:uppercase">${escapeHtml(type)}</span>
          ${sourceBadge}
        </div>
        <div class="card-body">
          <div class="card-title-row">
            <span class="card-title">${escapeHtml(shortContent)}</span>
          </div>
        </div>
      </article>`;
}

function renderResults(append = false) {
    if (!append) {
        resultsContainer.innerHTML = allResults.map(createCard).join('');
    } else {
        resultsContainer.insertAdjacentHTML('beforeend', allResults.slice(-10).map(createCard).join(''));
    }

    // Load aggregate children
    document.querySelectorAll('.card-aggregate').forEach(card => {
        const aggId = card.dataset.id;
        if (card.dataset.loaded === 'true') return;
        card.dataset.loaded = 'true';
        loadAggregateChildren(aggId);
    });

    if (allResults.length === 0 && currentQuery) {
        emptyState.hidden = false;
        emptyState.innerHTML = `
            <div class="empty-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
            </div>
            <h3>No knowledge atoms found</h3>
            <p>No results for "${escapeHtml(currentQuery)}". Try different keywords.</p>`;
    } else {
        emptyState.hidden = true;
    }
    updatePaginationControls();
}

async function doSearch(query, page) {
    if (loading) return;
    loading = true;
    showLoading(true, page);
    try {
        const resp = await fetch(`/api/atomics?q=${encodeURIComponent(query)}&limit=50`);
        const data = await resp.json();
        const fetched = data.atomics || [];
        if (page === 1) {
            allResults = fetched;
            showLoading(false, page);
            renderResults(false);
        } else {
            allResults = allResults.concat(fetched);
            showLoading(false, page);
            renderResults(true);
        }
        hasMore = fetched.length >= 50;
        currentPage = page;
        if (!hasMore && allResults.length > 0) endOfResults.hidden = false;
    } catch (err) {
        console.error('Search failed:', err);
        showLoading(false, page);
        resultsContainer.innerHTML = '<div class="message error">Search request failed.</div>';
        hasMore = false;
    } finally {
        loading = false;
        updatePaginationControls();
    }
}

async function loadAggregateChildren(aggId) {
    try {
        const resp = await fetch(`/api/atomics/${aggId}/children`);
        const data = await resp.json();
        const children = data.children || [];
        const container = document.getElementById(`agg-${escapeHtml(aggId)}`);
        if (!container) return;
        if (children.length === 0) {
            container.innerHTML = '<span class="card-empty">No children yet</span>';
            return;
        }
        container.innerHTML = children.map(child => {
            const typeColors = { heading: '#1f6feb', text: '#64748b', code_block: '#238636', quote: '#8250df', link: '#9e6a03', image: '#da3633', entity: '#d29922' };
            const color = typeColors[child.type] || '#64748b';
            const src = child.source_url
                ? `<a href="${escapeHtml(child.source_url)}" target="_blank" rel="noopener" class="card-source-badge" title="${escapeHtml(child.source_title || child.source_url)}">${escapeHtml(child.source_site_name || child.source_url.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</a>`
                : '';
            return `<div class="card-aggregate-child">
                <span class="card-chip" style="background:${color};color:#fff;padding:0.1rem 0.3rem;border-radius:0.3rem;font-size:0.65rem;text-transform:uppercase">${escapeHtml(child.type || 'text')}</span>
                ${src}
                <div class="card-aggregate-content">${escapeHtml((child.content || '').slice(0, 200))}</div>
            </div>`;
        }).join('');
    } catch (err) {
        console.error('Load children failed:', err);
    }
}

function updatePaginationControls() {
    const autoLoad = settingsState.autoLoad !== false;
    const showLoadMore = !autoLoad && hasMore && !!currentQuery;
    const showSentinel = autoLoad && hasMore && !!currentQuery;
    const showEndMessage = !hasMore && !!currentQuery && allResults.length > 0;
    sentinel.hidden = !showSentinel;
    loadMoreButton.hidden = !showLoadMore;
    endOfResults.hidden = !showEndMessage;
    if (!sentinel.hidden) ensureSentinelObserved();
}

function ensureSentinelObserved() {
    if (sentinel && !sentinel.hidden) {
        observer.unobserve(sentinel);
        observer.observe(sentinel);
    }
}

// ─── Library/Dashboard ─────────────────────────────────────────
async function loadLibrary() {
    loading = true;
    webMode = false;
    currentQuery = '';
    try {
        const resp = await fetch('/api/library');
        const data = await resp.json();
        resultsContainer.innerHTML = renderDashboard(data);
        attachDashboardHandlers();
    } catch (err) {
        console.error('Library load failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load saved content.</div>';
    }
    loading = false;
}

function renderDashboard(data) {
    const stats = data.stats || {};
    const atomics = data.atomics || [];

    const statHtml = `<div class="dashboard-stats">
        <span class="stat-item"><strong>${atomics.length || 0}</strong> knowledge atoms</span>
        <span class="stat-sep">·</span>
        <span class="stat-item"><strong>${stats.captures || 0}</strong> sources</span>
    </div>`;

    let atomsHtml = '';
    if (atomics.length > 0) {
        atomsHtml = `<div class="dashboard-section">
            <div class="dashboard-section-title">📋 Recent atoms</div>
            <div class="dashboard-atoms-list">${atomics.map(a => {
                const content = (a.content || '').slice(0, 100);
                const type = a.type || 'text';
                return `<div class="dashboard-atom-item">
                    <span class="dashboard-atom-type">${escapeHtml(type)}</span>
                    <span class="dashboard-atom-content">${escapeHtml(content)}</span>
                </div>`;
            }).join('')}</div>
        </div>`;
    }

    return `<div class="dashboard-wrap">${statHtml}${atomsHtml}</div>`;
}

function attachDashboardHandlers() {
    // No interactive elements in simplified dashboard yet
}

// ─── Sources renderer ──────────────────────────────────────────
async function sourcesSearch(searchTerm) {
    if (!searchTerm) {
        resultsContainer.innerHTML = '<div class="message">Showing all saved sources</div>';
        await doSearch('', 1);
        return;
    }
    await doSearch(searchTerm, 1);
    const header = document.querySelector('.result-card')?.parentElement?.previousElementSibling;
    if (resultsContainer.children.length > 0 && !resultsContainer.querySelector('.sources-badge')) {
        const badge = document.createElement('div');
        badge.className = 'sources-badge';
        badge.textContent = `📄 Sources for "${searchTerm}"`;
        resultsContainer.insertBefore(badge, resultsContainer.firstChild);
    }
}

// ─── Facts renderer ──────────────────────────────────────────
async function factsSearch(searchTerm) {
    if (!searchTerm) {
        resultsContainer.innerHTML = '<div class="message">Showing all extracted facts</div>';
        await doSearch('', 1);
        return;
    }
    loading = true;
    resultsContainer.innerHTML = '<div class="message">Looking up facts...</div>';
    try {
        const resp = await fetch(`/api/facts?q=${encodeURIComponent(searchTerm)}&limit=50`);
        const data = await resp.json();
        loading = false;
        const facts = data.facts || [];
        if (facts.length === 0) {
            emptyState.hidden = false;
            emptyState.innerHTML = `<div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div><h3>No facts found</h3><p>No extracted facts about "${escapeHtml(searchTerm)}". Try running AI fact extraction on relevant captures first.</p>`;
            resultsContainer.innerHTML = '';
            return;
        }
        hasMore = false;
        endOfResults.hidden = true;
        resultsContainer.innerHTML = `<div class="sources-badge">💡 ${facts.length} fact${facts.length !== 1 ? 's' : ''} about "${escapeHtml(searchTerm)}"</div>
            <div class="facts-list">${facts.map(f => renderFactCard(f)).join('')}</div>`;
    } catch (err) {
        loading = false;
        console.error('Facts search failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load facts.</div>';
    }
}

function renderFactCard(f) {
    const srcTitle = f.source_title || 'Untitled';
    return `<div class="fact-card">
        <span class="fact-bullet">•</span>
        <span class="fact-text">${escapeHtml(f.content)}</span>
        ${f.source_url ? `<a href="${escapeHtml(f.source_url)}" class="fact-source-badge" target="_blank" rel="noopener" title="${escapeHtml(srcTitle)}">source</a>` : ''}
    </div>`;
}

// ─── Entity search ─────────────────────────────────────────────
async function entitySearch(searchTerm) {
    loading = true;
    showLoading(true, 1);
    resultsContainer.innerHTML = '';
    try {
        const url = searchTerm
            ? `/api/entities?search=${encodeURIComponent(searchTerm)}&sort=name&limit=50`
            : '/api/entities?sort=capture_count&limit=50';
        const resp = await fetch(url);
        const data = await resp.json();
        showLoading(false, 1);
        loading = false;
        const entities = data.entities || [];
        const total = data.total || 0;
        if (entities.length === 0) {
            emptyState.hidden = false;
            emptyState.innerHTML = `
                <div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div>
                <h3>No entities found</h3>
                <p>${searchTerm ? `No entities matching "${escapeHtml(searchTerm)}".` : 'No entities in your knowledge base yet.'}</p>`;
            resultsContainer.innerHTML = '';
            return;
        }
        hasMore = false;
        endOfResults.hidden = true;
        resultsContainer.innerHTML = `<div class="entity-list-header">${total} entit${total === 1 ? 'y' : 'ies'}</div>
            <div class="entity-list">${entities.map(renderEntityCard).join('')}</div>`;
        document.querySelectorAll('.entity-card').forEach(el => {
            el.addEventListener('click', () => openEntityDetail(el.dataset.id));
        });
    } catch (err) {
        showLoading(false, 1);
        loading = false;
        console.error('Entity search failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load entities.</div>';
    }
}

function renderEntityCard(e) {
    const typeColors = { tool: '#1f6feb', person: '#8250df', concept: '#0d4429', framework: '#9e6a03', language: '#da3633', platform: '#238636', company: '#d29922' };
    const color = typeColors[e.type] || '#64748b';
    return `<div class="entity-card" data-id="${escapeHtml(e.id)}">
        <span class="entity-type-badge" style="background:${color}">${e.type}</span>
        <span class="entity-name">${escapeHtml(e.name)}</span>
        <span class="entity-count">${e.capture_count} reference${e.capture_count !== 1 ? 's' : ''}</span>
        ${e.description ? `<span class="entity-desc">${escapeHtml(e.description.slice(0, 80))}${e.description.length > 80 ? '…' : ''}</span>` : ''}
    </div>`;
}

async function openEntityDetail(entityId) {
    loading = true;
    resultsContainer.innerHTML = '<div class="message">Loading entity...</div>';
    try {
        const resp = await fetch(`/api/entity/${entityId}`);
        const data = await resp.json();
        loading = false;
        if (!data || !data.entity) {
            resultsContainer.innerHTML = '<div class="message error">Entity not found.</div>';
            return;
        }
        const e = data.entity;
        const captures = data.captures || [];
        const relatedAtomics = data.related_atomics || [];
        const typeColors = { tool: '#1f6feb', person: '#8250df', concept: '#0d4429', framework: '#9e6a03', language: '#da3633', platform: '#238636', company: '#d29922' };
        const color = typeColors[e.type] || '#64748b';

        let html = `<div class="entity-detail">
            <button class="entity-back-btn">← Back to entities</button>
            <div class="entity-detail-header">
                <span class="entity-type-badge" style="background:${color}">${e.type}</span>
                <h2>${escapeHtml(e.name)}</h2>
                <span class="entity-count">${e.capture_count} source${e.capture_count !== 1 ? 's' : ''}</span>
            </div>`;
        if (e.description) {
            html += `<p class="entity-detail-desc">${escapeHtml(e.description)}</p>`;
        }
        if (e.aliases && e.aliases.length > 0) {
            html += `<div class="entity-aliases">Aliases: ${e.aliases.map(a => `<span class="entity-alias">${escapeHtml(a)}</span>`).join(' ')}</div>`;
        }
        if (relatedAtomics.length > 0) {
            html += `<div class="entity-section">
                <div class="entity-section-title">Related knowledge (${relatedAtomics.length})</div>
                <div class="entity-related-list">${relatedAtomics.map(a => {
                    const src = a.source_url
                        ? `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" class="entity-source-badge" title="${escapeHtml(a.source_title || a.source_url)}">${escapeHtml(a.source_site_name || a.source_url.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</a>`
                        : '';
                    return `<div class="entity-related-item">
                        <span class="entity-type-badge" style="background:${typeColors[a.type] || '#64748b'};font-size:0.65rem">${escapeHtml(a.type)}</span>
                        <span class="entity-related-content">${escapeHtml((a.content || '').slice(0, 120))}</span>
                        ${src}
                    </div>`;
                }).join('')}</div>
            </div>`;
        }
        if (captures.length > 0) {
            html += `<div class="entity-section">
                <div class="entity-section-title">Sources (${captures.length})</div>
                ${captures.map(c => `<div class="entity-capture" data-id="${c.id}">
                    <span class="entity-capture-title">${escapeHtml(c.source_title || 'Untitled')}</span>
                    ${c.source_site_name ? `<span class="entity-capture-site">${escapeHtml(c.source_site_name)}</span>` : ''}
                </div>`).join('')}
            </div>`;
        }
        html += '</div>';
        resultsContainer.innerHTML = html;
        document.querySelectorAll('.entity-capture').forEach(el => {
            el.addEventListener('click', () => {
                const url = el.dataset.id;
                if (url) window.open(url, '_blank');
            });
        });
        document.querySelector('.entity-back-btn')?.addEventListener('click', () => entitySearch(''));
    } catch (err) {
        loading = false;
        console.error('Entity detail failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load entity details.</div>';
    }
}

// ─── Route query ──────────────────────────────────────────
function routeQuery(query) {
    const hasArgs = query.includes(' ');
    if (query.startsWith('/entities')) return hasArgs ? entitySearch(query.slice('/entities '.length).trim()) : entitySearch('');
    if (query.startsWith('/sources')) return hasArgs ? sourcesSearch(query.slice('/sources '.length).trim()) : loadAll('sources');
    if (query.startsWith('/facts')) return hasArgs ? factsSearch(query.slice('/facts '.length).trim()) : loadAll('facts');
    if (query.startsWith('/cards')) return hasArgs ? doSearch(query.slice('/cards '.length).trim(), 1) : loadAll('cards');
    if (query.startsWith('/table')) return hasArgs ? doSearch(query.slice('/table '.length).trim(), 1) : loadAll('table');
    if (query.startsWith('/timeline')) return hasArgs ? doSearch(query.slice('/timeline '.length).trim(), 1) : loadAll('timeline');
    if (query.startsWith('/compare')) return hasArgs ? comparisonSearch(query.slice('/compare '.length).trim()) : (resultsContainer.innerHTML='<div class="message">Usage: /compare X and Y</div>', hasMore=false, endOfResults.hidden=true);
    if (query.startsWith('/markdown')) return hasArgs ? doSearch(query.slice('/markdown '.length).trim(), 1) : loadAll('markdown');
    return detectIntent(query);
}

async function loadAll(mode) {
    loading = true;
    resultsContainer.innerHTML = '<div class="message">Loading...</div>';
    try {
        const resp = await fetch('/browse');
        const data = await resp.json();
        allResults = Array.isArray(data) ? data : [];
        hasMore = false;
        currentPage = 1;
        currentQuery = '';
        renderResults(false);
        const badge = document.createElement('div');
        badge.className = 'sources-badge';
        const labels = { sources: '📄 All sources', facts: '💡 All captures', cards: '📇 All captures', table: '🗂️ All captures', timeline: '📅 All captures', markdown: '📝 All captures' };
        badge.textContent = labels[mode] || '📄 All items';
        if (resultsContainer.firstChild) {
            resultsContainer.insertBefore(badge, resultsContainer.firstChild);
        }
    } catch (err) {
        loading = false;
        console.error('Load all failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load captures.</div>';
    }
    loading = false;
}

async function detectIntent(query) {
    const lower = query.toLowerCase().trim();

    // Detect "compare X and Y" or "/compare X and Y"
    if (lower.includes('compare') && lower.includes(' and ')) {
        return comparisonSearch(query);
    }

    // Detect entity mention — try exact match
    const entityResult = await tryEntityMatch(query);
    if (entityResult) {
        return entitySearch(entityResult.name);
    }

    // Default: cards view
    return doSearch(query, 1);
}

async function tryEntityMatch(query) {
    try {
        const resp = await fetch(`/api/entities?search=${encodeURIComponent(query)}&sort=name&limit=5`);
        const data = await resp.json();
        const entities = data.entities || [];
        // Prefer exact name match
        const exact = entities.find(e => e.name.toLowerCase() === query.toLowerCase());
        if (exact) return exact;
        // If only one result and query is short, use it
        if (entities.length === 1 && query.length >= 3) return entities[0];
        return null;
    } catch {
        return null;
    }
}

// ─── Comparison renderer ──────────────────────────────────────
async function comparisonSearch(query) {
    // Parse "compare X and Y" or "X vs Y" or "X versus Y"
    const lower = query.toLowerCase();
    let name1 = '', name2 = '';
    const andMatch = lower.match(/compare\s+(.+?)\s+and\s+(.+)/i);
    const vsMatch = lower.match(/(.+?)\s+vs\s+(.+)/i);
    const versusMatch = lower.match(/(.+?)\s+versus\s+(.+)/i);
    if (andMatch) { name1 = andMatch[1].trim(); name2 = andMatch[2].trim(); }
    else if (vsMatch) { name1 = vsMatch[1].trim(); name2 = vsMatch[2].trim(); }
    else if (versusMatch) { name1 = versusMatch[1].trim(); name2 = versusMatch[2].trim(); }

    if (!name1 || !name2) {
        return doSearch(query, 1);
    }

    // Fetch both entities
    const [r1, r2] = await Promise.all([
        fetch(`/api/entities?search=${encodeURIComponent(name1)}&sort=name&limit=1`).then(r => r.json()),
        fetch(`/api/entities?search=${encodeURIComponent(name2)}&sort=name&limit=1`).then(r => r.json()),
    ]);
    const e1 = (r1.entities || [])[0];
    const e2 = (r2.entities || [])[0];

    if (!e1 && !e2) return doSearch(query, 1);

    resultsContainer.innerHTML = comparisonHtml(e1, e2, name1, name2);
    document.querySelectorAll('.comp-explore-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            queryInput.value = btn.dataset.cmd;
            form.dispatchEvent(new Event('submit'));
        });
    });
    hasMore = false;
    endOfResults.hidden = true;
}

function comparisonHtml(e1, e2, name1, name2) {
    const renderOne = (e, name) => {
        if (!e) return `<div class="comp-col comp-empty"><div class="comp-name">${escapeHtml(name)}</div><p style="color:var(--text-dim);font-size:0.82rem">No saved knowledge</p><button class="modal-btn comp-explore-btn" style="font-size:0.78rem;padding:0.25rem 0.5rem;margin-top:0.3rem" data-cmd="${escapeHtml(name)}">Search web for ${escapeHtml(name)}</button></div>`;
        return `<div class="comp-col">
            <div class="comp-name"><span class="entity-type-badge" style="background:${typeColor(e.type)}">${e.type}</span> ${escapeHtml(e.name)}</div>
            ${e.description ? `<p class="comp-desc">${escapeHtml(e.description)}</p>` : ''}
            <div class="comp-stat">${e.capture_count} sources</div>
            <div class="comp-actions"><button class="modal-btn comp-explore-btn" style="font-size:0.78rem;padding:0.25rem 0.5rem;margin-top:0.3rem" data-cmd="/entities ${escapeHtml(e.name)}">Explore →</button></div>
        </div>`;
    };
    return `<div class="comp-wrap"><div class="comp-header">Comparison</div><div class="comp-row">${renderOne(e1, name1)}${renderOne(e2, name2)}</div></div>`;
}

function typeColor(type) {
    const map = { tool: '#1f6feb', person: '#8250df', concept: '#0d4429', framework: '#9e6a03', language: '#da3633', platform: '#238636', company: '#d29922' };
    return map[type] || '#64748b';
}
