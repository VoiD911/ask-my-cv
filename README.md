# Interroge mon CV

Assistant RAG sur un CV, instrumenté de bout en bout : chaque étape du pipeline est un span
OpenTelemetry diffusé en direct au navigateur (SSE).

## Lancer en local

```bash
uv sync
gh release download model-v1.0.0 -p model.onnx -D models   # settings.yaml utilise le détecteur ONNX
uv run python -m ask_my_cv.ingest        # construit data/index.json à partir de data/cv.md
uv run uvicorn --factory ask_my_cv.app:create_app --port 8000 --no-access-log --no-proxy-headers
```

Avec un modèle local (optionnel) :

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull gemma3:1b
```

Sans Ollama, les requêtes basculent automatiquement sur le faux LLM (`fake:echo`).

L'image Docker (`docker build` / `docker run`) démarre en production par défaut
(`ASK_ENVIRONMENT=prod`) et refuse de démarrer sans un secret dédié :

```bash
docker build -t ask-my-cv .
docker run --rm -p 8000:8000 -e VISITOR_SALT=<secret d'au moins 32 caractères> ask-my-cv
```

`docker compose up` reste en mode développement (`ASK_ENVIRONMENT=dev`, voir `compose.yaml`).

## Endpoints

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/healthz` | Sonde de vie |
| GET | `/models` | Modèles publics et modèle par défaut |
| POST | `/ask` | `{"question": "...", "model": "..."}` → flux `text/event-stream` |

Événements : `stage.start`, `stage.end`, `llm.progress`, `answer`, `done` (voir `src/ask_my_cv/events.py`).

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

## Production (AWS, `ca-central-1`)

La configuration de production est `settings.aws.yaml` (`ASK_SETTINGS=settings.aws.yaml`) :

- **LLM** : Claude Haiku 4.5 via Bedrock (`ConverseStream`), profil d'inférence `us.` : les requêtes au LLM sont traitées aux États-Unis.
- **Embeddings** : Titan Text Embeddings V2, en région `ca-central-1` : les embeddings restent au Canada.
- **Recherche** : recherche vectorielle native DynamoDB (`SearchVectors`, index `embedding-index`, 1024 dimensions, `DOT_PRODUCT`).
- **Quotas et budget** : table DynamoDB `ledger`, compteurs atomiques, TTL `expires_at`.
- **Traces** : OpenTelemetry vers CloudWatch (OTLP signé SigV4) et Langfuse ; ni IP ni question dans les traces.

Secrets, uniquement par variables d'environnement : `VISITOR_SALT` (au moins 32 caractères), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

Indexer le CV dans DynamoDB (exige `embedder: bedrock`) :

```bash
ASK_SETTINGS=settings.aws.yaml uv run python -m ask_my_cv.ingest --target dynamodb
```

Les tests n'appellent jamais AWS : les clients sont simulés (`Stubber`, moto) et l'environnement AWS est isolé.
