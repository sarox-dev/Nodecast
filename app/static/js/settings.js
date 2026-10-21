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
const settingsChangeCopy = document.getElementById('settings-change-copy');
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


let activeSettingsCategory = localStorage.getItem('activeSettingsCategory') || 'Overview';
let accountData = null;
let currentSettingsUser = null;
let _dirty = false;
let _tabSnapshot = {};
let _savedInterval = 60;
const settingsSchema = [
    {
        category: 'Overview',
        description: 'Your Nodecast workspace at a glance.',
        items: []
    },
    {
        category: 'Account',
        description: 'Your account settings.',
        items: []  // Custom rendering
    },
    {
        category: 'AI',
        description: 'Connect AI providers to extract saved evidence and answer questions from your library.',
        items: []  // Custom rendering
    },
    {
        category: 'Updates',
        description: 'Check the installed version and control automatic updates for this Nodecast installation.',
        items: [
            { key: 'autoUpdate', label: 'Install updates automatically', type: 'checkbox', default: false },
        ]
    },
    {
        category: 'Extension',
        description: 'Connect the browser extension and control how captures are saved.',
        items: []  // Custom rendering, persisted per Nodecast account
    },
    {
        category: 'Appearance',
        description: 'Choose a complete color system and tune motion independently.',
        layout: 'sections',
        items: [
            { key: 'theme', label: 'Color mode', description: 'Dark and Light use curated accessible palettes. Custom starts from the same semantic color roles.', type: 'segmented', options: [{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }, { value: 'custom', label: 'Custom' }], default: 'dark', span: 2 },
            { key: 'customPrimary', label: 'Primary', description: 'Focus, selected controls and primary actions.', type: 'color', default: '#818cf8', visibleWhen: { key: 'theme', value: 'custom' } },
            { key: 'customSecondary', label: 'Secondary', description: 'Supporting emphasis and saved-content accents.', type: 'color', default: '#60a5fa', visibleWhen: { key: 'theme', value: 'custom' } },
            { key: 'customBackground', label: 'Background', description: 'Base canvas; surfaces and borders are derived from it.', type: 'color', default: '#0b0f14', visibleWhen: { key: 'theme', value: 'custom' }, span: 2 },
            { key: 'customIconTone', label: 'Icon and text color', description: 'Choose a light or dark foreground for all text and icons in the custom palette.', type: 'segmented', options: [{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }], default: 'light', visibleWhen: { key: 'theme', value: 'custom' }, span: 2 },
            { key: 'animationDuration', label: 'Interface animation', description: 'Duration used by panels, focus states and view transitions.', type: 'range', min: 0, max: 600, step: 20, unit: 'ms', default: 160, span: 2 },
            { key: 'graphMotion', label: 'Constellation motion', description: 'Strength of pointer repulsion and ambient graph movement.', type: 'range', min: 0, max: 200, step: 10, unit: '%', default: 100, span: 2 },
            { key: 'respectSystemMotion', label: 'Respect system motion preference', description: 'When enabled, Nodecast disables non-essential movement if the operating system requests reduced motion.', type: 'toggle', default: true, span: 2 }
        ]
    },
    {
        category: 'Shortcuts',
        description: 'Keyboard shortcuts available across the Nodecast workspace.',
        items: []
    },
    {
        category: 'Search',
        description: 'Choose where Web Search redirects and which provider supplies suggestions before Enter.',
        items: [
            { key: 'preferredEngine', label: 'Redirect Web Search to',
              type: 'select',
              options: [
                  { value: 'https://duckduckgo.com/?q=', label: 'DuckDuckGo' },
                  { value: 'https://google.com/search?q=', label: 'Google' },
                  { value: 'https://www.bing.com/search?q=', label: 'Bing' },
                  { value: 'https://search.brave.com/search?q=', label: 'Brave' },
                  { value: 'https://www.startpage.com/do/dsearch?query=', label: 'Startpage' },
                  { value: 'custom', label: 'Custom URL template' },
              ],
              default: 'https://duckduckgo.com/?q=' },
            { key: 'customSearchUrl', label: 'Custom search URL — use {query}', type: 'text', default: '' },
            { key: 'suggestionsEnabled', label: 'Show query suggestions while typing', type: 'checkbox', default: true },
            { key: 'suggestionProvider', label: 'Suggestion provider',
              type: 'select',
              options: [
                  { value: 'duckduckgo', label: 'DuckDuckGo' },
                  { value: 'google', label: 'Google' },
                  { value: 'bing', label: 'Bing' },
                  { value: 'none', label: 'None' },
              ],
              default: 'duckduckgo' },
            { key: 'webSearchOpenMode', label: 'Open results',
              type: 'select',
              options: [
                  { value: 'same-tab', label: 'In the current tab' },
                  { value: 'new-tab', label: 'In a new tab' },
              ],
              default: 'same-tab' },
            { key: 'autoLoad', label: 'Auto load more results on scroll', type: 'checkbox', default: true },
        ]
    },
];

