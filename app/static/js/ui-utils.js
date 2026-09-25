// ─── ui-utils.js — Shared UI utilities for Nodecast ──────────────────────

window.showToast = function(message, type = 'error', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<span style="flex:1">${message}</span><button class="toast-dismiss">✕</button>`;
    el.querySelector('.toast-dismiss').addEventListener('click', () => el.remove());
    container.appendChild(el);
    setTimeout(() => { if (el.parentNode) el.remove(); }, duration);
};

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

function showConfirmDialog(msg, opts = {}) {
    const { prompt: promptLabel, defaultValue } = opts;
    return new Promise((resolve) => {
        const confirmOverlay = document.getElementById('confirm-overlay');
        const confirmClose = document.getElementById('confirm-close');
        const confirmMessage = document.getElementById('confirm-message');
        const confirmCancel = document.getElementById('confirm-cancel');
        const confirmDelete = document.getElementById('confirm-delete');
        if (!confirmOverlay || !confirmMessage) { resolve(false); return; }
        confirmMessage.textContent = msg;
        confirmOverlay.hidden = false;
        confirmOverlay.removeAttribute('aria-hidden');
        const inputGroup = document.getElementById('confirm-input-group');
        const inputLabel = document.getElementById('confirm-input-label');
        const inputEl = document.getElementById('confirm-input');
        if (promptLabel) {
            inputGroup.hidden = false;
            inputLabel.textContent = promptLabel;
            inputEl.value = defaultValue || '';
            inputEl.focus();
            confirmDelete.textContent = 'Confirm';
            confirmDelete.style.background = 'var(--danger,#f87171)';
            confirmDelete.style.color = '#fff';
            confirmDelete.style.border = 'none';
        } else {
            inputGroup.hidden = true;
            confirmDelete.textContent = 'Delete';
            confirmDelete.style.background = '';
            confirmDelete.style.color = '';
            confirmDelete.style.border = '';
        }
        function cleanup() {
            confirmOverlay.hidden = true;
            confirmOverlay.setAttribute('aria-hidden', 'true');
            confirmOverlay.removeEventListener('click', overlayClick);
            if (confirmClose) confirmClose.removeEventListener('click', rejectClick);
            if (confirmCancel) confirmCancel.removeEventListener('click', rejectClick);
            if (confirmDelete) confirmDelete.removeEventListener('click', acceptClick);
            if (inputEl) inputEl.value = '';
        }
        function acceptClick() {
            if (promptLabel) { resolve(inputEl.value); }
            else { resolve(true); }
            cleanup();
        }
        function rejectClick() { cleanup(); resolve(false); }
        function overlayClick(e) { if (e.target === confirmOverlay) { cleanup(); resolve(false); } }
        if (confirmDelete) confirmDelete.addEventListener('click', acceptClick);
        if (confirmCancel) confirmCancel.addEventListener('click', rejectClick);
        if (confirmClose) confirmClose.addEventListener('click', rejectClick);
        confirmOverlay.addEventListener('click', overlayClick);
        if (promptLabel && inputEl) {
            inputEl.addEventListener('keydown', function inputKeydown(e) {
                if (e.key === 'Enter') { acceptClick(); }
            });
        }
    });
}

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
            flushParagraph(); flushList();
            const level = trimmed.match(/^#+/)[0].length;
            const content = trimmed.replace(/^#{1,6}\s/, '');
            html += `<h${Math.min(level, 3)}>${formatInline(content)}</h${Math.min(level, 3)}>`;
        } else if (/^[-*]\s+/.test(trimmed)) {
            flushParagraph();
            if (!inList) { html += '<ul>'; inList = true; }
            html += `<li>${formatInline(trimmed.replace(/^[-*]\s+/, ''))}</li>`;
        } else if (/^```/.test(trimmed)) {
            flushParagraph(); flushList();
            html += '<pre><code>' + escapeHtml(text) + '</code></pre>';
        } else if (!trimmed) {
            flushParagraph(); flushList();
        } else {
            paragraph.push(trimmed);
        }
    });
    flushParagraph(); flushList();
    return html || `<pre>${escapeHtml(text)}</pre>`;
}

function skeletonLoader(lines = 3) {
    const variants = ['skeleton-line-sm', 'skeleton-line-md', 'skeleton-line-lg'];
    let html = '<div class="skeleton-loader">';
    for (let i = 0; i < lines; i++) {
        html += `<div class="skeleton-line ${variants[i % variants.length]}"></div>`;
    }
    html += '</div>';
    return html;
}

function formatInline(text) {
    return escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}