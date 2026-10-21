// Controller for the constellation home, central Search/Ask input, and result surface.
(function createWorkspaceController() {
    function isTypingTarget(target) {
        return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
    }

    window.addEventListener('DOMContentLoaded', () => {
        const store = window.nodecastWorkspaceStore;
        const shell = document.querySelector('.workspace-shell');
        const form = document.getElementById('search-form');
        const query = document.getElementById('query');
        const content = document.getElementById('content-view');
        const stage = document.getElementById('constellation-stage');
        const title = document.getElementById('workspace-view-title');
        const eyebrow = document.getElementById('workspace-view-eyebrow');
        const description = document.getElementById('workspace-view-description');
        const results = document.getElementById('results-container');
        const projectionButtons = [...document.querySelectorAll('[data-projection]')];

        function openResults(label = 'Recent memory') {
            content.hidden = false;
            stage.classList.add('constellation-stage-muted');
            shell.classList.add('results-open');
            eyebrow.textContent = 'Personal recall';
            title.textContent = label;
            description.textContent = 'Answers and evidence from information you intentionally saved.';
        }

        function closeResults() {
            content.hidden = true;
            stage.classList.remove('constellation-stage-muted');
            shell.classList.remove('results-open');
            const loading = document.getElementById('loading-indicator');
            if (loading) loading.hidden = true;
            query?.focus();
        }

        function applyProjection(projection) {
            results?.classList.toggle('workspace-projection-focus', projection === 'focus');
            results?.classList.toggle('workspace-projection-sources', projection === 'sources');
            projectionButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.projection === projection)));
            store?.set({ projection });
        }

        projectionButtons.forEach(button => button.addEventListener('click', () => applyProjection(button.dataset.projection)));
        document.getElementById('workspace-results-close')?.addEventListener('click', closeResults);
        form?.addEventListener('submit', () => {
            if (window.webMode) return;
            const value = query.value.trim();
            if (!value) return;
            openResults(value.replace(/^\/\w+\s*/, '') || 'Library results');
            store?.set({ query: value, section: 'library', projection: 'list' });
            applyProjection('list');
        });
        results?.addEventListener('click', event => {
            if (event.target.closest('a, button, input, select, textarea')) return;
            const card = event.target.closest('.result-card, .dashboard-atom-item');
            if (!card) return;
            results.querySelectorAll('.workspace-selected').forEach(item => item.classList.remove('workspace-selected'));
            card.classList.add('workspace-selected');
        });
        document.addEventListener('keydown', event => {
            if (window.nodecastShortcutMatches?.(event, 'toggle_mode')) {
                event.preventDefault();
                window.setWebMode?.(!window.webMode);
                return;
            }
            const settingsOpen = !document.getElementById('settings-overlay')?.hidden;
            const dialogOpen = [...document.querySelectorAll('[role="dialog"]')].some(dialog => !dialog.closest('[hidden]') && !dialog.hidden && dialog.getClientRects().length);
            const printable = event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
            if (printable && content.hidden && !settingsOpen && !dialogOpen && !isTypingTarget(event.target)) {
                event.preventDefault();
                query?.focus();
                query?.setRangeText(event.key, query.selectionStart ?? query.value.length, query.selectionEnd ?? query.value.length, 'end');
                query?.dispatchEvent(new Event('input', { bubbles: true }));
                return;
            }
            if (window.nodecastShortcutMatches?.(event, 'close_view') && !content.hidden && !isTypingTarget(event.target)) closeResults();
        });

        window.nodecastWorkspace = { openResults, closeResults };
        store?.set({ inspectorOpen: false, section: 'home' });
        window.setWebMode?.(true);
        window.setTimeout(() => query?.focus(), 0);
    });
})();
