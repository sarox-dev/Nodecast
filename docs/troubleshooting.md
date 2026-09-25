# Troubleshooting

## App does not start

```bash
docker compose ps
docker compose logs app
curl http://localhost:5000/api/server/health
```

## A highlighted save has no atomics

- Confirm the extension sent both `anchor.selected_text` and `page_html`.
- Check `/api/ai/pending-count` and `/api/ai/batch-status`.
- Verify the atomic extraction provider/model under Settings → AI.
- A failed or absent AI assignment falls back to a single cleaned text atomic when the extraction job runs.

## AI provider is offline

- From Docker, local providers must normally use `host.docker.internal`.
- LM Studio default: `http://host.docker.internal:1234/v1`.
- Ollama OpenAI-compatible default: `http://host.docker.internal:11434/v1`.

## Reset local development data

Stop the app before removing `contents/users/`, `contents/users.db`, and `contents/.jwt_secret`, then start it and register again. This is destructive and intended only while the project has no data that must be preserved.
