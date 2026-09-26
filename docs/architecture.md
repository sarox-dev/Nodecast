# Architecture

> Atomic Schema v2 is active: derived knowledge has `evidence`, `concept` or
> `aggregate` roles and relations carry method, reason, confidence and lifecycle
> status. `/api/memory` is the canonical retrieval boundary; atomic endpoints
> remain compatibility and diagnostic APIs.

## Product boundary

Nodecast is not a general web-search engine or a manual note organizer. It is a local memory layer for knowledge a person deliberately saves, with exact source provenance.

## Pipeline

```text
Browser Extension
  → POST /api/capture
  → immutable raw CapturePackage + optional page HTML
  → captures source reference
  → pending atomic_extraction job (highlighted content only)
  → HTML cleaner
  → atomics
  → entity atomics
  → cross-source atomic_relations
  → aggregate atomics
  → search, entity, graph and text views
```

## Extension integration

Core and the MV3 extension communicate through a small `window.postMessage` bridge on the loopback Nodecast workspace only. The bridge exposes status and commands, never credentials. An authenticated Core session creates a 90-second one-time pairing code; the extension exchanges it directly with `/api/extension/exchange` and stores the returned bearer token in extension storage. Per-user capture preferences live in Core's `user_settings` and are cached by the extension for immediate use on arbitrary pages.

For a highlighted capture, the content script snapshots the selection and CapturePackage before the floating button receives focus. The button is isolated in Shadow DOM, constrained to the viewport and reports saving/success/error states. Password fields, editable controls and the Core workspace itself do not receive a floating save control.

A save without highlighted text is a bookmark: Nodecast stores source metadata and does not extract page knowledge. A highlighted save queues background atomic processing.

## Data model

Each user has `contents/users/{user_id}/nodecast.db`.

- `captures`: source URL, title, site, timestamps, project/tags and raw path.
- `atomics`: every derived knowledge unit (`text`, `heading`, `fact`, `summary`, `tag`, `entity`, `aggregate`, `code_block`, `quote`, `link`, `image`). `source_id` provides provenance back to a capture.
- `atomic_relations`: links only atomic IDs. Common types include `precedes`, `references`, `related_to`, and `child_of`.
- `ai_providers`, `ai_feature_assignments`, `pending_ai_jobs`: encrypted provider configuration and background processing.

There are no separate entity, fact, tag-summary, KnowledgeObject, or mixed capture/entity relation stores.

## Runtime

- FastAPI backend and server-rendered vanilla HTML/CSS/JS UI.
- SQLite per user; global SQLite only for accounts/settings.
- Docker Compose runs one app service on `APP_PORT` (default 5000).
- The modular workspace shell keeps navigation, projection, selection and Inspector state in a small serializable client store. Library, Sources, Entities, Graph and Web Search are projections over the same workspace rather than separate applications.
- Web Search requests type-ahead suggestions through the authenticated `/api/web/suggestions` proxy, then redirects the browser to the independently configured external search URL. SearXNG is no longer part of Nodecast.
- Users can configure the Nodecast URL as their browser start/new-tab page without an extension page override. A future opt-in extension adapter may restyle supported result pages with provider-specific CSS only; it will not replace provider HTML.
