/* A small, account-scoped tour. Saved text and local search never require AI. */
(() => {
    const DISCORD_INVITE = 'https://discord.gg/tFAM5JST4U';
    const steps = [
        { title: 'Your knowledge, ready to find again', label: 'Welcome to Nodecast',
          body: 'Save something useful now. Find it later and open the original source — without organising folders or setting up an AI account.',
          hint: 'This quick tour takes about a minute. You can skip it now and replay it from Settings → Overview anytime.', visual: 'Save → Find → Open source' },
        { title: 'Connect your browser', label: '1 · Set up once', target: '#sidebar-brand-settings',
          body: 'The settings button is in the top-left corner. Open Settings → Extension to install the browser extension and connect it to this account.',
          hint: 'Your saves belong to the connected account. Check the account name before saving.', visual: 'Settings → Extension → Connect' },
        { title: 'Keep the useful part', label: '2 · Save',
          body: 'On a webpage, highlight useful text and click the floating Save button. You can add a reason, or leave it empty. The extension can also save a whole page.',
          hint: 'Nodecast keeps the original text and source. Indexing runs in the background; a saved item may take a moment to appear in search.', visual: 'Highlight text → Save' },
        { title: 'Ask searches what you saved', label: '3 · Find', target: '#search-bar-wrapper',
          body: 'This search bar has two modes. Web searches the internet. Click Web to switch to Ask, type a phrase from something you saved, and press Enter.',
          hint: 'Local source results work without AI. A configured AI model is optional if you want a generated answer.', visual: 'Web ↔ Ask' },
        { title: 'Go back to the evidence', label: '4 · Verify',
          body: 'Ask shows saved excerpts with their source. Open a result to inspect its text, then use the source link to return to the original page. Grid and List change the result layout.',
          hint: 'The constellation is another way to explore your saved knowledge. Settings stays available in the top-left corner.', visual: 'Saved excerpt → Original source' },
        { title: 'You’re ready to try it', label: 'Keep in touch',
          body: 'Save one useful passage, switch to Ask, and find it again. That is all you need to get started.',
          hint: 'Need help or want to share feedback? Join the Nodecast Discord community. The invite opens the rules channel.', visual: 'A small library. A useful answer.', community: true },
    ];
    let userId = null;
    let overlay = null;
    let panel = null;
    let index = 0;
    let previousFocus = null;
    let inertState = [];
    const localKey = () => `nodecast.workspaceTour.v1.${userId}`;

    function create() {
        if (overlay) return;
        overlay = document.createElement('div');
        overlay.id = 'onboarding-overlay';
        overlay.hidden = true;
        overlay.innerHTML = `
          <div class="onboarding-spotlight" aria-hidden="true" hidden></div>
          <section class="onboarding-panel" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" aria-describedby="onboarding-body">
            <div class="onboarding-topline"><span id="onboarding-label"></span><button type="button" data-tour-close aria-label="Close tour">×</button></div>
            <div class="onboarding-progress" aria-hidden="true">${steps.map(() => '<span></span>').join('')}</div>
            <div class="onboarding-visual" aria-hidden="true"></div>
            <h2 id="onboarding-title" tabindex="-1"></h2>
            <p id="onboarding-body"></p>
            <p class="onboarding-hint"></p>
            <a class="onboarding-community" href="${DISCORD_INVITE}" target="_blank" rel="noopener noreferrer" hidden>Join Nodecast on Discord ↗</a>
            <div class="onboarding-footer"><button type="button" data-tour-skip>Skip tour</button><span id="onboarding-count" aria-live="polite"></span><div class="onboarding-navigation"><button type="button" data-tour-back>Back</button><button type="button" data-tour-next>Next</button></div></div>
          </section>`;
        document.body.appendChild(overlay);
        panel = overlay.querySelector('.onboarding-panel');
        overlay.querySelector('[data-tour-close]').addEventListener('click', dismiss);
        overlay.querySelector('[data-tour-skip]').addEventListener('click', dismiss);
        overlay.querySelector('[data-tour-back]').addEventListener('click', () => { index--; render(); });
        overlay.querySelector('[data-tour-next]').addEventListener('click', () => {
            if (index === steps.length - 1) dismiss();
            else { index++; render(); }
        });
        document.addEventListener('keydown', event => {
            if (overlay.hidden) return;
            // Keep workspace shortcuts from changing the page behind the tour.
            event.stopImmediatePropagation();
            if (event.key === 'Escape') { event.preventDefault(); dismiss(); }
            if (event.key === 'Tab') {
                const controls = [...panel.querySelectorAll('button, a[href]')].filter(el => !el.disabled && !el.hidden && el.getClientRects().length);
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && (document.activeElement === first || !controls.includes(document.activeElement))) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && (document.activeElement === last || !controls.includes(document.activeElement))) { event.preventDefault(); first.focus(); }
            }
        }, true);
        window.addEventListener('resize', position);
    }

    function position() {
        if (!overlay || overlay.hidden) return;
        const target = document.querySelector(steps[index].target || '#no-tour-target');
        const spotlight = overlay.querySelector('.onboarding-spotlight');
        const box = target?.getBoundingClientRect();
        const anchored = box && box.width && box.height;
        spotlight.hidden = !anchored;
        if (anchored) Object.assign(spotlight.style, {
            left: `${Math.max(4, box.left - 6)}px`, top: `${Math.max(4, box.top - 6)}px`,
            width: `${Math.min(box.width + 12, innerWidth - 8)}px`, height: `${box.height + 12}px`,
        });
        const width = panel.offsetWidth, height = panel.offsetHeight;
        let left = (innerWidth - width) / 2, top = (innerHeight - height) / 2;
        if (anchored) {
            left = box.left;
            top = box.bottom + 22;
            if (top + height > innerHeight - 16) top = box.top - height - 22;
        }
        panel.style.left = `${Math.max(16, Math.min(left, innerWidth - width - 16))}px`;
        panel.style.top = `${Math.max(16, Math.min(top, innerHeight - height - 16))}px`;
    }

    function render() {
        const step = steps[index];
        overlay.querySelector('#onboarding-label').textContent = step.label;
        overlay.querySelector('#onboarding-title').textContent = step.title;
        overlay.querySelector('#onboarding-body').textContent = step.body;
        overlay.querySelector('.onboarding-hint').textContent = step.hint;
        overlay.querySelector('.onboarding-visual').textContent = step.visual;
        overlay.querySelector('.onboarding-community').hidden = !step.community;
        overlay.querySelector('#onboarding-count').textContent = `${index + 1} / ${steps.length}`;
        overlay.querySelector('[data-tour-back]').hidden = index === 0;
        overlay.querySelector('[data-tour-next]').textContent = index === steps.length - 1 ? 'Get started' : 'Next';
        overlay.querySelectorAll('.onboarding-progress span').forEach((el, i) => el.classList.toggle('active', i <= index));
        position();
        overlay.querySelector('#onboarding-title').focus({ preventScroll: true });
    }

    function show() {
        if (!userId) return;
        create();
        if (!overlay.hidden) return;
        previousFocus = document.activeElement;
        inertState = [...document.body.children].filter(el => el !== overlay && el.tagName !== 'SCRIPT').map(el => [el, el.inert]);
        inertState.forEach(([el]) => { el.inert = true; });
        index = 0;
        overlay.hidden = false;
        render();
    }

    async function dismiss() {
        if (!overlay || overlay.hidden) return;
        overlay.hidden = true;
        inertState.forEach(([el, wasInert]) => { el.inert = wasInert; });
        inertState = [];
        const restore = previousFocus?.isConnected && previousFocus.tabIndex >= 0 && !previousFocus.disabled && previousFocus.getClientRects().length ? previousFocus : document.getElementById('sidebar-brand-settings');
        restore?.focus({ preventScroll: true });
        try { localStorage.setItem(localKey(), 'true'); } catch {}
        try {
            const response = await fetch('/api/onboarding', { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dismissed: true }) });
            if (!response.ok) throw new Error('preference_not_saved');
        } catch {
            window.showNotification?.({ title: 'Tour preference', message: 'The tour is closed. Your account preference could not be saved; it may appear again on another browser.', type: 'error', key: 'tour-preference' });
        }
    }

    async function init(user) {
        if (!user?.user_id || user.role !== 'member') return;
        userId = user.user_id;
        let locallyDismissed = false;
        try { locallyDismissed = localStorage.getItem(localKey()) === 'true'; } catch {}
        try {
            const response = await fetch('/api/onboarding');
            if (!response.ok) return;
            const preference = await response.json();
            if (!preference.dismissed && !locallyDismissed && document.getElementById('settings-overlay')?.hidden) show();
        } catch { /* A missing preference must not block the workspace. Replay remains available. */ }
    }

    document.addEventListener('click', event => {
        if (!event.target.closest('[data-replay-tour]')) return;
        window.closeSettings?.();
        if (document.getElementById('settings-overlay')?.hidden) show();
    });
    window.nodecastOnboarding = { init, show };
})();
