// Shared manual / natural-language filter state, scoped to the signed-in member.
(function createLibraryFilters() {
    const empty = () => ({ sources: [], capture_types: [], period: 'any', start_date: null, end_date: null });
    const periods = { today: 'Today', yesterday: 'Yesterday', last7: 'Last 7 days', last30: 'Last 30 days' };
    const kindLabel = kind => ({ snippet: 'Snippet', page: 'Page', bookmark: 'Bookmark', article: 'Article', video: 'Video', issue: 'Issue', chat: 'Chat', pdf: 'PDF' }[kind] || kind);
    const clone = value => JSON.parse(JSON.stringify(value));
    const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    let selected = empty(), draft = empty(), options = { sources: [], capture_types: [] };
    let storageKey = '', dialog, opener, browseController, browseBody, browseOffset = 0, browseItems = [], browseGeneration = 0;
    const phraseQueries = new Map();
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    function hasActive() { return selected.sources.length > 0 || selected.capture_types.length > 0 || selected.period !== 'any'; }
    function save() { if (storageKey) try { localStorage.setItem(storageKey, JSON.stringify(selected)); } catch {} }
    function count() { return selected.sources.length + selected.capture_types.length + Number(selected.period !== 'any'); }
    function render() {
        const chips = [...selected.sources.map(value => ({facet:'sources', value, text:value})),
            ...selected.capture_types.map(value => ({facet:'capture_types', value, text:kindLabel(value)}))];
        if (selected.period !== 'any') chips.push({facet:'period', value:selected.period, text:'Saved: ' + (periods[selected.period] || `${selected.start_date || 'Any date'} → ${selected.end_date || 'No end date'}`)});
        const html = chips.map(chip => `<button type="button" class="library-filter-chip" data-remove-filter="${chip.facet}" data-filter-value="${esc(chip.value)}" aria-label="Remove ${esc(chip.text)} filter">${esc(chip.text)} <span aria-hidden="true">×</span></button>`).join('') + (chips.length ? '<button type="button" class="library-filter-clear" data-clear-library-filters>Clear all</button>' : '');
        ['home-filter-chips','filter-bar'].forEach(id => {
            const host = document.getElementById(id); if (!host) return;
            host.innerHTML = html;
            host.hidden = !chips.length || (id === 'home-filter-chips' && window.webMode === true);
        });
        document.querySelectorAll('[data-open-library-filters]').forEach(button => {
            button.classList.toggle('has-filters', chips.length > 0);
            button.setAttribute('aria-label', `Filter saved items${count() ? `, ${count()} active` : ''}`);
            const badge = button.querySelector('[data-filter-count]'); if (badge) { badge.hidden = !count(); badge.textContent = count(); }
        });
    }
    function accept(data, query) {
        if (data?.filters) { selected = clone(data.filters); save(); render(); }
        if (data?.filter_phrases && query) phraseQueries.set(query, data.filter_phrases);
    }
    function request(interpret = true, query = '') { return { filters:clone(selected), timezone, interpret_filters:interpret, filter_phrases:phraseQueries.get(query) || [] }; }
    function changed() {
        save(); render();
        if (!document.getElementById('content-view')?.hidden) {
            if (typeof memorySearchController !== 'undefined') memorySearchController?.abort();
            if (typeof loading !== 'undefined') loading = false;
            if (typeof currentQuery !== 'undefined' && (currentQuery.trim() || hasActive())) doSearch(currentQuery, 1, false, false);
            else { browseController?.abort(); window.nodecastWorkspace?.closeResults(); }
        }
    }
    function close() { dialog.close(); opener?.focus(); }
    function optionsHtml(field, filter = '') {
        const all = [...options[field]];
        draft[field].forEach(value => { if (!all.some(row => row.value === value)) all.unshift({value, count:0}); });
        const rows = all.filter(row => row.value.toLowerCase().includes(filter.toLowerCase()));
        return rows.length ? rows.map(row => `<label class="library-filter-option"><input type="checkbox" data-filter-facet="${field}" value="${esc(row.value)}" ${draft[field].includes(row.value) ? 'checked' : ''}><span>${esc(field === 'capture_types' ? kindLabel(row.value) : row.value)}</span><small>${row.count}</small></label>`).join('') : '<p class="library-filter-empty">No matching saved sources.</p>';
    }
    function renderOptions() {
        document.getElementById('library-filter-sources').innerHTML = optionsHtml('sources', document.getElementById('library-filter-source-search').value);
        document.getElementById('library-filter-types').innerHTML = optionsHtml('capture_types');
    }
    function renderDates() { document.getElementById('library-filter-dates').hidden = document.getElementById('library-filter-period').value !== 'custom'; }
    async function open(button) {
        window.setWebMode?.(false);
        opener = button; draft = clone(selected);
        document.getElementById('library-filter-source-search').value = '';
        document.getElementById('library-filter-period').value = draft.period;
        document.getElementById('library-filter-start').value = draft.start_date || '';
        document.getElementById('library-filter-end').value = draft.end_date || '';
        document.getElementById('library-filter-timezone').textContent = `Calendar dates in ${timezone}.`;
        document.getElementById('library-filter-error').hidden = true;
        renderOptions(); renderDates(); dialog.showModal();
        // setWebMode schedules focus on the search bar; keep focus in this modal.
        setTimeout(() => document.getElementById('library-filter-source-search').focus(), 0);
        try {
            const response = await fetch('/api/memory/filters');
            if (!response.ok) throw new Error('Sources could not be loaded. Close and reopen filters to retry.');
            options = await response.json();
            if (dialog.open) renderOptions();
        } catch (error) { const message = document.getElementById('library-filter-error'); message.hidden = false; message.textContent = error.message; }
    }
    function renderBrowse(data, append) {
        browseItems = append ? browseItems.concat(data.items) : data.items;
        browseOffset = browseItems.length;
        document.getElementById('saved-browse-count').textContent = `${browseItems.length} of ${data.page.total}`;
        document.getElementById('saved-browse-items').innerHTML = browseItems.map(item => `<article class="result-card saved-browse-card" data-saved-source="${esc(item.id)}"><h3>${esc(item.source_title || 'Untitled saved item')}</h3><div class="saved-browse-meta"><span>${esc(kindLabel(item.capture_type))}</span><time datetime="${esc(item.saved_at)}">${esc(typeof formatTimeLong === 'function' ? formatTimeLong(item.saved_at) : item.saved_at)}</time></div>${/^https?:\/\//i.test(item.source_url) ? `<a class="memory-source-link" href="${esc(safeExternalUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">${esc(item.domain || item.source_site_name || 'Open source')} ↗</a>` : ''}<a class="saved-snapshot-link" href="/api/capture/${encodeURIComponent(item.id)}/render/markdown" target="_blank" rel="noopener noreferrer">Saved text</a></article>`).join('');
        document.getElementById('saved-browse-status').textContent = data.page.total ? '' : 'No saved items match this text and these filters.';
        document.getElementById('saved-browse-more').hidden = !data.page.has_more;
    }
    async function searchSaved(query, body, signal, append = false) {
        const host = document.getElementById('saved-browse'); if (!host) return;
        if (!append) { browseController?.abort(); browseController = new AbortController(); browseBody = {query, ...body}; browseItems = []; browseOffset = 0; }
        const controller = browseController;
        const generation = ++browseGeneration;
        const abort = () => controller.abort();
        signal?.addEventListener('abort', abort, {once:true});
        host.hidden = false;
        const status = document.getElementById('saved-browse-status');
        status.textContent = 'Loading saved items…';
        document.getElementById('saved-browse-more').disabled = true;
        if (!append) { document.getElementById('saved-browse-items').innerHTML = ''; document.getElementById('saved-browse-count').textContent = ''; document.getElementById('saved-browse-more').hidden = true; }
        try {
            if (signal?.aborted) { controller.abort(); return; }
            const response = await fetch('/api/memory/browse', {method:'POST', headers:{'Content-Type':'application/json'}, signal:controller.signal, body:JSON.stringify({...browseBody, limit:20, offset:browseOffset, synthesize:false})});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (generation !== browseGeneration || controller.signal.aborted) return;
            renderBrowse(data, append);
        } catch (error) {
            if (generation === browseGeneration && !controller.signal.aborted) status.textContent = 'Saved items could not be loaded. Search again to retry.';
        } finally {
            signal?.removeEventListener('abort', abort);
            if (generation === browseGeneration) document.getElementById('saved-browse-more').disabled = false;
        }
    }
    window.nodecastLibraryFilters = { hasActive, accept, request, searchSaved, render };
    window.addEventListener('nodecast:search-mode', render);
    window.addEventListener('DOMContentLoaded', () => {
        const uid = document.body.dataset.libraryUser;
        storageKey = uid ? `nodecast.libraryFilters.${uid}` : '';
        try {
            const saved = storageKey ? JSON.parse(localStorage.getItem(storageKey) || 'null') : null;
            if (saved && Array.isArray(saved.sources) && Array.isArray(saved.capture_types) && ['any','today','yesterday','last7','last30','custom'].includes(saved.period)) selected = {...empty(), ...saved};
        } catch {}
        dialog = document.getElementById('library-filters-dialog');
        document.querySelectorAll('[data-open-library-filters]').forEach(button => button.addEventListener('click', () => open(button)));
        document.querySelectorAll('[data-close-library-filters]').forEach(button => button.addEventListener('click', close));
        dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close(); } });
        dialog.addEventListener('cancel', () => { setTimeout(() => opener?.focus(),0); });
        document.getElementById('library-filter-period').addEventListener('change', renderDates);
        document.getElementById('library-filter-source-search').addEventListener('input', renderOptions);
        dialog.addEventListener('change', event => { const field = event.target.dataset.filterFacet; if (!field) return; const value = event.target.value; if (event.target.checked && draft[field].length >= 20) {
            event.target.checked = false;
            const error = document.getElementById('library-filter-error'); error.hidden = false; error.textContent = 'Choose up to 20 values per filter.'; return;
        }
        draft[field] = event.target.checked ? [...new Set([...draft[field], value])] : draft[field].filter(item => item !== value); });
        const clear = () => { selected = empty(); changed(); if (dialog.open) close(); };
        document.getElementById('library-filters-clear').addEventListener('click', clear);
        document.getElementById('library-filters-form').addEventListener('submit', event => {
            event.preventDefault();
            draft.period = document.getElementById('library-filter-period').value;
            draft.start_date = draft.period === 'custom' ? document.getElementById('library-filter-start').value || null : null;
            draft.end_date = draft.period === 'custom' ? document.getElementById('library-filter-end').value || null : null;
            const invalid = draft.period === 'custom' && ((!draft.start_date && !draft.end_date) || (draft.start_date && draft.end_date && draft.start_date > draft.end_date));
            const error = document.getElementById('library-filter-error'); error.hidden = !invalid;
            if (invalid) { error.textContent = 'Choose a valid date range. From must be on or before Through.'; return; }
            selected = clone(draft); close(); changed();
        });
        ['home-filter-chips','filter-bar'].forEach(id => document.getElementById(id)?.addEventListener('click', event => {
            if (event.target.closest('[data-clear-library-filters]')) { clear(); return; }
            const button = event.target.closest('[data-remove-filter]'); if (!button) return;
            const field = button.dataset.removeFilter;
            if (field === 'period') { selected.period = 'any'; selected.start_date = selected.end_date = null; }
            else selected[field] = selected[field].filter(value => value !== button.dataset.filterValue);
            changed();
        }));
        document.getElementById('saved-browse-more').addEventListener('click', () => searchSaved(browseBody.query, browseBody, null, true));
        render();
    });
})();
