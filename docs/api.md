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

## AI

- `/api/ai/providers*` — provider CRUD, connection/model lookup.
- `/api/ai/assignments*` — models assigned to atomic extraction, entity extraction and aggregate creation.
- `POST /api/ai/process-unprocessed`
- `POST /api/ai/regenerate-all`
- `GET /api/ai/batch-status`
- `GET /api/ai/relation-graph` — atomic nodes and atomic relations.

## Auth

Auth routes are under `/auth`; register/login return credentials usable by the browser extension and API clients.
