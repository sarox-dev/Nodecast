// Safe page <-> extension bridge. Authentication tokens never enter page JavaScript.
(function () {
    const pending = new Map();
    let status = { checked: false, checking: false, detected: false, connected: false, version: '', username: '', capabilities: [] };
    let detectionPromise = null;

    function request(type, payload = {}, timeout = 1800) {
        const requestId = crypto.randomUUID();
        return new Promise((resolve) => {
            const timer = setTimeout(() => {
                pending.delete(requestId);
                resolve(null);
            }, timeout);
            pending.set(requestId, { resolve, timer });
            window.postMessage({
                source: 'nodecast-core', type, requestId, payload,
            }, window.location.origin);
        });
    }

    function publish(next) {
        status = { ...status, ...next };
        window.dispatchEvent(new CustomEvent('nodecast:extension-status', { detail: { ...status } }));
    }

    window.addEventListener('message', (event) => {
        if (event.source !== window || event.origin !== window.location.origin) return;
        const message = event.data;
        if (!message || message.source !== 'nodecast-extension') return;
        const waiter = pending.get(message.requestId);
        if (waiter) {
            clearTimeout(waiter.timer);
            pending.delete(message.requestId);
            waiter.resolve(message.payload || null);
        }
        if (message.type === 'NODECAST_EXTENSION_STATUS') {
            publish({ checked: true, checking: false, detected: true, ...(message.payload || {}) });
        }
    });

    async function runDetection() {
        publish({ checking: true });
        let result = await request('NODECAST_EXTENSION_PING', {}, 900);
        if (!result) {
            await new Promise(resolve => setTimeout(resolve, 250));
            result = await request('NODECAST_EXTENSION_PING', {}, 1200);
        }
        if (result) publish({ checked: true, checking: false, detected: true, ...result });
        else publish({ checked: true, checking: false, detected: false, connected: false, version: '', username: '', capabilities: [] });
        return { ...status };
    }

    function detect(force = false) {
        if (!force && detectionPromise) return detectionPromise;
        detectionPromise = runDetection();
        return detectionPromise;
    }

    async function pair() {
        const response = await fetch('/api/extension/pairing-code', { method: 'POST' });
        if (!response.ok) throw new Error((await response.json()).detail || 'Could not create pairing code');
        const pairing = await response.json();
        const result = await request('NODECAST_EXTENSION_PAIR', {
            code: pairing.code,
            coreOrigin: window.location.origin,
        }, 6000);
        if (!result?.success) throw new Error(result?.message || 'Extension did not accept the connection');
        publish({ detected: true, connected: true, username: result.username || '' });
        return result;
    }

    async function syncSettings() {
        return request('NODECAST_EXTENSION_SYNC_SETTINGS', {}, 4000);
    }

    async function disconnect() {
        const result = await request('NODECAST_EXTENSION_DISCONNECT', {}, 2500);
        if (result?.success) publish({ detected: true, connected: false, username: '' });
        return result;
    }

    window.nodecastExtension = {
        whenReady: () => detect(false),
        refresh: () => detect(true),
        pair,
        syncSettings,
        disconnect,
        getStatus: () => ({ ...status }),
    };
    window.addEventListener('DOMContentLoaded', () => setTimeout(() => detect(false), 100), { once: true });
})();
