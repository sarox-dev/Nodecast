# Deployment

Nodecast currently deploys as one local FastAPI service.

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f app
```

The default URL is `http://localhost:5000`; change `APP_PORT` in `.env` if needed. Persist and back up `contents/` and `.env`: they contain accounts, per-user knowledge databases, raw captures, the JWT secret and the encryption key used for AI credentials.

Nodecast has no SearXNG, Redis, PostgreSQL, Celery, or cloud-sync dependency. For remote exposure, put TLS and access controls in front of the app; the default configuration is intended for a trusted local machine.
