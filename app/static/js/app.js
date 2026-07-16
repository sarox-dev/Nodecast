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
    let accountData = null;
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
        } else {
            settingsList.innerHTML = category.items.map(item => createField({ ...item, category: category.category })).join('');
        }
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
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

        // ─── Providers section ────────────────────────────────────
        html += '<div class="settings-section-header"><h3>AI Providers</h3></div>';
        html += '<div class="settings-list" style="gap:0.3rem">';
        if (aiProviders.length === 0) {
            html += '<div style="color:var(--text-dim);font-size:0.85rem;padding:0.5rem 0">No AI providers configured. Add one below.</div>';
        } else {
            for (const p of aiProviders) {
                const info = providerModels.get(p.id);
                const online = info ? info.online : false;
                const hasAssignment = aiAssignments.some(a => a.provider_id === p.id);
                const statusBadge = online
                    ? '<span class="ai-badge" style="background:#22c55e;color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.4rem">● online</span>'
                    : '<span class="ai-badge" style="background:#f87171;color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.4rem">● offline</span>';
                const modelCount = info && info.models ? `· ${info.models.length} models` : '';
                html += `<div class="settings-field" style="justify-content:space-between">
                  <div>
                    <span style="font-weight:600">${escapeHtml(p.name)}</span>
                    ${statusBadge}
                    <span style="color:var(--text-dim);font-size:0.78rem;margin-left:0.3rem">${escapeHtml(p.base_url)}</span>
                    ${modelCount ? `<span style="color:var(--text-dim);font-size:0.75rem;margin-left:0.3rem">${modelCount}</span>` : ''}
                    ${hasAssignment ? '<span class="ai-badge" style="background:var(--accent);color:#fff;font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:4px;margin-left:0.3rem">assigned</span>' : ''}
                  </div>
                  <div style="display:flex;gap:0.3rem">
                    <button class="ai-edit-provider modal-btn modal-btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-url="${escapeHtml(p.base_url)}">Edit</button>
                    <button class="ai-delete-provider modal-btn" style="padding:0.25rem 0.5rem;font-size:0.75rem;background:var(--danger,#f87171);color:#fff;border:none" data-id="${p.id}" data-name="${escapeHtml(p.name)}">Delete</button>
                  </div>
                </div>`;
            }
        }
        html += '</div>';

        // Add provider button
        html += `<button id="ai-add-provider-btn" class="modal-btn modal-btn-primary" type="button" style="margin-top:0.4rem">+ Add Connection</button>`;

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

            html += `<div class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.4rem">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                  <span style="font-weight:600">${escapeHtml(feat.name)}</span>
                  <span style="color:var(--text-dim);font-size:0.78rem;margin-left:0.4rem">${escapeHtml(feat.description)}</span>
                </div>
                ${assignment ? `<span class="ai-badge" style="background:#22c55e;color:#fff;font-size:0.7rem;padding:0.15rem 0.5rem;border-radius:4px">active</span>` : `<span style="color:var(--text-dim);font-size:0.75rem">not configured</span>`}
              </div>
              <div style="display:flex;gap:0.4rem;align-items:center" data-feature="${feat.id}">
                <select class="ai-assign-provider" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem">
                  <option value="">— Select provider —</option>
                  ${aiProviders.map(p => `<option value="${p.id}" ${assignment && assignment.provider_id === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                </select>
                <select class="ai-assign-model" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" ${assignment ? '' : 'disabled'}>
                  ${modelOptions}
                </select>
                <button class="ai-save-assignment modal-btn modal-btn-primary" type="button" style="padding:0.35rem 0.6rem;font-size:0.78rem">Save</button>
                ${assignment ? `<button class="ai-remove-assignment modal-btn modal-btn-secondary" type="button" style="padding:0.35rem 0.5rem;font-size:0.75rem" data-id="${assignment.id}">Remove</button>` : ''}
              </div>
              <span id="ai-assign-status-${feat.id}" class="note-status" hidden></span>
            </div>`;
        }
        html += '</div>';

        // ─── Bulk tagging section ────────────────────────────────
        html += '<div class="settings-section-header" style="margin-top:1.2rem"><h3>Bulk Tagging</h3></div>';
        html += '<div class="settings-list" style="gap:0.4rem">';
        html += `<button id="ai-tag-untagged" class="modal-btn modal-btn-primary" type="button" style="padding:0.4rem 0.75rem;font-size:0.82rem">Tag all untagged captures</button>`;
        html += `<button id="ai-process-all" class="modal-btn modal-btn-primary" type="button" style="padding:0.4rem 0.75rem;font-size:0.82rem">Process all (tag + summarize + extract entities)</button>`;
        html += `<button id="ai-retag-all" class="modal-btn" type="button" style="padding:0.4rem 0.75rem;font-size:0.82rem;background:var(--danger,#f87171);color:#fff;border:none">RETAG all captures (⚠ destructive)</button>`;
        html += '<span id="ai-bulk-status" class="note-status" style="margin-top:0.4rem" hidden></span>';
        html += '</div>';

        // ─── Batch processing section ────────────────────────────
        const batchInterval = localStorage.getItem('aiBatchInterval') ?? '60';
        const processOnOpen = localStorage.getItem('aiProcessOnOpen') !== 'false';
        html += '<div class="settings-section-header" style="margin-top:1.2rem"><h3>Batch Processing</h3></div>';
        html += '<div class="settings-list" style="gap:0.4rem">';
        html += `<label class="settings-field"><span>Process pending every</span><select id="ai-batch-interval" data-key="aiBatchInterval">
          <option value="0" ${batchInterval === '0' ? 'selected' : ''}>disabled (manual only)</option>
          <option value="15" ${batchInterval === '15' ? 'selected' : ''}>every 15 minutes</option>
          <option value="30" ${batchInterval === '30' ? 'selected' : ''}>every 30 minutes</option>
          <option value="60" ${batchInterval === '60' ? 'selected' : ''}>every 1 hour</option>
          <option value="360" ${batchInterval === '360' ? 'selected' : ''}>every 6 hours</option>
          <option value="1440" ${batchInterval === '1440' ? 'selected' : ''}>every 24 hours</option>
        </select></label>`;
        html += `<label class="settings-field toggle-field"><span>Process on page open</span><input type="checkbox" id="ai-process-on-open" ${processOnOpen ? 'checked' : ''} /></label>`;
        html += `<div id="ai-pending-status" class="settings-field" style="font-size:0.85rem;color:var(--text-dim)"><span id="ai-pending-count">—</span> <button id="ai-process-now-btn" class="modal-btn modal-btn-primary" type="button" style="padding:0.25rem 0.6rem;font-size:0.78rem">Process now</button></div>`;
        html += '</div>';

        html += '</div>';
        settingsList.innerHTML = html;
        attachAIHandlers();
    }

    function attachAIHandlers() {
        // Add provider
        document.getElementById('ai-add-provider-btn')?.addEventListener('click', () => openAIProviderModal(null));

        // Edit provider
        document.querySelectorAll('.ai-edit-provider').forEach(btn => {
            btn.addEventListener('click', () => openAIProviderModal({
                id: btn.dataset.id,
                name: btn.dataset.name,
                base_url: btn.dataset.url,
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

        // Provider dropdown change → fetch models
        document.querySelectorAll('.ai-assign-provider').forEach(sel => {
            sel.addEventListener('change', async () => {
                const container = sel.closest('[data-feature]');
                const modelSel = container.querySelector('.ai-assign-model');
                const providerId = sel.value;
                if (!providerId) {
                    modelSel.innerHTML = '<option value="">— Select model —</option>';
                    modelSel.disabled = true;
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
                        modelSel.innerHTML = '<option value="manual">(type model name below)</option>';
                        // Add a manual input as fallback
                        const container = sel.closest('[data-feature]');
                        const existingInput = container.querySelector('.ai-manual-model');
                        if (!existingInput) {
                            const input = document.createElement('input');
                            input.type = 'text';
                            input.className = 'ai-manual-model';
                            input.placeholder = 'Enter model name...';
                            input.style.cssText = 'flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem';
                            modelSel.parentNode.insertBefore(input, modelSel.nextSibling);
                            // When manual model changes, update the select
                            input.addEventListener('input', () => {
                                const opt = modelSel.querySelector('option[value="manual"]');
                                if (opt) opt.text = input.value || '(type model name below)';
                            });
                        }
                    }
                } catch {
                    modelSel.innerHTML = '<option value="manual">(connection failed — type model name)</option>';
                    const container = sel.closest('[data-feature]');
                    const existingInput = container.querySelector('.ai-manual-model');
                    if (!existingInput) {
                        const input = document.createElement('input');
                        input.type = 'text';
                        input.className = 'ai-manual-model';
                        input.placeholder = 'Enter model name manually...';
                        input.style.cssText = 'flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem';
                        modelSel.parentNode.insertBefore(input, modelSel.nextSibling);
                        input.addEventListener('input', () => {
                            const opt = modelSel.querySelector('option[value="manual"]');
                            if (opt) opt.text = input.value || '(connection failed — type model name)';
                        });
                    }
                }
            });
        });

        // Save assignment
        document.querySelectorAll('.ai-save-assignment').forEach(btn => {
            btn.addEventListener('click', async () => {
                const container = btn.closest('[data-feature]');
                const providerSel = container.querySelector('.ai-assign-provider');
                const modelSel = container.querySelector('.ai-assign-model');
                const feature = container.dataset.feature;
                const status = document.getElementById(`ai-assign-status-${feature}`);
                const providerId = providerSel.value;
                let model = modelSel.value;
                // Check for manual model input
                const manualInput = container.querySelector('.ai-manual-model');
                if (manualInput && manualInput.value.trim()) {
                    model = manualInput.value.trim();
                }
                if (!providerId || !model) {
                    status.textContent = 'Please select a provider and model.';
                    status.style.color = '#f87171';
                    status.hidden = false;
                    return;
                }
                status.hidden = true;
                try {
                    const r = await fetch('/api/ai/assignments', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ feature, provider_id: providerId, model }),
                    });
                    if (r.ok) {
                        status.textContent = 'Assignment saved ✓';
                        status.style.color = '#22c55e';
                        status.hidden = false;
                        setTimeout(() => renderAISettings(), 1000);
                    } else {
                        const d = await r.json();
                        status.textContent = d.detail || 'Failed';
                        status.style.color = '#f87171';
                        status.hidden = false;
                    }
                } catch {
                    status.textContent = 'Error saving assignment';
                    status.style.color = '#f87171';
                    status.hidden = false;
                }
            });
        });

        // Remove assignment
        document.querySelectorAll('.ai-remove-assignment').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    const r = await fetch(`/api/ai/assignments/${btn.dataset.id}`, { method: 'DELETE' });
                    if (r.ok) renderAISettings();
                } catch {}
            });
        });

        // Tag all untagged
        document.getElementById('ai-tag-untagged')?.addEventListener('click', async () => {
            const status = document.getElementById('ai-bulk-status');
            status.textContent = 'Tagging... this may take a while';
            status.style.color = 'var(--text-dim)';
            status.hidden = false;
            try {
                const r = await fetch('/api/ai/tag-all-untagged', { method: 'POST' });
                const d = await r.json();
                status.textContent = `Done: ${d.tagged} tagged, ${d.skipped} skipped, ${d.errors} errors (of ${d.total} total)`;
                status.style.color = d.errors > 0 ? '#f87171' : '#22c55e';
            } catch {
                status.textContent = 'Error running bulk tagging';
                status.style.color = '#f87171';
            }
        });

        // RETAG all (dangerous)
        document.getElementById('ai-retag-all')?.addEventListener('click', async () => {
            const retagCode = await showConfirmDialog(
                'This will delete existing AI tags and regenerate them for ALL captures.',
                { prompt: 'Type "RETAG" to confirm:', defaultValue: '' }
            );
            if (retagCode !== 'RETAG') return;
            const status = document.getElementById('ai-bulk-status');
            status.textContent = 'Re-tagging all captures... this will take a while';
            status.style.color = 'var(--text-dim)';
            status.hidden = false;
            try {
                const r = await fetch('/api/ai/retag-all', { method: 'POST' });
                const d = await r.json();
                status.textContent = `Done: ${d.tagged} tagged, ${d.skipped} skipped, ${d.errors} errors (of ${d.total} total)`;
                status.style.color = d.errors > 0 ? '#f87171' : '#22c55e';
            } catch {
                status.textContent = 'Error running retag';
                status.style.color = '#f87171';
            }
        // Process all (tag + summarize + extract entities)
        document.getElementById('ai-process-all')?.addEventListener('click', async () => {
            const status = document.getElementById('ai-bulk-status');
            status.textContent = 'Processing all captures (tag + summarize + extract entities)... this will take a while';
            status.style.color = 'var(--text-dim)';
            status.hidden = false;
            try {
                const r = await fetch('/api/ai/process-all', { method: 'POST' });
                const d = await r.json();
                status.textContent = `Done: ${d.tagged} tagged, ${d.summarized} summarized, ${d.entities_extracted} entities extracted, ${d.errors} errors (of ${d.total} total)`;
                status.style.color = d.errors > 0 ? '#f87171' : '#22c55e';
            } catch {
                status.textContent = 'Error running process all';
                status.style.color = '#f87171';
            }
        });
        });

        // ─── Batch processing handlers ───────────────────────────
        // Save interval on change
        document.getElementById('ai-batch-interval')?.addEventListener('change', function () {
            localStorage.setItem('aiBatchInterval', this.value);
            updateBatchInterval();
        });

        // Save process-on-open toggle
        document.getElementById('ai-process-on-open')?.addEventListener('change', function () {
            localStorage.setItem('aiProcessOnOpen', this.checked ? 'true' : 'false');
        });

        // Process now button
        document.getElementById('ai-process-now-btn')?.addEventListener('click', async function () {
            this.textContent = '⏳ Processing...';
            this.disabled = true;
            await triggerAIBatch();
            this.textContent = 'Process now';
            this.disabled = false;
            updatePendingCount();
        });

        // Update pending count
        updatePendingCount();
    }

    function triggerAIBatch() {
        return fetch('/api/ai/trigger-batch', { method: 'POST' })
            .then(r => {
                if (!r.ok) console.warn('Batch trigger returned', r.status);
                return r.json().catch(() => ({}));
            })
            .then(data => {
                if (data.status === 'started' || data.status === 'already_running') {
                    // Start polling for progress
                    pollBatchProgress();
                }
                updatePendingCount();
            })
            .catch(err => console.error('Batch trigger failed:', err));
    }

    let batchPollId = null;

    function pollBatchProgress() {
        if (batchPollId) return;  // already polling
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
                        text.textContent = `AI: ${done}/${total} (${status.current || 'processing...'})`;
                        batchPollId = setTimeout(poll, 2000);
                    } else {
                        // Done
                        bar.hidden = true;
                        fill.style.width = '0%';
                        batchPollId = null;
                        updatePendingCount();
                    }
                })
                .catch(() => {
                    batchPollId = setTimeout(poll, 5000);
                });
        }
        poll();
    }

    async function updatePendingCount() {
        try {
            const r = await fetch('/api/ai/pending-count');
            if (r.ok) {
                const data = await r.json();
                const el = document.getElementById('ai-pending-count');
                if (el) el.textContent = data.pending ?? data.count ?? '?';
            }
        } catch {}
    }

    let batchIntervalId = null;
    function updateBatchInterval() {
        if (batchIntervalId) {
            clearInterval(batchIntervalId);
            batchIntervalId = null;
        }
        const minutes = parseInt(localStorage.getItem('aiBatchInterval'), 10) || 0;
        if (minutes > 0) {
            batchIntervalId = setInterval(triggerAIBatch, minutes * 60 * 1000);
        }
    }
    // Initialise batch interval
    updateBatchInterval();

    function openAIProviderModal(existing) {
        // Create a simple modal for adding/editing provider
        const name = existing ? existing.name : '';
        const url = existing ? existing.base_url : '';
        const isEdit = !!existing;

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.display = 'flex';
        overlay.style.zIndex = '10000';
        overlay.innerHTML = `<div class="modal-panel" role="dialog" aria-modal="true" style="max-width:450px">
          <button class="modal-close ai-modal-close-btn" type="button" aria-label="Close">&times;</button>
          <div class="modal-header"><h3 class="modal-title">${isEdit ? 'Edit' : 'Add'} AI Provider</h3></div>
          <div class="note-form-body" style="gap:0.6rem">
            <div class="note-field">
              <label>Name <span class="required">*</span></label>
              <input id="ai-provider-name" type="text" value="${escapeHtml(name)}" placeholder="e.g. localAI, OpenAI" autocomplete="off" />
            </div>
            <div class="note-field">
              <label>Base URL <span class="required">*</span></label>
              <input id="ai-provider-url" type="text" value="${escapeHtml(url)}" placeholder="e.g. http://localhost:1234/v1" autocomplete="off" />
            </div>
            <div class="note-field">
              <label>API Key <span style="color:var(--text-dim);font-size:0.75rem">(optional for local)</span></label>
              <input id="ai-provider-key" type="password" placeholder="sk-..." autocomplete="off" />
            </div>
            <div id="ai-provider-status" class="note-status" hidden></div>
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

        document.getElementById('ai-provider-save-btn')?.addEventListener('click', async () => {
            const pName = document.getElementById('ai-provider-name').value.trim();
            const pUrl = document.getElementById('ai-provider-url').value.trim();
            const pKey = document.getElementById('ai-provider-key').value;
            const status = document.getElementById('ai-provider-status');
            if (!pName || !pUrl) {
                status.textContent = 'Name and Base URL are required';
                status.style.color = '#f87171';
                status.hidden = false;
                return;
            }
            status.hidden = true;
            try {
                if (isEdit) {
                    const body = { name: pName, base_url: pUrl };
                    if (pKey) body.api_key = pKey;
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
                        body: JSON.stringify({ name: pName, base_url: pUrl, api_key: pKey }),
                    });
                    if (r.ok) { close(); renderAISettings(); }
                    else { const d = await r.json(); status.textContent = d.detail || 'Failed'; status.style.color = '#f87171'; status.hidden = false; }
                }
            } catch {
                status.textContent = 'Error saving provider';
                status.style.color = '#f87171';
                status.hidden = false;
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

    function openSettings(category) {
        if (category) activeSettingsCategory = category;
        renderCategoryNav(); renderSettings();
        if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
        settingsOverlay.hidden = false; settingsOverlay.inert = false;
    }
    function openAccountSettings() { openSettings('Account'); }
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

    function setWebMode(web) {
        webMode = web;
        pageShell.classList.toggle('web-search-mode', web);
        queryInput.placeholder = web ? 'Search the web...' : 'Search your library...';
        // Switch active sidebar button
        document.getElementById('sidebar-library-nav')?.classList.toggle('active', !web);
        document.getElementById('sidebar-web-nav')?.classList.toggle('active', web);
        // Reload depending on mode
        if (!web) {
            loadLibrary();
        } else {
            // Web mode — show empty state
            allResults = [];
            resultsContainer.innerHTML = '<div class="empty-state" style="display:flex"><div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div><h3>Web Search</h3><p>Enter a query to search the web. Results come from SearXNG meta search.</p></div>';
            statusBar.hidden = true;
            emptyState.hidden = true;
            currentQuery = '';
            queryInput.value = '';
            queryInput.focus();
        }
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
        const viewLink = item._type === 'saved' ? `<a href="/capture/${item.id || item.capture_id}" class="card-view-link" title="Knowledge Viewer">🔍</a>` : '';
        return `
          <article class="result-card ${isSaved ? 'card-saved' : 'card-web'}" data-type="${isSaved ? 'saved' : 'web'}" data-index="${globalIndex}">
            <div class="card-meta">
              ${getFaviconHtml(item, domain)}
              <span class="card-domain">${escapeHtml(siteName || domain)}</span>
              <span class="card-badge ${badgeClass}">${badgeLabel}</span>
              ${enginesHtml}
              ${isSaved && ts ? `<span class="card-time">${ts}</span>` : ''}
              ${viewLink}
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

    // ─── AI batch processing on page load ───────────────────────
    if (localStorage.getItem('aiProcessOnOpen') !== 'false') {
        triggerAIBatch();
    }

});
