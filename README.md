<h1 align="center">Nodecast</h1>

<p align="center">
  <img src="app/static/logo.png" width="120" height="120" alt="Nodecast logo" />
</p>

<div align="center">

[![License: AGPL-3.0][license-badge]][license-url]
[![Stars][stars-badge]][stars-url]
[![Python][python-badge]][python-url]
[![Docker][docker-badge]][docker-url]
[![Discord][discord-badge]][discord-url]

</div>

<p align="center"><strong>Search once. Reuse forever.</strong></p>

<p align="center">
  Nodecast turns the web into your personal knowledge base —
  save content, not bookmarks, and find it again.
</p>

---

## What is Nodecast?

**Nodecast is a private, self-hosted research tool** that captures web pages as structured, searchable knowledge — not just URLs or screenshots.

When you save a page, Nodecast's extraction pipeline automatically parses the content into meaningful pieces: headings, paragraphs, images, code blocks, tables, videos, and metadata. Posts from sites like YouTube and Reddit get specialized extractors that pull out author, score, duration, comments — whatever matters. You can also highlight specific text before saving, which becomes an anchor point for future AI processing.

Everything stays on your machine. No cloud, no tracking.

---

## Quick Start

### One-command install

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/sarox-dev/Nodecast/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/sarox-dev/Nodecast/main/install.ps1 | iex
```

### Manual setup

```bash
git clone https://github.com/sarox-dev/Nodecast.git
cd Nodecast

# Configure environment
cp .env.example .env
# Then edit .env to set JWT_SECRET (required) and optionally adjust ports

# Start with Docker
docker compose up -d
```

The app runs at **http://localhost:5000**. On first run, register an admin account — after that you can log in and start saving.

### What you need

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- Git (for manual setup)
- About 5 minutes

---

## Features

| Feature | Description |
|---|---|
| 🔍 **Private Meta Search** | Powered by SearXNG — aggregates results from multiple search engines without tracking |
| ✂️ **Structured content extraction** | Not just HTML — headings, paragraphs, images, code, tables, lists, JSON-LD |
| 🎯 **Specialized site extractors** | YouTube (author, duration, description), Reddit (score, subreddit, comments) |
| 📎 **Anchor / selected text** | Highlight text before saving — preserved as a reference point for AI |
| 🔌 **Config-driven extractors** | Add new sites with YAML config files, no Python needed |
| 📁 **Project organization** | Group saved content into projects for structured knowledge management |
| 💾 **Local-first storage** | Your data stays on your machine. No cloud dependency |
| 🔎 **Full-text search** | Search across everything you've saved |
| 🧠 **AI Tagging** | Local or cloud AI models auto-generate tags, summaries, and key concepts |
| 🔗 **AI Connections** | Connect any OpenAI-compatible API (LM Studio, Ollama, OpenAI, etc.) |
| 📝 **Markdown & JSON export** | View extracted content as formatted Markdown or raw JSON |
| 🌐 **Browser extension** | Save highlights directly from any webpage (see below) |

---

## Extraction Pipeline

When you save a page, Nodecast runs a multi-stage extraction pipeline:

```
Browser Extension
       ↓
  Capture Package (JSON + full HTML + optional anchor)
       ↓
  URL Rewriting (SPA sites → static versions)
       ↓
  Extractor Pipeline:
       ├─ Python Extractors (YouTube — robust, vairāku avotu)
       ├─ Config Engine (YAML — viegli pievienot jaunas vietnes)
       └─ GenericHtmlExtractor (DOM-ordered content blocks)
       ↓
  Anchor pievienošana (if text was selected)
       ↓
  Knowledge Objects → SQLite
       ↓
  Renderer (Markdown/JSON/Knowledge Viewer)
       ↓
  AI Tagging (configurable provider + model)
       ↓
  Tags, Summary & Key Concepts → SQLite
