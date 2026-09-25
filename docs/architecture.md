# Architecture

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
- Web search opens the user's configured external search engine; SearXNG is no longer part of Nodecast.
