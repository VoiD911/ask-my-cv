# Interroge mon CV

Assistant RAG sur un CV, instrumenté de bout en bout : chaque étape du pipeline est un span
OpenTelemetry diffusé en direct au navigateur (SSE).

## Lancer en local

```bash
uv sync
uv run python -m ask_my_cv.ingest        # construit data/index.json à partir de data/cv.md
uv run uvicorn ask_my_cv.app:app --port 8000
```

Avec un modèle local (optionnel) :

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull gemma3:1b
```

Sans Ollama, les requêtes basculent automatiquement sur le faux LLM (`fake:echo`).

## Endpoints

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/healthz` | Sonde de vie |
| GET | `/models` | Modèles publics et modèle par défaut |
| POST | `/ask` | `{"question": "...", "model": "..."}` → flux `text/event-stream` |

Événements : `stage.start`, `stage.end`, `token`, `done` (voir `src/ask_my_cv/events.py`).

## Tests

```bash
uv run pytest -q && uv run ruff check . && uv run pyright
```
