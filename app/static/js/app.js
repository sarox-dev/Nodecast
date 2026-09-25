// ─── Shared state (global, accessed by all modules) ──────────────
let allResults = [];
let currentQuery = '';
let currentPage = 1;
let loading = false;
let hasMore = false;
let webMode = false;
let pageShell = null;
let form = null;
let queryInput = null;
let resultsContainer = null;
let sentinel = null;
let loadMoreButton = null;
let bottomLoading = null;
let endOfResults = null;
let emptyState = null;
let statusBar = null;
let loadingIndicator = null;
let scrollTopButton = null;
let observer = null;

window.addEventListener('DOMContentLoaded', async () => {
    let currentUser = null;
    try {
        const meRes = await fetch('/auth/me');
        if (meRes.ok) {
            currentUser = await meRes.json();
            const uname = document.getElementById('sidebar-username');
            if (uname) uname.textContent = currentUser.username;
            const subtitle = document.getElementById('sidebar-brand-subtitle');
            if (subtitle) subtitle.textContent = currentUser.username;
        } else {
            window.location.href = '/login';
            return;
        }
    } catch {
        window.location.href = '/login';
        return;
    }

    document.getElementById('logout-button')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch('/auth/logout', { method: 'POST' });
        window.location.href = '/login';
    });

    document.querySelector('.sidebar-brand')?.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        openAccountSettings();
    });

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
    const resultCount = document.getElementById('result-count');
    const settingsButton = document.getElementById('settings-button');
    loadingIndicator = document.getElementById('loading-indicator');
    scrollTopButton = document.createElement('button');
    scrollTopButton.id = 'scroll-top-button';
    scrollTopButton.className = 'scroll-top-button';
    scrollTopButton.type = 'button';
    scrollTopButton.hidden = true;
    scrollTopButton.textContent = '↑';
    document.body.appendChild(scrollTopButton);

    webMode = false;
    currentQuery = '';
    currentPage = 1;
    loading = false;
    hasMore = false;
    allResults = [];

    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const settingsList = document.getElementById('settings-list');
    const settingsSave = document.getElementById('settings-save');
    const settingsRevert = document.getElementById('settings-revert');
    const settingsCategories = document.getElementById('settings-categories');
    const settingsCategoryTitle = document.getElementById('settings-category-title');
    const settingsCategoryDescription = document.getElementById('settings-category-description');
    const settingsSearchInput = document.getElementById('settings-search-input');

    let activeSettingsCategory = localStorage.getItem('activeSettingsCategory') || 'Appearance';
    let accountData = null;

    settingsSearchInput?.addEventListener('input', (e) => filterSettings(e.target.value));
    settingsList?.addEventListener('change', (e) => { if (e.target.closest('[data-feature]')) return; if (e.target.matches('select, input')) _markDirty(); });
    settingsList?.addEventListener('input', (e) => { if (e.target.matches('input[type="text"], input[type="number"]')) _markDirty(); });
    settingsCategories?.addEventListener('click', (e) => {
        const button = e.target.closest('.settings-category-button');
        if (!button) return;
        if (_dirty) { _shakeActions(); return; }
        activeSettingsCategory = button.dataset.category;
        localStorage.setItem('activeSettingsCategory', activeSettingsCategory);
        renderCategoryNav(); renderSettings();
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
    });

    settingsButton.addEventListener('click', openSettings);
    settingsClose.addEventListener('click', closeSettings);
    settingsOverlay.addEventListener('click', (e) => { if (e.target === settingsOverlay) { if (_dirty) { _shakeActions(); } else { closeSettings(); } } });
    settingsSave.addEventListener('click', () => { _saveSettings(); applyTheme(); });
    settingsRevert.addEventListener('click', () => { renderSettings(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !settingsOverlay.hidden) { if (_dirty) { _shakeActions(); } else { closeSettings(); } } });

    const updateBanner = document.getElementById('update-banner');
    const updateBannerVersion = document.getElementById('update-banner-version');
    const updateBannerLink = document.getElementById('banner-update-link');
    const updateBannerDismiss = document.getElementById('banner-update-dismiss');

    if (updateBanner) {
        updateBannerDismiss?.addEventListener('click', () => { updateBanner.hidden = true; if (_cachedUpdateCheck?.latest_version) localStorage.setItem('updateDismissedVersion', _cachedUpdateCheck.latest_version); });
        updateBannerLink?.addEventListener('click', () => { openSettings('Updates'); updateBanner.hidden = true; });
        setTimeout(() => { _checkUpdate(); _scheduleUpdateCheck(); }, 1000);
    }

    function clearSkeletons() { resultsContainer.querySelectorAll('.result-card.skeleton').forEach(card => card.remove()); }

    function renderLoadingSkeletons(count = 4, append = false) {
        if (!append) resultsContainer.innerHTML = '';
        const skeletons = Array.from({ length: count }, () => `<article class="result-card skeleton"><div class="card-meta"><span class="skeleton-dot"></span><span class="skeleton-line skeleton-short"></span></div><span class="card-title skeleton-line skeleton-title"></span><p class="card-content skeleton-line skeleton-paragraph"></p></article>`).join('');
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

    form.addEventListener('submit', async (e) => {
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

    const slashHints = document.getElementById('slash-hints');
    queryInput.addEventListener('input', () => {
        const val = queryInput.value;
        if (val === '/') { slashHints.hidden = false; }
        else if (slashHints && !slashHints.hidden) { slashHints.hidden = true; }
    });
    queryInput.addEventListener('keydown', (e) => { if (e.key === 'Escape' && slashHints && !slashHints.hidden) { slashHints.hidden = true; } });
    if (slashHints) {
        slashHints.addEventListener('click', (e) => {
            const item = e.target.closest('.slash-hint-item');
            if (item) { queryInput.value = item.dataset.cmd + ' '; queryInput.focus(); slashHints.hidden = true; }
        });
    }

    document.getElementById('sidebar-library-nav')?.addEventListener('click', () => setWebMode(false));
    document.getElementById('sidebar-web-nav')?.addEventListener('click', () => setWebMode(true));

    observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad !== false) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });

    function ensureSentinelObserved() {
        if (sentinel && !sentinel.hidden) { observer.unobserve(sentinel); observer.observe(sentinel); }
    }
    observer.observe(sentinel);

    loadMoreButton?.addEventListener('click', () => { if (!loading && hasMore && currentQuery) doSearch(currentQuery, currentPage + 1); });

    scrollTopButton.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    function handleScrollTopVisibility() { scrollTopButton.hidden = window.scrollY <= window.innerHeight; }
    window.addEventListener('scroll', handleScrollTopVisibility, { passive: true });
    handleScrollTopVisibility();

    const sidebarProjectList = null;

    function loadProjects() {}

    const noteModal = document.getElementById('note-modal');
    const noteClose = document.getElementById('note-close');
    const noteCancel = document.getElementById('note-cancel');
    const noteSave = document.getElementById('note-save');
    const noteTitle = document.getElementById('note-title');
    const noteContent = document.getElementById('note-content');
    const noteStatus = document.getElementById('note-status');
    const newNoteBtn = document.getElementById('new-note-btn');

    function openNoteModal() { noteTitle.value = ''; noteContent.value = ''; noteStatus.hidden = true; noteModal.hidden = false; noteModal.inert = false; setTimeout(() => noteTitle.focus(), 120); }
    function closeNoteModal() { noteModal.hidden = true; noteModal.inert = true; }
    if (newNoteBtn) newNoteBtn.addEventListener('click', openNoteModal);
    noteClose?.addEventListener('click', closeNoteModal);
    noteCancel?.addEventListener('click', closeNoteModal);
    noteModal?.addEventListener('click', (e) => { if (e.target === noteModal) closeNoteModal(); });
    noteSave?.addEventListener('click', async () => {
        const title = noteTitle.value.trim();
        const content = noteContent.value.trim();
        if (!title || !content) { noteStatus.textContent = title ? 'Content is required' : 'Title is required'; noteStatus.className = 'note-status error'; noteStatus.hidden = false; return; }
        noteStatus.textContent = 'Saving...'; noteStatus.className = 'note-status'; noteStatus.hidden = false; noteSave.disabled = true;
        try {
            const resp = await fetch('/api/capture', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'manual', content, source: { url: '', title, site_name: 'Manual' }, project: document.getElementById('note-project').value || '', tags: [] }) });
            const data = await resp.json();
            if (data.success) { noteStatus.textContent = 'Saved ✓'; noteStatus.className = 'note-status success'; setTimeout(() => { closeNoteModal(); loadLibrary(); }, 600); }
            else { noteStatus.textContent = 'Save failed'; noteStatus.className = 'note-status error'; }
        } catch (err) { noteStatus.textContent = 'Server error'; noteStatus.className = 'note-status error'; }
        noteSave.disabled = false;
    });

    const confirmOverlay = document.getElementById('confirm-overlay');
    const confirmClose = document.getElementById('confirm-close');
    const confirmTitle = document.getElementById('confirm-title');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmCancel = document.getElementById('confirm-cancel');
    const confirmDelete = document.getElementById('confirm-delete');

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

    const editTagsAll = document.getElementById('edit-tags-all');
    const editTagsStatus = document.getElementById('edit-tags-status');

    function closeEditModal() {
        const em = document.getElementById('edit-modal');
        if (em) { em.hidden = true; em.inert = true; }
    }
    function openEditModal(item) {
        showToast('Edit is not available in this version', 'error', 3000);
    }
    function getEditTags() { return []; }
    function renderEditTagPicker(tags) {}
    function removeEditTagFromPicker(tag, tags) {}

    editClose?.addEventListener('click', closeEditModal);
    editCancel?.addEventListener('click', closeEditModal);
    editModal?.addEventListener('click', (e) => { if (e.target === editModal) closeEditModal(); });

    editTagsAdd?.addEventListener('click', () => {
        const tag = editTagsInput?.value?.trim();
        if (!tag) return;
        if (tag.length > 32) { editTagsStatus.textContent = 'Max 32 characters'; editTagsStatus.className = 'note-status error'; editTagsStatus.hidden = false; return; }
        const current = getEditTags();
        if (current.includes(tag)) { editTagsStatus.textContent = 'Tag already added'; editTagsStatus.className = 'note-status'; editTagsStatus.hidden = false; return; }
        current.push(tag);
        if (editTagsInput) editTagsInput.value = '';
        editTagsStatus.hidden = true;
        renderEditTagPicker(current);
    });
    editTagsInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); editTagsAdd?.click(); } });
    editTagsInput?.addEventListener('input', () => {
        const filter = editTagsInput.value.trim().toLowerCase();
        editTagsAll?.querySelectorAll('.edit-tag-option').forEach(btn => { btn.hidden = filter && !btn.textContent.toLowerCase().includes(filter); });
    });
    editSave?.addEventListener('click', async () => {
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
                loadProjects(); setTimeout(closeEditModal, 600); renderResults(false);
            } else { editStatus.textContent = 'Save failed'; editStatus.className = 'note-status error'; }
        } catch (err) { editStatus.textContent = 'Server error'; editStatus.className = 'note-status error'; }
        editSave.disabled = false;
    });

    const extBanner = document.getElementById('extension-banner');
    const bannerClose = document.getElementById('banner-close');
    const bannerInstallLink = document.getElementById('banner-install-link');
    const installModal = document.getElementById('install-modal');
    const installClose = document.getElementById('install-close');
    function checkExtensionInstalled() { if (localStorage.getItem('bannerDismissed') === 'true') return; const sentinel = document.querySelector('meta[name="nodecast-extension"]'); if (!sentinel || sentinel.content !== 'installed') extBanner.hidden = false; }
    bannerClose.addEventListener('click', () => { extBanner.hidden = true; localStorage.setItem('bannerDismissed', 'true'); });
    bannerInstallLink.addEventListener('click', () => { extBanner.hidden = true; installModal.hidden = false; installModal.inert = false; });
    installClose.addEventListener('click', () => { installModal.hidden = true; installModal.inert = true; });
    installModal.addEventListener('click', (e) => { if (e.target === installModal) { installModal.hidden = true; installModal.inert = true; } });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !installModal.hidden) { installModal.hidden = true; installModal.inert = true; } });
    setTimeout(checkExtensionInstalled, 300);

    const sidebarResizer = document.getElementById('sidebar-resizer');
    const workspaceSidebar = document.getElementById('workspace-sidebar');

    let sidebarWidth = Number(localStorage.getItem('nodecast.sidebarWidth') || 280);
    function applySidebarWidth() { document.documentElement.style.setProperty('--sidebar-width', `${sidebarWidth}px`); workspaceSidebar.style.width = `${sidebarWidth}px`; }
    applySidebarWidth();

    function startResize(startEvent) {
        const startX = startEvent.clientX;
        const startSidebar = sidebarWidth;
        const onMove = (e) => { sidebarWidth = Math.min(Math.max(220, startSidebar + (e.clientX - startX)), 360); applySidebarWidth(); };
        const onUp = () => { localStorage.setItem('nodecast.sidebarWidth', String(sidebarWidth)); document.body.classList.remove('resizing'); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
        document.body.classList.add('resizing');
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    sidebarResizer.addEventListener('mousedown', (e) => { e.preventDefault(); startResize(e); });

    renderSettings();
    loadLibrary();
    loadProjects();
    renderResults(false);
    updatePaginationControls();

    document.querySelectorAll('.sidebar-section-label').forEach(label => {
        const section = label.parentElement;
        const collapse = section.querySelector('.sidebar-collapse');
        if (!collapse) return;
        label.addEventListener('click', () => { label.classList.toggle('collapsed'); collapse.classList.toggle('collapsed'); });
    });

    let tagManageMode = 'rename';
    let tagManageTagData = [];

    const tagManageOverlay = document.getElementById('tag-manage-overlay');
    const tagManageClose = document.getElementById('tag-manage-close');
    const tagManageSearch = document.getElementById('tag-manage-search');
    const tagManageNew = document.getElementById('tag-manage-new');
    const tagManageAddBtn = document.getElementById('tag-manage-add-btn');
    const tagManageList = document.getElementById('tag-manage-list');
    const tagManageStatus = document.getElementById('tag-manage-status');
    const manageTagsBtn = document.getElementById('manage-tags-btn');
    const renameModeBtn = document.getElementById('tag-manage-mode-rename');
    const deleteModeBtn = document.getElementById('tag-manage-mode-delete');

    if (renameModeBtn) renameModeBtn.addEventListener('click', () => switchTagManageMode('rename'));
    if (deleteModeBtn) deleteModeBtn.addEventListener('click', () => switchTagManageMode('delete'));

    if (manageTagsBtn) {
        manageTagsBtn.addEventListener('click', () => { tagManageOverlay.hidden = false; tagManageOverlay.removeAttribute('aria-hidden'); showTagManageStatus('', ''); if (tagManageSearch) tagManageSearch.value = ''; switchTagManageMode('rename'); });
    }
    if (tagManageClose) { tagManageClose.addEventListener('click', () => { tagManageOverlay.hidden = true; tagManageOverlay.setAttribute('aria-hidden', 'true'); }); }
    if (tagManageOverlay) { tagManageOverlay.addEventListener('click', (e) => { if (e.target === tagManageOverlay) { tagManageOverlay.hidden = true; tagManageOverlay.setAttribute('aria-hidden', 'true'); } }); }
    if (tagManageSearch) { tagManageSearch.addEventListener('input', () => loadTagManageList()); }
    if (tagManageAddBtn && tagManageNew) {
        tagManageAddBtn.addEventListener('click', () => {
            const name = tagManageNew.value.trim();
            if (!name) { showTagManageStatus('Tag name cannot be empty.', 'error'); return; }
            if (name.length > 32) { showTagManageStatus('Max 32 characters.', 'error'); return; }
            fetch('/api/tags/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag: name }) })
                .then(r => r.json()).then(res => {
                    if (res.success || res.status === 'ok' || res.message) { showTagManageStatus('Tag created.', 'success'); tagManageNew.value = ''; loadTagManageList(); loadProjects(); renderResults(false); }
                    else { showTagManageStatus(res.error || 'Failed.', 'error'); }
                }).catch(() => showTagManageStatus('Network error.', 'error'));
        });
        tagManageNew.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); tagManageAddBtn.click(); } });
    }
});