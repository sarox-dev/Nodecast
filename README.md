# Nodecast

**Your knowledge layer. Your context. Your memory.**

Nodecast is a local-first memory layer for knowledge you deliberately save from the internet. Highlight useful content once; Nodecast turns it into searchable atomic knowledge, connects it across sources, and always keeps provenance back to the original page.

## Why

Bookmarks remember URLs. AI chats forget project-specific context. Nodecast keeps the verified fragments, solutions and decisions that matter to you so they can be found months later and eventually supplied to AI agents as durable personal context.

## Workflow

```text
Browser highlight → Save → background atomic extraction
                  → entities + cross-source relations + aggregates
                  → search / entity / graph views with source links
```

A save without highlighted text is intentionally just a bookmark.

## Stack

FastAPI, per-user SQLite, vanilla HTML/CSS/JavaScript, Docker, and optional local or hosted AI providers. Nodecast does not require SearXNG or a cloud database.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:5000`, register the first admin account, then connect the browser extension and optionally configure AI under Settings.

## Development

```bash
python -m pytest tests/ -v
uvicorn app.main:app --reload --port 5000
```

See [the documentation](docs/README.md) for architecture, API, deployment and the current user workflow.

## Direction

The current foundation is the capture + atomics + atomic-relations model. The roadmap builds specialized knowledge views, extension sync, community starter packs and an MCP server so AI agents can query the user's own verified context.
