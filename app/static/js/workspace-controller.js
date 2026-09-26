// Workspace shell controller. Existing feature modules remain responsible for data fetching/rendering.
(function createWorkspaceController() {
    const VIEW_COPY = {
        library: ['Personal memory', 'Library', 'Recent evidence and concepts from your saved sources.'],
        web: ['Search the web', 'Web Search', 'Send a query to your configured search engine.'],
        sources: ['Provenance', 'Sources', 'Audit saved pages and the evidence extracted from them.'],
        entities: ['Concept index', 'Concepts', 'Browse recurring people, tools and concepts.'],
        graph: ['Focused context', 'Knowledge Graph', 'Explore the selected memory and its accepted relationships.'],
    };

    function escapeWorkspaceHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function isTypingTarget(target) {
        return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
    }

    window.addEventListener('DOMContentLoaded', () => {
        const store = window.nodecastWorkspaceStore;
        if (!store) return;

        const shell = document.querySelector('.workspace-shell');
        const form = document.getElementById('search-form');
        const query = document.getElementById('query');
        const results = document.getElementById('results-container');
        const title = document.getElementById('workspace-view-title');
        const eyebrow = document.getElementById('workspace-view-eyebrow');
        const description = document.getElementById('workspace-view-description');
        const inspector = document.getElementById('workspace-inspector');
        const inspectorTitle = document.getElementById('workspace-inspector-title');
        const inspectorContent = document.getElementById('workspace-inspector-content');
        const inspectorToggle = document.getElementById('workspace-inspector-toggle');
        const inspectorClose = document.getElementById('workspace-inspector-close');
        const projectionButtons = [...document.querySelectorAll('[data-projection]')];
        const saveViewButton = document.getElementById('workspace-save-view');
        const savedViewsContainer = document.getElementById('workspace-saved-views');
        const navButtons = [...document.querySelectorAll('[data-workspace-view]')];

        function setSection(section) {
            const copy = VIEW_COPY[section] || VIEW_COPY.library;
            eyebrow.textContent = copy[0];
            title.textContent = copy[1];
            description.textContent = copy[2];
            navButtons.forEach(button => button.classList.toggle('active', button.dataset.workspaceView === section));
            const selectedId = section === 'graph' ? store.get().selectedId : null;
            store.set({ section, projection: section === 'graph' ? 'graph' : 'list', selectedId });
            projectionButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.projection === 'list')));
            document.getElementById('workspace-view-header').hidden = section === 'graph';
            if (section !== 'graph') clearSelection(false);
        }

        function showContentView() {
            window.graphMode = false;
            document.getElementById('graph-area').hidden = true;
            document.getElementById('content-view').hidden = false;
        }

        document.getElementById('sidebar-library-nav')?.addEventListener('click', () => setSection('library'));
        document.getElementById('sidebar-web-nav')?.addEventListener('click', () => setSection('web'));
        document.getElementById('sidebar-graph-nav')?.addEventListener('click', () => {
            if (!store.get().selectedId) {
                if (typeof showToast === 'function') showToast('Select a memory before opening its graph', 'info');
                return;
            }
            setSection('graph');
        });
        document.getElementById('sidebar-recent-view')?.addEventListener('click', () => {
            showContentView();
            if (typeof window.setWebMode === 'function') window.setWebMode(false);
            setSection('library');
        });
        document.getElementById('sidebar-sources-nav')?.addEventListener('click', async () => {
            showContentView();
            webMode = false;
            if (query) { query.value = '/sources '; query.placeholder = 'Filter saved sources...'; }
            setSection('sources');
            if (typeof loadLibrary === 'function') await loadLibrary();
        });
        document.getElementById('sidebar-entities-nav')?.addEventListener('click', async () => {
            showContentView();
            webMode = false;
            if (query) { query.value = '/entities '; query.placeholder = 'Filter concepts...'; }
            setSection('entities');
            if (typeof entitySearch === 'function') await entitySearch('');
        });

        function applyInspector(open) {
            shell.classList.toggle('inspector-collapsed', !open);
            inspectorToggle?.setAttribute('aria-pressed', String(open));
        }

        inspectorToggle?.addEventListener('click', () => store.set({ inspectorOpen: !store.get().inspectorOpen }));
        inspectorClose?.addEventListener('click', () => store.set({ inspectorOpen: false }));

        function clearSelection(resetInspector = true) {
            results?.querySelectorAll('.workspace-selected').forEach(element => element.classList.remove('workspace-selected'));
            if (!resetInspector) return;
            inspectorTitle.textContent = 'Nothing selected';
            inspectorContent.innerHTML = '<div class="workspace-inspector-empty"><span>↳</span><p>Select a memory to inspect its evidence, source and relationships.</p></div>';
            store.set({ selectedId: null });
        }

        function itemFromElement(element) {
            if (element.classList.contains('result-card')) {
                const index = Number(element.dataset.index);
                if (Number.isInteger(index) && Array.isArray(window.allResults || allResults)) {
                    const list = window.allResults || allResults;
                    if (list[index]) return list[index];
                }
                const aggregate = Array.isArray(window.allResults || allResults)
                    ? (window.allResults || allResults).find(item => item.id === element.dataset.id)
                    : null;
                if (aggregate) return aggregate;
            }
            if (element.classList.contains('dashboard-atom-item')) {
                return {
                    id: element.dataset.id,
                    type: element.dataset.type,
                    content: element.dataset.content || element.querySelector('.dashboard-atom-content')?.textContent || '',
                    source_url: element.dataset.sourceUrl || '',
                    source_title: element.dataset.sourceTitle || '',
                    source_site_name: element.dataset.sourceSite || '',
                };
            }
            if (element.classList.contains('entity-card')) {
                return {
                    id: element.dataset.id,
                    type: 'entity',
                    content: element.querySelector('.entity-name')?.textContent || 'Entity',
                    properties: { description: element.querySelector('.entity-desc')?.textContent || '' },
                };
            }
            return {
                id: element.dataset.id || '',
                type: 'memory',
                content: element.textContent.trim().replace(/\s+/g, ' '),
            };
        }

        function renderInspector(item, options = {}) {
            const content = item.summary || item.content || item.name || 'Untitled memory';
            const properties = item.properties && typeof item.properties === 'object' ? item.properties : {};
            const sourceUrl = item.source_url || '';
            const sourceTitle = item.source_title || item.source_site_name || sourceUrl || 'No source attached';
            const confidence = typeof item.confidence === 'number' ? `${Math.round(item.confidence * 100)}%` : '—';
            inspectorTitle.textContent = content.length > 48 ? `${content.slice(0, 48)}…` : content;
            inspectorContent.innerHTML = `
                <section class="inspector-section">
                    <div class="inspector-section-label">Evidence</div>
                    <p class="inspector-content-copy">${escapeWorkspaceHtml(content)}</p>
                </section>
                ${properties.description ? `<section class="inspector-section"><div class="inspector-section-label">Description</div><p class="inspector-content-copy">${escapeWorkspaceHtml(properties.description)}</p></section>` : ''}
                <section class="inspector-section">
                    <div class="inspector-section-label">Details</div>
                    <dl class="inspector-meta-grid">
                        <dt>Type</dt><dd>${escapeWorkspaceHtml(item.type || 'memory')}</dd>
                        <dt>Confidence</dt><dd>${confidence}</dd>
                        <dt>Extracted by</dt><dd>${escapeWorkspaceHtml(item.extracted_by || 'Nodecast')}</dd>
                        <dt>Source</dt><dd>${escapeWorkspaceHtml(sourceTitle)}</dd>
                    </dl>
                </section>
                ${sourceUrl ? `<section class="inspector-section"><div class="inspector-section-label">Original source</div><a class="inspector-source-link" href="${escapeWorkspaceHtml(sourceUrl)}" target="_blank" rel="noopener"><span>${escapeWorkspaceHtml(sourceTitle)}</span><span>↗</span></a></section>` : ''}
                ${item.id && !options.expanded ? `<button class="inspector-action" type="button" data-inspector-open-atomic="${escapeWorkspaceHtml(item.id)}"><span>Load source and relationships</span><span>→</span></button>` : ''}`;
            store.set({ selectedId: item.id || null, inspectorOpen: true });
            if (item.id && !sourceUrl && !options.expanded) {
                window.setTimeout(() => loadAtomicDetail(item.id), 0);
            }
        }

        async function loadAtomicDetail(id) {
            if (!id) return;
            const button = inspectorContent.querySelector('[data-inspector-open-atomic]');
            if (button) { button.disabled = true; button.firstElementChild.textContent = 'Loading…'; }
            try {
                const response = await fetch(`/api/memory/${encodeURIComponent(id)}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                const evidence = data.evidence || [];
                renderInspector(evidence[0] || data.memory || {}, { expanded: true });
                const relations = data.relations || [];
                if (relations.length) {
                    inspectorContent.insertAdjacentHTML('beforeend', `<section class="inspector-section"><div class="inspector-section-label">Relationships</div>${relations.slice(0, 12).map(relation => `<div class="inspector-meta-grid"><dt>${escapeWorkspaceHtml(relation.relation_type || 'related')}</dt><dd>${Math.round(Number(relation.strength || 0) * 100)}%</dd></div>`).join('')}</section>`);
                }
            } catch {
                if (button) { button.disabled = false; button.firstElementChild.textContent = 'Relationship details unavailable'; }
            }
        }

        results?.addEventListener('click', event => {
            if (event.target.closest('a, button, input, select, textarea')) return;
            const itemElement = event.target.closest('.result-card, .dashboard-atom-item, .entity-card, .fact-card, .entity-related-item');
            if (!itemElement) return;
            results.querySelectorAll('.workspace-selected').forEach(element => element.classList.remove('workspace-selected'));
            itemElement.classList.add('workspace-selected');
            renderInspector(itemFromElement(itemElement));
        });

        inspectorContent?.addEventListener('click', event => {
            const button = event.target.closest('[data-inspector-open-atomic]');
            if (button) loadAtomicDetail(button.dataset.inspectorOpenAtomic);
        });

        function applyProjection(projection) {
            const selected = results?.querySelector('.workspace-selected');
            if (projection === 'focus' && !selected) results?.querySelector('.result-card, .dashboard-atom-item, .entity-card')?.click();
            results?.classList.toggle('workspace-projection-focus', projection === 'focus');
            results?.classList.toggle('workspace-projection-sources', projection === 'sources');
            projectionButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.projection === projection)));
            store.set({ projection });
        }

        projectionButtons.forEach(button => button.addEventListener('click', () => applyProjection(button.dataset.projection)));

        form?.addEventListener('submit', () => {
            const value = query.value.trim();
            if (!value) return;
            saveViewButton.hidden = false;
            eyebrow.textContent = 'Memory retrieval';
            title.textContent = value.replace(/^\/\w+\s*/, '') || 'Results';
            description.textContent = 'Ranked saved knowledge with traceable sources.';
            store.set({ query: value, section: 'library', projection: 'list' });
            navButtons.forEach(button => button.classList.toggle('active', button.dataset.workspaceView === 'library'));
            applyProjection('list');
        });

        function renderSavedViews() {
            const views = store.get().savedViews;
            savedViewsContainer.innerHTML = views.map((view, index) => `<button type="button" class="sidebar-nav-btn sidebar-saved-view" data-saved-view-index="${index}"><span class="sidebar-nav-icon">•</span><span class="sidebar-nav-label">${escapeWorkspaceHtml(view.label)}</span></button>`).join('');
        }

        saveViewButton?.addEventListener('click', () => {
            const value = query.value.trim();
            if (!value) return;
            const current = store.get();
            const exists = current.savedViews.some(view => view.query === value && view.projection === current.projection);
            if (exists) {
                if (typeof showToast === 'function') showToast('View already saved', 'info');
                return;
            }
            const label = value.replace(/^\/\w+\s*/, '').slice(0, 28) || 'Saved view';
            store.set({ savedViews: [...current.savedViews, { label, query: value, projection: current.projection }] });
            renderSavedViews();
            if (typeof showToast === 'function') showToast('View saved', 'success');
        });

        savedViewsContainer?.addEventListener('click', event => {
            const button = event.target.closest('[data-saved-view-index]');
            if (!button) return;
            const view = store.get().savedViews[Number(button.dataset.savedViewIndex)];
            if (!view) return;
            query.value = view.query;
            form.requestSubmit();
            setTimeout(() => applyProjection(view.projection || 'list'), 0);
        });

        document.addEventListener('keydown', event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                query?.focus();
                query?.select();
                return;
            }
            if (isTypingTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
            if (event.key.toLowerCase() === 'g') {
                event.preventDefault();
                document.getElementById('sidebar-graph-nav')?.click();
                return;
            }
            if (event.key.toLowerCase() === 's') {
                event.preventDefault();
                applyProjection('sources');
                return;
            }
            if (!['j', 'k', 'ArrowDown', 'ArrowUp'].includes(event.key)) return;
            const items = [...results.querySelectorAll('.result-card:not([hidden]), .dashboard-atom-item:not([hidden]), .entity-card:not([hidden])')].filter(item => getComputedStyle(item).display !== 'none');
            if (!items.length) return;
            event.preventDefault();
            const currentIndex = items.findIndex(item => item.classList.contains('workspace-selected'));
            const direction = event.key === 'j' || event.key === 'ArrowDown' ? 1 : -1;
            const next = items[(currentIndex + direction + items.length) % items.length];
            next.click();
            next.scrollIntoView({ block: 'nearest' });
        });

        const resultObserver = new MutationObserver(() => {
            const state = store.get();
            results.classList.toggle('workspace-projection-focus', state.projection === 'focus');
            results.classList.toggle('workspace-projection-sources', state.projection === 'sources');
        });
        if (results) resultObserver.observe(results, { childList: true });

        store.subscribe(state => applyInspector(state.inspectorOpen));
        renderSavedViews();
        applyInspector(store.get().inspectorOpen);
        setSection('library');
    });
})();
