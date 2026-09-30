# Interroge mon CV

Assistant RAG sur un CV, instrumenté de bout en bout : chaque étape du pipeline est un span
OpenTelemetry diffusé en direct au navigateur (SSE).

## Comment ce projet a été construit

L'architecte fixe les objectifs et arbitre les choix ; des agents implémentent
les tâches et révisent les changements. La CI, les signatures des artefacts
et les évaluations vérifient les résultats.

La [spec](docs/spec/), les [plans](docs/plans/), le [suivi](docs/followups.md)
et les [journaux de développement](docs/journal/) rendent cette méthode
consultable. Les rapports des agents sont archivés avec les données privées
masquées et les références aux commits publiés. Les échanges privés et les
consignes des agents sont exclus.

Les [issues historiques](https://github.com/VoiD911/ask-my-cv/issues?q=is%3Aissue+label%3Ahistorique)
reconstituent les tâches : leur date de création GitHub est celle de la
reconstitution ; la date réelle du travail figure dans leur description.

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
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright
```

## Évaluations

Deux suites [promptfoo](https://promptfoo.dev) (`evals/`, un fournisseur HTTP maison qui lit le
flux SSE) :

- **À chaque PR** (`evals/pr.yaml`, job `evals` de `ci.yml`) : API locale, faux LLM
  (`settings.ci.yaml`), classifieur ONNX promu. Déterministe, sans dépendance réseau hors de
  `127.0.0.1` — ce sont les garanties du pipeline (citations, refus, blocage des entrées
  invalides, jeu adverse) qui sont prouvées à chaque changement.
- **Chaque nuit** (`evals/nightly.yaml`, job `redteam` de `nightly.yml`, cron `17 7 * * *` +
  `workflow_dispatch`) : vrai modèle, API **déployée** en production (`SITE_URL`, derrière
  CloudFront) — questions légitimes, informations absentes du CV, red team (fuite du prompt
  système reformulée sans vocabulaire d'injection, jeu adverse).

Les requêtes de nuit portent l'en-tête `X-Eval-Token` (secret `EVAL_TOKEN`, comparé en temps
constant à la valeur SSM) : elles tombent dans un compartiment de quota séparé (`eval`, limite
plus large que les visiteurs) sans jamais dépasser le plafond de dépense quotidien, et leurs
spans sont marqués `xops.eval=true`. Un jeton absent ou faux est traité comme un visiteur
ordinaire — aucun raccourci n'existe pour contourner les quotas ou se faire reconnaître comme
tel sans le secret.

Le trafic d'évaluation **partage le plafond de dépense quotidien** avec les visiteurs
(≈ 0,04 $ par nuit) : il n'a pas de budget à part. Si le plafond est atteint, les cas de nuit
échouent au lieu de passer à vide (`evals/usable.js` : une requête arrêtée par le quota, le
plafond ou une erreur ne prouve ni un refus, ni l'absence de fuite).

**Dérive du classifieur** (job `drift` de `nightly.yml`, `ml/drift.py`) : les scores
`xops.score` des spans `injection` des 7 derniers jours (hors trafic `xops.eval`) sont lus dans
CloudWatch Logs Insights (`aws/spans`, rôle IAM `ask-my-cv-nightly`, lecture seule) et comparés,
par PSI (Population Stability Index, 10 compartiments sur `[0, 1]`), à `domain_score_histogram`
du `metrics.json` du modèle promu (scores sur les 50 questions de
`ml/data/recruiter_eval.jsonl`, représentatives du trafic réel plutôt que du jeu de test
adverse). Les scores ≥ `--threshold` (0,5 par défaut, égal à `injection_threshold`) sont
exclus : ce sont des attaques bloquées, pas une dérive du modèle, et une vague d'attaques ne
doit pas déclencher l'alerte. En dessous de 50 scores restants sur la fenêtre, la mesure est
jugée non significative et le job réussit sans avis. PSI ≥ 0,1 : avertissement ; PSI ≥ 0,2 :
échec. Une référence sans `domain_score_histogram` (modèle antérieur à v1.2.0) donne un
avertissement et le job réussit : la dérive n'est pas calculable.

Job `report` (`needs: [redteam, drift]`, `if: failure()`) : à la moindre suite en échec, une
issue GitHub étiquetée `nightly` est ouverte (« Nuit : évaluations en échec », date, jobs en
échec, lien de l'exécution) — ou, si une telle issue est déjà ouverte, complétée d'un commentaire
plutôt que dupliquée.

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
- Annonces collées (#118) : un texte d'au moins 400 caractères (mesurés après NFKC et retrait
  des caractères de format, comme pour les deux détecteurs) que le classifieur laisse passer est
  soumis au garde-fou Bedrock « annonces » ; il est bloqué si l'un des deux le signale (mesuré :
  71 % des injections arrêtées, 13 % des annonces légitimes bloquées). **Limite connue** : une
  injection de moins de 400 caractères ne rencontre que le classifieur et le prompt ; les 71 %
  ne valent que pour les annonces de 400 caractères et plus. Échec isolé du garde-fou : décision
  du classifieur ; échecs répétés (5 sur 60 s venant d'au moins 3 visiteurs, ou 3 d'un même
  visiteur) : disjoncteur, annonces refusées une minute (`src/ask_my_cv/guardrail.py`, alarme
  `ask-my-cv-guardrail-errors`). L'état du disjoncteur est propre à chaque instance Lambda :
  les seuils ne sont pas globaux au service. Tout texte dépassant 10 000 caractères, avant ou
  après repli NFKC, est refusé (422) avant les détecteurs.

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
5. Miroir public : `crane copy` de l'image ECR vers `ghcr.io/void911/ask-my-cv:<sha>` (octets du manifeste copiés tels quels, y compris au rejeu d'un déploiement), puis contrôle que le digest GHCR est celui d'ECR. L'image GHCR est signée par `cosign sign` et reçoit deux attestations GitHub poussées aussi dans le registre : provenance SLSA et SBOM CycloneDX (`actions/attest`). Signature et attestations sont vérifiées avant le déploiement et liées au commit déployé (`--certificate-github-workflow-sha`, `--source-digest`).
   Rejeu d'un déploiement (tag ECR déjà présent) : rien n'est reconstruit, et l'image n'est acceptée que si elle porte déjà une signature de `ci.yml@main` émise pour ce commit ; sinon le job échoue (origine inconnue). Signatures et attestations ne sont émises que si aucune valide n'existe encore pour ce digest : pas de doublons. Contrepartie : une exécution interrompue entre le push ECR et la signature ne se rattrape pas par un rejeu (tag ECR immuable) ; il faut pousser un nouveau commit.
6. `update-function-code` avec `ecr/…@sha256:<digest>`, après avoir noté le digest en service.
7. Test de fumée de production (`infra/scripts/smoke_prod.py`). S'il échoue, le digest précédent est remis en service automatiquement, puis `/api/healthz` est contrôlé ; le job reste en échec, et un retour arrière raté est signalé comme tel.

#### Vérifier l'image

L'image construite pour chaque commit de `main` est publiée à l'identique (même digest) sur `ghcr.io/void911/ask-my-cv`, paquet public, vérifiable sans compte AWS. Elle y est publiée, signée et attestée avant le test de fumée de production : elle reste donc publiée même si un retour arrière suit, et une image présente sur GHCR n'est pas forcément celle en service. Le digest d'un commit s'obtient avec `docker buildx imagetools inspect ghcr.io/void911/ask-my-cv:<sha du commit>` (ligne `Digest:`).

Signature Sigstore (émise par le workflow `ci.yml` de `main`, et lui seul, pour ce commit) :

```bash
cosign verify ghcr.io/void911/ask-my-cv@sha256:<digest> \
  --certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-github-workflow-sha <sha du commit>
```

Provenance SLSA (et SBOM CycloneDX avec `--predicate-type https://cyclonedx.org/bom`). `gh attestation verify` interroge l'API GitHub : il faut être authentifié (`gh auth login` ou `GH_TOKEN`), même pour un dépôt public. Un compte GitHub suffit, pas besoin de compte AWS.

```bash
gh attestation verify oci://ghcr.io/void911/ask-my-cv@sha256:<digest> -R VoiD911/ask-my-cv \
  --signer-workflow VoiD911/ask-my-cv/.github/workflows/ci.yml \
  --source-ref refs/heads/main
```

`--source-ref` et `--source-digest` demandent gh ≥ 2.68.

Sans compte GitHub, la provenance se vérifie aussi anonymement avec cosign ≥ 3 (signatures et attestations rangées en bundles Sigstore, lus comme référents OCI), qui lit l'attestation dans le registre et son inscription dans Rekor :

```bash
cosign verify-attestation ghcr.io/void911/ask-my-cv@sha256:<digest> \
  --type https://slsa.dev/provenance/v1 \
  --certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-github-workflow-sha <sha du commit>
```

Les modèles du classifieur publiés par `train.yml` portent eux aussi une provenance SLSA depuis que le dépôt est public (aucune provenance rétroactive pour les versions antérieures) : `gh attestation verify model.onnx -R VoiD911/ask-my-cv`.

Le Lambda Web Adapter est tiré de `ghcr.io/void911/aws-lambda-adapter`, copie à l'identique (même digest, épinglé dans le `Dockerfile`) de `public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0` faite par `mirror.yml` : les tirages anonymes depuis `public.ecr.aws` échouaient par intermittence sur les exécuteurs GitHub.

**Décisions** (écarts assumés par rapport à la spec) :

- **Pas de canary CodeDeploy à 10 %** : pour un trafic de démo, test de fumée de production + retour arrière automatique donnent la même garantie sans alias, CodeDeploy ni alarmes. À revoir si le trafic devient réel.
- **`terraform apply` reste manuel** : les environnements GitHub avec approbation ne sont pas garantis sur un dépôt privé du plan gratuit, et un rôle CI capable d'`apply` aurait des droits d'administrateur. `terraform plan` en commentaire de PR est reporté : il faudrait un rôle de lecture incapable de lire les secrets SSM.
- **Miroir GHCR plutôt qu'ECR public authentifié** pour le Lambda Web Adapter : pas de droits IAM supplémentaires (`ecr-public:GetAuthorizationToken`, `sts:GetServiceBearerToken`) pour le rôle de déploiement, et le digest épinglé garantit les mêmes octets.

### Site

Le site statique (export Next.js, `web/out`, job `web` de la CI) est publié dans un bucket S3
privé (OAC), derrière le même CloudFront que l'API (comportement par défaut ; `/api/*` reste
routé vers la Lambda). Il n'est pas encore déployé (infra du site : tâche 8, reste à appliquer).

