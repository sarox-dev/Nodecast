// capture-view.js — Knowledge Viewer frontend
// Tab switching, lazy loading Raw tab, renderer switching, actions

(function () {
  'use strict';

  const CAPTURE_ID = document.querySelector('[data-action="export-markdown"]')?.dataset.id;
  const BASE_URL = window.location.origin;

  // ─── Tab switching ────────────────────────────────────────────

  const tabs = document.querySelectorAll('.kv-tab');
  const panels = document.querySelectorAll('.kv-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', function () {
      const target = this.dataset.tab;

      // Deactivate all
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));

      // Activate selected
      this.classList.add('active');
      const panel = document.getElementById(`panel-${target}`);
      if (panel) panel.classList.add('active');

      // Lazy load raw tab
      if (target === 'raw') {
        loadRawData();
      }
    });
  });

  // ─── Renderer switching ───────────────────────────────────────

  const rendererSelect = document.getElementById('renderer-select');
  const rendererRefresh = document.getElementById('renderer-refresh');
  const rendererOutput = document.getElementById('kv-renderer-output');

  function loadRenderer(name) {
    if (!CAPTURE_ID || !name) return;
    rendererOutput.innerHTML = '<p class="text-muted">Loading...</p>';

    fetch(`${BASE_URL}/api/capture/${CAPTURE_ID}/render/${name}`)
      .then(res => {
        if (!res.ok) throw new Error(`Renderer error: ${res.status}`);
        return res.text();
      })
      .then(html => {
        rendererOutput.innerHTML = html;
      })
      .catch(err => {
        rendererOutput.innerHTML = `<p class="kv-error">Failed to load renderer: ${err.message}</p>`;
      });
  }

  if (rendererSelect && rendererRefresh) {
    rendererRefresh.addEventListener('click', function () {
      loadRenderer(rendererSelect.value);
    });

    // Load initial renderer if not default
    rendererSelect.addEventListener('change', function () {
      loadRenderer(this.value);
    });
  }

  // ─── Lazy load Raw tab ────────────────────────────────────────

  let rawLoaded = false;

  function loadRawData() {
    if (rawLoaded || !CAPTURE_ID) return;
    rawLoaded = true;

    const loading = document.getElementById('raw-loading');
    const content = document.getElementById('raw-content');

    // Load capture package JSON
    fetch(`${BASE_URL}/api/capture/${CAPTURE_ID}`)
      .then(res => res.json())
      .then(data => {
        if (loading) loading.style.display = 'none';
        if (content) content.style.display = 'block';

        const jsonEl = document.querySelector('#raw-json code');
        if (jsonEl && data.capture) {
          jsonEl.textContent = JSON.stringify(data.capture, null, 2);
        }

        // Update has_html
        const hasHtmlEl = document.getElementById('raw-has-html');
        if (hasHtmlEl) {
          hasHtmlEl.textContent = data.has_html ? 'Yes' : 'No';
          hasHtmlEl.style.color = data.has_html ? '#3fb950' : '#8b949e';
        }

        // Set download/view links
        const downloadLink = document.getElementById('raw-html-download');
        const viewLink = document.getElementById('raw-html-view');
        if (downloadLink) {
          downloadLink.href = `${BASE_URL}/api/capture/${CAPTURE_ID}/page.html`;
        }
        if (viewLink) {
          viewLink.href = `${BASE_URL}/api/capture/${CAPTURE_ID}/page.html`;
          // Only show view link if HTML exists
          viewLink.style.display = data.has_html ? 'inline-block' : 'none';
          downloadLink.style.display = data.has_html ? 'inline-block' : 'none';
        }
      })
      .catch(err => {
        if (loading) {
          loading.innerHTML = `<p class="kv-error">Failed to load raw data: ${err.message}</p>`;
        }
      });
  }

  // ─── Actions ──────────────────────────────────────────────────

  // Export Markdown
  document.querySelectorAll('[data-action="export-markdown"]').forEach(btn => {
    btn.addEventListener('click', function () {
      const id = this.dataset.id;
      if (!id) return;
      window.open(`${BASE_URL}/api/capture/${id}/markdown`, '_blank');
    });
  });

  // Download Raw
  document.querySelectorAll('[data-action="download-raw"]').forEach(btn => {
    btn.addEventListener('click', function () {
      const id = this.dataset.id;
      if (!id) return;
      window.open(`${BASE_URL}/api/capture/${id}/knowledge`, '_blank');
    });
  });

  // Re-run Extractor
  document.querySelectorAll('[data-action="rerun-extractor"]').forEach(btn => {
    btn.addEventListener('click', function () {
      const id = this.dataset.id;
      if (!id) return;
      this.textContent = '⏳ Re-running...';
      this.disabled = true;

      fetch(`${BASE_URL}/api/capture/${id}/reextract`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            this.textContent = `✅ ${data.extracted} objects`;
            setTimeout(() => window.location.reload(), 1500);
          } else {
            this.textContent = '❌ Failed';
            console.error('Re-extract failed:', data);
          }
        })
        .catch(err => {
          this.textContent = '❌ Error';
          console.error('Re-extract error:', err);
        });
    });
  });

  // AI Analysis button — runs all configured features grouped by model
  document.querySelectorAll('[data-action="ai-analyze"]').forEach(btn => {
    btn.addEventListener('click', function () {
      const id = this.dataset.id;
      if (!id) return;
      this.textContent = '⏳ AI Analysis...';
      this.disabled = true;

      fetch(`${BASE_URL}/api/ai/process-capture/${id}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
          if (data.status === 'no_assignment') {
            this.textContent = '⚠️ No AI configured';
            this.disabled = false;
          } else if (data.errors > 0) {
            this.textContent = `⚠️ ${data.total - data.errors}/${data.total} done`;
            this.disabled = false;
            setTimeout(() => window.location.reload(), 2000);
          } else {
            this.textContent = `✅ ${data.total} features done`;
            setTimeout(() => window.location.reload(), 2000);
          }
        })
        .catch(err => {
          this.textContent = '❌ Error';
          this.disabled = false;
          console.error('AI analysis error:', err);
        });
    });
  });

  // Discover Relations button — runs Stage 1 deterministic relation discovery
  document.querySelectorAll('[data-action="discover-relations"]').forEach(btn => {
    btn.addEventListener('click', function () {
      const id = this.dataset.id;
      if (!id) return;
      this.textContent = '⏳ Discovering...';
      this.disabled = true;

      fetch(`${BASE_URL}/api/ai/discover-relations/${id}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
          const count = data.relations_created || 0;
          this.textContent = `✅ ${count} relations found`;
          setTimeout(() => window.location.reload(), 1500);
        })
        .catch(err => {
          this.textContent = '❌ Error';
          this.disabled = false;
          console.error('Relation discovery error:', err);
        });
    });
  });

})();