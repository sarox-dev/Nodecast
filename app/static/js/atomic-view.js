// ─── Atomic View — standalone module from app.js ────────────────
// State variables are declared in app.js (allResults, currentQuery, etc.)
// This module only assigns to them, does NOT redeclare with let.
let memorySearchGeneration = 0;
let memorySearchController = null;

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

    resultsContainer?.addEventListener('pointerover', showEvidencePopover);
    resultsContainer?.addEventListener('pointerout', hideEvidencePopover);
    resultsContainer?.addEventListener('focusin', showEvidencePopover);
    resultsContainer?.addEventListener('focusout', hideEvidencePopover);
    resultsContainer?.addEventListener('click', event => {
        if (event.target.closest('[data-refresh-recall]')) { doSearch(currentQuery, 1, true); return; }
        const reasonButton = event.target.closest('[data-edit-reason]');
        if (reasonButton) { editCaptureReason(reasonButton); return; }
        const citation = event.target.closest('[data-evidence-id]');
        if (!citation) return;
        const target = [...resultsContainer.querySelectorAll('[data-evidence-targets]')].find(node => {
            try { return JSON.parse(node.dataset.evidenceTargets).includes(citation.dataset.evidenceId); } catch { return false; }
        });
        if (target) {
            const details = target.closest('details'); if (details) details.open = true;
            const fullText = target.querySelector('.memory-fragment-text'); if (fullText) fullText.open = true;
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.focus({ preventScroll: true });
            return;
        }
        const card = resultsContainer.querySelector(`.result-card[data-id="${CSS.escape(citation.dataset.evidenceId)}"]`);
        if (card) {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.focus({ preventScroll: true });
        }
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) {
            queryInput.focus();
            if (typeof showNotification === 'function') showNotification({ title: 'Enter a question', message: 'Type a question or search term to continue.', type: 'error', key: 'memory-empty-query' });
            return;
        }
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

async function editCaptureReason(button) {
    const captureId = button.dataset.editReason;
    button.disabled = true;
    try {
        const response = await fetch(`/api/capture/${encodeURIComponent(captureId)}/reason`);
        if (!response.ok) throw new Error('Could not load the reason.');
        const data = await response.json();
        const form = document.createElement('form');
        form.className = 'memory-reason-form';
        const input = document.createElement('input');
        input.type = 'text'; input.maxLength = 500; input.value = data.reason || '';
        input.setAttribute('aria-label', 'Why did you save this?');
        const save = document.createElement('button'); save.type = 'submit'; save.textContent = 'Save reason';
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = 'Cancel';
        const status = document.createElement('span'); status.setAttribute('aria-live', 'polite');
        form.append(input, save, cancel, status); button.after(form); input.focus();
        cancel.onclick = () => { form.remove(); button.disabled = false; button.focus(); };
        form.onsubmit = async event => {
            event.preventDefault(); save.disabled = true;
            try {
                const reason = input.value.trim();
                const result = await fetch(`/api/capture/${encodeURIComponent(captureId)}/reason`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason,status:reason ? 'confirmed' : 'unknown'})});
                if (!result.ok) throw new Error('Could not save reason.');
                form.remove(); button.disabled = false; button.textContent = reason ? 'Edit save reason' : 'Add save reason'; button.focus();
            } catch (error) { status.textContent = error.message; save.disabled = false; }
        };
    } catch (error) { button.disabled = false; if (typeof showNotification === 'function') showNotification({title:'Save reason',message:error.message,type:'error'}); }
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
        loadingIndicator.hidden = page !== 1;
        bottomLoading.hidden = page === 1;
        if (page === 1) renderLoadingSkeletons(5, false);
        else renderLoadingSkeletons(3, true);
        endOfResults.hidden = true;
    } else {
        loadingIndicator.hidden = true;
        bottomLoading.hidden = true;
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
    const content = item.summary || item.content || '';
    const sourceUrl = item.source_url || '';
    const sourceTitle = item.source_site_name || item.source_title || '';
    const typeColors = { heading: '#1f6feb', text: '#64748b', code_block: '#238636', quote: '#8250df', link: '#9e6a03', image: '#da3633', entity: '#d29922', aggregate: '#22c55e' };
    const color = typeColors[type] || '#64748b';

    if (type === 'aggregate') {
        return `
          <article class="result-card card-aggregate" tabindex="0" data-type="aggregate" data-id="${escapeHtml(item.id)}" data-source-url="${escapeHtml(sourceUrl)}" data-source-title="${escapeHtml(sourceTitle)}">
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
      <article class="result-card" tabindex="0" data-type="atomic" data-id="${escapeHtml(item.id || '')}" data-index="${allResults.findIndex(r => r === item)}" data-source-url="${escapeHtml(sourceUrl)}" data-source-title="${escapeHtml(sourceTitle)}">
        <div class="card-meta">
          <span class="card-chip" style="background:${color};color:#fff;padding:0.15rem 0.4rem;border-radius:0.3rem;font-size:0.7rem;font-weight:600;text-transform:uppercase">${escapeHtml(type)}</span>
          ${sourceBadge}
        </div>
        <div class="card-body">
          <div class="card-title-row"><span class="card-title">${escapeHtml(item.title || shortContent)}</span></div>
          ${item.title && item.title !== shortContent ? `<p class="memory-card-summary">${escapeHtml(shortContent)}</p>` : ''}
          ${item.match_reason ? `<div class="memory-card-footer"><span>${escapeHtml(item.match_reason)}</span><span>${Number(item.source_count || 0)} source${Number(item.source_count || 0) === 1 ? '' : 's'}</span></div>` : ''}
          ${item.source_id ? `<button type="button" data-edit-reason="${escapeHtml(item.source_id)}">Edit save reason</button>` : ''}
        </div>
      </article>`;
}

function groupEvidenceBySource(items) {
    const groups = new Map();
    for (const item of items) {
        const key = item.source_id ? `source:${item.source_id}` : `evidence:${item.id}`;
        if (!groups.has(key)) groups.set(key, { id:item.source_id || '', title:item.source_title || item.title || 'Saved source', url:item.source_url || '', site:item.source_site_name || '', fragments:[] });
        const group = groups.get(key);
        const text = (item.excerpt || item.content || '').trim();
        const existing = item.excerpt_hash ? group.fragments.find(fragment => fragment.hash === item.excerpt_hash) : null;
        if (existing) existing.ids.push(String(item.id));
        else group.fragments.push({ text, hash:item.excerpt_hash || '', ids:[String(item.id)] });
    }
    return [...groups.values()];
}

function renderSourceGroups(items) {
    const groups = groupEvidenceBySource(items);
    if (!groups.length) return '';
    const fragmentCount = items.length;
    const card = group => {
        const renderFragment = fragment => {
            const text = fragment.text || 'No source excerpt available.';
            const body = text.length > 320 ? `<details class="memory-fragment-text"><summary>${escapeHtml(text.slice(0, 320))}… <span>Show full excerpt</span></summary><p>${escapeHtml(text)}</p></details>` : escapeHtml(text);
            return `<div class="memory-fragment" tabindex="-1" data-evidence-targets="${escapeHtml(JSON.stringify(fragment.ids))}">${body}</div>`;
        };
        const fragments = group.fragments;
        const extra = fragments.length > 1 ? `<details class="memory-fragments"><summary>${fragments.length - 1} more fragment${fragments.length === 2 ? '' : 's'}</summary>${fragments.slice(1).map(renderFragment).join('')}</details>` : '';
        const source = /^https?:\/\//i.test(group.url) ? `<a class="memory-source-link" href="${escapeHtml(group.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(group.site || 'Open source')} <span aria-hidden="true">↗</span></a>` : `<span class="memory-source-site">${escapeHtml(group.site || 'Saved source')}</span>`;
        return `<article class="result-card memory-source-card" data-source-id="${escapeHtml(group.id)}"><div class="memory-source-header"><div><h3>${escapeHtml(group.title)}</h3>${source}</div>${group.id ? `<details class="memory-card-menu"><summary aria-label="Source actions" title="Source actions">⋯</summary><div class="memory-card-menu-content"><button type="button" data-edit-reason="${escapeHtml(group.id)}">Edit save reason</button></div></details>` : ''}</div>${fragments.length ? renderFragment(fragments[0]) : ''}${extra}<div class="memory-source-count">${fragments.length} fragment${fragments.length === 1 ? '' : 's'}</div></article>`;
    };
    return `<section class="memory-sources"><div class="memory-sources-heading"><h2>Sources</h2><span>${groups.length} source${groups.length === 1 ? '' : 's'} · ${fragmentCount} evidence item${fragmentCount === 1 ? '' : 's'}</span></div><div class="memory-source-grid">${groups.map(card).join('')}</div></section>`;
}

function replaceMemoryResults(html) {
    const scrollPositions = [resultsContainer.closest('.results-area'), resultsContainer.closest('#content-view')].filter(Boolean).map(element => [element, element.scrollTop]);
    const openSources = new Set([...resultsContainer.querySelectorAll('.memory-source-card')].filter(card => card.querySelector('.memory-fragments[open]')).map(card => card.dataset.sourceId));
    resultsContainer.innerHTML = html;
    resultsContainer.querySelectorAll('.memory-source-card').forEach(card => {
        if (openSources.has(card.dataset.sourceId)) { const details = card.querySelector('.memory-fragments'); if (details) details.open = true; }
    });
    scrollPositions.forEach(([element, top]) => { element.scrollTop = top; });
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
            <h3>No saved evidence found</h3>
            <p>Nothing saved matches "${escapeHtml(currentQuery)}" yet. Try a different phrasing.</p>`;
    } else {
        emptyState.hidden = true;
    }
    updatePaginationControls();
}

async function doSearch(query, page, forceRefresh = false) {
    // Memory query returns one bounded packet and does not support paging.
    if (loading || page !== 1) return;
    memorySearchController?.abort();
    const controller = new AbortController();
    memorySearchController = controller;
    const generation = ++memorySearchGeneration;
    loading = true;
    showLoading(true, page);
    try {
        if (page === 1) {
            try {
                if (await doEvidenceFirstSearch(query, forceRefresh, controller.signal, generation)) return;
            } catch (streamError) {
                if (controller.signal.aborted || generation !== memorySearchGeneration) return;
                // A proxy or provider can interrupt a streamed response. Preserve
                // the normal local-result path rather than leaving the Library empty.
                console.warn('Streaming recall unavailable; using standard query.', streamError);
            }
        }
        const resp = await fetch('/api/memory/query', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({ query, limit: 8, token_budget: 700, mode: 'fast', synthesize: false }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (generation !== memorySearchGeneration) return;
        const fetched = data.items || [];
        window.currentMemoryViewModel = data;
        if (page === 1) {
            allResults = fetched;
            showLoading(false, page);
            renderMemoryView(data);
        } else {
            allResults = allResults.concat(fetched);
            showLoading(false, page);
            renderResults(true);
        }
        hasMore = false;
        currentPage = page;
        if (!hasMore && allResults.length > 0) endOfResults.hidden = false;
    } catch (err) {
        if (controller.signal.aborted || generation !== memorySearchGeneration) return;
        console.error('Search failed:', err);
        showLoading(false, page);
        resultsContainer.innerHTML = '<div class="message error">Search request failed.</div>';
        if (typeof showNotification === 'function') showNotification({ title: 'Search failed', message: err.message || 'The search request could not be completed.', type: 'error', key: 'memory-search' });
        hasMore = false;
    } finally {
        if (generation === memorySearchGeneration) {
            loading = false;
            updatePaginationControls();
        }
    }
}

async function doEvidenceFirstSearch(query, forceRefresh = false, signal, generation) {
    // Local recall never waits for an AI provider. It is the reliable baseline
    // and stays visible even if the stream or provider fails later.
    const diagnosticView = document.getElementById('ask-diagnostics');
    const diagnostics = settingsState.askSearchDiagnostics === true;
    const searchActivity = document.getElementById('ask-search-activity');
    if (searchActivity) { searchActivity.replaceChildren(); searchActivity.hidden = true; }
    if (diagnosticView) { diagnosticView.hidden = true; diagnosticView.textContent = ''; }
    const localResponse = await fetch('/api/memory/query', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        signal,
        body: JSON.stringify({ query, limit: 8, token_budget: 700, mode: 'fast', synthesize: false }),
    });
    if (!localResponse.ok) throw new Error(`HTTP ${localResponse.status}`);
    const local = await localResponse.json();
    if (signal.aborted || generation !== memorySearchGeneration) return true;
    allResults = local.items || [];
    window.currentMemoryViewModel = local;
    hasMore = false;
    currentPage = 1;
    showLoading(false, 1);
    renderMemoryView(local);
    const pending = {
        ...local,
        synthesis_status: 'streaming',
        synthesis: { status: 'streaming' },
    };
    window.currentMemoryViewModel = pending;
    renderStreamingMemoryView(pending);

    let resp;
    try {
        resp = await fetch('/api/memory/query/stream', {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/x-ndjson' },
            signal,
            body: JSON.stringify({
                query, limit: 8, token_budget: 700, mode: 'auto', response_language: 'auto',
                synthesize: true, stream_version: 2, force_refresh: forceRefresh,
                diagnostics,
                request_id: globalThis.crypto?.randomUUID?.() || `memory-${Date.now()}`,
            }),
        });
    } catch (error) {
        if (signal.aborted || generation !== memorySearchGeneration) return true;
        renderStreamFallback(local, error);
        return true;
    }
    if (!resp.ok) {
        renderStreamFallback(local, new Error(`HTTP ${resp.status}`));
        return true;
    }
    if (!resp.body) {
        renderStreamFallback(local, new Error('Streaming response body is unavailable'));
        return true;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let completed = false;
    try {
        while (true) {
            const { value, done } = await reader.read();
            if (signal.aborted || generation !== memorySearchGeneration) return true;
            buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.trim()) completed = handleMemoryStreamEvent(JSON.parse(line)) || completed;
            }
            if (done) break;
        }
        if (buffer.trim()) completed = handleMemoryStreamEvent(JSON.parse(buffer)) || completed;
        if (!completed) throw new Error('AI stream ended before request.completed');
    } catch (error) {
        if (signal.aborted || generation !== memorySearchGeneration) return true;
        renderStreamFallback(window.currentMemoryViewModel || local, error);
    } finally {
        reader.releaseLock();
    }
    return true;
}

function evidenceById(id) {
    const model = window.currentMemoryViewModel || {};
    return [...(model.evidence || []), ...(model.items || [])].find(item => String(item.id) === String(id));
}

function evidencePopover() {
    let popover = document.getElementById('memory-evidence-popover');
    if (!popover) {
        popover = document.createElement('aside');
        popover.id = 'memory-evidence-popover';
        popover.className = 'memory-evidence-popover';
        popover.setAttribute('role', 'tooltip');
        popover.hidden = true;
        document.body.appendChild(popover);
    }
    return popover;
}

function showEvidencePopover(event) {
    const citation = event.target.closest?.('[data-evidence-id]');
    if (!citation || (event.type === 'pointerover' && event.relatedTarget && citation.contains(event.relatedTarget))) return;
    const evidence = evidenceById(citation.dataset.evidenceId);
    if (!evidence) return;
    const popover = evidencePopover();
    const title = evidence.title || evidence.source_title || 'Saved evidence';
    const text = evidence.excerpt || evidence.content || '';
    const source = evidence.source_site_name || evidence.source_title || evidence.source_url || '';
    popover.replaceChildren();
    const heading = document.createElement('strong');
    heading.textContent = title;
    const body = document.createElement('p');
    body.textContent = text.length > 420 ? `${text.slice(0, 420)}…` : text;
    popover.append(heading, body);
    if (source && source !== title) {
        const meta = document.createElement('span');
        meta.textContent = source;
        popover.append(meta);
    }
    popover.hidden = false;
    citation.setAttribute('aria-describedby', popover.id);
    const rect = citation.getBoundingClientRect();
    const width = Math.min(360, window.innerWidth - 24);
    popover.style.width = `${width}px`;
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const top = rect.bottom + 8 + popover.offsetHeight <= window.innerHeight
        ? rect.bottom + 8
        : Math.max(12, rect.top - popover.offsetHeight - 8);
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
}

function hideEvidencePopover(event) {
    const citation = event.target.closest?.('[data-evidence-id]');
    if (!citation) return;
    if (event.relatedTarget && citation.contains(event.relatedTarget)) return;
    citation.removeAttribute('aria-describedby');
    const popover = document.getElementById('memory-evidence-popover');
    if (popover) popover.hidden = true;
}

function renderStreamFallback(local, error) {
    const fallback = {
        ...local,
        synthesis_status: 'error',
        synthesis: { status: 'error', code: 'stream_unavailable', message: 'AI streaming is unavailable. Local results are still available.' },
    };
    window.currentMemoryViewModel = fallback;
    renderMemoryView(fallback);
    if (typeof showNotification === 'function') showNotification({
        title: 'AI streaming unavailable', message: fallback.synthesis.message, type: 'error', duration: 0, key: 'memory-stream',
        actionLabel: 'Open AI settings', onAction: () => typeof openSettings === 'function' && openSettings('AI'),
    });
    console.warn('Streaming recall unavailable; local results remain available.', error);
}

function handleMemoryStreamEvent(event) {
    // v2 is typed and ordered; legacy meta/delta/done remains accepted during rollout.
    if (event.version === '2.0') {
        if (event.event === 'query.analyzed') {
            updateMemoryStreamStatus('Understanding your question');
            return false;
        }
        if (event.event === 'search.started') {
            updateMemoryStreamStatus('Finding saved evidence');
            return false;
        }
        if (event.event === 'search.completed') {
            updateMemoryStreamStatus('Reviewing saved evidence');
            return false;
        }
        if (event.event === 'search.performed') {
            const activity = document.getElementById('ask-search-activity');
            if (activity && typeof event.data?.query === 'string') {
                const line = document.createElement('div');
                line.textContent = `Searched: ${event.data.query}`;
                activity.appendChild(line);
                activity.hidden = false;
            }
            return false;
        }
        if (event.event === 'answer.block') {
            const {section, block} = event.data || {};
            if (Number.isInteger(section) && section >= 0 && section < 100 && block) {
                (window.currentMemoryBlocks[section] ||= []).push(block);
                renderStreamingDraft(window.currentMemoryDraft || '');
            }
            return false;
        }
        if (event.event === 'evidence.selected') event = { event: 'meta', data: event.data?.result };
        else if (event.event === 'answer.delta') event = { event: 'delta', text: event.data?.text };
        else if (event.event === 'request.completed') event = { event: 'done', data: event.data?.result };
        else if (event.event === 'request.error' || event.event === 'request.cancelled') {
            const current = window.currentMemoryViewModel || { items: [] };
            renderStreamFallback(current, new Error(event.data?.message || event.event));
            return true;
        } else return false;
    }
    if (event.event === 'meta') {
        const data = event.data;
        allResults = data.items || [];
        window.currentMemoryViewModel = data;
        hasMore = false;
        currentPage = 1;
        showLoading(false, 1);
        renderStreamingMemoryView(data);
        updateMemoryStreamStatus(`Reading ${allResults.length} evidence item${allResults.length === 1 ? '' : 's'}`);
        return false;
    }
    if (event.event === 'delta') {
        updateMemoryStreamStatus('Writing evidence-backed answer');
        window.currentMemoryDraft = (window.currentMemoryDraft || '') + (event.text || '');
        renderStreamingDraft(window.currentMemoryDraft);
        return false;
    }
    if (event.event === 'done') {
        const data = event.data;
        const diagnosticView = document.getElementById('ask-diagnostics');
        if (diagnosticView && data.diagnostics) {
            const d = data.diagnostics;
            diagnosticView.textContent = `Search diagnostics — planner: ${d.planner_status}; original candidates: ${d.original_candidates}; additional searches: ${d.alternative_queries}; results per additional search: ${(d.alternative_candidate_counts || []).map(n => n === null ? 'error' : n).join(', ') || 'none'}; merged candidates: ${d.merged_candidates}; selected evidence: ${d.selected_evidence}.`;
            diagnosticView.hidden = false;
        }
        allResults = data.items || [];
        window.currentMemoryViewModel = data;
        hasMore = false;
        currentPage = 1;
        showLoading(false, 1);
        renderMemoryView(data);
        return true;
    }
    return false;
}

function updateMemoryStreamStatus(message) {
    const label = resultsContainer.querySelector('[data-streaming-status]');
    if (label) label.textContent = message;
}

function renderStreamingDraft(text) {
    const draft = resultsContainer.querySelector('[data-streaming-draft]');
    if (!draft) return;
    const blocks = text.trimStart().split(/\n\n+/);
    const summary = blocks.shift() || '';
    draft.innerHTML = `<p class="memory-synthesis-summary">${escapeHtml(summary)}</p>` + blocks.map((block, index) => {
        const [heading, ...content] = block.split('\n');
        const structured = window.currentMemoryBlocks?.[index] || [];
        return `<section class="memory-synthesis-section memory-synthesis-section-live">
            <h3>${escapeHtml(heading)}</h3>
            ${structured.length ? structured.map(renderSynthesisBlock).join('') : `<p>${escapeHtml(content.join('\n'))}</p>`}
        </section>`;
    }).join('');
}

function renderStreamingMemoryView(viewModel) {
    window.currentMemoryDraft = '';
    window.currentMemoryBlocks = [];
    replaceMemoryResults(`<section class="memory-synthesis memory-synthesis-streaming" aria-live="polite">
        <div class="memory-synthesis-label memory-stream-status" data-streaming-status>Finding saved evidence</div>
        <h2>${escapeHtml(currentQuery)}</h2>
        <div class="memory-synthesis-draft" data-streaming-draft><p class="memory-synthesis-summary"></p></div>
    </section>` + renderSourceGroups(allResults));
    emptyState.hidden = true;
    updatePaginationControls();
}

function renderCitationParts(parts, fallbackText, fallbackIds = []) {
    const entries = Array.isArray(parts) ? parts : [{text: fallbackText || ''}];
    let hasCitation = false;
    const button = id => {
        const index = allResults.findIndex(item => String(item.id) === String(id));
        if (index < 0) return '';
        hasCitation = true;
        return `<button type="button" class="memory-inline-citation" data-evidence-id="${escapeHtml(id)}" aria-label="Open supporting evidence ${index + 1}">${index + 1}</button>`;
    };
    const content = entries.map(part => part.evidence_id ? button(part.evidence_id) : escapeHtml(part.text || '')).join('');
    return content + (hasCitation ? '' : fallbackIds.map(button).join(''));
}

function renderSynthesisBlock(block) {
    const cell = item => item?.missing ? '<span class="memory-synthesis-missing">Not found in saved sources</span>' : renderCitationParts(item?.parts, '');
    if ((block.type === 'bullets' || block.type === 'numbered') && Array.isArray(block.items)) {
        const tag = block.type === 'numbered' ? 'ol' : 'ul';
        return `<${tag} class="memory-synthesis-list">${block.items.map(item => `<li>${cell(item)}</li>`).join('')}</${tag}>`;
    }
    if (block.type === 'table' && Array.isArray(block.columns) && Array.isArray(block.rows)) {
        return `<div class="memory-synthesis-table-scroll" tabindex="0" role="region" aria-label="Comparison table"><table><thead><tr>${block.columns.map(column => `<th scope="col">${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${block.rows.map(row => `<tr>${row.map(item => `<td>${cell(item)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    return '';
}

function renderMemoryView(viewModel) {
    const synthesis = viewModel.answer || viewModel.synthesis || {};
    if (synthesis.status === 'error' && typeof showNotification === 'function') {
        showNotification({
            title: synthesis.http_status ? `AI error ${synthesis.http_status}` : 'AI synthesis unavailable',
            message: synthesis.message || 'AI synthesis failed. Local results are still available.',
            type: 'error', duration: 0, key: `ai:${synthesis.code || 'error'}`,
            actionLabel: 'Open AI settings',
            onAction: () => typeof openSettings === 'function' && openSettings('AI'),
        });
    }
    const hasSynthesis = viewModel.synthesis_status === 'success' && synthesis.summary;
    const isEmptyLibrary = !currentQuery && allResults.length === 0;
    const synthesisHtml = isEmptyLibrary ? `<section class="memory-empty-library">
        <span class="memory-synthesis-label">Your private recall layer</span>
        <h2>Save something worth finding later.</h2>
        <p>Highlight text on any webpage and press Save. Nodecast keeps the original source locally, then makes it available when you ask in your own words.</p>
    </section>` : hasSynthesis ? `<section class="memory-synthesis memory-synthesis-${escapeHtml(viewModel.view || 'list')}">
        <div class="memory-synthesis-label">AI synthesis</div>
        ${viewModel.cache?.hit ? `<div class="memory-cache-note">Saved answer · ${escapeHtml(formatTimeLong(viewModel.cache.created_at))} <button type="button" data-refresh-recall>Generate again</button></div>` : ''}
        <h2>${escapeHtml(synthesis.title || currentQuery)}</h2>
        <p>${renderCitationParts(synthesis.summary_parts, synthesis.summary)}</p>
        ${(synthesis.sections || []).map(section => `<div class="memory-synthesis-section"><h3>${escapeHtml(section.title)}</h3>${section.blocks?.length ? section.blocks.map(renderSynthesisBlock).join('') : `<p>${renderCitationParts(section.content_parts, section.content, section.evidence_ids || [])}</p>`}</div>`).join('')}
    </section>` : `<div class="memory-fallback-note">${escapeHtml(memoryFallbackMessage(synthesis))}</div>`;
    replaceMemoryResults(synthesisHtml + renderSourceGroups(allResults));
    emptyState.hidden = true;
    updatePaginationControls();
}

function memoryFallbackMessage(synthesis) {
    if (synthesis.status === 'error') return 'AI synthesis failed. Saved evidence remains available below.';
    switch (synthesis.code) {
        case 'no_saved_sources': return 'No saved sources yet. Save a source before asking for an evidence-backed answer.';
        case 'no_indexed_evidence': return 'Sources are saved, but no searchable evidence is available yet. AI cannot answer from saved evidence until it is indexed.';
        case 'no_matching_evidence': return 'No matching evidence was found for this question. AI cannot answer from saved evidence; try different wording.';
        case 'provider_unavailable': return 'Saved evidence is available, but no Recall synthesis model is configured. Connect one in Settings → AI.';
        default: return 'Showing saved evidence without an AI-generated answer.';
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
    const showEndMessage = false;
    sentinel.hidden = !showSentinel;
    loadMoreButton.hidden = !showLoadMore;
    bottomLoading.hidden = true;
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
    showLoading(false, 1);
    try {
        const resp = await fetch('/api/memory?limit=8');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        allResults = data.items || [];
        window.currentMemoryViewModel = data;
        renderMemoryView(data);
    } catch (err) {
        console.error('Library load failed:', err);
        resultsContainer.innerHTML = '<div class="message error">Could not load saved content.</div>';
        if (typeof showNotification === 'function') showNotification({ title: 'Library unavailable', message: err.message || 'Could not load saved content.', type: 'error', key: 'library-load' });
    }
    loading = false;
    showLoading(false, 1);
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
                return `<div class="dashboard-atom-item" tabindex="0" data-id="${escapeHtml(a.id || '')}" data-type="${escapeHtml(type)}" data-content="${escapeHtml(a.content || '')}" data-source-url="${escapeHtml(a.source_url || '')}" data-source-title="${escapeHtml(a.source_title || '')}" data-source-site="${escapeHtml(a.source_site_name || '')}">
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
    return `<div class="entity-card" tabindex="0" data-id="${escapeHtml(e.id)}">
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
    if (query.startsWith('/sources')) return hasArgs ? sourcesSearch(query.slice('/sources '.length).trim()) : loadLibrary();
    if (query.startsWith('/cards')) return hasArgs ? doSearch(query.slice('/cards '.length).trim(), 1) : loadLibrary();
    if (query.startsWith('/table')) return hasArgs ? doSearch(query.slice('/table '.length).trim(), 1) : loadLibrary();
    if (query.startsWith('/timeline')) return hasArgs ? doSearch(query.slice('/timeline '.length).trim(), 1) : loadLibrary();
    if (query.startsWith('/compare')) return hasArgs ? doSearch(`compare ${query.slice('/compare '.length).trim()}`, 1) : (resultsContainer.innerHTML='<div class="message">Usage: /compare X and Y</div>', hasMore=false, endOfResults.hidden=true);
    if (query.startsWith('/markdown')) return hasArgs ? doSearch(query.slice('/markdown '.length).trim(), 1) : loadLibrary();
    return doSearch(query, 1);
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