Le job `deploy`, après le déploiement de l'API et son test de fumée :

1. Télécharge l'artefact `web-out-${{ github.sha }}` produit par le job `web` (déjà construit,
   jamais reconstruit à ce stade).
2. Publie `_next/static/**` avec `Cache-Control: public, max-age=31536000, immutable` (fichiers
   hachés par contenu, jamais supprimés — un ancien build encore chargé par un visiteur continue
   de trouver ses chunks), puis le reste (HTML compris) avec `Cache-Control: no-cache` et
   `--delete` pour nettoyer ce qui a disparu du build, sans jamais toucher `_next/static/`
   (exclu explicitement, donc protégé de cette suppression).
3. Invalide tout le cache CloudFront (`create-invalidation --paths "/*"`) et attend sa fin
   (`wait invalidation-completed`).
4. Test de fumée du site : `GET /` contient « Interroge mon CV » ; `GET /api/healthz` inchangé
   (script Python existant, `infra/scripts/smoke_prod.py`).

Ces quatre étapes sont ignorées (avis `::notice::`, pas d'échec) tant que la variable CI
`SITE_BUCKET` n'est pas définie : le pipeline reste vert avant que l'infra du site ne soit
appliquée. Variables CI additionnelles : `SITE_BUCKET`, `DISTRIBUTION_ID` (avec `SITE_URL`, déjà
utilisée par le test de fumée de l'API, qui deviendra `https://job.stevelang.net`).

#### Langues (français, anglais)

Le site existe en français (racine, URL publiques inchangées : `/`, `/architecture/`, `/xops/`,
`/livraison/…`) et en anglais sous `/en/…`. next-intl sans middleware (incompatible avec
`output: "export"`) : deux racines de layout, `web/src/app/(fr)` et `web/src/app/en`, fixent
`<html lang>` et la langue (`setRequestLocale`) ; chaque page partage sa vue (`web/src/views`).
Textes d'interface dans `web/messages/{fr,en}.json` (clés identiques, vérifiées par Vitest) ;
contenus longs dans `web/src/lib/*-content.ts` et leur version `*.en.ts` (même forme imposée par
le typage, preuves et chemins définis une seule fois côté français). Sélecteur de langue en
simple lien, alternatives `hreflang` (x-default : français) et URL canonique sur chaque page.
Le CV (`data/cv.md`) et le journal de /livraison restent en français. L'API ne change pas : dans
l'interface anglaise, ses messages de blocage et sa phrase de refus (exacte, en français) sont
rendus en anglais, l'original du refus restant affiché.

#### CSP

Scripts : aucun `'unsafe-inline'` effectif. L'export statique de Next.js contient des scripts en
ligne (charge RSC `self.__next_f.push(...)`), différents d'une page à l'autre et d'un build à
l'autre. `npm run build` enchaîne `next build` et `web/scripts/csp.mjs` (dans le script `build`
lui-même, pas en `postbuild`, qu'un `ignore-scripts=true` ferait sauter). Ce script parcourt
chaque page HTML de `web/out`, calcule le SHA-256 (base64) du texte exact de chacun de ses scripts
en ligne et insère en tête du `<head>`, juste après `<meta charset>` (une CSP meta ne couvre que
ce qui la suit : aucun script ne la précède) :

```html
<meta http-equiv="Content-Security-Policy" content="script-src 'self' 'sha256-…' 'sha256-…'">
```

Le build échoue si une page n'a pas de `<head>`, si un script précède la meta, si un script a
un attribut `src` vide ou si une meta CSP est déjà présente. `node --test web/scripts/*.test.mjs`
teste ces cas ; la CI vérifie en outre que chaque page de `web/out` porte la meta.

L'en-tête CloudFront (`site_csp`, `infra/prod/variables.tf`) porte le reste de la politique
(`default-src`, `connect-src`, `frame-ancestors`, …) et garde `script-src 'self' 'unsafe-inline'`.
Le navigateur applique l'en-tête **et** la meta : un script n'est exécuté que s'il satisfait les
deux, donc un script en ligne dont le hash manque dans la meta est bloqué. `style-src` garde
`'unsafe-inline'` (styles en ligne de React Flow). `next dev` n'est pas concerné (seul `web/out`
est modifié).

Vérification : le serveur e2e (`web/e2e/serve.mjs`) sert l'en-tête de production, lu dans
`variables.tf`. Chaque test e2e écoute `securitypolicyviolation` dans chaque document ainsi que
les messages console CSP : aucune violation tolérée. `web/e2e/csp.spec.ts` contrôle en plus, pour
`/`, `/architecture/`, `/xops/`, `/en/`, `/en/xops/`, `/en/livraison/1a/`, `/404.html`,
`/_not-found/` et une page inexistante, que la meta est en tête du `<head>`,
avant tout `<script>`, et que le hash de chaque script en ligne du DOM y figure ; un témoin vérifie qu'un script
en ligne non haché est bien bloqué et que la violation est détectée.

#### Lighthouse

Le job `web` de la CI lance `@lhci/cli` 0.15.1 sur l'export statique (`staticDistDir: web/out`,
serveur intégré de lhci — jamais l'API, jamais la CSP/l'en-tête CloudFront de prod) : 3 exécutions
Lighthouse desktop, puis 3 en mobile (`web/lighthouserc.desktop.json`,
`web/lighthouserc.mobile.json`). `upload.target: filesystem` écrit les rapports HTML/JSON dans
`web/lhci-report/{desktop,mobile}` (gitignorés), publiés comme artefact CI (`if: always()`, donc
même en échec).

