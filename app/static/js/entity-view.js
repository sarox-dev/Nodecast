
// ─── Helpers ──────────────────────────────────────────

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
}

// ─── Entity Search ────────────────────────────────────

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

// ─── Render Entity Card ───────────────────────────────

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

// ─── Open Entity Detail ───────────────────────────────

async function openEntityDetail(entityId) {
    loading = true;
    resultsContainer.innerHTML = skeletonLoader(5);
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