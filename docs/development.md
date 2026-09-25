# Development

```bash
cp .env.example .env
docker compose up -d
python -m pytest tests/ -v
```

Local server:

```bash
uvicorn app.main:app --reload --port 5000
```

Before editing, use CodeGraph to inspect source and impact:

```bash
codegraph explore "feature or flow"
codegraph node "symbol"
codegraph affected app/path.py
codegraph sync
```

The extractor tests validate the deterministic URL/config/HTML extractors. Changes to atomics, APIs, relations and database behavior should add focused integration tests; extractor success alone does not validate the knowledge pipeline.

SQLite rules: inspect schema before raw SQL, use `source_title/source_url/source_site_name`, and do not call `.get()` on `sqlite3.Row`.
