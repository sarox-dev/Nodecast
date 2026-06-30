<h1 align="center">Recollect</h1>

<p align="center">
  <img src="app/static/logo.png" width="120" height="120" alt="Recollect logo" />
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
  Recollect turns the web into your personal knowledge base —
  save content, not bookmarks, and find it again instantly.
</p>

---

## What is Recollect?

**Recollect is a private, self-hosted research tool** that lets you capture, organize, and instantly find useful information from the web.

Instead of losing solutions in browser tabs or scattered bookmarks, Recollect stores the **actual content** you care about — with full text search, project organization, and optional AI-powered features.

Search privately via **SearXNG** (meta search engine), save highlighted text from web pages, and retrieve everything from a single local-first interface.

---

## Quick Start

### One-command install

**Linux / macOS:**
```bash
curl -fsSL https://github.com/sarox-dev/Recollect/releases/latest/download/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://github.com/sarox-dev/Recollect/releases/latest/download/install.ps1 | iex
```

### Manual setup

```bash
git clone https://github.com/sarox-dev/Recollect.git
cd Recollect

# Configure environment
cp .env.example .env

# Start with Docker
docker compose up -d
```

The app runs at **http://localhost:5000**.

### What you need
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- Git (for manual setup)

---

## Features

| Feature | Description |
|---|---|
| 🔍 **Private Meta Search** | Powered by SearXNG — aggregates results from multiple search engines without tracking |
| ✂️ **Content-first saving** | Save highlighted text, not URLs. Keep the parts that matter |
| 📁 **Project organization** | Group saved content into projects for structured knowledge management |
| 💾 **Local-first storage** | Your data stays on your machine. No cloud dependency |
| 🔎 **Search inside saved content** | Full-text search across everything you've saved |
| 🌐 **Browser extension** | Save highlights directly from any webpage (optional) |

---

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Browser        │────▶│  FastAPI App  │────▶│  SearXNG    │
│  (UI / Ext.)    │     │  (port 5000)  │     │  (port 8080) │
└─────────────────┘     └──────┬───────┘     └─────────────┘
                               │
                        ┌──────▼───────┐
                        │  Local       │
                        │  Storage     │
                        │  (contents/) │
                        └──────────────┘
```

- **FastAPI** — Python web server serving the frontend and API
- **SearXNG** — Self-hosted meta search engine (Docker)
- **Local storage** — All saved content stored in a local directory
- **Browser extension** — Chrome extension for capturing highlights (separate repo)

---

## Environment Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | App bind address |
| `APP_PORT` | `5000` | App port |
| `SEARXNG_PORT` | `8080` | SearXNG internal port |
| `SEARXNG_URL` | `http://searxng:8080` | SearXNG internal URL |

---

## Browser Extension

The [Recollect browser extension](https://github.com/sarox-dev/Recollect-Extension) lets you:
- Select text on any webpage and save it directly to Recollect
- Use keyboard shortcuts (`Alt+Shift+R`) for quick saving
- See how many highlights you've saved at a glance

Install from the Chrome Web Store or load unpacked in developer mode.

---

## Use Cases

- **Developers** — Save stack overflow solutions, config snippets, and bug fixes
- **Researchers** — Collect and organize sources, quotes, and findings
- **Students** — Keep learning materials searchable and project-structured
- **Privacy-conscious users** — Search and save without tracking

---

## Roadmap

### ✅ MVP (current)
- Private meta search (SearXNG)
- Content saving with metadata
- Project-based organization
- Local-first storage
- Full-text search

### 🚧 In progress
- Browser extension improvements
- AI summarization and auto-tagging
- Premium features (extension)

### 🔮 Future
- Hosted version
- Integrations (Obsidian, Notion)
- Plugin system
- Themes

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

- Open an [issue](https://github.com/sarox-dev/Recollect/issues)
- Suggest features
- Join the [Discord](https://discord.gg/BXEDCJP7mT)

---

## License

Copyright (c) 2026 Saroxtech

Recollect is licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See the LICENSE file for details.

Commercial licenses for proprietary use (for example, embedding Recollect in closed-source software or OEM distribution) are available from the copyright holder.

---

## Links

- 🌍 **Website**: [recollect.saroxtech.com](https://recollect.saroxtech.com)
- 💬 **Discord**: [Join the community](https://discord.gg/BXEDCJP7mT)
- 🐙 **GitHub**: [github.com/sarox-dev/Recollect](https://github.com/sarox-dev/Recollect)
- 🔌 **Extension**: [Recollect-Extension](https://github.com/sarox-dev/Recollect-Extension)

[license-badge]: https://img.shields.io/badge/License-AGPL--3.0-blue?logo=gnu
[license-url]: LICENSE
[stars-badge]: https://img.shields.io/github/stars/sarox-dev/Recollect?style=social
[stars-url]: https://github.com/sarox-dev/Recollect
[python-badge]: https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=yellow
[python-url]: https://python.org
[docker-badge]: https://img.shields.io/badge/Docker-Compose-green?logo=docker
[docker-url]: https://hub.docker.com
[discord-badge]: https://img.shields.io/discord/1490718135081242745?style=for-the-badge&logo=discord&logoColor=white&label=Join&labelColor=1e2124&color=7289da
[discord-url]: https://discord.gg/BXEDCJP7mT