```

### Generic HTML v3.0

For any web page, identifies the main content container (`<article>` → `<main>` → `<body>`), walks the DOM in document order, and creates typed blocks:

| Block type | Extracted from | Fields |
|---|---|---|
| `heading` | h1-h6 | content, level |
| `paragraph` | p | content |
| `image` | img | src, alt, width, height |
| `code` | pre/code | content, language |
| `table` | table | rows[][] |
| `blockquote` | blockquote | content |
| `list_item` | ul/ol/li | content, list_type, depth |
| `hr` | hr | — |

All blocks preserve document order, so the rendered output matches the original page layout.

### Config Engine

Sites with known structure get YAML configs under `extractor_configs/`:

| Config | Extracts |
|---|---|
| `youtube_video.yaml` | video_id, title, author, channel_id, duration, view_count, keywords, publish_date, category |
| `reddit_post.yaml` (old.reddit.com) | title, author, subreddit, score, timestamp, comments_count |

Configs use `json_var`, `json_ld`, `$meta:` tags, and `$css:` selectors to locate data — no Python required.

### URL Rewriting

For SPA sites that serve empty HTML shells:

| Original | Rewritten to | Why |
|---|---|---|
| `www.reddit.com` | `old.reddit.com` | www sends 8KB loading page |
| (more coming) | | |

### Anchor / Selected Text

If you highlight text before saving, it's stored as a separate `anchor` Knowledge Object alongside the full page content — preserving both the specific selection and its context (text before/after, CSS selector, XPath).

---

## Environment Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | App bind address |
| `APP_PORT` | `5000` | App port |
| `JWT_SECRET` | *(required)* | Secret key for auth tokens (generate with `openssl rand -hex 32`) |
| `JWT_EXPIRY_HOURS` | `72` | Token expiration |
| `SEARXNG_PORT` | `8080` | SearXNG internal port |
| `SEARXNG_URL` | `http://searxng:8080` | SearXNG internal URL |

---

## Project Structure

```
Nodecast/
├── app/
│   ├── api/routes/         — FastAPI endpoints (capture, knowledge, auth, etc.)
│   ├── core/               — Security, config
│   ├── models/             — Pydantic models (CapturePackage, KnowledgeObject)
│   ├── services/
│   │   ├── extractors/     — Extraction pipeline
│   │   │   ├── engine.py          — Config-driven engine
│   │   │   ├── config_loader.py   — YAML config loader
│   │   │   ├── html_tools.py      — JSON/JS variable extraction
│   │   │   ├── path_tools.py      — Dot notation resolver
│   │   │   ├── url_tools.py       — Domain/path matching
│   │   │   ├── youtube.py         — Python YouTube extractor
│   │   │   ├── generic_html.py    — v3.0 DOM-ordered content blocks
│   │   │   └── configs/           — YAML site configs
│   │   │       ├── youtube_video.yaml
│   │   │       └── reddit_post.yaml
│   │   ├── renderers/      — Markdown, JSON renderers
│   │   ├── knowledge_store.py     — Knowledge Object CRUD
│   │   └── extractor_pipeline.py  — Pipeline orchestrator
│   ├── static/             — CSS, JS
│   └── templates/          — Jinja2 HTML templates
├── contents/               — Local storage (per-user directories)
├── searxng/                — SearXNG config
├── tests/
│   ├── extractors/
│   │   ├── test_extractors.py  — 48 tests
│   │   ├── fixtures/           — HTML test pages
│   │   └── expected/           — Expected Knowledge Objects
│   └── e2e_*.py               — End-to-end tests
├── docker-compose.yml
├── Dockerfile
├── install.sh / install.ps1
└── README.md
```

## Browser Extension