Scores mesurés (3 runs identiques, Chrome pour Testing sur `ubuntu-latest`) :

| Catégorie      | Desktop | Mobile |
| -------------- | ------- | ------ |
| Performance    | 1.00    | 0.95   |
| Accessibilité  | 1.00    | 1.00   |
| Best Practices | 1.00    | 0.96   |
| SEO            | 1.00    | 1.00   |

Budgets (`assert.assertions`, `minScore`) : accessibilité verrouillée à 0,95 (non négociable,
indépendamment du score mesuré), les autres avec une marge large sous la mesure plutôt que
« juste en dessous » — `ubuntu-latest` est un runner partagé, plus bruité qu'un poste local
(CPU/IO variables d'une exécution à l'autre), et Performance est la catégorie la plus sensible à ce
bruit (LCP, TBT). Fixer le budget à un point sous une mesure unique locale aurait rendu la CI
flaky. `assert.aggregationMethod: "median-run"` réduit déjà une partie du bruit intra-exécution
en évaluant les assertions sur l'exécution (parmi les 3) la plus proche de la médiane plutôt que
sur une agrégation par métrique :

| Catégorie      | Desktop | Mobile |
| -------------- | ------- | ------ |
| Performance    | 0.90    | 0.80   |
| Accessibilité  | 0.95    | 0.95   |
| Best Practices | 0.95    | 0.90   |
| SEO            | 0.95    | 0.95   |

