# Interroge mon CV

Assistant RAG sur un CV, instrumenté de bout en bout : chaque étape du pipeline est un span
OpenTelemetry diffusé en direct au navigateur (SSE).

## Lancer en local

```bash
uv sync
uv run python -m ask_my_cv.ingest        # construit data/index.json à partir de data/cv.md
uv run uvicorn --factory ask_my_cv.app:create_app --port 8000 --no-access-log
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

Les journaux d'accès sont désactivés : ils contiendraient les IP des visiteurs.

## Tests

```bash
uv run pytest -q && uv run ruff check . && uv run pyright
```

## Classifieur d'injection (MLOps)

```bash
uv sync --group ml
uv run python -m ml.fetch                        # sources épinglées, vérifiées par sha256
uv run python -m ml.train --version v0.0.0 --out dist
```

- La porte d'évaluation (`ml/gates.yaml`) fait échouer l'entraînement si un seuil n'est pas tenu :
  rappel et faux positifs sur deepset, rappel hors distribution sur Gandalf, ensemble adverse écrit
  à la main, et parité entre le modèle ONNX servi et scikit-learn.
- L'entraînement est reproductible : même sha256 de modèle en local et en CI.
- Les modèles publiés sont des releases `model-vX.Y.Z` signées par le workflow `train.yml`
  (Sigstore keyless) ; la CI vérifie la signature avant de construire l'image.
- `models/prod.json` désigne le modèle en production ; il ne change que par PR.
- En local, pour utiliser le modèle promu : `gh release download model-<version> -p model.onnx -D models`.
