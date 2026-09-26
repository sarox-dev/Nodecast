# Deployment

Nodecast can run in Docker or as a native Python service. The release installers provide an interactive setup for both modes and can register a host-side automatic updater.

```bash
# Linux / macOS
curl -fsSL https://github.com/sarox-dev/Nodecast/releases/latest/download/install.sh | bash
```

```powershell
# Windows PowerShell
irm https://github.com/sarox-dev/Nodecast/releases/latest/download/install.ps1 | iex
```

The first registered Nodecast account is the administrator. Only that account can see or change update settings. Automatic updates are always orchestrated by the host: systemd/launchd/cron on Linux or macOS and Task Scheduler on Windows. The application container is never given access to the Docker socket.

For manual Docker deployment:

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f app
```

The default URL is `http://localhost:5000`; change `APP_PORT` in `.env` if needed. Persist and back up `contents/` and `.env`: they contain accounts, per-user knowledge databases, raw captures, the JWT secret and the encryption key used for AI credentials.

Nodecast has no SearXNG, Redis, PostgreSQL, Celery, or cloud-sync dependency. For remote exposure, put TLS and access controls in front of the app; the default configuration is intended for a trusted local machine.
