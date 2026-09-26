// Small serializable state store for the modular Workspace shell.
(function createWorkspaceStore() {
    const persisted = (() => {
        try { return JSON.parse(localStorage.getItem('nodecast.workspace') || '{}'); }
        catch { return {}; }
    })();

    const state = {
        section: 'library',
        projection: 'list',
        query: '',
        selectedId: null,
        inspectorOpen: persisted.inspectorOpen !== false,
        savedViews: Array.isArray(persisted.savedViews) ? persisted.savedViews : [],
    };
    const listeners = new Set();

    function snapshot() {
        return JSON.parse(JSON.stringify(state));
    }

    function persist() {
        localStorage.setItem('nodecast.workspace', JSON.stringify({
            inspectorOpen: state.inspectorOpen,
            savedViews: state.savedViews,
        }));
    }

    function set(patch) {
        Object.assign(state, patch);
        persist();
        const next = snapshot();
        listeners.forEach(listener => listener(next));
        window.dispatchEvent(new CustomEvent('nodecast:workspace-state', { detail: next }));
        return next;
    }

    function subscribe(listener) {
        listeners.add(listener);
        listener(snapshot());
        return () => listeners.delete(listener);
    }

    window.nodecastWorkspaceStore = { get: snapshot, set, subscribe };
})();