const settingsState = {};
const SETTINGS_CATEGORY_META = {
    Overview: { icon: '<path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-13h6V4h-6v3Z"/>' },
    Account: { icon: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>' },
    AI: { icon: '<rect x="5" y="7" width="14" height="12" rx="3"/><path d="M12 3v4M8.5 12h.01m6.99 0h.01M9 16h6M3 11v4m18-4v4"/>' },
    Updates: { icon: '<path d="M20 12a8 8 0 1 1-2.3-5.7L20 8"/><path d="M20 3v5h-5"/>' },
    Extension: { icon: '<path d="M8.5 3H4a1 1 0 0 0-1 1v4.5a2.5 2.5 0 1 1 0 5V20a1 1 0 0 0 1 1h6.5a2.5 2.5 0 1 1 5 0H20a1 1 0 0 0 1-1v-4.5a2.5 2.5 0 1 0 0-5V4a1 1 0 0 0-1-1h-6.5a2.5 2.5 0 1 0-5 0Z"/>' },
    Appearance: { icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18c2 0 3-1.5 1.8-3.2-.8-1.1 0-2.8 1.4-2.8H18a3 3 0 0 0 3-3c0-5-4-9-9-9Z"/>' },
    Shortcuts: { icon: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h2m2 0h2m2 0h2M7 13h6m2 0h2"/>' },
    Search: { icon: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>' },
};

function settingsIcon(category) {
    return `<svg class="settings-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SETTINGS_CATEGORY_META[category]?.icon || ''}</svg>`;
}

const NODECAST_SHORTCUTS = [
    { id: 'toggle_mode', label: 'Toggle Web / Ask mode', default: 'Mod+K' },
    { id: 'submit_query', label: 'Run current search or question', default: 'Enter' },
    { id: 'suggestion_next', label: 'Next search suggestion', default: 'ArrowDown' },
    { id: 'suggestion_previous', label: 'Previous search suggestion', default: 'ArrowUp' },
    { id: 'close_view', label: 'Close current result view', default: 'Escape' },
];
let shortcutDraft = null;

function shortcutValue(id) {
    const definition = NODECAST_SHORTCUTS.find(item => item.id === id);
    return localStorage.getItem(`shortcut.${id}`) ?? definition?.default ?? '';
}

function shortcutFromEvent(event) {
    const modifiers = [];
    if (event.ctrlKey || event.metaKey) modifiers.push('Mod');
    if (event.altKey) modifiers.push('Alt');
    if (event.shiftKey) modifiers.push('Shift');
    const ignored = ['Control', 'Meta', 'Alt', 'Shift'];
    if (ignored.includes(event.key)) return '';
    const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
    return [...modifiers, key].join('+');
}

function shortcutMatches(event, id) {
    const parts = shortcutValue(id).split('+').filter(Boolean);
    if (!parts.length) return false;
    const expectedKey = parts.at(-1);
    const actualKey = event.key.length === 1 ? event.key.toUpperCase() : event.key;
    return actualKey === expectedKey
        && (parts.includes('Mod') === (event.ctrlKey || event.metaKey))
        && (parts.includes('Alt') === event.altKey)
        && (parts.includes('Shift') === event.shiftKey);
}
window.nodecastShortcutMatches = shortcutMatches;

function infoTip(text, label = 'More information') {
    if (!text) return '';
    return `<span class="settings-info"><button type="button" class="settings-info-button" aria-label="${escapeHtml(label)}">i</button><span class="settings-info-popover" role="tooltip">${escapeHtml(text)}</span></span>`;
}

function positionInfoPopover(info) {
    const popover = info?.querySelector('.settings-info-popover');
    const button = info?.querySelector('.settings-info-button');
    if (!popover || !button) return;
    const edge = 10;
    const gap = 8;
    const anchor = button.getBoundingClientRect();
    const box = popover.getBoundingClientRect();
    let left = anchor.left + (anchor.width - box.width) / 2;
    left = Math.max(edge, Math.min(left, window.innerWidth - box.width - edge));
    let top = anchor.top - box.height - gap;
    let placement = 'top';
    if (top < edge) {
        top = anchor.bottom + gap;
        placement = 'bottom';
    }
    if (top + box.height > window.innerHeight - edge) {
        top = Math.max(edge, window.innerHeight - box.height - edge);
    }
    popover.style.left = `${Math.round(left)}px`;
    popover.style.top = `${Math.round(top)}px`;
    popover.dataset.placement = placement;
}

document.addEventListener('pointerover', event => {
    const info = event.target.closest?.('.settings-info');
    if (info) positionInfoPopover(info);
});
document.addEventListener('focusin', event => {
    const info = event.target.closest?.('.settings-info');
    if (info) positionInfoPopover(info);
});
window.addEventListener('resize', () => {
    document.querySelectorAll('.settings-info:hover, .settings-info:focus-within').forEach(positionInfoPopover);
});
document.querySelector('.settings-main')?.addEventListener('scroll', () => {
    document.querySelectorAll('.settings-info:hover, .settings-info:focus-within').forEach(positionInfoPopover);
}, { passive: true });

function resetButton(item, value) {
    if (!Object.prototype.hasOwnProperty.call(item, 'default')) return '';
    const isDefault = JSON.stringify(value) === JSON.stringify(item.default);
    return `<button type="button" class="settings-reset" data-reset-key="${escapeHtml(item.key)}" aria-label="Reset ${escapeHtml(item.label)} to default" title="Reset to default" ${isDefault ? 'disabled' : ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button>`;
}

function visibleSettingsSchema() {
    return settingsSchema.filter(category => category.category !== 'Updates' || currentSettingsUser?.is_admin);
}

async function loadCurrentSettingsUser() {
    if (currentSettingsUser) return currentSettingsUser;
    try {
        const response = await fetch('/auth/me');
        currentSettingsUser = response.ok ? await response.json() : null;
    } catch {
        currentSettingsUser = null;
    }
    return currentSettingsUser;
}

// Settings must remain usable when an optional provider, extension, or network
// request is unavailable.  In particular, never leave a skeleton indefinitely.
async function fetchSettingsJson(url, fallback = null, timeout = 5000, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        return response.ok ? await response.json() : fallback;
    } catch {
        return fallback;
    } finally {
        clearTimeout(timer);
    }
}

async function getExtensionStatus(timeout = 3000) {
    const fallback = { detected: false, connected: false };
    const ready = window.nodecastExtension?.whenReady?.();
    if (!ready) return fallback;
    return Promise.race([
        Promise.resolve(ready).catch(() => fallback),
        new Promise(resolve => setTimeout(() => resolve(fallback), timeout)),
    ]);
}

function getValue(item) {
    const stored = localStorage.getItem(item.key);
    if (stored === null) return item.default;
    if (item.type === 'checkbox' || item.type === 'toggle') return stored === 'true';
    if (item.type === 'number' || item.type === 'range') return Number(stored);
    if (item.type === 'multiselect') {
        try { return JSON.parse(stored); } catch { return item.default || []; }
    }
    return stored;
}

function setValue(key, value) {
    settingsState[key] = value;
    localStorage.setItem(key, Array.isArray(value) ? JSON.stringify(value) : String(value));
}

function createField(item) {
    const value = getValue(item);
    settingsState[item.key] = value;
    const categoryAttr = item.category ? ` data-category="${escapeHtml(item.category)}"` : '';
    const spanClass = item.span === 2 ? ' settings-span-2' : '';
    const visibility = item.visibleWhen
        ? ` data-visible-key="${escapeHtml(item.visibleWhen.key)}" data-visible-value="${escapeHtml(String(item.visibleWhen.value))}"`
        : '';
    const copy = `<span class="settings-field-copy"><strong>${escapeHtml(item.label)}${infoTip(item.description, `About ${item.label}`)}</strong></span>`;
    const wrapper = (control, extraClass = '') => `<label class="settings-field settings-control settings-control-${item.type}${spanClass}${extraClass}" data-setting-label="${escapeHtml(item.label)}"${categoryAttr}${visibility}>${copy}<span class="settings-control-slot">${control}${resetButton(item, value)}</span></label>`;
    if (item.type === 'select') {
        return wrapper(`<select data-key="${escapeHtml(item.key)}">${item.options.map(o => `<option value="${escapeHtml(o.value)}" ${o.value === value ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}</select>`);
    }
    if (item.type === 'checkbox' || item.type === 'toggle') {
        return wrapper(`<input type="checkbox" role="switch" data-key="${escapeHtml(item.key)}" ${value ? 'checked' : ''} />`, ' toggle-field');
    }
    if (item.type === 'segmented') {
        const buttons = item.options.map(option => `<button type="button" class="settings-segment${option.value === value ? ' active' : ''}" data-segment-value="${escapeHtml(option.value)}" aria-pressed="${option.value === value}">${escapeHtml(option.label)}</button>`).join('');
        return wrapper(`<input type="hidden" data-key="${escapeHtml(item.key)}" value="${escapeHtml(value)}"><span class="settings-segmented" role="group" aria-label="${escapeHtml(item.label)}">${buttons}</span>`);
    }
    if (item.type === 'range') {
        return wrapper(`<span class="settings-range"><input type="range" data-key="${escapeHtml(item.key)}" value="${value}" min="${item.min}" max="${item.max}" step="${item.step || 1}"><output>${value}${escapeHtml(item.unit || '')}</output></span>`);
    }
    if (item.type === 'color') {
        return wrapper(`<span class="settings-color"><input type="color" data-key="${escapeHtml(item.key)}" value="${escapeHtml(value)}"><output>${escapeHtml(value)}</output></span>`);
    }
    if (item.type === 'multiselect') {
        const selected = Array.isArray(value) ? value : [];
        return wrapper(`<select multiple data-key="${escapeHtml(item.key)}">${item.options.map(o => `<option value="${escapeHtml(o.value)}" ${selected.includes(o.value) ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}</select>`);
    }
    if (item.type === 'button') {
        return wrapper(`<button type="button" class="modal-btn" data-setting-action="${escapeHtml(item.action || item.key)}">${escapeHtml(item.buttonLabel || item.label)}</button>`);
    }
    if (item.type === 'info') {
        return `<div class="settings-field settings-control settings-control-info${spanClass}"${categoryAttr}>${copy}</div>`;
    }
    return wrapper(`<input type="${escapeHtml(item.type)}" data-key="${escapeHtml(item.key)}" value="${escapeHtml(value)}" min="${item.min ?? ''}" max="${item.max ?? ''}" />`);
}

function updateConditionalSettings() {
    settingsList.querySelectorAll('[data-visible-key]').forEach(field => {
        const controller = settingsList.querySelector(`[data-key="${field.dataset.visibleKey}"]`);
        const current = controller?.type === 'checkbox' ? String(controller.checked) : String(controller?.value ?? '');
        field.hidden = current !== field.dataset.visibleValue;
    });
}

function bindGenericSettingsControls() {
    settingsList.querySelectorAll('.settings-segmented').forEach(group => {
        group.addEventListener('click', event => {
            const button = event.target.closest('[data-segment-value]');
            if (!button) return;
            const input = group.parentElement.querySelector('input[type="hidden"]');
            input.value = button.dataset.segmentValue;
            group.querySelectorAll('.settings-segment').forEach(candidate => {
                const active = candidate === button;
                candidate.classList.toggle('active', active);
                candidate.setAttribute('aria-pressed', String(active));
            });
            _markDirty();
            updateConditionalSettings();
            refreshResetButtons();
        });
    });
    settingsList.querySelectorAll('.settings-range input').forEach(input => {
        input.addEventListener('input', () => {
            const item = settingsSchema.flatMap(category => category.items).find(candidate => candidate.key === input.dataset.key);
            input.nextElementSibling.textContent = `${input.value}${item?.unit || ''}`;
            _markDirty();
            refreshResetButtons();
        });
    });
    settingsList.querySelectorAll('.settings-color input').forEach(input => {
        input.addEventListener('input', () => {
            input.nextElementSibling.textContent = input.value.toUpperCase();
            _markDirty();
            refreshResetButtons();
        });
    });
    settingsList.querySelectorAll('[data-reset-key]').forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            const item = settingsSchema.flatMap(category => category.items).find(candidate => candidate.key === button.dataset.resetKey);
            const input = settingsList.querySelector(`[data-key="${button.dataset.resetKey}"]`);
            if (!item || !input) return;
            if (item.type === 'checkbox' || item.type === 'toggle') input.checked = Boolean(item.default);
            else if (item.type === 'multiselect') [...input.options].forEach(option => { option.selected = (item.default || []).includes(option.value); });
            else input.value = item.default ?? '';
            if (item.type === 'segmented') {
                input.parentElement.querySelectorAll('[data-segment-value]').forEach(segment => {
                    const active = segment.dataset.segmentValue === String(item.default);
                    segment.classList.toggle('active', active);
                    segment.setAttribute('aria-pressed', String(active));
                });
            }
            if (item.type === 'range') input.nextElementSibling.textContent = `${input.value}${item.unit || ''}`;
            if (item.type === 'color') input.nextElementSibling.textContent = input.value.toUpperCase();
            button.disabled = true;
            _markDirty();
            updateConditionalSettings();
        });
    });
    updateConditionalSettings();
}

function refreshResetButtons() {
    settingsList.querySelectorAll('[data-reset-key]').forEach(button => {
        const item = settingsSchema.flatMap(category => category.items).find(candidate => candidate.key === button.dataset.resetKey);
        const input = settingsList.querySelector(`[data-key="${button.dataset.resetKey}"]`);
        if (!item || !input) return;
        let current = input.value;
        if (item.type === 'checkbox' || item.type === 'toggle') current = input.checked;
        if (item.type === 'number' || item.type === 'range') current = Number(input.value);
        if (item.type === 'multiselect') current = [...input.selectedOptions].map(option => option.value);
        button.disabled = JSON.stringify(current) === JSON.stringify(item.default);
    });
}

function renderCategoryNav() {
    settingsCategories.innerHTML = visibleSettingsSchema().map(cat => `
        <li class="settings-category-item">
          <button type="button" class="settings-category-button${cat.category === activeSettingsCategory ? ' active' : ''}" data-category="${cat.category}">
            ${settingsIcon(cat.category)}
            <span class="settings-category-copy"><strong>${cat.category}</strong></span>
          </button>
        </li>
    `).join('');
}

function renderSettings() {
    if (activeSettingsCategory === 'Updates' && !currentSettingsUser?.is_admin) activeSettingsCategory = 'Overview';
    const category = settingsSchema.find(cat => cat.category === activeSettingsCategory) || settingsSchema[0];
    settingsCategoryTitle.textContent = category.category;
    settingsCategoryDescription.textContent = '';
    settingsList.className = 'settings-list';
    if (category.category === 'Overview') {
        renderSettingsOverview();
        return;
    } else if (category.category === 'Account') {
        renderAccountSettings();
    } else if (category.category === 'AI') {
        renderAISettings();
    } else if (category.category === 'Updates') {
        renderUpdatesSettings();
    } else if (category.category === 'Extension') {
        renderExtensionSettings();
        return;
    } else if (category.category === 'Shortcuts') {
        renderShortcutSettings();
        return;
    } else {
        settingsList.className = `settings-list settings-layout-${category.layout || 'list'}`;
        settingsList.innerHTML = category.items.map(item => createField({ ...item, category: category.category })).join('');
        bindGenericSettingsControls();
    }
    if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
    _snapshotTab();
    _clearDirty();
}

function _snapshotTab() {
    _tabSnapshot = {};
    const category = settingsSchema.find(cat => cat.category === activeSettingsCategory);
    if (!category || ['Overview', 'Account', 'AI', 'Updates', 'Extension', 'Shortcuts'].includes(category.category)) return;
    category.items.forEach(item => {
        _tabSnapshot[item.key] = getValue(item);
    });
}

async function renderSettingsOverview() {
    settingsList.innerHTML = '<div class="settings-overview-loading">Loading workspace status…</div>';
    const [extension, account, providerData, serverSettings] = await Promise.all([
        getExtensionStatus(),
        fetchSettingsJson('/auth/me'),
        fetchSettingsJson('/api/ai/providers'),
        fetchSettingsJson('/api/server/settings'),
    ]);
    currentSettingsUser = account;
    if (activeSettingsCategory !== 'Overview' || settingsSearchInput?.value.trim()) return;

    const storedTheme = localStorage.getItem('theme') || 'dark';
    const theme = storedTheme === 'light' ? 'light' : 'dark';
    const engine = localStorage.getItem('preferredEngine') || 'https://duckduckgo.com/?q=';
    let engineName = 'DuckDuckGo';
    try { engineName = engine === 'custom' ? 'Custom provider' : new URL(engine).hostname.replace(/^www\./, ''); } catch {}
    const extensionState = extension.connected ? 'Connected' : (extension.detected ? 'Ready to connect' : 'Not installed');
    const providerCount = Array.isArray(providerData?.providers) ? providerData.providers.length : 0;
    const updateNotifications = serverSettings?.auto_update ?? getValue(settingsSchema.find(category => category.category === 'Updates').items[0]);
    const overviewDetails = {
        Account: account?.username || 'Local user',
        AI: `${providerCount} ${providerCount === 1 ? 'provider' : 'providers'}`,
        Updates: updateNotifications ? 'Automatic updates on' : 'Automatic updates off',
        Extension: extensionState,
        Appearance: theme[0].toUpperCase() + theme.slice(1),
        Shortcuts: '5 available',
        Search: engineName,
    };
    const overviewRows = visibleSettingsSchema()
        .filter(category => category.category !== 'Overview')
        .map(category => {
            const detail = overviewDetails[category.category] || SETTINGS_CATEGORY_META[category.category]?.hint || 'Open settings';
            const statusClass = category.category === 'Extension' ? ` class="status-${extension.connected ? 'ok' : 'muted'}"` : '';
            return `<button type="button" class="settings-overview-row" data-open-settings="${escapeHtml(category.category)}"><span>${escapeHtml(category.category)}</span><strong${statusClass}>${escapeHtml(detail)}</strong><span class="row-arrow">›</span></button>`;
        })
        .join('');

    settingsList.innerHTML = `
      <div class="settings-overview" data-category="Overview">
        <div class="settings-overview-grid">
          ${overviewRows}
        </div>
      </div>`;
    settingsList.querySelectorAll('[data-open-settings]').forEach(button => {
        button.addEventListener('click', () => openSettings(button.dataset.openSettings));
    });
    _clearDirty();
}

async function renderExtensionSettings() {
    settingsList.innerHTML = '<div class="extension-settings-loading">Checking extension connection…</div>';
    const [status, remote] = await Promise.all([
        getExtensionStatus(),
        fetchSettingsJson('/api/extension/settings'),
    ]);
    if (activeSettingsCategory !== 'Extension' || settingsSearchInput?.value.trim()) return;

    const settings = remote?.settings || {
        floating_button_enabled: true,
        min_selection_length: 10,
        notification_position: 'top-center',
        default_project: '',
    };
    const stateClass = status.connected ? 'connected' : (status.detected ? 'available' : 'missing');
    const username = status.username || remote?.username || 'this account';
    const isFirefox = /Firefox/i.test(navigator.userAgent);
    const browserName = isFirefox ? 'Firefox-based' : 'Chromium-based';

    settingsList.innerHTML = `
      <div class="extension-settings" data-category="Extension">
        <section class="extension-connection-card ${stateClass}">
          <div class="extension-connection-main">
            <div><strong>${status.connected ? `Connected as <span class="extension-account-name">${escapeHtml(username)}</span>` : (status.detected ? 'Extension ready to connect' : 'Extension not installed')}</strong>
            ${!status.detected ? `<p>Install the ${browserName} build from <a href="https://github.com/sarox-dev/Nodecast-Extension/releases" target="_blank" rel="noopener">Nodecast Extension releases</a>, then return here.</p>` : (!status.connected ? '<p>Connect once to save captures into this account.</p>' : '')}</div>
          </div>
          <div class="extension-connection-meta">${status.version ? `v${escapeHtml(status.version)}` : ''}</div>
          <div class="extension-connection-actions">
            ${!status.detected ? '<a class="modal-btn modal-btn-primary" href="https://github.com/sarox-dev/Nodecast-Extension/releases" target="_blank" rel="noopener">Open releases</a>' : ''}
            ${status.detected && !status.connected ? '<button type="button" class="primary" data-extension-action="connect">Connect to this account</button>' : ''}
            <button type="button" data-extension-action="check">Check connection</button>
            ${status.connected ? '<button type="button" data-extension-action="disconnect">Disconnect</button>' : ''}
          </div>
          <div class="extension-action-status" aria-live="polite"></div>
        </section>
        <section class="extension-preferences" ${status.connected ? '' : 'aria-disabled="true"'}>
          <div class="settings-module-heading"><h4>Capture behavior${infoTip('The floating button saves immediately. Keyboard shortcut and right-click remain available as fallback methods.')}</h4></div>
          <label class="settings-field toggle-field"><span>Show floating Save button</span><span class="settings-control-slot"><input type="checkbox" data-key="floating_button_enabled" ${settings.floating_button_enabled ? 'checked' : ''} ${status.connected ? '' : 'disabled'} /><button type="button" class="settings-reset" data-extension-reset="floating_button_enabled" ${settings.floating_button_enabled === true ? 'disabled' : ''} aria-label="Reset floating Save button"><svg viewBox="0 0 24 24"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button></span></label>
          <label class="settings-field"><span>Minimum selection length${infoTip('The floating Save control appears only after at least this many characters are selected.')}</span><span class="settings-control-slot"><input type="number" data-key="min_selection_length" min="1" max="500" value="${Number(settings.min_selection_length) || 10}" ${status.connected ? '' : 'disabled'} /><button type="button" class="settings-reset" data-extension-reset="min_selection_length" ${Number(settings.min_selection_length) === 10 ? 'disabled' : ''} aria-label="Reset minimum selection length"><svg viewBox="0 0 24 24"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button></span></label>
          <label class="settings-field"><span>Save notification position</span><span class="settings-control-slot"><select data-key="notification_position" ${status.connected ? '' : 'disabled'}>${['top-left','top-center','top-right','bottom-left','bottom-center','bottom-right'].map(value => `<option value="${value}" ${settings.notification_position === value ? 'selected' : ''}>${value.replace('-', ' ')}</option>`).join('')}</select><button type="button" class="settings-reset" data-extension-reset="notification_position" ${settings.notification_position === 'top-center' ? 'disabled' : ''} aria-label="Reset notification position"><svg viewBox="0 0 24 24"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button></span></label>
          <label class="settings-field"><span>Default project</span><span class="settings-control-slot"><input type="text" data-key="default_project" maxlength="200" value="${escapeHtml(settings.default_project || '')}" placeholder="No project" ${status.connected ? '' : 'disabled'} /><button type="button" class="settings-reset" data-extension-reset="default_project" ${!settings.default_project ? 'disabled' : ''} aria-label="Reset default project"><svg viewBox="0 0 24 24"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button></span></label>
        </section>
      </div>`;

    _tabSnapshot = { ...settings };
    _clearDirty();

    settingsList.querySelectorAll('[data-extension-action]').forEach(button => {
        button.addEventListener('click', async () => {
            const output = settingsList.querySelector('.extension-action-status');
            button.disabled = true;
            output.textContent = '';
            try {
                if (button.dataset.extensionAction === 'connect') {
                    output.textContent = 'Connecting…';
                    await window.nodecastExtension.pair();
                    output.textContent = 'Connected.';
                } else if (button.dataset.extensionAction === 'disconnect') {
                    await window.nodecastExtension.disconnect();
                } else if (button.dataset.extensionAction === 'check') {
                    output.textContent = 'Checking…';
                    const refreshed = await window.nodecastExtension.refresh();
                    if (refreshed?.connected) {
                        const result = await window.nodecastExtension.syncSettings();
                        if (!result?.success) throw new Error(result?.message || 'Connection check failed');
                    }
                }
                await renderExtensionSettings();
            } catch (error) {
                output.textContent = error.message;
                output.classList.add('error');
                button.disabled = false;
            }
        });
    });
    const extensionDefaults = { floating_button_enabled: true, min_selection_length: 10, notification_position: 'top-center', default_project: '' };
    settingsList.querySelectorAll('[data-extension-reset]').forEach(button => button.addEventListener('click', event => {
        event.preventDefault();
        const key = button.dataset.extensionReset;
        const input = settingsList.querySelector(`[data-key="${key}"]`);
        if (input.type === 'checkbox') input.checked = extensionDefaults[key]; else input.value = extensionDefaults[key];
        button.disabled = true;
        _markDirty();
    }));
    settingsList.querySelectorAll('.extension-preferences [data-key]').forEach(input => input.addEventListener('input', () => {
        const button = settingsList.querySelector(`[data-extension-reset="${input.dataset.key}"]`);
        const current = input.type === 'checkbox' ? input.checked : (input.type === 'number' ? Number(input.value) : input.value);
        if (button) button.disabled = current === extensionDefaults[input.dataset.key];
    }));
}

function _markDirty() {
    if (_dirty) return;
    _dirty = true;
    document.getElementById('settings-save').disabled = false;
    document.getElementById('settings-revert').disabled = false;
    document.getElementById('settings-actions-bar')?.classList.add('has-changes');
    if (settingsChangeCopy) settingsChangeCopy.textContent = 'Unsaved changes';
}

function _clearDirty() {
    _dirty = false;
    const saveBtn = document.getElementById('settings-save');
    const revertBtn = document.getElementById('settings-revert');
    if (saveBtn) saveBtn.disabled = true;
    if (revertBtn) revertBtn.disabled = true;
    document.getElementById('settings-actions-bar')?.classList.remove('has-changes');
    if (settingsChangeCopy) settingsChangeCopy.textContent = 'No unsaved changes';
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
    let user = null, users = null, settings = null, sessionAccounts = [];
    try {
        const r1 = await fetch('/auth/me');
        user = r1.ok ? await r1.json() : null;
        const r2 = await fetch('/auth/settings');
        settings = r2.ok ? await r2.json() : null;
        const r4 = await fetch('/auth/accounts');
        sessionAccounts = r4.ok ? (await r4.json()).accounts || [] : [];
    } catch {}
    // Try to get users list
    try {
        const r3 = await fetch('/auth/users');
        users = r3.ok ? (await r3.json()).users : null;
    } catch {}

    settingsList.innerHTML = `<div class="account-settings" data-category="Account">
      <section class="settings-module">
        <div class="settings-module-heading"><h4>Profile</h4>${infoTip('Update the username used by this Nodecast account.')}</div>
        <div class="account-identity"><span class="account-avatar">${escapeHtml((user?.username || '?')[0].toUpperCase())}</span><span><strong>${escapeHtml(user?.username || '')}</strong><small>${user?.is_admin ? 'Current administrator account' : 'Local Nodecast account'}</small></span></div>
        <div class="settings-inline-form">
          <input id="acc-new-username" type="text" placeholder="New username" />
          <input id="acc-username-pw" type="password" placeholder="Current password" />
          <button id="acc-change-username" class="modal-btn modal-btn-primary" type="button">Change username</button>
        </div>
        <span id="acc-username-status" class="note-status" hidden></span>
      </section>
      <section class="settings-module">
        <div class="settings-module-heading"><h4>Password</h4>${infoTip('Changing a password requires the current password. Recovery requests will be added with the new account system.')}</div>
        <div class="settings-inline-form">
          <input id="acc-cur-pw" type="password" placeholder="Current password" />
          <input id="acc-new-pw" type="password" placeholder="New password" />
          <button id="acc-change-pw" class="modal-btn modal-btn-primary" type="button">Change password</button>
        </div>
        <span id="acc-pw-status" class="note-status" hidden></span>
      </section>
      <section class="settings-module account-session-row">
        <div class="account-session-content">
          <div class="settings-module-heading"><h4>Accounts</h4>${infoTip('Accounts authenticated in this browser can be switched without signing every account out. The extension identity is replaced at the same time.')}</div>
          <div class="account-switch-list">${sessionAccounts.map(account => `<button type="button" class="account-switch-item${account.active ? ' active' : ''}" data-switch-account="${escapeHtml(account.id)}" ${account.active ? 'disabled' : ''}><span class="account-avatar">${escapeHtml(account.username[0].toUpperCase())}</span><span><strong>${escapeHtml(account.username)}</strong><small>${escapeHtml(account.role || 'member')}</small></span>${account.active ? '<span>Current</span>' : '<span>Switch</span>'}</button>`).join('')}</div>
          <div class="settings-inline-form account-add-form"><input id="account-add-username" type="text" autocomplete="username" placeholder="Another username"><input id="account-add-password" type="password" autocomplete="current-password" placeholder="Password"><button id="account-add-button" class="modal-btn modal-btn-secondary" type="button">Add account</button></div>
          <span id="account-switch-status" class="note-status" hidden></span>
        </div>
        <button id="account-logout-button" class="modal-btn modal-btn-secondary" type="button">Log out this account</button>
      </section>
    </div>`;

    document.getElementById('account-logout-button')?.addEventListener('click', async () => {
        const response = await fetch('/auth/logout', { method: 'POST' });
        const result = response.ok ? await response.json() : {};
        window.location.href = result.has_active_account ? '/' : '/login';
    });

    async function syncExtensionAccount() {
        const extension = await window.nodecastExtension?.refresh?.();
        if (extension?.detected && extension?.connected) await window.nodecastExtension.pair();
    }
    document.querySelectorAll('[data-switch-account]').forEach(button => button.addEventListener('click', async () => {
        const status = document.getElementById('account-switch-status');
        status.hidden = false; status.textContent = 'Switching account…';
        const response = await fetch('/auth/switch-account', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({user_id: button.dataset.switchAccount}) });
        if (!response.ok) { status.textContent = (await response.json()).detail || 'Could not switch account'; return; }
        try { await syncExtensionAccount(); } catch { /* old bound token is invalid after the Core switch */ }
        window.location.reload();
    }));
    document.getElementById('account-add-button')?.addEventListener('click', async () => {
        const status = document.getElementById('account-switch-status');
        status.hidden = false; status.textContent = 'Authenticating account…';
        const response = await fetch('/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username: document.getElementById('account-add-username').value.trim(), password: document.getElementById('account-add-password').value}) });
        if (!response.ok) { status.textContent = (await response.json()).detail || 'Could not add account'; return; }
        try { await syncExtensionAccount(); } catch { /* extension can be reconnected from its settings */ }
        window.location.reload();
    });

    // Bind event handlers
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

function renderShortcutSettings() {
    shortcutDraft = Object.fromEntries(NODECAST_SHORTCUTS.map(item => [item.id, shortcutValue(item.id)]));
    const display = value => value.replace('Mod', /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl').replace('ArrowDown', '↓').replace('ArrowUp', '↑');
    settingsList.innerHTML = `<div class="shortcut-list" data-category="Shortcuts">${NODECAST_SHORTCUTS.map(item => `
      <div class="settings-field shortcut-row" data-shortcut-row="${item.id}">
        <span>${escapeHtml(item.label)}${infoTip('Click the key field, then press a new shortcut. Backspace or Delete restores the default.')}</span>
        <span class="shortcut-control">
          <button type="button" class="shortcut-capture" data-shortcut-id="${item.id}" aria-label="Change ${escapeHtml(item.label)}">${escapeHtml(display(shortcutDraft[item.id]) || 'Not set')}</button>
          <button type="button" class="settings-reset shortcut-reset" data-shortcut-reset="${item.id}" aria-label="Reset ${escapeHtml(item.label)}" ${shortcutDraft[item.id] === item.default ? 'disabled' : ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button>
        </span>
      </div>`).join('')}</div>`;
    settingsList.querySelectorAll('[data-shortcut-id]').forEach(button => {
        button.addEventListener('click', () => {
            settingsList.querySelectorAll('.shortcut-capture.recording').forEach(item => { item.classList.remove('recording'); item.textContent = display(shortcutDraft[item.dataset.shortcutId]) || 'Not set'; });
            button.classList.add('recording');
            button.textContent = 'Press shortcut…';
            button.focus();
        });
        button.addEventListener('keydown', event => {
            if (!button.classList.contains('recording')) return;
            event.preventDefault();
            const definition = NODECAST_SHORTCUTS.find(item => item.id === button.dataset.shortcutId);
            if (event.key === 'Backspace' || event.key === 'Delete') {
                shortcutDraft[definition.id] = definition.default;
            } else if (event.key === 'Escape') {
                button.classList.remove('recording');
                button.textContent = display(shortcutDraft[definition.id]) || 'Not set';
                return;
            } else {
                const value = shortcutFromEvent(event);
                if (!value) return;
                const conflict = Object.entries(shortcutDraft).find(([id, current]) => id !== definition.id && current === value);
                if (conflict) {
                    showToast('That shortcut is already used by Nodecast', 'error');
                    return;
                }
                shortcutDraft[definition.id] = value;
            }
            button.classList.remove('recording');
            button.textContent = display(shortcutDraft[definition.id]) || 'Not set';
            const reset = settingsList.querySelector(`[data-shortcut-reset="${definition.id}"]`);
            if (reset) reset.disabled = shortcutDraft[definition.id] === definition.default;
            _markDirty();
        });
    });
    settingsList.querySelectorAll('[data-shortcut-reset]').forEach(button => button.addEventListener('click', () => {
        const definition = NODECAST_SHORTCUTS.find(item => item.id === button.dataset.shortcutReset);
        shortcutDraft[definition.id] = definition.default;
        const capture = settingsList.querySelector(`[data-shortcut-id="${definition.id}"]`);
        capture.textContent = display(definition.default) || 'Not set';
        button.disabled = true;
        _markDirty();
    }));
    _snapshotTab();
    _clearDirty();
}

// ─── AI Settings ─────────────────────────────────────────────────

let aiProviders = [];
let aiAssignments = [];
let autoAssignProviderId = '';
const providerModelCache = new Map();
const providerModelLoads = new Set();

function queueProviderModelCatalog(provider) {
    if (providerModelLoads.has(provider.id) || providerModelCache.has(provider.id)) return;
    providerModelLoads.add(provider.id);
    providerModelCache.set(provider.id, { models: [], state: 'loading' });
    fetchSettingsJson(`/api/ai/providers/${provider.id}/models`, null, 6500)
        .then(data => {
            providerModelCache.set(provider.id, data
                ? { models: data.models || [], state: data.error ? 'error' : 'ready', error: data.error || '' }
                : { models: [], state: 'error', error: 'timeout' });
        })
        .catch(() => providerModelCache.set(provider.id, { models: [], state: 'error', error: 'timeout' }))
        .finally(() => {
            providerModelLoads.delete(provider.id);
            if (activeSettingsCategory === 'AI') updateProviderCatalogUI(provider.id);
        });
}

function providerStatusMarkup(info) {
    if (info.state === 'ready') {
        return `<span class="ai-connectivity-track"><span>Connected</span><span>${info.models.length} models</span></span>`;
    }
    return info.state === 'loading' ? 'Checking connection' : 'Catalog unavailable';
}

function updateProviderCatalogUI(providerId) {
    const info = providerModelCache.get(providerId) || { models: [], state: 'loading' };
    const status = settingsList.querySelector(`[data-provider-status="${CSS.escape(providerId)}"]`);
    if (status) {
        status.className = `ai-connectivity${info.state === 'ready' ? ' ai-connectivity-ready' : ''}${info.state === 'error' ? ' ai-connectivity-error' : ''}`;
        status.innerHTML = providerStatusMarkup(info);
    }
    settingsList.querySelectorAll('[data-feature]').forEach(row => {
        const provider = row.querySelector('.ai-assign-provider');
        const model = row.querySelector('.ai-assign-model');
        if (provider?.value !== providerId || !model || info.state !== 'ready') return;
        const selected = model.value;
        model.innerHTML = '<option value="">— Select model —</option>' + info.models.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name || item.id)}</option>`).join('');
        if ([...model.options].some(option => option.value === selected)) model.value = selected;
    });
    const providerForAll = document.getElementById('ai-provider-for-all');
    const modelForAll = document.getElementById('ai-model-for-all');
    if (providerForAll?.value === providerId && modelForAll && info.state === 'ready') {
        const selected = modelForAll.value;
        modelForAll.innerHTML = '<option value="">Choose model</option>' + info.models.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name || item.id)}</option>`).join('');
        if ([...modelForAll.options].some(option => option.value === selected)) modelForAll.value = selected;
    }
}

async function renderAISettings() {
    const cat = settingsSchema.find(c => c.category === 'AI');
    const desc = cat ? cat.description : '';
    settingsCategoryDescription.textContent = desc;
    settingsList.innerHTML = skeletonLoader(6);

    // Provider configuration is local. Do not let an unreachable external
    // model catalog block this view from rendering.
    const [providerData, assignmentData] = await Promise.all([
        fetchSettingsJson('/api/ai/providers', { providers: [] }),
        fetchSettingsJson('/api/ai/assignments', { assignments: [] }),
    ]);
    aiProviders = providerData?.providers || [];
    aiAssignments = assignmentData?.assignments || [];
    if (activeSettingsCategory !== 'AI' || settingsSearchInput?.value.trim()) return;

    // Model catalogs are optional remote metadata. They load after the Settings
    // surface renders, so an unavailable provider never leaves this view blocked.
    aiProviders.forEach(queueProviderModelCatalog);

    let html = '<div class="settings-field-group">';

    // Fetch saved interval from server
    const autoProcessSettings = await fetchSettingsJson('/api/ai/auto-process-settings');
    if (autoProcessSettings) _savedInterval = autoProcessSettings.interval_minutes || 60;

    // ─── Providers section ────────────────────────────────────
    html += `<div class="settings-module-heading ai-section-heading"><h4>AI providers${infoTip('Providers supply models for extraction, recall synthesis and other AI features.')}</h4><button id="ai-add-provider-btn" class="modal-btn modal-btn-primary settings-action-button" type="button"><span aria-hidden="true">＋</span> Add provider</button></div>`;

    // Configured providers list
    html += '<div class="settings-list" style="gap:0.3rem">';
    if (aiProviders.length === 0) {
        html += '<div style="color:var(--text-dim);font-size:0.85rem;padding:0.3rem 0">No AI providers configured.</div>';
    } else {
        for (const p of aiProviders) {
            const info = providerModelCache.get(p.id) || { models: [], state: 'loading' };
            const hasAssignment = aiAssignments.some(a => a.provider_id === p.id);
            const providerKey = p.provider_key || '';
            const iconPath = `/static/assets/AI_providers/${providerKey === 'chatgpt' ? 'openai' : providerKey}.svg?v=20261021-2`;
            const iconHtml = providerKey
                ? `<img src="${iconPath}" class="ai-provider-logo" alt="" />`
                : '<span class="ai-provider-logo ai-provider-logo-fallback" aria-hidden="true">AI</span>';
            const statusBadge = `<span class="ai-connectivity${info.state === 'ready' ? ' ai-connectivity-ready' : ''}${info.state === 'error' ? ' ai-connectivity-error' : ''}" data-provider-status="${escapeHtml(p.id)}">${providerStatusMarkup(info)}</span>`;
            html += `<div class="ai-provider-card ${hasAssignment ? 'in-use' : 'unused'}" data-provider-id="${escapeHtml(p.id)}">
              ${iconHtml}
              <div class="ai-provider-copy"><strong title="${escapeHtml(p.name)}">${escapeHtml(p.name.slice(0, 40))}</strong>${statusBadge}</div>
              <div class="ai-provider-actions">
                ${p.provider_type === 'chatgpt_oauth' ? '' : `<button class="ai-edit-provider settings-icon-button" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-url="${escapeHtml(p.base_url)}" data-key="${escapeHtml(providerKey)}" aria-label="Edit ${escapeHtml(p.name)}" title="Edit"><svg viewBox="0 0 24 24"><path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"/><path d="m14 7 3 3"/></svg></button>`}
                <button class="ai-delete-provider settings-icon-button danger" data-id="${p.id}" data-name="${escapeHtml(p.name)}" aria-label="Delete ${escapeHtml(p.name)}" title="Delete"><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5"/></svg></button>
              </div>
            </div>`;
        }
    }
    html += '</div>';

    // ─── Feature assignments section ──────────────────────────
    html += `<div class="settings-module-heading"><h4>Feature assignments${infoTip('Assign a provider and model to each AI function. Bulk controls update all rows but changes are saved only with Save changes.')}</h4></div>`;
    html += '<div class="settings-list" style="gap:0.6rem">';

    // Fetch available features
    const featureData = await fetchSettingsJson('/api/ai/features', { features: [] });
    const features = featureData?.features || [];
    const assignedProviderIds = features.map(feat => aiAssignments.find(item => item.feature === feat.id)?.provider_id || autoAssignProviderId || '');
    const commonProvider = assignedProviderIds.length && assignedProviderIds.every(id => id === assignedProviderIds[0]) ? assignedProviderIds[0] : '';
    const assignedModels = features.map(feat => aiAssignments.find(item => item.feature === feat.id)?.model || '');
    const commonModel = commonProvider && assignedModels.length && assignedModels.every(model => model === assignedModels[0]) ? assignedModels[0] : '';
    const commonCatalog = providerModelCache.get(commonProvider)?.models || [];
    html += `<div class="ai-bulk-assignment">
      <label><span>Provider for all</span><select id="ai-provider-for-all"><option value="">Mixed / not set</option>${aiProviders.map(provider => `<option value="${provider.id}" ${commonProvider === provider.id ? 'selected' : ''}>${escapeHtml(provider.name)}</option>`).join('')}</select></label>
      <label id="ai-model-for-all-wrap" ${commonProvider ? '' : 'hidden'}><span>Model for all</span><select id="ai-model-for-all"><option value="">Choose model</option>${commonCatalog.map(model => `<option value="${escapeHtml(model.id)}" ${commonModel === model.id ? 'selected' : ''}>${escapeHtml(model.name || model.id)}</option>`).join('')}</select></label>
    </div>`;

    for (const feat of features) {
        const assignment = aiAssignments.find(a => a.feature === feat.id);
        const selectedProviderId = assignment?.provider_id || autoAssignProviderId || '';

        // Build model options — pre-populate from fetched models for the assigned provider
        let modelOptions = '<option value="">— Select model —</option>';
        if (assignment) {
            const info = providerModelCache.get(assignment.provider_id);
            if (info && info.models && info.models.length > 0) {
                modelOptions = info.models.map(m =>
                    `<option value="${escapeHtml(m.id)}" ${m.id === assignment.model ? 'selected' : ''}>${escapeHtml(m.name || m.id)}</option>`
                ).join('');
            } else {
                modelOptions = `<option value="${escapeHtml(assignment.model)}" selected>${escapeHtml(assignment.model)}</option>`;
            }
        }

        html += `<div class="settings-field ai-assignment-row">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:600">${escapeHtml(feat.name)}</span>
              ${infoTip(feat.description, `About ${feat.name}`)}
            </div>
          </div>
          <div style="display:flex;gap:0.4rem;align-items:center" data-feature="${feat.id}">
            <select class="ai-assign-provider" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem">
              <option value="">— Select provider —</option>
              ${aiProviders.map(p => `<option value="${p.id}" ${selectedProviderId === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
            </select>
            <select class="ai-assign-model" style="flex:1;padding:0.35rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.82rem" ${assignment ? '' : 'disabled'}>
              ${modelOptions}
            </select>
            <button type="button" class="settings-reset ai-assignment-reset" aria-label="Reset ${escapeHtml(feat.name)} assignment" ${selectedProviderId ? '' : 'disabled'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button>
          </div>
          <span id="ai-assign-status-${feat.id}" class="note-status" hidden></span>
        </div>`;
    }
    html += '</div>';

    // ─── AI Processing section ───────────────────────────────
    html += `<div class="settings-module-heading"><h4>AI processing${infoTip('Process new captures or rebuild all derived AI data. Raw captures remain the immutable source.')}</h4></div>`;
    html += '<div class="settings-list" style="gap:0.4rem">';
    html += `<div class="ai-processing-actions"><button id="ai-process-unprocessed" class="modal-btn modal-btn-primary settings-action-button" type="button"><span aria-hidden="true">▶</span> Process unprocessed</button>`;
    html += `<button id="ai-regenerate-all" class="modal-btn settings-action-button danger" type="button"><span aria-hidden="true">↻</span> Regenerate all data</button></div>`;
    html += `<div id="ai-progress-bar" class="ai-progress-bar" role="progressbar" aria-label="AI processing progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" hidden>
      <div class="ai-progress-copy">
        <span id="ai-progress-text">Preparing AI processing…</span>
        <span id="ai-progress-detail"></span>
      </div>
      <div class="ai-progress-track"><div id="ai-progress-fill" class="ai-progress-fill" style="width:0%"></div></div>
    </div>`;
    html += '<span id="ai-bulk-status" class="note-status" style="margin-top:0.4rem" hidden></span>';

    // Auto-process slider — saves to server
    const batchInterval = getSavedInterval();
    html += `<label class="settings-field" style="flex-direction:column;align-items:stretch;gap:0.3rem;margin-top:0.5rem">
      <div style="display:flex;justify-content:space-between;font-size:0.8rem">
        <span>Auto-process on server every${infoTip('Controls how often the server checks for pending AI enrichment work.')}</span>
        <span><span id="ai-batch-interval-label">${_formatInterval(batchInterval)}</span><button type="button" class="settings-reset" id="ai-batch-interval-reset" aria-label="Reset processing interval" ${batchInterval === 60 ? 'disabled' : ''}><svg viewBox="0 0 24 24"><path d="M4 4v6h6M5.5 15a7 7 0 1 0 .8-7.8L4 10"/></svg></button></span>
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
    document.getElementById('ai-batch-interval-reset')?.addEventListener('click', () => {
        const input = document.getElementById('ai-batch-interval');
        input.value = 60;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('ai-batch-interval-reset').disabled = true;
    });

    document.getElementById('ai-provider-for-all')?.addEventListener('change', async event => {
        const providerId = event.target.value;
        const rows = [...document.querySelectorAll('[data-feature]')];
        rows.forEach(row => {
            const provider = row.querySelector('.ai-assign-provider');
            provider.value = providerId;
            provider.dispatchEvent(new Event('change', { bubbles: true }));
        });
        const modelWrap = document.getElementById('ai-model-for-all-wrap');
        const modelSelect = document.getElementById('ai-model-for-all');
        modelWrap.hidden = !providerId;
        modelSelect.innerHTML = '<option value="">Choose model</option>';
        if (providerId) {
            const data = await fetchSettingsJson(`/api/ai/providers/${providerId}/models`, { models: [] }, 4000);
            modelSelect.innerHTML += (data.models || []).map(model => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.name || model.id)}</option>`).join('');
        }
        _markAIDirty();
    });
    document.getElementById('ai-model-for-all')?.addEventListener('change', event => {
        document.querySelectorAll('.ai-assign-model').forEach(select => {
            if ([...select.options].some(option => option.value === event.target.value)) select.value = event.target.value;
        });
        _markAIDirty();
    });
    document.querySelectorAll('.ai-assignment-reset').forEach(button => button.addEventListener('click', () => {
        const row = button.closest('[data-feature]');
        row.querySelector('.ai-assign-provider').value = '';
        const model = row.querySelector('.ai-assign-model');
        model.innerHTML = '<option value="">— Select model —</option>';
        model.disabled = true;
        button.disabled = true;
        _markAIDirty();
    }));

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
                container.querySelector('.ai-assignment-reset').disabled = true;
                _markAIDirty();
                return;
            }
            modelSel.innerHTML = '<option value="">Loading models...</option>';
            modelSel.disabled = false;
            container.querySelector('.ai-assignment-reset').disabled = false;
            try {
                const data = await fetchSettingsJson(`/api/ai/providers/${providerId}/models`, { models: [] }, 4000);
                if (data.models && data.models.length > 0) {
                    modelSel.innerHTML = '<option value="">— Select model —</option>' + data.models.map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name || m.id)}</option>`).join('');
                } else {
                    const message = data.error === 'reconnect_required' ? 'Reconnect ChatGPT' : 'No models found';
                    modelSel.innerHTML = `<option value="">${message}</option>`;
                    if (data.error && typeof showNotification === 'function') {
                        showNotification({ title: 'Could not load AI models', message: data.error === 'reconnect_required' ? 'ChatGPT authorization must be renewed.' : 'The provider model catalog is unavailable.', type: 'error', key: `ai-models:${providerId}` });
                    }
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
                renderBatchProgress({ running: true, operation: 'atomic_extraction', total: d.total || 0, processed: 0, errors: 0, skipped: 0 });
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
                renderBatchProgress({ running: true, operation: 'regenerate', total: d.total || 0, processed: 0, errors: 0, skipped: 0 });
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
    let serverSettings = null;
    try {
        const sr = await fetch('/api/server/settings');
        if (sr.ok) {
            const sd = await sr.json();
            serverSettings = sd;
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
    html += '<span>Install updates automatically</span>';
    html += `<label class="toggle"><input type="checkbox" data-key="autoUpdate" ${settingsState.autoUpdate ? 'checked' : ''} /><span class="toggle-slider"></span></label>`;
    html += '</div>';

    html += `<p style="color:var(--text-dim);font-size:0.78rem;margin-top:0.25rem">The host-side updater checks every 30 minutes and safely restarts the ${escapeHtml(serverSettings?.installation_mode || 'Nodecast')} installation when a release is available.</p>`;

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
                                <p style="margin:0 0 0.35rem 0;font-size:0.82rem">Open the release, download the installer and SHA256SUMS, then verify it before running.</p>
                                <a class="modal-btn" href="${_escapeHtml(data.release_url || 'https://github.com/sarox-dev/Nodecast/releases/latest')}" target="_blank" rel="noopener">Open release</a>
                            </div>
                        </div>`;
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
                        <a class="modal-btn" href="${_escapeHtml(_cachedUpdateCheck.release_url || 'https://github.com/sarox-dev/Nodecast/releases/latest')}" target="_blank" rel="noopener">Open verified release</a>
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

function renderBatchProgress(status) {
    const bar = document.getElementById('ai-progress-bar');
    const fill = document.getElementById('ai-progress-fill');
    const text = document.getElementById('ai-progress-text');
    const detail = document.getElementById('ai-progress-detail');
    if (!bar || !fill || !text || !detail) return;

    const total = Math.max(Number(status.total) || 0, 0);
    const processed = Number(status.processed) || 0;
    const errors = Number(status.errors) || 0;
    const skipped = Number(status.skipped) || 0;
    const done = processed + errors + skipped;
    const pct = total > 0 ? Math.min(Math.round((done / total) * 100), 100) : 0;
    const operation = status.operation === 'regenerate' ? 'Regenerating library' : 'Processing captures';
    document.querySelectorAll('#ai-process-unprocessed, #ai-regenerate-all').forEach(button => {
        button.disabled = Boolean(status.running);
    });

    if (!status.running && total === 0) {
        bar.hidden = true;
        return;
    }

    bar.hidden = false;
    bar.setAttribute('aria-valuenow', String(status.running ? pct : 100));
    fill.style.width = `${status.running ? pct : 100}%`;
    text.textContent = status.running
        ? `${operation} · ${done} of ${total}`
        : `Completed · ${processed} processed${errors ? `, ${errors} failed` : ''}${skipped ? `, ${skipped} skipped` : ''}`;
    detail.textContent = status.running
        ? (status.current || (total ? 'Preparing first capture…' : 'Checking captures…'))
        : (errors ? 'Some captures could not be processed.' : 'AI data is up to date.');
    bar.dataset.state = status.running ? 'running' : (errors ? 'error' : 'complete');
}

function pollBatchProgress(callback) {
    if (callback) batchPollCallback = callback;
    if (batchPollId !== null) return;

    function poll() {
        fetch('/api/ai/batch-status')
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(status => {
                // Keep UI errors separate from an unavailable status endpoint.
                // A rendering regression must not claim that AI processing itself
                // cannot be read, nor restart the polling failure loop.
                try {
                    renderBatchProgress(status);
                } catch (error) {
                    console.error('Could not render AI processing progress:', error);
                }
                if (status.running) {
                    batchPollId = setTimeout(poll, 2000);
                } else {
                    batchPollId = null;
                    if (batchPollCallback) {
                        try {
                            batchPollCallback(status);
                        } catch (error) {
                            console.error('AI processing completion callback failed:', error);
                        }
                        batchPollCallback = null;
                    }
                    if ((status.errors || 0) > 0 && typeof showNotification === 'function') {
                        showNotification({
                            title: 'AI processing finished with errors',
                            message: `${status.errors} capture${status.errors === 1 ? '' : 's'} could not be processed.`,
                            type: 'error',
                            key: 'ai-batch-errors',
                        });
                    }
                }
            })
            .catch(() => {
                batchPollId = null;
                if (typeof showNotification === 'function') {
                    showNotification({ title: 'Progress unavailable', message: 'Nodecast could not read the AI processing status.', type: 'error', key: 'ai-batch-progress' });
                }
                batchPollId = setTimeout(poll, 5000);
            });
    }
    batchPollId = setTimeout(poll, 0);
}

async function checkRunningBatch() {
    if (batchPollId) return;  // already polling
    try {
        const r = await fetch('/api/ai/batch-status');
        const status = await r.json();
        renderBatchProgress(status);
        if (status.running) {
            pollBatchProgress();
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
                btn.addEventListener('click', async () => {
                    if (btn.dataset.oauth === 'true') {
                        const authWindow = window.open('', 'nodecast-chatgpt-oauth', 'popup,width=620,height=760');
                        try {
                            const response = await fetch('/api/ai/chatgpt/start', { method: 'POST' });
                            const data = await response.json();
                            if (!response.ok || !data.authorization_url) throw new Error(data.detail || 'Could not start ChatGPT authorization');
                            overlay.remove();
                            if (authWindow) authWindow.location.href = data.authorization_url;
                            else window.location.href = data.authorization_url;
                            const started = Date.now();
                            const poll = setInterval(async () => {
                                if (Date.now() - started > 300000) { clearInterval(poll); return; }
                                try {
                                    const providersResponse = await fetch('/api/ai/providers');
                                    const providersData = await providersResponse.json();
                                    if ((providersData.providers || []).some(provider => provider.provider_type === 'chatgpt_oauth')) {
                                        clearInterval(poll);
                                        if (authWindow && !authWindow.closed) authWindow.close();
                                        if (typeof showNotification === 'function') showNotification({ title: 'ChatGPT connected', message: 'You can now assign your ChatGPT plan to Nodecast AI features.', type: 'success', key: 'chatgpt-connected' });
                                        renderAISettings();
                                    }
                                } catch {}
                            }, 1500);
                        } catch (error) {
                            if (authWindow) authWindow.close();
                            if (typeof showNotification === 'function') showNotification({ title: 'ChatGPT connection failed', message: error.message, type: 'error', key: 'chatgpt-oauth' });
                        }
                        return;
                    }
                    overlay.remove();
                    openAIProviderModal(null, {
                        key: btn.dataset.key,
                        name: btn.dataset.name,
                        url: btn.dataset.url,
                        requiresApiKey: btn.dataset.apikey === 'true',
                        apiStyle: btn.dataset.apiStyle,
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
    const iconPath = `/static/assets/AI_providers/${p.key === 'chatgpt' ? 'openai' : p.key}.svg?v=20261021-2`;
    const desc = p.oauth ? 'Use your eligible Plus or Pro plan — no API key' : (p.default_base_url || 'Custom base URL');
    return `<button class="ai-preset-select" type="button" style="display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.6rem;border:1px solid var(--border);border-radius:8px;background:var(--bg,#0d1117);color:var(--text);cursor:pointer;transition:background 0.15s;text-align:left;width:100%" data-key="${p.key}" data-url="${p.default_base_url}" data-apikey="${p.requires_api_key}" data-name="${p.name}" data-oauth="${Boolean(p.oauth)}" data-api-style="${p.api_style || 'openai'}"
      onmouseover="this.style.background='var(--surface,#161b22)'" onmouseout="this.style.background='var(--bg,#0d1117)'">
      <img src="${iconPath}" width="28" height="28" alt="" style="flex-shrink:0" />
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
    const iconPath = providerKey ? `/static/assets/AI_providers/${providerKey}.svg?v=20261021-2` : '';
    const iconHtml = iconPath ? `<img src="${iconPath}" width="22" height="22" alt="" style="vertical-align:middle;margin-right:0.4rem" />` : '';

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
                const wasFirstProvider = aiProviders.length === 0;
                const r = await fetch('/api/ai/providers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (r.ok) {
                    const created = await r.json();
                    if (wasFirstProvider) autoAssignProviderId = created.id;
                    close(); renderAISettings();
                }
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
    if (!q) {
        renderSettings();
        return;
    }
    const customEntries = [
        ['Account', 'Username and password', 'Change username password session logout account'],
        ['AI', 'AI providers', 'Provider connection models OpenAI OpenRouter ChatGPT'],
        ['AI', 'Feature assignments', 'Models extraction synthesis aggregates'],
        ['AI', 'AI processing', 'Process captures regenerate interval'],
        ['Extension', 'Extension connection', 'Install Chromium Firefox connect account releases'],
        ['Extension', 'Capture behavior', 'Floating save selection notification project'],
        ['Shortcuts', 'Keyboard shortcuts', 'Keys Web Ask close results suggestions'],
        ['Updates', 'Application updates', 'Version releases automatic install'],
    ];
    const schemaEntries = visibleSettingsSchema().flatMap(category => category.items.map(item => [category.category, item.label, item.description || '']));
    const categoryEntries = visibleSettingsSchema().map(category => [category.category, category.category, category.description || '']);
    const matches = [...categoryEntries, ...schemaEntries, ...customEntries]
        .filter(entry => entry.join(' ').toLowerCase().includes(q))
        .filter((entry, index, list) => list.findIndex(candidate => candidate[0] === entry[0] && candidate[1] === entry[1]) === index)
        .slice(0, 24);
    settingsList.className = 'settings-list settings-search-results';
    settingsList.innerHTML = matches.length ? matches.map(([category, label, context]) => `
      <button type="button" class="settings-search-result" data-search-category="${escapeHtml(category)}">
        <span class="settings-search-result-icon">${settingsIcon(category)}</span>
        <span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(category)}${context ? ` · ${escapeHtml(context)}` : ''}</small></span>
        <span aria-hidden="true">›</span>
      </button>`).join('') : '<div class="settings-search-empty">No settings found.</div>';
    settingsList.querySelectorAll('[data-search-category]').forEach(button => {
        button.addEventListener('click', () => {
            settingsSearchInput.value = '';
            openSettings(button.dataset.searchCategory);
        });
    });
}

settingsSearchInput?.addEventListener('input', (e) => filterSettings(e.target.value));
// Track input changes in settings (dirty state)
settingsList?.addEventListener('change', (e) => {
    if (e.target.closest('[data-feature]')) return; // AI has its own dirty tracking
    if (e.target.matches('select, input')) { _markDirty(); refreshResetButtons(); }
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
            if (item.type === 'checkbox' || item.type === 'toggle') value = input.checked;
            else if (item.type === 'number' || item.type === 'range') value = Number(input.value);
            else if (item.type === 'multiselect') value = [...input.selectedOptions].map(option => option.value);
            else value = input.value;
            setValue(item.key, value);
        });
    });
}

async function openSettings(category) {
    await loadCurrentSettingsUser();
    if (category === 'Updates' && !currentSettingsUser?.is_admin) category = 'Overview';
    if (category) activeSettingsCategory = category;
    renderCategoryNav(); renderSettings();
    if (settingsSearchInput?.value.trim()) filterSettings(settingsSearchInput.value);
    settingsOverlay.hidden = false;
    settingsOverlay.inert = false;
    settingsOverlay.removeAttribute('aria-hidden');
}
function openAccountSettings() { openSettings('Account'); }
function closeSettings() {
    if (_dirty) { _shakeActions(); return; }
    document.activeElement?.blur();
    settingsOverlay.inert = true;
    settingsOverlay.hidden = true;
    settingsOverlay.setAttribute('aria-hidden', 'true');
}

async function _saveSettings() {
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
        autoAssignProviderId = '';
        _clearDirty();
        setTimeout(() => renderAISettings(), 800);
        return;
    }

    if (category.category === 'Shortcuts') {
        NODECAST_SHORTCUTS.forEach(item => localStorage.setItem(`shortcut.${item.id}`, shortcutDraft?.[item.id] ?? item.default));
        _clearDirty();
        showToast('Shortcuts saved', 'success');
        return;
    }

    if (category.category === 'Account') {
        _clearDirty();
        return;
    }

    if (category.category === 'Extension') {
        const payload = {
            floating_button_enabled: settingsList.querySelector('[data-key="floating_button_enabled"]')?.checked ?? true,
            min_selection_length: Number(settingsList.querySelector('[data-key="min_selection_length"]')?.value) || 10,
            notification_position: settingsList.querySelector('[data-key="notification_position"]')?.value || 'top-center',
            default_project: settingsList.querySelector('[data-key="default_project"]')?.value.trim() || '',
        };
        try {
            const response = await fetch('/api/extension/settings', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            });
            if (!response.ok) throw new Error((await response.json()).detail || 'Could not save extension settings');
            const sync = await window.nodecastExtension?.syncSettings();
            if (sync && !sync.success) throw new Error(sync.message || 'Saved in Core, but extension sync failed');
            _tabSnapshot = { ...payload };
            _clearDirty();
            showToast('Extension settings saved', 'success');
        } catch (error) {
            showToast(error.message, 'error');
        }
        return;
    }

    if (category.category === 'Search') {
        const engine = settingsList.querySelector('[data-key="preferredEngine"]')?.value;
        const customTemplate = settingsList.querySelector('[data-key="customSearchUrl"]')?.value.trim() || '';
        if (engine === 'custom') {
            try {
                const candidate = new URL(customTemplate.replace('{query}', 'nodecast'));
                if (!['http:', 'https:'].includes(candidate.protocol) || !customTemplate.includes('{query}')) throw new Error();
            } catch {
                showToast('Custom search URL must be an http(s) URL containing {query}', 'error');
                return;
            }
        }
    }

    // Regular settings
    category.items.forEach(item => {
        const input = settingsList.querySelector(`[data-key="${item.key}"]`);
        if (!input) return;
        let value;
        if (item.type === 'checkbox' || item.type === 'toggle') value = input.checked;
        else if (item.type === 'number' || item.type === 'range') value = Number(input.value);
        else if (item.type === 'multiselect') value = [...input.selectedOptions].map(option => option.value);
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
    const root = document.documentElement;
    const theme = settingsState.theme || localStorage.getItem('theme') || 'dark';
    root.dataset.theme = theme;
    const validHex = value => /^#[0-9a-f]{6}$/i.test(value || '');
    if (theme === 'custom') {
        const primary = settingsState.customPrimary || localStorage.getItem('customPrimary') || '#818cf8';
        const secondary = settingsState.customSecondary || localStorage.getItem('customSecondary') || '#60a5fa';
        const background = settingsState.customBackground || localStorage.getItem('customBackground') || '#0b0f14';
        if (validHex(primary)) root.style.setProperty('--primary', primary);
        if (validHex(secondary)) root.style.setProperty('--secondary', secondary);
        if (validHex(background)) root.style.setProperty('--background', background);
        const rgb = background.slice(1).match(/../g).map(part => parseInt(part, 16) / 255)
            .map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
        const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
        root.dataset.customTone = luminance > 0.38 ? 'light' : 'dark';
        const foregroundTone = settingsState.customIconTone || localStorage.getItem('customIconTone') || 'light';
        root.dataset.iconTone = foregroundTone;
        root.dataset.foregroundTone = foregroundTone;
    } else {
        root.style.removeProperty('--primary');
        root.style.removeProperty('--secondary');
        root.style.removeProperty('--background');
        delete root.dataset.customTone;
        delete root.dataset.foregroundTone;
        root.dataset.iconTone = theme === 'light' ? 'dark' : 'light';
    }
    const duration = Math.max(0, Math.min(600, Number(settingsState.animationDuration ?? localStorage.getItem('animationDuration') ?? 160)));
    const respectMotion = settingsState.respectSystemMotion ?? (localStorage.getItem('respectSystemMotion') !== 'false');
    root.dataset.respectSystemMotion = String(respectMotion);
    root.style.setProperty('--motion-duration', `${duration}ms`);
    root.style.setProperty('--transition-fast', `${Math.round(duration * 0.75)}ms ease`);
    root.style.setProperty('--transition-base', `${Math.round(duration * 1.25)}ms ease`);
    root.style.setProperty('--transition-slow', `${Math.round(duration * 2.2)}ms cubic-bezier(0.4, 0, 0.2, 1)`);
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
    await loadCurrentSettingsUser();
    if (!currentSettingsUser?.is_admin) return;
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

function getAnimationSpeedStr() { return `${settingsState.animationDuration ?? 160}ms`; }

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
