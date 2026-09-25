// ─── Settings module — extracted from app.js ──────────────────────
// All code is global (not wrapped in modules or DOMContentLoaded).
// Intended to be loaded alongside or instead of the settings portion of app.js.

// DOM element references (set in app.js inside DOMContentLoaded)
const settingsOverlay = document.getElementById('settings-overlay');
const settingsClose = document.getElementById('settings-close');
const settingsList = document.getElementById('settings-list');
const settingsSave = document.getElementById('settings-save');
const settingsRevert = document.getElementById('settings-revert');
const settingsCategories = document.getElementById('settings-categories');
const settingsCategoryTitle = document.getElementById('settings-category-title');
const settingsCategoryDescription = document.getElementById('settings-category-description');
const settingsSearchInput = document.getElementById('settings-search-input');
const sidebarResizer = document.getElementById('sidebar-resizer');
const workspaceSidebar = document.getElementById('workspace-sidebar');
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
        description: 'Connect AI providers to atomic extraction, entity linking, and aggregation.',
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
        description: 'Search behavior settings.',
        items: [
            { key: 'preferredEngine', label: 'Default search engine',
              type: 'select',
              options: [
                  { value: 'https://duckduckgo.com/?q=', label: 'DuckDuckGo' },
                  { value: 'https://google.com/search?q=', label: 'Google' },
                  { value: 'https://www.bing.com/search?q=', label: 'Bing' },
                  { value: 'https://search.brave.com/search?q=', label: 'Brave' },
                  { value: 'https://www.startpage.com/do/dsearch?query=', label: 'Startpage' },
              ],
              default: 'https://duckduckgo.com/?q=' },
            { key: 'autoLoad', label: 'Auto load more results on scroll', type: 'checkbox', default: true },
        ]
    },
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
    settingsList.innerHTML = skeletonLoader(6);

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

    /* Legacy per-table AI actions were removed with the atomic model.
    document.getElementById('ai-discover-relations-all')?.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = '⏳ Discovering...';
        const status = document.getElementById('ai-bulk-status');
        status.hidden = true;
        try {
            const r = await fetch('/api/ai/discover-relations-all', { method: 'POST' });
            const d = await r.json();
            if (d.status === 'started') {
                this.textContent = '⏳ Discovering...';
                status.textContent = 'Discovering relations in background — see progress bar above';
                status.style.color = 'var(--text-dim)';
                status.hidden = false;
                pollBatchProgress((finalStatus) => {
                    this.textContent = '🔍 Find relations for all captures';
                    this.disabled = false;
                    status.textContent = `Done: ${finalStatus.processed || 0} processed, ${finalStatus.errors || 0} errors (of ${finalStatus.total || 0} total)`;
                    status.style.color = (finalStatus.errors || 0) > 0 ? '#f87171' : '#22c55e';
                });
            } else if (d.status === 'already_running') {
                this.textContent = '🔍 Find relations for all captures';
                this.disabled = false;
                status.textContent = d.message || 'Already running';
                status.style.color = '#fbbf24';
                status.hidden = false;
            } else {
                this.textContent = '🔍 Find relations for all captures';
                this.disabled = false;
                status.textContent = d.message || 'Done';
                status.style.color = '#22c55e';
                status.hidden = false;
            }
        } catch {
            status.textContent = 'Error running find relations';
            status.style.color = '#f87171';
            status.hidden = false;
            this.textContent = '🔍 Find relations for all captures';
            this.disabled = false;
        }
    });

    // ─── Type All Relations ─────────────────────────────────
    document.getElementById('ai-type-relations-all')?.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = '⏳ Typing...';
        const status = document.getElementById('ai-bulk-status');
        status.hidden = true;
        try {
            const r = await fetch('/api/ai/type-relations-all', { method: 'POST' });
            const d = await r.json();
            if (d.status === 'started') {
                this.textContent = '⏳ Typing...';
                status.textContent = 'Typing relations in background — see progress bar above';
                status.style.color = 'var(--text-dim)';
                status.hidden = false;
                pollBatchProgress((finalStatus) => {
                    this.textContent = '🏷️ Type All Relations (AI)';
                    this.disabled = false;
                    status.textContent = `Done: ${finalStatus.processed || 0} processed, ${finalStatus.errors || 0} errors (of ${finalStatus.total || 0} total)`;
                    status.style.color = (finalStatus.errors || 0) > 0 ? '#f87171' : '#22c55e';
                });
            } else if (d.status === 'already_running') {
                this.textContent = '🏷️ Type All Relations (AI)';
                this.disabled = false;
                status.textContent = d.message || 'Already running';
                status.style.color = '#fbbf24';
                status.hidden = false;
            } else {
                this.textContent = '🏷️ Type All Relations (AI)';
                this.disabled = false;
                status.textContent = d.message || 'Done';
                status.style.color = '#22c55e';
                status.hidden = false;
            }
        } catch {
            status.textContent = 'Error running type relations';
            status.style.color = '#f87171';
            status.hidden = false;
            this.textContent = '🏷️ Type All Relations (AI)';
            this.disabled = false;
        }
    });

    // ─── Extract Facts for All ───────────────────────────────
    document.getElementById('ai-extract-facts-all')?.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = '⏳ Extracting facts...';
        const status = document.getElementById('ai-bulk-status');
        status.hidden = true;
        try {
            const r = await fetch('/api/ai/extract-facts-all', { method: 'POST' });
            const d = await r.json();
            if (d.status === 'started') {
                this.textContent = '⏳ Extracting facts...';
                status.textContent = 'Extracting facts in background — see progress bar above';
                status.style.color = 'var(--text-dim)';
                status.hidden = false;
                pollBatchProgress((finalStatus) => {
                    this.textContent = '💡 Extract Facts (AI)';
                    this.disabled = false;
                    status.textContent = `Done: ${finalStatus.processed || 0} processed, ${finalStatus.errors || 0} errors (of ${finalStatus.total || 0} total)`;
                    status.style.color = (finalStatus.errors || 0) > 0 ? '#f87171' : '#22c55e';
                });
            } else if (d.status === 'already_running') {
                this.textContent = '💡 Extract Facts (AI)';
                this.disabled = false;
                status.textContent = d.message || 'Already running';
                status.style.color = '#fbbf24';
                status.hidden = false;
            } else {
                this.textContent = '💡 Extract Facts (AI)';
                this.disabled = false;
                status.textContent = d.message || 'Done';
                status.style.color = '#22c55e';
                status.hidden = false;
            }
        } catch {
            status.textContent = 'Error running fact extraction';
            status.style.color = '#f87171';
            status.hidden = false;
            this.textContent = '💡 Extract Facts (AI)';
            this.disabled = false;
            showToast('Fact extraction failed. Check API key in Settings.', 'error', 5000);
        }
    });

    */
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
    // Load server auto_update setting
    try {
        const sr = await fetch('/api/server/settings');
        if (sr.ok) {
            const sd = await sr.json();
            if (sd.auto_update !== undefined) {
                settingsState.autoUpdate = sd.auto_update;
            }
        }
    } catch {}
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
            fetch('/api/server/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_update: toggle.checked }),
            }).catch(() => {});
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

function getAnimationSpeedStr() { return settingsState.animationSpeed || 'fast'; }

// ─── Tag Management ────────────────────────────────────────────────

let tagManageMode = 'rename';
let tagManageTagData = [];

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