The [Nodecast browser extension](https://github.com/sarox-dev/Nodecast-Extension) lets you:
- Select text on any webpage and save it directly to Nodecast
- Use keyboard shortcuts (`Alt+Shift+R`) for quick saving
- See how many highlights you've saved at a glance

The extension sends the full page HTML alongside any highlighted text, so you always get both the content and your specific selection.

> **Note:** The Chrome Web Store release is planned for 2029 due to current publishing restrictions. Until then, the extension can be loaded unpacked in Developer Mode.

---

## Knowledge Objects — What Gets Saved

When you open a saved capture in Nodecast, you'll see structured data in three views:

| Tab | Shows |
|---|---|
| **Overview** | Capture summary (URL, type, date), type stats, actions |
| **Renderers** | Formatted Markdown with styled blocks |
| **Knowledge** | Each Knowledge Object as a card with properties |
| **Raw** | Original Capture Package JSON + HTML download |

Currently supported Knowledge Object types:

| Type | Source |
|---|---|
| `document` | Generic HTML — ordered blocks of paragraphs, headings, images, code, tables |
| `metadata` | All sources — title, description, keywords, OG/Twitter tags |
| `video` | YouTube — author, channel, duration, views, publish date, category |
| `reddit_post` | Reddit — author, subreddit, score, timestamp, comments |
| `json_ld` | Schema.org JSON-LD data found in pages |
| `anchor` | User-selected text with before/after context and CSS/XPath |

---

## Testing

```bash
# Run all extractor tests
python -m pytest tests/extractors/test_extractors.py -v

# Run end-to-end tests (requires internet)
python tests/e2e_test_reddit_real.py
python tests/e2e_test_youtube_real.py
```

Currently **48 automated tests** covering JSON extraction, URL matching, path resolution, config loading, and full pipeline execution.

---

## Roadmap

### ✅ Completed

- Auth system (per-user SQLite, JWT, bcrypt)
- Capture Package format (full HTML + metadata + anchor)
- GenericHtmlExtractor v3.0 with DOM-ordered content blocks
- Config-driven extraction engine (YAML site configs)
- YouTube extractor (Python, multi-source with fallback)
- Reddit config (old.reddit.com)
- URL rewriting (www.reddit.com → old.reddit.com)
- Anchor as Knowledge Object (selected text preservation)
- Markdown/JSON renderers
- Knowledge Viewer UI (5 tabs)
- AI Connections system (add/edit/delete providers, model fetch)
- AI Tagging engine (Context Builder, local/cloud models)
- Auto-tagging on capture save + bulk tag/retag
- Tag normalization + existing tag awareness
- AI Analysis card in Knowledge Viewer

### 🚧 In Progress

- Full-text search across Knowledge Objects
- Home page / capture listing improvements

### 🔮 Future

- YouTube subtitle/transcript extraction
- AI-powered config generation
- Inline save buttons (CaptureLayout)
- Knowledge Graph visualization
- Marketplace for community configs
- Hosted / cloud version

---

## Business Model

| Tier | Features |
|---|---|
| 🟢 **Open Source** | Self-hosted, free forever, all core features |
| 🔴 **Premium** | Cloud sync, AI features, advanced extension capabilities |

The core is and always will be open source under AGPL-3.0. Premium features are offered as a commercial extension — never taken away from the free version.

---

## Contributing

This project is in early development. Contributions, ideas, and feedback are welcome.

- Open an [issue](https://github.com/sarox-dev/Nodecast/issues)
- Create a new [site config](https://github.com/sarox-dev/Nodecast/tree/main/app/services/extractors/configs) for your favorite website
- Join the [Discord](https://discord.gg/BXEDCJP7mT)

---

## License

Copyright (c) 2026 Saroxtech

Nodecast is licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See the LICENSE file for details.

Commercial licenses for proprietary use (for example, embedding Nodecast in closed-source software or OEM distribution) are available from the copyright holder.

---

## Links

- 🌍 **Website**: [nodecast.dev](https://nodecast.dev)
- 📖 **Docs**: [docs.nodecast.dev](https://docs.nodecast.dev)
- 💬 **Discord**: [Join the community](https://discord.gg/BXEDCJP7mT)
- 🐙 **GitHub**: [github.com/sarox-dev/Nodecast](https://github.com/sarox-dev/Nodecast)
- 🔌 **Extension**: [Nodecast-Extension](https://github.com/sarox-dev/Nodecast-Extension)
- 📺 **YouTube**: [@Nodecast-dev](https://youtube.com/@Nodecast-dev)

[license-badge]: https://img.shields.io/badge/License-AGPL--3.0-blue?logo=gnu
[license-url]: LICENSE
[stars-badge]: https://img.shields.io/github/stars/sarox-dev/Nodecast?style=social
[stars-url]: https://github.com/sarox-dev/Nodecast
[python-badge]: https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=yellow
[python-url]: https://python.org
[docker-badge]: https://img.shields.io/badge/Docker-Compose-green?logo=docker
[docker-url]: https://hub.docker.com
[discord-badge]: https://img.shields.io/discord/1490718135081242745?style=for-the-badge&logo=discord&logoColor=white&label=Join&labelColor=1e2124&color=7289da
[discord-url]: https://discord.gg/BXEDCJP7mT