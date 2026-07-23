window.addEventListener('DOMContentLoaded', async () => {
    // ─── Auth check ───────────────────────────────────────────────
    let currentUser = null;
    try {
        const meRes = await fetch('/auth/me');
        if (meRes.ok) {
            currentUser = await meRes.json();
            const uname = document.getElementById('sidebar-username');
            if (uname) uname.textContent = currentUser.username;
            subtitle = document.getElementById('sidebar-brand-subtitle');
            if (subtitle) subtitle.textContent = currentUser.username;
        } else {
            // Not logged in — redirect to login
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

    // Brand click opens Account settings
    document.querySelector('.sidebar-brand')?.addEventListener('click', (e) => {
        if (e.target.closest('button')) return; // ignore button clicks inside brand
        openAccountSettings();
    });

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

    let webMode = false;
    let currentQuery = '';
    let currentPage = 1;
    let loading = false;
    let hasMore = false;
    let allResults = [];
    let activeProject = '';
    let activeTags = [];
    let previewItem = null;
    let pinnedPreviewItem = null;
    let previewHoverTimer = null;

    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const settingsList = document.getElementById('settings-list');
    const settingsSave = document.getElementById('settings-save');
    const settingsRevert = document.getElementById('settings-revert');
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

    let activeSettingsCategory = localStorage.getItem('activeSettingsCategory') || 'Appearance';
    let accountData = null;
    let _dirty = false;
    let _tabSnapshot = {};
    let _savedInterval = 60;
    const settingsSchema = [
        {
            category: 'Account',
            description: 'Your account settings.',
            items: []  // Custom rendering
        },
        {
            category: 'AI',
            description: 'Connect AI providers and assign models to features like auto-tagging, summarization, and entity extraction.',
            items: []  // Custom rendering
        },
        {
            category: 'Updates',
            description: 'Check for new versions and manage auto-updates.',
            items: [
                { key: 'autoUpdate', label: 'Auto update when available', type: 'checkbox', default: false },
            ]
        },
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
        if (category.category === 'Account') {
            renderAccountSettings();
        } else if (category.category === 'AI') {
            renderAISettings();
        } else if (category.category === 'Updates') {
            renderUpdatesSettings();
        } else {
            settingsList.innerHTML = category.items.map(item => createField({ ...item, category: category.category })).join('');
        }
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
        _snapshotTab();
        _clearDirty();
    }

    function _snapshotTab() {
        _tabSnapshot = {};
        const category = settingsSchema.find(cat => cat.category === activeSettingsCategory);
        if (!category || category.category === 'Account' || category.category === 'AI' || category.category === 'Updates') return;
        category.items.forEach(item => {
            _tabSnapshot[item.key] = getValue(item);
        });
    }

    function _markDirty() {
        if (_dirty) return;
        _dirty = true;
        document.getElementById('settings-save').disabled = false;
        document.getElementById('settings-revert').disabled = false;
    }

    function _clearDirty() {
        _dirty = false;
        const saveBtn = document.getElementById('settings-save');
        const revertBtn = document.getElementById('settings-revert');
        if (saveBtn) saveBtn.disabled = true;
        if (revertBtn) revertBtn.disabled = true;
    }

    function _shakeActions() {
        document.querySelectorAll('#settings-actions-bar button').forEach(btn => {
            btn.classList.remove('shake');
            void btn.offsetWidth; // reflow
            btn.classList.add('shake');
            setTimeout(() => btn.classList.remove('shake'), 500);
        });
    }

    async function renderAccountSettings() {
        // Fetch fresh account data
        let user = null, users = null, settings = null;
        try {
            const r1 = await fetch('/auth/me');
            user = r1.ok ? await r1.json() : null;
            const r2 = await fetch('/auth/settings');
            settings = r2.ok ? await r2.json() : null;
        } catch {}
        // Try to get users list
        try {
            const r3 = await fetch('/auth/users');
            users = r3.ok ? (await r3.json()).users : null;
        } catch {}

        const isAdmin = user?.is_admin;
        let html = '<div class="settings-field-group">';

        // Username
        html += `<div class="settings-field"><span>Username</span><span style="color:var(--text-dim);font-size:0.85rem">${user?.username || ''}</span></div>`;

        // Copy API Token
        html += `<div class="settings-field"><span>API Token</span><button id="acc-copy-token" class="modal-btn modal-btn-primary" type="button" style="padding:0.35rem 0.75rem;font-size:0.78rem">Copy API Token</button></div>`;

        // Change username
        html += `<div class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.4rem">
          <span>Change username</span>
          <div style="display:flex;gap:0.4rem">
            <input id="acc-new-username" type="text" placeholder="New username" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" />
            <input id="acc-username-pw" type="password" placeholder="Password" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" />
            <button id="acc-change-username" class="modal-btn modal-btn-primary" type="button" style="padding:0.35rem 0.6rem;font-size:0.78rem">Save</button>
          </div>
          <span id="acc-username-status" class="note-status" hidden></span>
        </div>`;

        // Change password
        html += `<div class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.4rem">
          <span>Change password</span>
          <div style="display:flex;gap:0.4rem">
            <input id="acc-cur-pw" type="password" placeholder="Current password" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" />
            <input id="acc-new-pw" type="password" placeholder="New password" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" />
            <button id="acc-change-pw" class="modal-btn modal-btn-primary" type="button" style="padding:0.35rem 0.6rem;font-size:0.78rem">Save</button>
          </div>
          <span id="acc-pw-status" class="note-status" hidden></span>
        </div>`;

        // Admin-only: registration toggle
        if (isAdmin) {
            const openReg = settings?.open_registration !== false;
            html += `<div class="settings-field toggle-field">
              <span>Open registration (anyone can sign up)</span>
              <input type="checkbox" id="acc-open-reg" ${openReg ? 'checked' : ''} />
            </div>`;
        }

        html += '</div>';

        // Admin-only: users list
        if (isAdmin && users) {
            html += `<div class="settings-section-header" style="margin-top:1rem"><h3>Users</h3></div>`;
            html += `<div class="settings-list" style="gap:0.3rem">`;
            for (const u of users) {
                const isYou = u.user_id === user?.user_id;
                html += `<div class="settings-field" style="justify-content:space-between">
                  <span>${u.username}${u.is_admin ? ' <span style="color:var(--accent);font-size:0.75rem">(admin)</span>' : ''}${isYou ? ' <span style="color:var(--text-dim);font-size:0.75rem">(you)</span>' : ''}</span>
                  ${!isYou ? `<div style="display:flex;gap:0.3rem">
                    <button class="acc-admin-action modal-btn modal-btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem" data-uid="${u.user_id}" data-uname="${u.username}" data-action="clear_data">Clear data</button>
                    <button class="acc-admin-action modal-btn" style="padding:0.25rem 0.5rem;font-size:0.75rem;background:var(--danger,#f87171);color:#fff;border:none" data-uid="${u.user_id}" data-uname="${u.username}" data-action="delete">Delete</button>
                  </div>` : ''}
                </div>`;
            }
            html += `</div>`;
            // Admin password confirmation
            html += `<div class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.4rem;margin-top:0.5rem">
              <span>Enter your admin password to confirm actions:</span>
              <div style="display:flex;gap:0.4rem">
                <input id="acc-admin-pw" type="password" placeholder="Admin password" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" />
                <span id="acc-admin-status" class="note-status" style="font-size:0.78rem;color:var(--text-dim)" hidden></span>
              </div>
            </div>`;
        }

        settingsList.innerHTML = html;

        // Bind event handlers
        document.getElementById('acc-copy-token')?.addEventListener('click', async () => {
            try {
                const r = await fetch('/auth/token');
                const d = await r.json();
                await navigator.clipboard.writeText(d.token);
                document.getElementById('acc-copy-token').textContent = 'Copied!';
                setTimeout(() => document.getElementById('acc-copy-token').textContent = 'Copy API Token', 2000);
            } catch {}
        });

        document.getElementById('acc-change-username')?.addEventListener('click', async () => {
            const newUsername = document.getElementById('acc-new-username').value.trim();
            const password = document.getElementById('acc-username-pw').value;
            const status = document.getElementById('acc-username-status');
            status.hidden = false;
            try {
                const r = await fetch('/auth/change-username', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({password, new_username: newUsername}),
                });
                const d = await r.json();
                if (d.success) {
                    status.textContent = 'Username updated! Relogin...';
                    status.style.color = 'var(--accent)';
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    status.textContent = d.detail || 'Failed';
                    status.style.color = '#f87171';
                }
            } catch { status.textContent = 'Error'; status.style.color = '#f87171'; }
        });

        document.getElementById('acc-change-pw')?.addEventListener('click', async () => {
            const current = document.getElementById('acc-cur-pw').value;
            const newpw = document.getElementById('acc-new-pw').value;
            const status = document.getElementById('acc-pw-status');
            status.hidden = false;
            try {
                const r = await fetch('/auth/change-password', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({current_password: current, new_password: newpw}),
                });
                const d = await r.json();
                if (d.success) {
                    status.textContent = 'Password updated!';
                    status.style.color = 'var(--accent)';
                    document.getElementById('acc-cur-pw').value = '';
                    document.getElementById('acc-new-pw').value = '';
                } else {
                    status.textContent = d.detail || 'Failed';
                    status.style.color = '#f87171';
                }
            } catch { status.textContent = 'Error'; status.style.color = '#f87171'; }
        });

        // Admin: open registration toggle
        document.getElementById('acc-open-reg')?.addEventListener('change', async (e) => {
            const open = e.target.checked;
            await fetch('/auth/settings/registration?open_registration=' + open, { method: 'POST' });
        });

        // Admin: user actions (delete / clear data)
        document.querySelectorAll('.acc-admin-action').forEach(btn => {
            btn.addEventListener('click', async () => {
                const targetUserId = btn.dataset.uid;
                const targetUsername = btn.dataset.uname;
                const action = btn.dataset.action;
                const adminPw = document.getElementById('acc-admin-pw')?.value;
                if (!adminPw) {
                    document.getElementById('acc-admin-status').textContent = 'Enter admin password first';
                    document.getElementById('acc-admin-status').hidden = false;
                    return;
                }
                if (action === 'delete' && !confirm('Delete user "' + targetUsername + '" and all their data?')) return;
                const status = document.getElementById('acc-admin-status');
                status.hidden = false;
                try {
                    const r = await fetch('/auth/admin/user', {
                        method: 'POST',
                        headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({target_user_id: targetUserId, admin_password: adminPw, action}),
                    });
                    const d = await r.json();
                    if (d.success) {
                        status.textContent = d.message;
                        status.style.color = 'var(--accent)';
                        document.getElementById('acc-admin-pw').value = '';
                        setTimeout(() => renderAccountSettings(), 1500);
                    } else {
                        status.textContent = d.detail || 'Failed';
                        status.style.color = '#f87171';
                    }
                } catch { status.textContent = 'Error'; status.style.color = '#f87171'; }
            });
        });
    }

    // ─── AI Settings ─────────────────────────────────────────────────

    let aiProviders = [];
    let aiAssignments = [];

    async function renderAISettings() {
        const cat = settingsSchema.find(c => c.category === 'AI');
        const desc = cat ? cat.description : '';
        settingsCategoryDescription.textContent = desc;

        // Fetch providers and assignments
        try {
            const rp = await fetch('/api/ai/providers');
            aiProviders = rp.ok ? (await rp.json()).providers : [];
        } catch { aiProviders = []; }
        try {
            const ra = await fetch('/api/ai/assignments');
            aiAssignments = ra.ok ? (await ra.json()).assignments : [];
        } catch { aiAssignments = []; }

        // Fetch models for ALL providers in parallel (shows online status + pre-populates dropdowns)
        const providerModels = new Map();
        await Promise.all(aiProviders.map(async (p) => {
            try {
                const r = await fetch(`/api/ai/providers/${p.id}/models`);
                if (r.ok) {
                    const data = await r.json();
                    providerModels.set(p.id, { models: data.models || [], online: true });
                } else {
                    providerModels.set(p.id, { models: [], online: false });
                }
            } catch {
                providerModels.set(p.id, { models: [], online: false });
            }
        }));

        let html = '<div class="settings-field-group">';

        // Fetch saved interval from server
        try {
            const r = await fetch('/api/ai/auto-process-settings');
            if (r.ok) {
                const data = await r.json();
                _savedInterval = data.interval_minutes || 60;
            }
        } catch {}

        // ─── Providers section ────────────────────────────────────
        html += '<div class="settings-section-header"><h3>AI Providers</h3></div>';

        // Configured providers list
        html += '<div class="settings-list" style="gap:0.3rem">';
        if (aiProviders.length === 0) {
            html += '<div style="color:var(--text-dim);font-size:0.85rem;padding:0.3rem 0">No AI providers configured.</div>';
        } else {
            for (const p of aiProviders) {
                const info = providerModels.get(p.id);
                const online = info ? info.online : false;
                const hasAssignment = aiAssignments.some(a => a.provider_id === p.id);
                const providerKey = p.provider_key || '';
                const iconPath = `/static/assets/AI_providers/${providerKey}.svg`;
                const iconStyle = providerKey === 'lmstudio' ? ' style="filter:invert(1)"' : '';
                const iconHtml = providerKey
                    ? `<img src="${iconPath}" width="18" height="18"${iconStyle} alt="" style="vertical-align:middle;margin-right:0.3rem" />`
                    : '';
                const statusBadge = online
                    ? '<span class="ai-badge" style="background:#22c55e;color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.4rem">● online</span>'
                    : '<span class="ai-badge" style="background:#f87171;color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.4rem">● offline</span>';
                const modelCount = info && info.models ? `· ${info.models.length} models` : '';
                html += `<div class="settings-field" style="justify-content:space-between">
                  <div>
                    ${iconHtml}<span style="font-weight:600">${escapeHtml(p.name)}</span>
                    ${statusBadge}
                    <span style="color:var(--text-dim);font-size:0.78rem;margin-left:0.3rem">${escapeHtml(p.base_url)}</span>
                    ${modelCount ? `<span style="color:var(--text-dim);font-size:0.75rem;margin-left:0.3rem">${modelCount}</span>` : ''}
                    ${hasAssignment ? '<span class="ai-badge" style="background:var(--accent);color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.3rem">assigned</span>' : ''}
                  </div>
                  <div style="display:flex;gap:0.3rem">
                    <button class="ai-edit-provider modal-btn modal-btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-url="${escapeHtml(p.base_url)}" data-key="${escapeHtml(providerKey)}">Edit</button>
                    <button class="ai-delete-provider modal-btn" style="padding:0.25rem 0.5rem;font-size:0.75rem;background:var(--danger,#f87171);color:#fff;border:none" data-id="${p.id}" data-name="${escapeHtml(p.name)}">Delete</button>
                  </div>
                </div>`;
            }
        }
        html += '</div>';

        // Add provider button
        html += `<button id="ai-add-provider-btn" class="modal-btn modal-btn-primary" type="button" style="margin-top:0.4rem">+ Add Provider</button>`;
        // Also show edit for the first provider inline hint
        html += '<div style="font-size:0.75rem;color:var(--text-dim);margin-top:0.2rem">Edits open a dialog to change URL, API key, or test connection.</div>';

        // ─── Feature assignments section ──────────────────────────
        html += '<div class="settings-section-header" style="margin-top:1.2rem"><h3>Feature Assignments</h3></div>';
        html += '<div class="settings-list" style="gap:0.6rem">';

        // Fetch available features
        let features = [];
        try {
            const rf = await fetch('/api/ai/features');
            features = rf.ok ? (await rf.json()).features : [];
        } catch {}

        for (const feat of features) {
            const assignment = aiAssignments.find(a => a.feature === feat.id);
            const assignedProvider = assignment ? aiProviders.find(p => p.id === assignment.provider_id) : null;

            // Build model options — pre-populate from fetched models for the assigned provider
            let modelOptions = '<option value="">— Select model —</option>';
            if (assignment) {
                const info = providerModels.get(assignment.provider_id);
                if (info && info.models && info.models.length > 0) {
                    modelOptions = info.models.map(m =>
                        `<option value="${escapeHtml(m.id)}" ${m.id === assignment.model ? 'selected' : ''}>${escapeHtml(m.id)}</option>`
                    ).join('');
                } else {
                    modelOptions = `<option value="${escapeHtml(assignment.model)}" selected>${escapeHtml(assignment.model)}</option>`;
                }
            }

            html += `<div class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.3rem">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                  <span style="font-weight:600">${escapeHtml(feat.name)}</span>
                  <span style="color:var(--text-dim);font-size:0.78rem;margin-left:0.4rem">${escapeHtml(feat.description)}</span>
                </div>
              </div>
              <div style="display:flex;gap:0.4rem;align-items:center" data-feature="${feat.id}">
                <select class="ai-assign-provider" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem">
                  <option value="">— Select provider —</option>
                  ${aiProviders.map(p => `<option value="${p.id}" ${assignment && assignment.provider_id === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                </select>
                <select class="ai-assign-model" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" ${assignment ? '' : 'disabled'}>
                  ${modelOptions}
                </select>
              </div>
              <span id="ai-assign-status-${feat.id}" class="note-status" hidden></span>
            </div>`;
        }
        html += '</div>';

        // ─── AI Processing section ───────────────────────────────
        html += '<div class="settings-section-header" style="margin-top:1.2rem"><h3>AI Processing</h3></div>';
        html += '<div class="settings-list" style="gap:0.4rem">';
        html += `<button id="ai-process-unprocessed" class="modal-btn modal-btn-primary" type="button" style="padding:0.4rem 0.75rem;font-size:0.82rem">Process unprocessed captures</button>`;
        html += `<button id="ai-regenerate-all" class="modal-btn" type="button" style="padding:0.4rem 0.75rem;font-size:0.82rem;background:var(--danger,#f87171);color:#fff;border:none">Regenerate all data (⚠ destructive)</button>`;
        html += '<span id="ai-bulk-status" class="note-status" style="margin-top:0.4rem" hidden></span>';

        // Auto-process slider — saves to server
        const batchInterval = getSavedInterval();
        html += `<label class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.3rem;margin-top:0.5rem">
          <div style="display:flex;justify-content:space-between;font-size:0.8rem">
            <span>Auto-process on server every</span>
            <span id="ai-batch-interval-label">${_formatInterval(batchInterval)}</span>
          </div>
          <input type="range" id="ai-batch-interval" min="5" max="120" step="5" value="${batchInterval}" style="width:100%;accent-color:var(--accent);" />
          <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-dim)">
            <span>5 min</span>
            <span>2 hours</span>
          </div>
        </label>`;
        html += '</div>';

        html += '</div>';
        settingsList.innerHTML = html;
        attachAIHandlers();
    }

    function attachAIHandlers() {
        // Add Provider button — opens provider type selector
        document.getElementById('ai-add-provider-btn')?.addEventListener('click', () => {
            openProviderSelector();
        });

        // Edit provider
        document.querySelectorAll('.ai-edit-provider').forEach(btn => {
            btn.addEventListener('click', () => openAIProviderModal({
                id: btn.dataset.id,
                name: btn.dataset.name,
                base_url: btn.dataset.url,
                provider_key: btn.dataset.key,
            }));
        });

        // Delete provider
        document.querySelectorAll('.ai-delete-provider').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`Delete provider "${btn.dataset.name}"? This will also remove any feature assignments using it.`)) return;
                try {
                    const r = await fetch(`/api/ai/providers/${btn.dataset.id}`, { method: 'DELETE' });
                    if (r.ok) renderAISettings();
                } catch {}
            });
        });

        // Provider dropdown change → fetch models + auto-select first
        document.querySelectorAll('.ai-assign-provider').forEach(sel => {
            sel.addEventListener('change', async () => {
                const container = sel.closest('[data-feature]');
                const modelSel = container.querySelector('.ai-assign-model');
                const providerId = sel.value;
                if (!providerId) {
                    modelSel.innerHTML = '<option value="">— Select model —</option>';
                    modelSel.disabled = true;
                    _markAIDirty();
                    return;
                }
                modelSel.innerHTML = '<option value="">Loading models...</option>';
                modelSel.disabled = false;
                try {
                    const r = await fetch(`/api/ai/providers/${providerId}/models`);
                    const data = r.ok ? await r.json() : { models: [] };
                    if (data.models && data.models.length > 0) {
                        modelSel.innerHTML = data.models.map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.id)}</option>`).join('');
                    } else {
                        modelSel.innerHTML = '<option value="">No models found</option>';
                    }
                } catch {
                    modelSel.innerHTML = '<option value="">Failed to load models</option>';
                }
                _markAIDirty();
            });
        });

        // Model change → mark dirty
        document.querySelectorAll('.ai-assign-model').forEach(sel => {
            sel.addEventListener('change', _markAIDirty);
        });

        // Process unprocessed captures
        document.getElementById('ai-process-unprocessed')?.addEventListener('click', async function () {
            this.disabled = true;
            this.textContent = '⏳ Starting...';
            const status = document.getElementById('ai-bulk-status');
            status.hidden = true;
            try {
                const r = await fetch('/api/ai/process-unprocessed', { method: 'POST' });
                const d = await r.json();
                if (d.status === 'started') {
                    this.textContent = '⏳ Processing...';
                    status.textContent = 'Processing in background — see progress bar above';
                    status.style.color = 'var(--text-dim)';
                    status.hidden = false;
                    pollBatchProgress((finalStatus) => {
                        this.textContent = 'Process unprocessed captures';
                        this.disabled = false;
                        status.textContent = `Done: ${finalStatus.processed || 0} processed, ${finalStatus.errors || 0} errors (of ${finalStatus.total || 0} total)`;
                        status.style.color = (finalStatus.errors || 0) > 0 ? '#f87171' : '#22c55e';
                    });
                } else if (d.status === 'already_running') {
                    this.textContent = 'Process unprocessed captures';
                    this.disabled = false;
                    status.textContent = d.message || 'Already running';
                    status.style.color = '#fbbf24';
                    status.hidden = false;
                } else {
                    this.textContent = 'Process unprocessed captures';
                    this.disabled = false;
                    status.textContent = d.message || 'All captures already processed.';
                    status.style.color = '#22c55e';
                    status.hidden = false;
                }
            } catch {
                status.textContent = 'Error running processing';
                status.style.color = '#f87171';
                status.hidden = false;
                this.textContent = 'Process unprocessed captures';
                this.disabled = false;
            }
        });

        // Regenerate all data (destructive)
        document.getElementById('ai-regenerate-all')?.addEventListener('click', async function () {
            const confirmCode = await showConfirmDialog(
                'This will delete ALL existing AI data (tags, summaries, entities) and regenerate everything. This cannot be undone.',
                { prompt: 'Type "REGENERATE" to confirm:', defaultValue: '' }
            );
            if (confirmCode !== 'REGENERATE') return;
            this.disabled = true;
            this.textContent = '⏳ Regenerating...';
            const status = document.getElementById('ai-bulk-status');
            status.hidden = true;
            try {
                const r = await fetch('/api/ai/regenerate-all', { method: 'POST' });
                const d = await r.json();
                if (d.status === 'started') {
                    status.textContent = 'Regenerating in background — see progress bar above';
                    status.style.color = 'var(--text-dim)';
                    status.hidden = false;
                    pollBatchProgress((finalStatus) => {
                        this.textContent = 'Regenerate all data (⚠ destructive)';
                        this.disabled = false;
                        status.textContent = `Done: ${finalStatus.processed || 0} processed, ${finalStatus.errors || 0} errors (of ${finalStatus.total || 0} total)`;
                        status.style.color = (finalStatus.errors || 0) > 0 ? '#f87171' : '#22c55e';
                    });
                } else if (d.status === 'already_running') {
                    this.textContent = 'Regenerate all data (⚠ destructive)';
                    this.disabled = false;
                    status.textContent = d.message || 'Already running';
                    status.style.color = '#fbbf24';
                    status.hidden = false;
                } else {
                    this.textContent = 'Regenerate all data (⚠ destructive)';
                    this.disabled = false;
                    status.textContent = d.message || 'Done';
                    status.style.color = '#22c55e';
                    status.hidden = false;
                }
            } catch {
                status.textContent = 'Error running regeneration';
                status.style.color = '#f87171';
                status.hidden = false;
                this.textContent = 'Regenerate all data (⚠ destructive)';
                this.disabled = false;
            }
        });

        // ─── Batch processing handlers ───────────────────────────
        // Save interval to server
        document.getElementById('ai-batch-interval')?.addEventListener('input', function () {
            const val = parseInt(this.value, 10);
            const label = document.getElementById('ai-batch-interval-label');
            if (label) label.textContent = _formatInterval(val);
            // Save to server
            fetch('/api/ai/auto-process-settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interval_minutes: val }),
            }).catch(() => {});
        });

        // Check if AI processing is already running (progress bar)
        checkRunningBatch();
    }

    // ─── Updates Settings ──────────────────────────────────────────────

    async function renderUpdatesSettings() {
        let html = '<div class="settings-field-group">';

        // Current version card
        html += '<div class="update-card">';
        html += '<div class="update-card-section">';
        html += '<span class="update-label">Current version</span>';
        html += `<span class="update-version-badge current">v${_cachedUpdateCheck?.current_version || '...'}</span>`;
        html += `<span class="update-build-date">build ${_cachedUpdateCheck?.build_date || '...'}</span>`;
        html += '</div></div>';

        // Check button
        html += '<div style="display:flex;gap:0.5rem;margin-top:0.75rem">';
        html += '<button id="update-check-btn" class="modal-btn modal-btn-primary" type="button">Check for updates</button>';
        html += '</div>';

        // Status area
        html += '<div id="update-status-area" style="margin-top:0.75rem"></div>';

        // Auto-update checkbox
        html += '<div class="settings-field toggle-field" style="margin-top:1rem">';
        html += '<span>Auto update when available</span>';
        html += `<label class="toggle"><input type="checkbox" data-key="autoUpdate" ${settingsState.autoUpdate ? 'checked' : ''} /><span class="toggle-slider"></span></label>`;
        html += '</div>';

        html += '<p style="color:var(--text-dim);font-size:0.78rem;margin-top:0.25rem">When enabled, you&rsquo;ll see a banner when a new version is available.</p>';

        html += '</div>';
        settingsList.innerHTML = html;

        // Wire toggle
        const toggle = settingsList.querySelector('[data-key="autoUpdate"]');
        if (toggle) {
            toggle.addEventListener('change', () => {
                settingsState.autoUpdate = toggle.checked;
                setValue('autoUpdate', toggle.checked);
                _markDirty();
            });
        }

        // Wire check button
        const checkBtn = document.getElementById('update-check-btn');
        if (checkBtn) {
            checkBtn.addEventListener('click', async () => {
                const area = document.getElementById('update-status-area');
                area.innerHTML = '<div class="update-spinner"></div><span style="color:var(--text-dim)">Checking...</span>';
                checkBtn.disabled = true;
                try {
                    const r = await fetch('/api/update/check');
                    const data = await r.json();
                    _cachedUpdateCheck = data;
                    if (data.error) {
                        area.innerHTML = `<span style="color:#f87171">Error: ${data.error}</span>`;
                    } else if (data.has_update) {
                        area.innerHTML = `
                            <div class="update-available-card">
                                <div class="update-available-header">
                                    <span class="update-version-badge latest">v${data.latest_version}</span>
                                    <span class="update-badge-available">Update available</span>
                                </div>
                                <p style="font-size:0.82rem;color:var(--text-dim);margin:0.5rem 0">
                                    Released ${new Date(data.published_at).toLocaleDateString()}
                                </p>
                                <div class="update-release-notes">${_escapeHtml(data.release_notes || '')}</div>
                                <div class="update-install-cmd">
                                    <p style="margin:0 0 0.35rem 0;font-size:0.82rem">Install from terminal:</p>
                                    <code id="update-install-cmd-display">curl -fsSL https://github.com/sarox-dev/Nodecast/releases/latest/download/install.sh | bash</code>
                                    <button id="update-copy-cmd" class="modal-btn" type="button" style="padding:0.25rem 0.5rem;font-size:0.75rem">Copy</button>
                                </div>
                            </div>`;
                        const copyBtn = document.getElementById('update-copy-cmd');
                        const cmdDisplay = document.getElementById('update-install-cmd-display');
                        if (copyBtn && cmdDisplay) {
                            copyBtn.addEventListener('click', () => {
                                navigator.clipboard.writeText(cmdDisplay.textContent);
                                copyBtn.textContent = 'Copied!';
                                setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
                            });
                        }
                    } else {
                        area.innerHTML = `<div class="update-up-to-date">
                            <span style="color:#22c55e;font-size:1.2rem">✓</span>
                            <span>You&rsquo;re up to date (v${data.current_version})</span>
                        </div>`;
                    }
                } catch (e) {
                    area.innerHTML = `<span style="color:#f87171">Error: ${e.message}</span>`;
                }
                checkBtn.disabled = false;
            });
        }

        // Auto-trigger check if we have cached data
        const area = document.getElementById('update-status-area');
        if (_cachedUpdateCheck && !_cachedUpdateCheck.error) {
            if (_cachedUpdateCheck.has_update) {
                area.innerHTML = `
                    <div class="update-available-card">
                        <div class="update-available-header">
                            <span class="update-version-badge latest">v${_cachedUpdateCheck.latest_version}</span>
                            <span class="update-badge-available">Update available</span>
                        </div>
                        <p style="font-size:0.82rem;color:var(--text-dim);margin:0.5rem 0">
                            Released ${new Date(_cachedUpdateCheck.published_at).toLocaleDateString()}
                        </p>
                        <div class="update-install-cmd">
                            <code>curl -fsSL https://github.com/sarox-dev/Nodecast/releases/latest/download/install.sh | bash</code>
                        </div>
                    </div>`;
            } else {
                area.innerHTML = `<div class="update-up-to-date">
                    <span style="color:#22c55e">✓</span>
                    <span>Up to date (v${_cachedUpdateCheck.current_version})</span>
                </div>`;
            }
        }
    }

    function _escapeHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function _markAIDirty() {
        _markDirty();
    }

    function getSavedInterval() {
        return _savedInterval;
    }

    function _formatInterval(minutes) {
        if (minutes < 60) return `${minutes}min`;
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return m > 0 ? `${h}h ${m}min` : `${h}h`;
    }

    let batchPollId = null;
    let batchPollCallback = null;

    function pollBatchProgress(callback) {
        if (batchPollId) return;  // already polling
        if (callback) batchPollCallback = callback;
        const bar = document.getElementById('ai-progress-bar');
        const fill = document.getElementById('ai-progress-fill');
        const text = document.getElementById('ai-progress-text');
        if (!bar || !fill || !text) return;

        function poll() {
            fetch('/api/ai/batch-status')
                .then(r => r.json())
                .then(status => {
                    if (status.running) {
                        bar.hidden = false;
                        const total = status.total || 1;
                        const done = (status.processed || 0) + (status.errors || 0) + (status.skipped || 0);
                        const pct = Math.round((done / total) * 100);
                        fill.style.width = Math.min(pct, 100) + '%';
                        const op = status.operation ? status.operation.replace(/_/g, ' ') : 'AI';
                        text.textContent = `${op}: ${done}/${total} (${status.current || 'processing...'})`;
                        batchPollId = setTimeout(poll, 2000);
                    } else {
                        // Done
                        bar.hidden = true;
                        fill.style.width = '0%';
                        batchPollId = null;
                        if (batchPollCallback) {
                            batchPollCallback(status);
                            batchPollCallback = null;
                        }
                        updatePendingCount();
                    }
                })
                .catch(() => {
                    batchPollId = setTimeout(poll, 5000);
                });
        }
        poll();
    }

    async function checkRunningBatch() {
        if (batchPollId) return;  // already polling
        try {
            const r = await fetch('/api/ai/batch-status');
            const status = await r.json();
            if (status.running) {
                pollBatchProgress();
            } else {
                // No batch running — trigger processing if anything is unprocessed
                // (silent — only starts if there's work to do)
                fetch('/api/ai/process-unprocessed', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.status === 'started') {
                            pollBatchProgress();
                        }
                    })
                    .catch(() => {});
            }
        } catch {}
    }

    function openProviderSelector() {
        // Fetch provider presets from backend
        fetch('/api/ai/provider-presets')
            .then(r => r.json())
            .then(data => {
                const presets = data.presets || [];
                // Group: local first, then cloud
                const localKeys = ['lmstudio', 'ollama', 'custom'];
                const local = presets.filter(p => localKeys.includes(p.key));
                const cloud = presets.filter(p => !localKeys.includes(p.key));

                const overlay = document.createElement('div');
                overlay.className = 'modal-overlay';
                overlay.style.display = 'flex';
                overlay.style.zIndex = '10000';
                overlay.innerHTML = `<div class="modal-panel" role="dialog" aria-modal="true" style="max-width:460px;max-height:80vh;display:flex;flex-direction:column">
                  <button class="modal-close ai-modal-close-btn" type="button" aria-label="Close">&times;</button>
                  <div class="modal-header"><h3 class="modal-title">Select Provider Type</h3></div>
                  <div class="note-form-body" style="gap:0.3rem;overflow-y:auto;flex:1">
                    <div style="font-size:0.75rem;color:var(--text-dim);font-weight:600;margin-top:0.2rem">LOCAL</div>
                    ${local.map(p => _providerPresetBtn(p)).join('')}
                    <div style="font-size:0.75rem;color:var(--text-dim);font-weight:600;margin-top:0.5rem">CLOUD</div>
                    ${cloud.map(p => _providerPresetBtn(p)).join('')}
                  </div>
                  <div class="modal-actions" style="border-top:1px solid var(--border);padding-top:0.5rem;margin-top:0.3rem">
                    <button class="modal-btn modal-btn-secondary ai-modal-close-btn" type="button">Cancel</button>
                  </div>
                </div>`;
                document.body.appendChild(overlay);

                const close = () => { overlay.remove(); };
                overlay.querySelectorAll('.ai-modal-close-btn').forEach(b => b.addEventListener('click', close));
                overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

                overlay.querySelectorAll('.ai-preset-select').forEach(btn => {
                    btn.addEventListener('click', () => {
                        overlay.remove();
                        openAIProviderModal(null, {
                            key: btn.dataset.key,
                            name: btn.dataset.name,
                            url: btn.dataset.url,
                            requiresApiKey: btn.dataset.apikey === 'true',
                        });
                    });
                });
            })
            .catch(() => {
                // Fallback: open modal with empty form
                openAIProviderModal(null, null);
            });
    }

    function _providerPresetBtn(p) {
        const iconPath = `/static/assets/AI_providers/${p.key}.svg`;
        const iconStyle = p.key === 'lmstudio' ? ' style="filter:invert(1)"' : '';
        const desc = p.default_base_url || 'Custom base URL';
        return `<button class="ai-preset-select" type="button" style="display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.6rem;border:1px solid var(--border);border-radius:8px;background:var(--bg,#0d1117);color:var(--text);cursor:pointer;transition:background 0.15s;text-align:left;width:100%" data-key="${p.key}" data-url="${p.default_base_url}" data-apikey="${p.requires_api_key}" data-name="${p.name}"
          onmouseover="this.style.background='var(--surface,#161b22)'" onmouseout="this.style.background='var(--bg,#0d1117)'">
          <img src="${iconPath}" width="28" height="28"${iconStyle} alt="" style="flex-shrink:0" />
          <div style="flex:1">
            <div style="font-weight:600;font-size:0.85rem">${p.name}</div>
            <div style="font-size:0.72rem;color:var(--text-dim)">${desc}</div>
          </div>
        </button>`;
    }

    function openAIProviderModal(existing, preset) {
        const isEdit = !!existing;
        const providerKey = isEdit ? (existing.provider_key || '') : (preset ? preset.key : '');
        const displayName = isEdit ? existing.name : (preset ? preset.name : '');
        const baseUrl = isEdit ? existing.base_url : (preset ? preset.url : '');
        const requiresApiKey = isEdit ? true : (preset ? preset.requiresApiKey : true);
        const iconPath = providerKey ? `/static/assets/AI_providers/${providerKey}.svg` : '';
        const iconStyle = providerKey === 'lmstudio' ? ' style="filter:invert(1)"' : '';
        const iconHtml = iconPath ? `<img src="${iconPath}" width="22" height="22"${iconStyle} alt="" style="vertical-align:middle;margin-right:0.4rem" />` : '';

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.display = 'flex';
        overlay.style.zIndex = '10000';
        overlay.innerHTML = `<div class="modal-panel" role="dialog" aria-modal="true" style="max-width:480px">
          <button class="modal-close ai-modal-close-btn" type="button" aria-label="Close">&times;</button>
          <div class="modal-header"><h3 class="modal-title">${iconHtml}${isEdit ? 'Edit' : 'Add'} ${escapeHtml(displayName)}</h3></div>
          <div class="note-form-body" style="gap:0.6rem">
            <div class="note-field">
              <label>Provider Name <span class="required">*</span></label>
              <input id="ai-provider-name" type="text" value="${escapeHtml(displayName)}" placeholder="e.g. My OpenAI" autocomplete="off" />
            </div>
            <div class="note-field">
              <label>Base URL <span class="required">*</span></label>
              <input id="ai-provider-url" type="text" value="${escapeHtml(baseUrl)}" placeholder="https://api.openai.com/v1" autocomplete="off" />
            </div>
            <div class="note-field" id="ai-key-field" ${requiresApiKey ? '' : 'style="display:none"'}>
              <label>API Key <span class="required">*</span></label>
              <input id="ai-provider-key" type="password" placeholder="sk-..." autocomplete="off" />
              <div style="font-size:0.7rem;color:var(--text-dim);margin-top:0.2rem">Required for ${escapeHtml(displayName)}</div>
            </div>
            <div id="ai-provider-status" class="note-status" hidden></div>
            <div style="display:flex;justify-content:center">
              <button id="ai-test-connection-btn" class="modal-btn" type="button" style="padding:0.4rem 1rem;font-size:0.78rem;background:var(--surface,#161b22);color:var(--text);border:1px solid var(--border);border-radius:6px">Test Connection</button>
            </div>
          </div>
          <div class="modal-actions">
            <button class="modal-btn modal-btn-secondary ai-modal-close-btn" type="button">Cancel</button>
            <button id="ai-provider-save-btn" class="modal-btn modal-btn-primary" type="button">${isEdit ? 'Save' : 'Add'} Provider</button>
          </div>
        </div>`;
        document.body.appendChild(overlay);

        const close = () => { overlay.remove(); };
        overlay.querySelectorAll('.ai-modal-close-btn').forEach(b => b.addEventListener('click', close));
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

        // Test Connection
        document.getElementById('ai-test-connection-btn')?.addEventListener('click', async function () {
            const pUrl = document.getElementById('ai-provider-url').value.trim();
            const pKey = document.getElementById('ai-provider-key')?.value || '';
            const status = document.getElementById('ai-provider-status');
            if (!pUrl) {
                status.textContent = 'Enter a Base URL first.';
                status.style.color = '#f87171'; status.hidden = false;
                return;
            }
            this.textContent = '⏳ Testing...';
            this.disabled = true;
            status.hidden = true;
            try {
                const r = await fetch('/api/ai/providers/test-connection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: 'test', base_url: pUrl, api_key: pKey }),
                });
                const d = await r.json();
                status.textContent = d.status === 'ok' ? '✓ Connected' : (d.message || 'Failed');
                status.style.color = d.status === 'ok' ? '#22c55e' : '#f87171';
                status.hidden = false;
            } catch {
                status.textContent = 'Connection test failed.';
                status.style.color = '#f87171'; status.hidden = false;
            }
            this.textContent = 'Test Connection';
            this.disabled = false;
        });

        // Save
        const providerKeyForSave = providerKey;
        document.getElementById('ai-provider-save-btn')?.addEventListener('click', async () => {
            const pName = document.getElementById('ai-provider-name').value.trim();
            const pUrl = document.getElementById('ai-provider-url').value.trim();
            const pKey = document.getElementById('ai-provider-key')?.value || '';
            const status = document.getElementById('ai-provider-status');
            if (!pName || !pUrl) {
                status.textContent = 'Name and Base URL are required';
                status.style.color = '#f87171'; status.hidden = false;
                return;
            }
            status.hidden = true;
            try {
                const body = { name: pName, base_url: pUrl, api_key: pKey, provider_key: providerKeyForSave, api_style: preset ? preset.apiStyle || 'openai' : 'openai' };
                if (isEdit) {
                    const r = await fetch(`/api/ai/providers/${existing.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    if (r.ok) { close(); renderAISettings(); }
                    else { const d = await r.json(); status.textContent = d.detail || 'Failed'; status.style.color = '#f87171'; status.hidden = false; }
                } else {
                    const r = await fetch('/api/ai/providers', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    if (r.ok) { close(); renderAISettings(); }
                    else { const d = await r.json(); status.textContent = d.detail || 'Failed'; status.style.color = '#f87171'; status.hidden = false; }
                }
            } catch {
                status.textContent = 'Error saving provider';
                status.style.color = '#f87171'; status.hidden = false;
            }
        });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
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
    // Track input changes in settings (dirty state)
    settingsList?.addEventListener('change', (e) => {
        if (e.target.closest('[data-feature]')) return; // AI has its own dirty tracking
        if (e.target.matches('select, input')) _markDirty();
    });
    settingsList?.addEventListener('input', (e) => {
        if (e.target.matches('input[type="text"], input[type="number"]')) _markDirty();
    });
    settingsCategories?.addEventListener('click', (e) => {
        const button = e.target.closest('.settings-category-button');
        if (!button) return;
        if (_dirty) {
            _shakeActions();
            return;
        }
        activeSettingsCategory = button.dataset.category;
        localStorage.setItem('activeSettingsCategory', activeSettingsCategory);
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

    function openSettings(category) {
        if (category) activeSettingsCategory = category;
        renderCategoryNav(); renderSettings();
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
        settingsOverlay.hidden = false; settingsOverlay.inert = false;
    }
    function openAccountSettings() { openSettings('Account'); }
    function closeSettings() {
        if (_dirty) { _shakeActions(); return; }
        document.activeElement?.blur(); settingsOverlay.inert = true; settingsOverlay.hidden = true;
    }

    settingsButton.addEventListener('click', openSettings);
    settingsClose.addEventListener('click', closeSettings);
    settingsOverlay.addEventListener('click', (e) => { if (e.target === settingsOverlay) { if (_dirty) { _shakeActions(); } else { closeSettings(); } } });
    settingsSave.addEventListener('click', () => { _saveSettings(); applyTheme(); });
    settingsRevert.addEventListener('click', () => { renderSettings(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !settingsOverlay.hidden) { if (_dirty) { _shakeActions(); } else { closeSettings(); } } });

    function _saveSettings() {
        const category = settingsSchema.find(cat => cat.category === activeSettingsCategory);
        if (!category) return;

        if (category.category === 'AI') {
            // Save AI assignments
            const rows = document.querySelectorAll('[data-feature]');
            for (const row of rows) {
                const feature = row.dataset.feature;
                const providerSel = row.querySelector('.ai-assign-provider');
                const modelSel = row.querySelector('.ai-assign-model');
                const providerId = providerSel.value;
                const model = modelSel.value;
                const assignment = aiAssignments.find(a => a.feature === feature);
                try {
                    if (!providerId || !model) {
                        if (assignment) {
                            fetch(`/api/ai/assignments/${assignment.id}`, { method: 'DELETE' });
                        }
                    } else {
                        fetch('/api/ai/assignments', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ feature, provider_id: providerId, model }),
                        });
                    }
                } catch {}
            }
            _clearDirty();
            setTimeout(() => renderAISettings(), 800);
            return;
        }

        if (category.category === 'Account') {
            _clearDirty();
            return;
        }

        // Regular settings
        category.items.forEach(item => {
            const input = settingsList.querySelector(`[data-key="${item.key}"]`);
            if (!input) return;
            let value;
            if (item.type === 'checkbox') value = input.checked;
            else if (item.type === 'number') value = Number(input.value) || item.default;
            else value = input.value;
            setValue(item.key, value);
        });
        _clearDirty();
    }

    function initSettings() {
        settingsSchema.forEach(cat => cat.items.forEach(item => { settingsState[item.key] = getValue(item); }));
    }
    initSettings();
    // Check for running or pending AI processing on page load
    setTimeout(() => checkRunningBatch(), 500);

    function applyTheme() {
        const theme = settingsState.theme || 'dark';
        document.documentElement.dataset.theme = theme === 'light' ? 'light' : '';
    }
    applyTheme();

    // ─── Update notification ────────────────────────────────────
    const updateBanner = document.getElementById('update-banner');
    const updateBannerVersion = document.getElementById('update-banner-version');
    const updateBannerLink = document.getElementById('banner-update-link');
    const updateBannerDismiss = document.getElementById('banner-update-dismiss');
    let _cachedUpdateCheck = null;
    let _updateCheckTimer = null;

    async function _checkUpdate() {
        if (localStorage.getItem('updateBannerDismissed') === 'true') return;
        try {
            const [verR, checkR] = await Promise.all([
                fetch('/api/version'),
                fetch('/api/update/check'),
            ]);
            const ver = verR.ok ? await verR.json() : null;
            const check = checkR.ok ? await checkR.json() : null;
            _cachedUpdateCheck = {
                current_version: ver?.version || '?',
                build_date: ver?.build_date || '?',
                ...(check || {}),
            };
            if (check?.has_update && !updateBanner.hidden) {
                updateBannerVersion.textContent = check.latest_version;
                updateBanner.hidden = false;
            }
            if (check?.has_update && check.latest_version !== localStorage.getItem('updateDismissedVersion')) {
                updateBannerVersion.textContent = check.latest_version;
                updateBanner.hidden = false;
            }
        } catch {}
    }

    function _scheduleUpdateCheck() {
        if (_updateCheckTimer) clearInterval(_updateCheckTimer);
        _updateCheckTimer = setInterval(_checkUpdate, 6 * 60 * 60 * 1000);
    }

    if (updateBanner) {
        updateBannerDismiss?.addEventListener('click', () => {
            updateBanner.hidden = true;
            if (_cachedUpdateCheck?.latest_version) {
                localStorage.setItem('updateDismissedVersion', _cachedUpdateCheck.latest_version);
            }
        });
        updateBannerLink?.addEventListener('click', () => {
            openSettings('Updates');
            updateBanner.hidden = true;
        });
        setTimeout(() => { _checkUpdate(); _scheduleUpdateCheck(); }, 1000);
    }

    function getEngines() {
        const values = searchEngineFields.filter(field => settingsState[field.key] !== false).map(field => field.engine);
        return values.length ? values.join(',') : 'duckduckgo';
    }

    function getShowEngines() { return settingsState.showEngines !== false; }
    function getHoverPreviewEnabled() { return settingsState.hoverPreview !== false; }
    function getAnimationSpeedStr() { return settingsState.animationSpeed || 'fast'; }

    function setWebMode(web) {
        webMode = web;
        graphMode = false;
        pageShell.classList.toggle('web-search-mode', web);
        document.getElementById('graph-area').hidden = true;
        document.getElementById('content-view').hidden = false;
        queryInput.placeholder = web ? 'Search the web...' : 'Search your library...';
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', !web);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', web);
        document.getElementById('sidebar-graph-nav')?.classList.toggle('active', false);
        if (!web) {
            loadLibrary();
        } else {
            allResults = [];
            resultsContainer.innerHTML = '<div class="empty-state" style="display:flex"><div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div><h3>Web Search</h3><p>Enter a query to search the web. Results come from SearXNG meta search.</p></div>';
            statusBar.hidden = true;
            emptyState.hidden = true;
            currentQuery = '';
            queryInput.value = '';
            queryInput.focus();
        }
    }

    let graphMode = false;
    let graphSimulation = null;

    function setGraphMode() {
        graphMode = true;
        webMode = false;
        pageShell.classList.remove('web-search-mode');
        document.getElementById('graph-area').hidden = false;
        document.getElementById('content-view').hidden = true;
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', false);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', false);
        document.getElementById('sidebar-graph-nav')?.classList.toggle('active', true);
        loadGraph();
    }

    async function loadGraph() {
        const area = document.getElementById('graph-area');
        const container = document.getElementById('graph-container');
        const loading = document.getElementById('graph-loading');
        const empty = document.getElementById('graph-empty');
        loading.hidden = false;
        empty.hidden = true;
        container.innerHTML = '';
        try {
            const r = await fetch('/api/ai/relation-graph?limit=200');
            const data = await r.json();
            loading.hidden = true;
            if (!data.nodes || data.nodes.length === 0) {
                empty.hidden = false;
                return;
            }
            renderGraph(data, container);
        } catch (e) {
            loading.hidden = true;
            container.innerHTML = `<div class="graph-error">Error loading graph: ${e.message}</div>`;
        }
    }

    function renderGraph(data, container) {
        const width = container.clientWidth || 800;
        const height = container.clientHeight || 500;
        const svg = d3.select(container).append('svg')
            .attr('width', width).attr('height', height);

        const g = svg.append('g');

        svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', (e) => {
            g.attr('transform', e.transform);
        }));

        const nodes = data.nodes.map(n => ({ ...n }));
        const nodeMap = {};
        nodes.forEach(n => nodeMap[n.id] = n);

        const edges = data.edges.map(e => ({
            source: e.source_id,
            target: e.target_id,
            relation_type: e.relation_type,
            strength: e.strength || 0.5,
        })).filter(e => nodeMap[e.source] && nodeMap[e.target]);

        const color = d => d.type === 'capture' ? '#60a5fa' : '#22c55e';

        const link = g.append('g').selectAll('line')
            .data(edges).join('line')
            .attr('stroke', '#2a2a4a')
            .attr('stroke-width', d => Math.max(1, (d.strength || 0.5) * 4))
            .attr('stroke-opacity', 0.4);

        const linkLabel = g.append('g').selectAll('text')
            .data(edges).join('text')
            .text(d => d.relation_type)
            .attr('class', 'edge-label')
            .attr('font-size', '9px')
            .attr('fill', '#94a3b8')
            .attr('text-anchor', 'middle')
            .attr('visibility', 'hidden');

        let currentZoom = 1;
        const ZOOM_THRESHOLD = 1.5;

        function refreshEdgeLabels() {
            linkLabel.attr('visibility', 'hidden');
            if (currentZoom >= ZOOM_THRESHOLD) {
                linkLabel.attr('visibility', null);
            }
        }

        // Zoom handler
        svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', (e) => {
            g.attr('transform', e.transform);
            currentZoom = e.transform.k;
            refreshEdgeLabels();
        }));

        const node = g.append('g').selectAll('g')
            .data(nodes).join('g')
            .style('cursor', 'pointer')
            .call(d3.drag()
                .on('start', (e, d) => {
                    graphSimulation?.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
                .on('end', (e, d) => {
                    graphSimulation?.alphaTarget(0);
                    d.fx = null; d.fy = null;
                })
            );

        node.append('circle')
            .attr('r', d => d.type === 'capture' ? 8 : 6)
            .attr('fill', color)
            .attr('stroke', '#1a1a2e')
            .attr('stroke-width', 2);

        node.append('text')
            .text(d => d.label.length > 30 ? d.label.slice(0, 30) + '...' : d.label)
            .attr('dx', d => d.type === 'capture' ? 12 : 8)
            .attr('dy', 4)
            .attr('font-size', '11px')
            .attr('fill', '#e2e8f0')
            .attr('pointer-events', 'none');

        node.on('click', (e, d) => {
            if (d.type === 'capture') {
                window.open(`/capture/${d.id}`, '_blank');
            }
        });

        node.append('title')
            .text(d => `${d.label} (${d.type}${d.subtype ? ': ' + d.subtype : ''})`);

        // Build edge index per node for hover lookup
        const nodeEdges = {};
        edges.forEach((e, i) => {
            const sid = typeof e.source === 'object' ? e.source.id : e.source;
            const tid = typeof e.target === 'object' ? e.target.id : e.target;
            (nodeEdges[sid] = nodeEdges[sid] || []).push(i);
            (nodeEdges[tid] = nodeEdges[tid] || []).push(i);
        });

        function showEdgeLabels(indices) {
            linkLabel.attr('visibility', (_, i) => indices.includes(i) ? null : 'hidden');
        }

        function hideEdgeLabels() {
            refreshEdgeLabels();
        }

        node.on('mouseenter', (e, d) => {
            const indices = nodeEdges[d.id] || [];
            showEdgeLabels(indices);
        });
        node.on('mouseleave', () => hideEdgeLabels());

        link.on('mouseenter', (e, d) => {
            const i = edges.indexOf(d);
            showEdgeLabels([i]);
        });
        link.on('mouseleave', () => hideEdgeLabels());

        function readGraphSettings() {
            const s = Number(document.getElementById('graph-spacing')?.value || 5);
            const g = Number(document.getElementById('graph-gravity')?.value || 3);
            return { spacing: s, gravity: g };
        }

        function buildSimFromSettings() {
            const { spacing, gravity } = readGraphSettings();
            const s = spacing;
            const g = gravity * 0.005;
            if (graphSimulation) {
                graphSimulation.force('link').distance(30 * s);
                graphSimulation.force('charge').strength(-50 * s);
                graphSimulation.force('collision').radius(10 + s * 4);
                graphSimulation.force('x').strength(g);
                graphSimulation.force('y').strength(g);
                graphSimulation.alpha(1).restart();
            } else {
                graphSimulation = d3.forceSimulation(nodes)
                    .force('link', d3.forceLink(edges).id(d => d.id).distance(30 * s).strength(0.3))
                    .force('charge', d3.forceManyBody().strength(-50 * s))
                    .force('center', d3.forceCenter(width / 2, height / 2))
                    .force('collision', d3.forceCollide().radius(10 + s * 4))
                    .force('x', d3.forceX(width / 2).strength(g))
                    .force('y', d3.forceY(height / 2).strength(g));

                graphSimulation.on('tick', () => {
                    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                    linkLabel.attr('x', d => (d.source.x + d.target.x) / 2)
                        .attr('y', d => (d.source.y + d.target.y) / 2);
                    node.attr('transform', d => `translate(${d.x},${d.y})`);
                });

                graphSimulation.alpha(1).restart();
            }
        }

        buildSimFromSettings();

        const spacingSlider = document.getElementById('graph-spacing');
        const spacingVal = document.getElementById('graph-spacing-val');
        const gravitySlider = document.getElementById('graph-gravity');
        const gravityVal = document.getElementById('graph-gravity-val');

        function wireSlider(slider, valDisplay) {
            if (slider) {
                slider.addEventListener('input', () => {
                    if (valDisplay) valDisplay.textContent = slider.value;
                    buildSimFromSettings();
                });
            }
        }
        wireSlider(spacingSlider, spacingVal);
        wireSlider(gravitySlider, gravityVal);

        // Hamburger menu toggle
        const settingsBtn = document.getElementById('graph-settings-btn');
        const settingsPopup = document.getElementById('graph-settings-popup');
        if (settingsBtn && settingsPopup) {
            settingsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                settingsPopup.hidden = !settingsPopup.hidden;
            });
            document.addEventListener('click', (e) => {
                if (!settingsPopup.hidden && !settingsPopup.contains(e.target) && e.target !== settingsBtn) {
                    settingsPopup.hidden = true;
                }
            });
        }

        const ro = new ResizeObserver(() => {
            const w = container.clientWidth;
            const h = container.clientHeight;
            svg.attr('width', w).attr('height', h);
            if (graphSimulation) {
                graphSimulation.force('center', d3.forceCenter(w / 2, h / 2));
                graphSimulation.force('x', d3.forceX(w / 2));
                graphSimulation.force('y', d3.forceY(h / 2));
                graphSimulation.alpha(0.3).restart();
            }
        });
        ro.observe(container);
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

    const TYPE_ICONS = {
        page: '/static/assets/capture_types/page.svg',
        video: '/static/assets/capture_types/video.svg',
        reddit_post: '/static/assets/capture_types/reddit.svg',
        bookmark: '/static/assets/capture_types/bookmark.svg',
    };

    function getTypeIconHtml(captureType) {
        const icon = TYPE_ICONS[captureType] || null;
        if (!icon) return '';
        return `<img class="card-type-icon" src="${escapeHtml(icon)}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
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
        const cardTitle = item.summary || item.content || item.title || 'Untitled';
        const subtitle = item.title || '';
        const urlDisplay = item.url ? item.url.replace(/^https?:\/\//, '').replace(/\/$/, '') : '';
        const highlightedTitle = highlightText(cardTitle, currentQuery);
        const chipHtml = chips.slice(0, 2).map(ch => `<span class="card-chip">${escapeHtml(ch)}</span>`).join('');
        const globalIndex = allResults.findIndex(r => r === item);
        const viewLink = isSaved ? `<a href="/capture/${item.id || item.capture_id}" class="card-view-link" title="Knowledge Viewer">🔍</a>` : '';
        const typeIcon = getTypeIconHtml(item.capture_type);
        const subtitleHtml = subtitle && subtitle !== cardTitle
            ? `<span class="card-subtitle">${escapeHtml(subtitle)}</span>`
            : '';
        return `
          <article class="result-card ${isSaved ? 'card-saved' : 'card-web'}" data-type="${isSaved ? 'saved' : 'web'}" data-index="${globalIndex}">
            <div class="card-meta">
              ${getFaviconHtml(item, domain)}
              <span class="card-domain">${escapeHtml(siteName || domain)}</span>
              <span class="card-badge saved">Saved</span>
              ${isSaved && ts ? `<span class="card-time">${ts}</span>` : ''}
              ${viewLink}
            </div>
            <div class="card-body">
              <div class="card-title-row">
                ${typeIcon}
                <span class="card-title" data-url="${item.url || '#'}">${highlightedTitle}</span>
              </div>
              ${subtitleHtml}
              ${urlDisplay ? `<span class="card-url">${escapeHtml(urlDisplay)}</span>` : ''}
            </div>
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
        if (activeTags.length > 0) {
            filtered = filtered.filter(item => Array.isArray(item.tags) && item.tags.some(t => activeTags.includes(t)));
        }
        return filtered;
    }

    function updateStatusBar(items) {
        statusBar.hidden = false;
        const total = allResults._total || allResults.length;
        const visible = items.length;
        if (!webMode && currentQuery) {
            resultCount.textContent = `${visible} result${visible !== 1 ? 's' : ''} in library`;
        } else if (webMode && currentQuery) {
            resultCount.textContent = `${visible} web result${visible !== 1 ? 's' : ''}`;
        } else {
            statusBar.hidden = true;
        }
    }

    function updatePaginationControls() {
        const autoLoad = settingsState.autoLoad !== false;
        const isActive = currentQuery;
        const showLoadMore = !autoLoad && hasMore && isActive;
        const showSentinel = autoLoad && hasMore && isActive;
        const showEndMessage = !hasMore && isActive && allResults.length > 0;
        const showLoadingMore = hasMore && isActive && loading && currentPage > 1;
        sentinel.hidden = !showSentinel;
        loadMoreButton.hidden = !showLoadMore;
        endOfResults.hidden = !showEndMessage;
        // bottomLoading: managed by showLoading, but ensure it's hidden at end
        if (!loading) bottomLoading.hidden = true;
        if (showEndMessage) bottomLoading.hidden = true;
        if (!sentinel.hidden) ensureSentinelObserved();
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
            let renderedIndices = new Set();
            if (!append) {
                renderedIndices = new Set();
                resultsContainer.innerHTML = items.map(createCard).join('');
                attachCardHandlers();
                const cards = resultsContainer.querySelectorAll('.result-card');
                const animSpeed = settingsState.animationSpeed || 'fast';
                const delayStep = animSpeed === 'fast' ? 30 : animSpeed === 'slow' ? 100 : animSpeed === 'instant' ? 0 : 50;
                resultsContainer.style.setProperty('--card-transition', animSpeed === 'instant' ? '0s' : '');
                cards.forEach((card, idx) => {
                    const delay = idx * delayStep;
                    if (delayStep === 0) {
                        card.classList.add('visible');
                    } else {
                        setTimeout(() => card.classList.add('visible'), delay);
                    }
                });
            } else {
                const newItems = items.filter(item => !renderedIndices.has(allResults.findIndex(r => r === item)));
                if (!newItems.length) { updatePaginationControls(); return; }
                const html = newItems.map(createCard).join('');
                resultsContainer.insertAdjacentHTML('beforeend', html);
                newItems.forEach(item => renderedIndices.add(allResults.findIndex(r => r === item)));
                attachCardHandlers();
                const newCards = resultsContainer.querySelectorAll('.result-card:not(.visible)');
                const animSpeed = settingsState.animationSpeed || 'fast';
                const delayStep = animSpeed === 'fast' ? 30 : animSpeed === 'slow' ? 100 : animSpeed === 'instant' ? 0 : 50;
                resultsContainer.style.setProperty('--card-transition', animSpeed === 'instant' ? '0s' : '');
                newCards.forEach((card, idx) => {
                    const delay = idx * delayStep;
                    if (delayStep === 0) {
                        card.classList.add('visible');
                    } else {
                        setTimeout(() => card.classList.add('visible'), delay);
                    }
                });
            }

            updateStatusBar(items);
            const total = allResults._total || allResults.length;
            if (total === 0 && currentQuery) {
                emptyState.hidden = false;
                const modeText = webMode ? 'web' : 'your library';
                emptyState.innerHTML = `
                    <div class="empty-icon">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
                    </div>
                    <h3>No results for "${escapeHtml(currentQuery)}"</h3>
                    <p>Try different keywords. No matches in ${modeText}.</p>`;
            } else {
                emptyState.hidden = true;
            }
            updatePaginationControls();
        }

    async function doSearch(query, page) {
        if (loading) return;
        loading = true;
        showLoading(true, page);
        const sourceParam = webMode ? 'web' : 'local';
        const url = `/search?q=${encodeURIComponent(query)}&page=${page}&source=${sourceParam}${activeProject ? `&project=${encodeURIComponent(activeProject)}` : ''}`;
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
                allResults = allResults.concat(fetched);
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

    async function loadLibrary() {
        loading = true;
        webMode = false;
        currentQuery = '';
        try {
            const url = activeProject ? `/browse?project=${encodeURIComponent(activeProject)}` : '/browse';
            const resp = await fetch(url);
            const data = await resp.json();
            allResults = Array.isArray(data) ? data : [];
            hasMore = false;
            currentPage = 1;
            renderResults(false);
        } catch (err) {
            console.error('Library load failed:', err);
            resultsContainer.innerHTML = '<div class="message error">Could not load saved content.</div>';
        }
        loading = false;
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
        await doSearch(query, 1);
        queryInput.blur();
    });

document.getElementById('sidebar-library-nav')?.addEventListener('click', () => setWebMode(false));
document.getElementById('sidebar-web-nav')?.addEventListener('click', () => setWebMode(true));
document.getElementById('sidebar-graph-nav')?.addEventListener('click', () => setGraphMode());

    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading && hasMore && currentQuery && settingsState.autoLoad !== false) {
            doSearch(currentQuery, currentPage + 1);
        }
    }, { rootMargin: '300px' });

    function ensureSentinelObserved() {
        if (sentinel && !sentinel.hidden) {
            observer.unobserve(sentinel);
            observer.observe(sentinel);
        }
    }
    // Initial observe — sentinel is hidden, but when it becomes visible
    // updatePaginationControls will call ensureSentinelObserved
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
        const contextBefore = item.context?.before || '';
        const contextAfter = item.context?.after || '';
        const selectionHtml = item.context?.selection_html || '';
        let previewContentHtml = '';
        if (contextBefore || contextAfter) {
            let beforeEsc = escapeHtml(contextBefore);
            let afterEsc = escapeHtml(contextAfter);
            let contentEsc = escapeHtml(previewBody);
            if (selectionHtml) {
                previewContentHtml = `<div class="preview-context">${escapeHtml(contextBefore)}<span class="sel-text">${selectionHtml}</span>${escapeHtml(contextAfter)}</div>`;
            } else {
                previewContentHtml = `<div class="preview-with-context"><span class="preview-ctx-before">${beforeEsc}</span><span class="sel-text">${contentEsc}</span><span class="preview-ctx-after">${afterEsc}</span></div>`;
            }
        } else {
            previewContentHtml = renderMarkdown(previewBody);
        }
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
            <div class="preview-content">${previewContentHtml}</div>
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
            const confirmed = await showConfirmDialog('Delete this saved item?'); if (!confirmed) return;
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
                button.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    showProjectContextMenu(e, project.name, button);
                });
                sidebarProjectList.appendChild(button);
            });
            sidebarTags.innerHTML = '';
            (data.tags || []).forEach(tag => {
                const btn = document.createElement('button');
                btn.className = 'sidebar-tag-btn' + (activeTags.includes(tag) ? ' active' : '');
                btn.textContent = tag;
                btn.addEventListener('click', () => {
                    const idx = activeTags.indexOf(tag);
                    if (idx >= 0) activeTags.splice(idx, 1);
                    else activeTags.push(tag);
                    loadProjects();
                    renderResults(false);
                });
                sidebarTags.appendChild(btn);
            });
            if (activeTags.length > 0) {
                const clearBtn = document.createElement('button');
                clearBtn.className = 'sidebar-tag-clear-btn';
                clearBtn.textContent = 'Clear filters (' + activeTags.length + ')';
                clearBtn.addEventListener('click', () => {
                    activeTags = [];
                    loadProjects();
                    renderResults(false);
                });
                sidebarTags.appendChild(clearBtn);
            }
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
            importResult.textContent = 'Server error — is Nodecast running?';
            importResult.className = 'import-result error';
            importResult.hidden = false;
        }
    }


    // ─── Confirmation dialog ─────────────────────────────────────
    const confirmOverlay = document.getElementById('confirm-overlay');
    const confirmClose = document.getElementById('confirm-close');
    const confirmTitle = document.getElementById('confirm-title');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmCancel = document.getElementById('confirm-cancel');
    const confirmDelete = document.getElementById('confirm-delete');

    function showConfirmDialog(msg, opts = {}) {
        const { prompt: promptLabel, defaultValue } = opts;
        return new Promise((resolve) => {
            confirmMessage.textContent = msg;
            confirmOverlay.hidden = false;
            confirmOverlay.removeAttribute('aria-hidden');

            const inputGroup = document.getElementById('confirm-input-group');
            const inputLabel = document.getElementById('confirm-input-label');
            const inputEl = document.getElementById('confirm-input');
            const deleteBtn = document.getElementById('confirm-delete');

            if (promptLabel) {
                inputGroup.hidden = false;
                inputLabel.textContent = promptLabel;
                inputEl.value = defaultValue || '';
                inputEl.focus();
                deleteBtn.textContent = 'Confirm';
                deleteBtn.style.background = 'var(--danger,#f87171)';
                deleteBtn.style.color = '#fff';
                deleteBtn.style.border = 'none';
            } else {
                inputGroup.hidden = true;
                deleteBtn.textContent = 'Delete';
                deleteBtn.style.background = '';
                deleteBtn.style.color = '';
                deleteBtn.style.border = '';
            }

            function cleanup() {
                confirmOverlay.hidden = true;
                confirmOverlay.setAttribute('aria-hidden', 'true');
                confirmOverlay.removeEventListener('click', overlayClick);
                confirmClose.removeEventListener('click', rejectClick);
                confirmCancel.removeEventListener('click', rejectClick);
                confirmDelete.removeEventListener('click', acceptClick);
                inputEl.value = '';
            }
            function acceptClick() {
                if (promptLabel) {
                    resolve(inputEl.value);
                } else {
                    resolve(true);
                }
                cleanup();
            }
            function rejectClick() { cleanup(); resolve(false); }
            function overlayClick(e) { if (e.target === confirmOverlay) { cleanup(); resolve(false); } }

            confirmDelete.addEventListener('click', acceptClick);
            confirmCancel.addEventListener('click', rejectClick);
            confirmClose.addEventListener('click', rejectClick);
            confirmOverlay.addEventListener('click', overlayClick);
            
            if (promptLabel) {
                inputEl.addEventListener('keydown', function inputKeydown(e) {
                    if (e.key === 'Enter') { acceptClick(); }
                });
            }
        });
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
        editStatus.hidden = true;
        editModal.hidden = false;
        editModal.inert = false;
        loadProjects();
        renderEditTagPicker(item.tags || []);
    }
    function closeEditModal() { editModal.hidden = true; editModal.inert = true; editingItem = null; }

    const editTagsAll = document.getElementById('edit-tags-all');
    const editTagsStatus = document.getElementById('edit-tags-status');

    function renderEditTagPicker(selectedTags) {
        // Render the currently selected tags as chips
        editTagsList.innerHTML = '';
        (selectedTags || []).forEach(tag => {
            const chip = document.createElement('span');
            chip.className = 'edit-tag-chip';
            chip.innerHTML = `${escapeHtml(tag)} <button class="edit-tag-remove" data-tag="${escapeHtml(tag)}">&times;</button>`;
            chip.querySelector('.edit-tag-remove').addEventListener('click', () => {
                removeEditTagFromPicker(tag, selectedTags);
            });
            editTagsList.appendChild(chip);
        });

        // Load all available tags and show as clickable options
        fetch('/api/tags').then(r => r.json()).then(data => {
            const allTags = data.tags || [];
            editTagsAll.innerHTML = '';
            let hasMatch = false;
            allTags.forEach(tag => {
                const isSelected = selectedTags.includes(tag);
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'edit-tag-option' + (isSelected ? ' selected' : '');
                btn.textContent = tag;
                btn.addEventListener('click', () => {
                    if (isSelected) {
                        const idx = selectedTags.indexOf(tag);
                        if (idx >= 0) selectedTags.splice(idx, 1);
                    } else {
                        selectedTags.push(tag);
                    }
                    renderEditTagPicker(selectedTags);
                });
                editTagsAll.appendChild(btn);

                const filter = editTagsInput.value.trim().toLowerCase();
                if (filter && tag.toLowerCase().includes(filter)) hasMatch = true;
                if (filter) btn.hidden = !tag.toLowerCase().includes(filter);
            });

            if (allTags.length === 0) {
                editTagsAll.innerHTML = '<div class="edit-tags-empty">No tags yet. Type a name and click Add.</div>';
            } else {
                editTagsStatus.hidden = true;
            }
        }).catch(() => {});
    }

    function removeEditTagFromPicker(tag, selectedTags) {
        const idx = selectedTags.indexOf(tag);
        if (idx >= 0) selectedTags.splice(idx, 1);
        renderEditTagPicker(selectedTags);
    }

    function getEditTags() {
        const tags = [];
        editTagsList.querySelectorAll('.edit-tag-chip').forEach(chip => {
            const removeBtn = chip.querySelector('.edit-tag-remove');
            if (removeBtn) tags.push(removeBtn.dataset.tag);
        });
        return tags;
    }

    editClose.addEventListener('click', closeEditModal);
    editCancel.addEventListener('click', closeEditModal);
    editModal.addEventListener('click', (e) => { if (e.target === editModal) closeEditModal(); });

    editTagsAdd.addEventListener('click', () => {
        const tag = editTagsInput.value.trim();
        if (!tag) return;
        if (tag.length > 32) { editTagsStatus.textContent = 'Max 32 characters'; editTagsStatus.className = 'note-status error'; editTagsStatus.hidden = false; return; }
        const current = getEditTags();
        if (current.includes(tag)) { editTagsStatus.textContent = 'Tag already added'; editTagsStatus.className = 'note-status'; editTagsStatus.hidden = false; return; }
        current.push(tag);
        editTagsInput.value = '';
        editTagsStatus.hidden = true;
        renderEditTagPicker(current);
    });
    editTagsInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); editTagsAdd.click(); }
    });
    editTagsInput.addEventListener('input', () => {
        // Filter the options as user types
        const filter = editTagsInput.value.trim().toLowerCase();
        editTagsAll.querySelectorAll('.edit-tag-option').forEach(btn => {
            btn.hidden = filter && !btn.textContent.toLowerCase().includes(filter);
        });
    });
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
    function checkExtensionInstalled() { if (localStorage.getItem('bannerDismissed') === 'true') return; const sentinel = document.querySelector('meta[name="nodecast-extension"]'); if (!sentinel || sentinel.content !== 'installed') extBanner.hidden = false; }
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

    let sidebarWidth = Number(localStorage.getItem('nodecast.sidebarWidth') || 280);
    let previewWidth = Number(localStorage.getItem('nodecast.previewWidth') || 360);
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
            localStorage.setItem('nodecast.sidebarWidth', String(sidebarWidth));
            localStorage.setItem('nodecast.previewWidth', String(previewWidth));
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
    loadLibrary();
    loadProjects();
    renderResults(false);
    updatePaginationControls();

    




    // ─── Project context menu ───────────────────────────────────
    function showProjectContextMenu(e, projectName, btn) {
        const existing = document.getElementById('project-context-menu');
        if (existing) existing.remove();
        
        const menu = document.createElement('div');
        menu.id = 'project-context-menu';
        menu.className = 'project-context-menu';
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        
        const deleteOpt = document.createElement('div');
        deleteOpt.className = 'context-menu-option context-menu-danger';
        deleteOpt.textContent = 'Delete "' + projectName + '"';
        deleteOpt.addEventListener('click', async () => {
            menu.remove();
            const confirmedProj = await showConfirmDialog('Remove project "' + projectName + '" from all items?'); if (!confirmedProj) return;
            fetch('/api/projects/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: projectName })
            }).then(r => r.json()).then(res => {
                if (res.success || res.message) {
                    if (activeProject === projectName) selectProject('');
                    loadProjects();
                    renderResults(false);
                }
            }).catch(() => {});
        });
        menu.appendChild(deleteOpt);
        
        document.body.appendChild(menu);
        
        document.addEventListener('click', () => { if (menu.parentNode) menu.remove(); }, { once: true });
    }
    // ─── Collapsible sidebar sections ────────────────────────────
    document.querySelectorAll('.sidebar-section-label').forEach(label => {
        const section = label.parentElement;
        const collapse = section.querySelector('.sidebar-collapse');
        if (!collapse) return;
        label.addEventListener('click', () => {
            label.classList.toggle('collapsed');
            collapse.classList.toggle('collapsed');
        });
    });



    // ─── Tag Management Modal ────────────────────────────────────
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

    function showTagManageStatus(msg, type) {
        tagManageStatus.textContent = msg;
        tagManageStatus.className = 'note-status ' + (type || '') + (msg ? '' : ' hidden');
    }

    function loadTagManageList() {
        fetch('/api/tags').then(r => r.json()).then(data => {
            tagManageTagData = data.tags || [];
            const filter = (tagManageSearch ? tagManageSearch.value.trim().toLowerCase() : '');
            const filtered = filter ? tagManageTagData.filter(t => t.toLowerCase().includes(filter)) : tagManageTagData;
            
            tagManageList.innerHTML = '';
            filtered.forEach(tag => {
                const chip = document.createElement('span');
                chip.className = 'tag-manage-chip';
                chip.textContent = tag;
                chip.title = tag;
                
                if (tagManageMode === 'rename') {
                    chip.addEventListener('click', () => {
                        const oldName = chip.textContent;
                        const input = document.createElement('input');
                        input.type = 'text';
                        input.className = 'tag-manage-chip-input';
                        input.value = oldName;
                        input.maxLength = 32;
                        chip.textContent = '';
                        chip.appendChild(input);
                        input.focus();
                        input.select();
                        
                        function saveRename() {
                            const newName = input.value.trim();
                            if (!newName || newName === oldName) {
                                chip.textContent = oldName;
                                return;
                            }
                            if (newName.length > 32) { showTagManageStatus('Max 32 characters.', 'error'); chip.textContent = oldName; return; }
                            fetch('/api/tags/rename', {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ old: oldName, new: newName })
                            }).then(r => r.json()).then(res => {
                                if (res.success || res.message) {
                                    showTagManageStatus('Renamed.', 'success');
                                    loadTagManageList();
                                    loadProjects();
                                    renderResults(false);
                                } else { showTagManageStatus('Failed.', 'error'); chip.textContent = oldName; }
                            }).catch(() => { showTagManageStatus('Network error.', 'error'); chip.textContent = oldName; });
                        }
                        
                        input.addEventListener('keydown', (ev) => {
                            if (ev.key === 'Enter') { ev.preventDefault(); input.blur(); }
                            if (ev.key === 'Escape') { chip.textContent = oldName; }
                        });
                        input.addEventListener('blur', saveRename);
                    });
                } else {
                    // Delete mode
                    chip.classList.add('tag-manage-chip-deletable');
                    chip.addEventListener('click', async () => {
                        const oldName = chip.textContent;
                        const confirmedTag = await showConfirmDialog('Delete tag "' + oldName + '" from all items?'); if (!confirmedTag) return;
                        fetch('/api/tags/delete', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tag: oldName })
                        }).then(r => r.json()).then(res => {
                            if (res.success || res.message) {
                                showTagManageStatus('Deleted.', 'success');
                                loadTagManageList();
                                loadProjects();
                                renderResults(false);
                            } else { showTagManageStatus('Failed.', 'error'); }
                        }).catch(() => showTagManageStatus('Network error.', 'error'));
                    });
                }
                tagManageList.appendChild(chip);
            });
            if (filtered.length === 0) {
                tagManageList.innerHTML = '<div class="tag-manage-empty">' +
                    (filter ? 'No tags match "' + filter + '".' : 'No tags yet. Create your first tag above.') + '</div>';
            }
        }).catch(() => showTagManageStatus('Failed to load tags.', 'error'));
    }

    function switchTagManageMode(mode) {
        tagManageMode = mode;
        renameModeBtn.classList.toggle('active', mode === 'rename');
        deleteModeBtn.classList.toggle('active', mode === 'delete');
        loadTagManageList();
    }

    if (renameModeBtn) renameModeBtn.addEventListener('click', () => switchTagManageMode('rename'));
    if (deleteModeBtn) deleteModeBtn.addEventListener('click', () => switchTagManageMode('delete'));

    if (manageTagsBtn) {
        manageTagsBtn.addEventListener('click', () => {
            tagManageOverlay.hidden = false;
            tagManageOverlay.removeAttribute('aria-hidden');
            showTagManageStatus('', '');
            if (tagManageSearch) tagManageSearch.value = '';
            switchTagManageMode('rename');
        });
    }
    if (tagManageClose) {
        tagManageClose.addEventListener('click', () => { tagManageOverlay.hidden = true; tagManageOverlay.setAttribute('aria-hidden', 'true'); });
    }
    if (tagManageOverlay) {
        tagManageOverlay.addEventListener('click', (e) => { if (e.target === tagManageOverlay) { tagManageOverlay.hidden = true; tagManageOverlay.setAttribute('aria-hidden', 'true'); } });
    }
    if (tagManageSearch) {
        tagManageSearch.addEventListener('input', () => loadTagManageList());
    }
    if (tagManageAddBtn && tagManageNew) {
        tagManageAddBtn.addEventListener('click', () => {
            const name = tagManageNew.value.trim();
            if (!name) { showTagManageStatus('Tag name cannot be empty.', 'error'); return; }
            if (name.length > 32) { showTagManageStatus('Max 32 characters.', 'error'); return; }
            fetch('/api/tags/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag: name }) })
                .then(r => r.json()).then(res => {
                    if (res.success || res.status === 'ok' || res.message) {
                        showTagManageStatus('Tag created.', 'success');
                        tagManageNew.value = '';
                        loadTagManageList();
                        loadProjects();
                        renderResults(false);
                    } else { showTagManageStatus(res.error || 'Failed.', 'error'); }
                }).catch(() => showTagManageStatus('Network error.', 'error'));
        });
        tagManageNew.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); tagManageAddBtn.click(); } });
    }
});
