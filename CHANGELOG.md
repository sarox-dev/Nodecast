## v1.1.1 (2026-07-21)

- fix: release workflow pushes to main, moves tag, updates version.json and CHANGELOG (e7eebe2)
- fix: read from /dev/tty when piping install.sh via curl | bash (38afb8b)
- fix: searxng permission conflict on install, read APP_PORT from .env (9db9831)
- feat: auto-update system with version.json, notification banner, updates settings tab, install TUI (8d3a3a6)


# Changelog

## v1.1.1 (2026-07-21)

- Auto-update system: version.json as single source of truth, update notification banner, Updates settings tab with version info, check for updates, release notes, and install command
- Install scripts: custom directory prompt, APP_PORT from .env, searxng permission fix, /dev/tty for piped install
- CI: auto-bump version.json and CHANGELOG.md on tag push, commit to main before release

## v1.0.0 — Nodecast rebrand (2026-07-13)

### Breaking changes

- Complete rebrand: **Recollect → Nodecast**
- All code, URLs, Docker configs, DB files renamed
- New website: [nodecast.dev](https://nodecast.dev)
- GitHub: [sarox-dev/Nodecast](https://github.com/sarox-dev/Nodecast)
- Extension rebranded as [Nodecast-Extension](https://github.com/sarox-dev/Nodecast-Extension)

### Notes

- Old `recollect.db` files automatically renamed to `nodecast.db`
- Cookie name changed from `recollect_token` to `nodecast_token`
- LocalStorage keys migrated from `recollect.*` to `nodecast.*`
- All old data preserved — no migration needed

## v0.2.0 — AI Tagging & Connections (2026-07-10)

### New Features

**AI Connections (Settings → AI)**
- Add/edit/delete AI providers (OpenAI-compatible APIs)
- Supports local (LM Studio, Ollama) and cloud providers
- API keys encrypted at rest with Fernet (ENCRYPTION_KEY in .env)
- Auto-detect Docker environment: `localhost` → `host.docker.internal`
- Fetch available models from provider endpoint
- Assign providers + models to features (currently: Tag Knowledge Objects)

**AI Tagging**
- Automatic tagging on every new capture save
- Context Builder: 4 priority levels (anchor → metadata → extractor data → document blocks)
- Token-efficient: respects ~2000 token budget, truncates from bottom
- Generates 3-5 tags, one-sentence summary, and 2-3 key concepts
- **Existing tag awareness**: AI sees all previously used tags and reuses them when applicable
- **Tag normalization**: lowercase, hyphen-separated, site-name filtering, deduplication
- Manual tagging: "AI Tag" button in Knowledge Viewer
- Bulk tagging: "Tag all untagged" in Settings → AI
- RETAG all: destructive re-tag with confirmation prompt

**Knowledge Viewer**
- New "AI Analysis" card in Overview tab (tags, summary, key concepts, model)
- New `badge-concept` CSS style for key concepts
- "AI Tag" action button for manual re-tagging

### Infrastructure
- `cryptography` dependency added (Fernet encryption)
- `extra_hosts: host.docker.internal:host-gateway` in docker-compose.yml
- DB migration: `ai_providers`, `ai_feature_assignments`, `capture_ai_tags` tables
- Auto-ENCRYPTION_KEY generation on first startup

### Bug Fixes
- z-index conflict between Settings panel and AI provider modal
- `btn.closest('[data-feature]')` returning the button instead of container
- LM Studio model fetch: fallback to manual model input when connection fails
- `localhost` not reachable from Docker containers (auto-rewritten to `host.docker.internal`)

---

## v0.1.0 — Capture Infrastructure & Knowledge Layer (2026-07-06)

### New Features
- Capture Package JSON schema (URL, source, page_metadata, anchor, tags, project)
- Capture Layout YAML configuration (domain matching, capture type)
- Extension sends full Capture Package with page HTML, OG/Twitter/Schema metadata
- Knowledge Object model with 6 types: document, video, reddit_post, json_ld, anchor, metadata
- GenericHtmlExtractor v3.0 — DOM-ordered content blocks, SPA shell detection
- Config Engine — YAML configs extract with json_var, json_ld, CSS selectors, $meta sources
- YouTubeExtractor (Python) — full video info
- Reddit config — old.reddit.com support with URL rewriting
- URL Rewriting: www.reddit.com → old.reddit.com automatically
- Anchor as Knowledge Object (selected_text, css_selector, xpath, context)
- 4 shared tools: html_tools, path_tools, url_tools
- Markdown + JSON renderers
- Knowledge Viewer: 5 tabs (Overview, Renderers, Knowledge, Raw, History)
- 48 tests passing

### Infrastructure
- Multi-user auth with JWT, bcrypt, SQLite
- Setup flow, login/register, API Token support
- Docker + Docker Compose with SearXNG

---

## v0.0.3 — MVP Release (2026-06-30)

- Browser Extension with highlight → save → API
- Backend with SQLite storage
- Web UI with merged search (saved + web)
- SearXNG meta search engine
- Docker + Docker Compose deployment