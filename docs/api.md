# API

Default base URL: `http://localhost:5000`. Data endpoints require the JWT cookie or bearer token returned by auth.

## Capture

- `POST /api/capture` — store a CapturePackage; highlighted HTML queues atomic extraction.
- `GET /api/capture` — list source captures.
- `GET|PATCH|DELETE /api/capture/{id}` — read, edit metadata, or delete a capture and its atomics.
- `POST /api/capture/{id}/reextract` — delete derived atomics and queue extraction again.
- `GET /api/capture/{id}/markdown` — render that capture's atomics as Markdown.

## Knowledge

- `GET /api/atomics?q=&type=&limit=50`
- `GET|DELETE /api/atomics/{id}`
- `GET /api/atomics/{id}/children`
- `POST /api/atomics/dedup`
- `GET /api/entities` and `GET /api/entity/{id}` — entity projections over atomics.
- `GET /api/facts?q=` — fact projections over `atomic(type=fact)`.
- `GET /search?q=` — local atomic search.
- `GET /api/library` — lightweight discovery summary.

## Personal recall

- `POST /api/memory/query` — retrieve a small, source-diverse evidence packet for a natural-language question. The response always contains `items`, `evidence`, `sources`, `synthesis_status` and `capabilities`; `answer` is present only when a configured Recall synthesis model returned cited sections.
- `GET /api/memory` — recent saved evidence.
- `GET /api/memory/{id}`, `/sources`, `/evidence` and `/graph` — progressively reveal a selected memory and its provenance.
- `POST /api/memory/{id}/feedback` and `POST /api/relations/{id}/feedback` — record usefulness and relation corrections.

## AI

- `POST /api/ai/chatgpt/start` creates a short-lived PKCE transaction and returns the
  official ChatGPT authorization URL.
- `GET /api/ai/chatgpt/callback` validates the OAuth callback and attaches encrypted
  ChatGPT-plan credentials to the Nodecast user represented by the one-time state.

ChatGPT plan inference is stateless: Responses API calls set `store:false` and contain
only Nodecast-selected evidence.

- `/api/ai/providers*` — provider CRUD, connection/model lookup.
- `/api/ai/assignments*` — models assigned to atomic extraction, Recall synthesis, entity extraction and aggregate creation.
- `POST /api/ai/process-unprocessed`
- `POST /api/ai/regenerate-all`
- `GET /api/ai/batch-status` — returns the active operation, running state,
  processed/error/skipped/total counts, remaining pending jobs and current source title.
- `GET /api/ai/relation-graph` — atomic nodes and atomic relations.

## Auth

Auth routes are under `/auth`; register/login return credentials usable by the browser extension and API clients.