**Écart réel corrigé plutôt que budgété** : la page appelait `GET /api/models` dès le montage
(`Demo.tsx`) pour peupler le sélecteur de modèle. Servi seul (sans l'API, comme dans ce job),
`web/out` répond 404 à cet appel, et Chrome journalise l'échec réseau en erreur console — audit
`errors-in-console` (Best Practices) en échec, indépendamment du `catch` déjà en place (qui masque
le sélecteur mais n'empêche pas Chrome de journaliser la requête réseau ratée). Corrigé en
différant l'appel à la première interaction avec la saisie (focus, ou premier envoi de question)
plutôt qu'au chargement : la page reste inerte tant qu'aucune question n'est amorcée, conforme à
l'hypothèse de départ (`Demo.interact.test.tsx`). Un `favicon.ico` manquant causait la même erreur
(`errors-in-console`) ; `src/app/icon.svg` (convention de métadonnées de Next.js) le remplace.

Écart mesuré non corrigé : en mobile, Best Practices reste à 0,96 (`font-size` — quelques libellés
du bandeau de circuit sous 12px) et Performance à 0,95 (LCP ≈ 2,97 s). Budgétés tels quels
(0,95 / 0,94) plutôt que « corrigés » : hors périmètre de cette tâche (CI Lighthouse), à traiter
séparément si le confort de lecture mobile ou le LCP doivent être améliorés.

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

## Gouvernance

- **PR obligatoires sur `main`**, avec vérifications requises avant fusion : `security`, `test`, `evals`, `web`, `terraform` (jobs de `.github/workflows/ci.yml`). Ensemble de règles « main protégée » actif : ni push direct, ni push forcé, ni suppression ; contournement réservé à l’administrateur et uniquement par PR.
- **Environnements protégés** `production` (job `deploy`, `.github/workflows/ci.yml`) et `nightly` (jobs `redteam` et `drift`, `.github/workflows/nightly.yml`), tous deux limités à la branche `main` (politique de déploiement personnalisée côté GitHub).
- **Sujets OIDC par environnement** : le rôle de déploiement n'accepte que le sujet immuable `repo:VoiD911@15268916/ask-my-cv@1389934708:environment:production`, le rôle de nuit que `…:environment:nightly` (`infra/bootstrap`). Un job de `main` sans environnement, une autre branche, un fork ou une PR ne peuvent prendre aucun des deux rôles.
- **`EVAL_TOKEN`** est uniquement un secret de l'environnement `nightly`, lu par le job `redteam` (aucune copie au niveau du dépôt).
- **Revues** : postées en commentaire de la PR par un agent de revue, jamais en tant qu'« approval » GitHub ; la fusion reste décidée par le contrôleur humain.
