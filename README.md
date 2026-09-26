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

Déployée et vérifiée le 2026-09-26. `ask-my-cv-api.cloudfront.net` (en clair : `d35ssr2343raxt.cloudfront.net`) sert l'API à `/api/*`.

### Architecture

```
Navigateur
   │  POST /api/ask  (x-amz-content-sha256 obligatoire, voir plus bas)
   ▼
CloudFront (d35ssr2343raxt.cloudfront.net)
   │  fonction CloudFront : strip /api, méthodes filtrées, https-only,
   │  en-têtes de sécurité gérés
   │  OAC → signature SigV4
   ▼
Lambda Function URL (AWS_IAM, RESPONSE_STREAM)
   │  appel direct de l'URL → 403 (seul CloudFront est autorisé)
   ▼
Conteneur Lambda (Lambda Web Adapter 1.1.0 + uvicorn)
   │
   ├──▶ Bedrock : Claude Haiku 4.5 (profil `us.`) + Titan V2 embeddings (ca-central-1)
   ├──▶ DynamoDB : `ask-my-cv-chunks` (index vectoriel natif, DOT_PRODUCT, 1024 dim, awscc)
   │              `ask-my-cv-ledger` (TTL)
   ├──▶ SSM Parameter Store : VISITOR_SALT, LANGFUSE_* (SecureString, sous /ask-my-cv)
   └──▶ traces OTLP → X-Ray / CloudWatch Transaction Search (aws/spans, rétention 14 j)
                    → Langfuse (US)
```

Budget AWS Budgets : 15 $/mois hors crédits, alertes par courriel.

### Configuration de production

La configuration de production est `settings.aws.yaml` (`ASK_SETTINGS=settings.aws.yaml`) :

- **LLM** : Claude Haiku 4.5 via Bedrock (`ConverseStream`), profil d'inférence `us.` : les requêtes au LLM sont traitées aux États-Unis.
- **Embeddings** : Titan Text Embeddings V2, en région `ca-central-1` : les embeddings restent au Canada.
- **Recherche** : recherche vectorielle native DynamoDB (`SearchVectors`, index `embedding-index`, 1024 dimensions, `DOT_PRODUCT`).
- **Quotas et budget** : table DynamoDB `ledger`, compteurs atomiques, TTL `expires_at`.
- **Traces** : OpenTelemetry vers CloudWatch (OTLP signé SigV4) et Langfuse ; ni IP ni question dans les traces.

Secrets, uniquement par variables d'environnement (chargées depuis SSM en production) : `VISITOR_SALT` (au moins 32 caractères), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

Indexer le CV dans DynamoDB (exige `embedder: bedrock`) :

```bash
ASK_SETTINGS=settings.aws.yaml uv run python -m ask_my_cv.ingest --target dynamodb
```

Les tests n'appellent jamais AWS : les clients sont simulés (`Stubber`, moto) et l'environnement AWS est isolé.

### `x-amz-content-sha256` obligatoire

L'OAC CloudFront → Lambda Function URL exige, pour tout `POST`, l'en-tête `x-amz-content-sha256` égal au SHA-256 hexadécimal du corps exact envoyé. Sans lui (ou avec une valeur qui ne correspond pas au corps), CloudFront renvoie une erreur avant même d'atteindre la Lambda. `infra/scripts/smoke_prod.py` calcule cet en-tête ; un futur client web devra faire de même (`crypto.subtle.digest`).

### Ordre de mise en place (première fois)

1. `terraform apply` sur `infra/bootstrap` (état S3, ECR, fournisseur OIDC GitHub, rôle de déploiement). Le fournisseur OIDC existait déjà dans le compte : importé avec `terraform import`.
2. Première image : `docker build --platform linux/amd64 --provenance=false --sbom=false -t <repo>:<tag> .` puis `docker push`.
3. `terraform apply` sur `infra/prod` (14 ressources : tables, IAM, Lambda, CloudFront, observabilité, budget).
4. Secrets : `infra/scripts/put-secrets.sh` (ou les valeurs reprises d'un fichier `.env` non versionné).
5. `infra/scripts/enable-transaction-search.sh` (activation unique par compte).
6. Ingestion : `ASK_SETTINGS=settings.aws.yaml uv run python -m ask_my_cv.ingest --target dynamodb`.
7. Test de fumée réel : `python infra/scripts/smoke_prod.py <site_url>`.
8. `gh variable set AWS_DEPLOY_ROLE_ARN / ECR_REPOSITORY_URL / SITE_URL` → active le job `deploy` de la CI (OIDC) : reconstruit/pousse l'image si besoin, la signe et la vérifie, `update-function-code` par digest, puis rejoue le test de fumée en production (voir « Chaîne de sécurité »).

Après ce déploiement, `terraform plan` n'affiche plus aucun changement sur les deux racines.

### Chaîne de sécurité

Tout est dans `.github/workflows/ci.yml`. Les outils tournent depuis leurs images Docker officielles épinglées par digest (pas d'actions tierces) ; les actions GitHub sont épinglées par SHA de commit et Dependabot tient à jour actions, `uv.lock` et Dockerfile.

**À chaque PR et à chaque push sur `main`** (job `security`) :

| Scan | Outil | Portée |
|---|---|---|
| Secrets | gitleaks | tout l'historique git (règles par défaut, aucune exception) |
| Code | semgrep | règles `p/python`, `p/dockerfile`, `p/github-actions`, `p/secrets` |
| Dépendances | osv-scanner | `uv.lock` |
| IaC | trivy config | `infra/`, sévérités HIGH et CRITICAL (constats acceptés et datés dans `.trivyignore.yaml`) |

Le job `test` construit aussi l'image, vérifie que chaque module d'exécution s'y importe, la scanne avec trivy (HIGH/CRITICAL corrigeables) et publie son SBOM CycloneDX (syft) en artefact de la CI (`sbom-<sha>`, 30 jours).

**Au déploiement** (push sur `main`, job `deploy`) :

1. L'image est poussée dans ECR (tags `IMMUTABLE`) ; la suite ne manipule plus que son **digest**.
2. SBOM CycloneDX de l'image poussée, lu directement dans ECR par syft.
3. Signature `cosign sign` et attestation du SBOM `cosign attest --type cyclonedx`, **sans clé** : le certificat Sigstore est émis pour l'identité OIDC du workflow GitHub et l'opération est inscrite au journal de transparence Rekor. cosign 3 range signature et attestation en *bundles* Sigstore, attachés à l'image comme référents OCI. Rekor est public : même si le dépôt est privé, le nom du dépôt, le chemin du workflow, le commit et le digest de l'image y sont visibles.
4. `cosign verify` et `cosign verify-attestation` exigent l'identité exacte `…/.github/workflows/ci.yml@refs/heads/main` : une image signée par un autre workflow ou une autre branche est refusée. Lambda ne sait pas vérifier la signature d'une image conteneur : la vérification se fait donc en CI, juste avant le déploiement, sur le digest qui sera déployé.
5. `update-function-code` avec `ecr/…@sha256:<digest>`, après avoir noté le digest en service.
6. Test de fumée de production (`infra/scripts/smoke_prod.py`). S'il échoue, le digest précédent est remis en service automatiquement, puis `/api/healthz` est contrôlé ; le job reste en échec, et un retour arrière raté est signalé comme tel.

Vérifier soi-même une image (accès ECR requis tant que l'image est privée) :

```bash
cosign verify <compte>.dkr.ecr.ca-central-1.amazonaws.com/ask-my-cv@sha256:<digest> \
  --certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Même chose pour le SBOM avec `cosign verify-attestation --type cyclonedx` (mêmes options).

**Décisions** (écarts assumés par rapport à la spec) :

- **Pas de canary CodeDeploy à 10 %** : pour un trafic de démo, test de fumée de production + retour arrière automatique donnent la même garantie sans alias, CodeDeploy ni alarmes. À revoir si le trafic devient réel.
- **`terraform apply` reste manuel** : les environnements GitHub avec approbation ne sont pas garantis sur un dépôt privé du plan gratuit, et un rôle CI capable d'`apply` aurait des droits d'administrateur. `terraform plan` en commentaire de PR est reporté : il faudrait un rôle de lecture incapable de lire les secrets SSM.
- **Provenance SLSA (`attest-build-provenance`) reportée** : les attestations GitHub exigent un dépôt public (ou GitHub Enterprise). La signature cosign et l'attestation SBOM, elles, fonctionnent sur un dépôt privé.
- **Vérification publique par copier-coller** impossible tant que l'image est dans un ECR privé : à traiter avec la publication (miroir public).

### Coût

≈ 1 $/mois hors Bedrock (Lambda, CloudFront, DynamoDB, ECR, CloudWatch, S3, SSM). Une question ≈ 0,0009 $ (Bedrock).

### Destruction

```bash
terraform -chdir=infra/prod destroy
```

Puis, sur `infra/bootstrap` : retirer `prevent_destroy` sur le bucket d'état et sur le dépôt ECR, vider le bucket (toutes les versions) et le dépôt ECR, puis `terraform destroy`.

### Notes Windows

- Git Bash réécrit les chemins `/...` avant de les passer à `aws.exe` : les scripts exportent `MSYS_NO_PATHCONV=1`.
- En PowerShell, des variables `AWS_*` laissées par `aws configure export-credentials` prennent le pas sur une session `aws login` plus récente : `Remove-Item Env:AWS_*` avant de relancer `aws login`.

### Leçons du déploiement

- `requests` n'était qu'une dépendance transitive de dev : l'image démarrait puis plantait au premier appel (import manquant). Elle est maintenant déclarée explicitement, et les imports sont vérifiés à l'intérieur de l'image construite (pas seulement dans l'environnement de dev).
- L'export OTLP vers X-Ray exige `xray:PutTraceSegments` en plus de `xray:PutSpans` / `PutSpansForIndexing` : sans elle, l'export échoue en 403.
- GitHub émet désormais des sujets OIDC immuables : `repo:<propriétaire>@<id>/<dépôt>@<id>:ref:...` (à relever avec `gh api repos/<o>/<r>/actions/oidc/customization/sub`) ; la politique de confiance du rôle de déploiement a été mise à jour en conséquence.
