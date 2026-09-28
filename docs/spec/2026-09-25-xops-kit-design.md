# xops-kit + « Interroge mon CV » — design

- **Date :** 2026-09-25
- **Statut :** validé en brainstorming, en attente de relecture
- **Objectif :** un toolkit personnel réutilisable dans tous les projets, qui couvre DevOps, DevSecOps, MLOps, MLSecOps, LLMOps, LLMSecOps, AIOps et FinOps, démontré par une application de référence et un site portfolio interactif, pour décrocher un emploi.

## 1. Vue d'ensemble et découpage

Le système se découpe en quatre sous-projets. Chacun aura son propre plan d'implémentation, dans cet ordre :

| # | Sous-projet | Dépôt | Rôle |
|---|---|---|---|
| 1 | Application de référence « Interroge mon CV » | `ask-my-cv` | La preuve : un RAG sur le CV, équipé de bout en bout. Plans : 1a cœur d'API, 1b classifieur, **1c-1a durcissement**, **1c-1b adaptateurs AWS**, **1c-2 infrastructure**, 1d DevSecOps, 1e site |
| 2 | Toolkit réutilisable | `xops-kit` | Template, workflows, modules Terraform, paquets, audit |
| 3 | Plugin Claude Code `xops` | `xops-kit/claude-plugin` | Sélection d'ECC + skills pour les cases manquantes |
| 4 | Site portfolio | `ask-my-cv/web` | Démos interactives et preuves publiques |

**Principe de construction :** on construit d'abord l'application (1), puis on *extrait* vers le kit (2) ce qui se répète. On n'abstrait jamais quelque chose qui n'a pas été fait au moins une fois pour de vrai. Une fois le kit extrait, l'application est régénérée ou mise à jour depuis le template, ce qui prouve que le kit fonctionne sur un vrai projet.

**Langages :** Python pour le backend, le ML et la lib `xops-core`. TypeScript pour le site et le composant `flow-viz`.

## 2. Architecture (sous-projet 1)

### 2.1 Composants d'exécution

| Composant | AWS (principal) | Portable (local / VPS) |
|---|---|---|
| Site | Next.js export statique sur S3 + CloudFront | n'importe quel serveur statique |
| API | Image Docker FastAPI dans Lambda via Lambda Web Adapter, streaming SSE (Function URL) | même image, `docker compose up` |
| Région | **`ca-central-1` (Montréal)** pour toute l'infrastructure | — |
| LLM | Amazon Bedrock : Claude Haiku 4.5 par défaut via le profil d'inférence **`us.`** (les requêtes LLM sont traitées aux États-Unis, mention obligatoire sur le site), autres modèles via liste blanche | Ollama |
| LLM, second cloud | Azure AI Foundry, modèles serverless uniquement, désactivé sans identifiants | — |
| Embeddings | Bedrock Titan Text Embeddings V2 (1024 dimensions, normalisés, produit scalaire) | embedder par hachage (ou Ollama) |
| Recherche vectorielle | DynamoDB vector search natif (GA le 2026-08-05), table on-demand, API `SearchVectors` | index JSON chargé en mémoire (fichier) |
| Quotas et budget | table DynamoDB `ledger` (on-demand) : compteurs atomiques, écritures conditionnelles, TTL | en mémoire |
| Artefacts ML | GitHub Releases `model-vX.Y.Z` (registre) + `models/prod.json` (alias prod, promu par PR) ; miroir S3 en 1c | dossier `models/` |
| Traces | OpenTelemetry, deux exports : **CloudWatch** (OTLP signé SigV4, `ca-central-1` : exploitation, alarmes, canary) et **Langfuse Cloud** (vitrine LLM, sans IP ni question brute) ; plus le flux SSE vers le navigateur | console ou aucun export |
| Garde-fou budgétaire | AWS Budgets → alarme → bascule en « mode démo » | plafond dans la config |

**Portabilité :** tout accès externe passe par une interface (`LLMProvider`, `EmbeddingProvider`, `VectorStore`, `BudgetLedger`, `ArtifactStore`). L'implémentation se choisit dans la config (`settings.yaml` et variables d'environnement), jamais dans le code.

### 2.2 Sélection de modèle

- La config déclare les fournisseurs et modèles disponibles, avec leur coût par token.
- Liste blanche publique : seuls les modèles marqués `public: true` apparaissent dans le sélecteur du site.
- Chaîne de bascule configurable (ex. `bedrock:haiku → azure:llama-3.3-70b → ollama:gemma`) en cas de panne ou de délai dépassé.
- Un fournisseur sans identifiants apparaît comme « hors ligne » dans l'interface, sans erreur.

### 2.3 Services exclus (pièges de coût)

OpenSearch Serverless, EKS, NAT Gateway, instances GPU, load balancers permanents, déploiements Azure en *managed compute*.

## 3. Pipeline d'une requête

Chaque étape est un span OpenTelemetry. Ce même span alimente le diagramme en direct (SSE) et l'historique (Langfuse).

| # | Étape | Détail | Échec | Ops démontrés |
|---|---|---|---|---|
| 1 | Réception | `trace_id`, validation, modèle choisi | requête mal formée : 422 (sans renvoyer l'entrée) ; question ou modèle refusés : événement `blocked` | DevOps |
| 2 | Quota et budget | limite par visiteur (IP hachée), plafond quotidien global ; dépenses suivies par fournisseur (plafonds par fournisseur avec Azure) | **fermé** : refus ou mode démo | FinOps, AIOps |
| 3 | Classifieur d'injection | modèle ONNX maison, version et score dans le span, seuil configurable | **fermé** : refus | MLSecOps, MLOps |
| 4 | Embedding | embedding de la question | erreur visible (pas de bascule : l'index est lié au modèle d'embedding) | LLMOps |
| 5 | Recherche vectorielle | top 5 passages du CV | erreur visible | LLMOps |
| 6 | Prompt versionné | template `prompt@vN` stocké dans le dépôt, passages cités | — | LLMOps, gouvernance |
| 7 | Appel LLM | génération côté serveur ; seule la **progression** (nombre de tokens) est diffusée, jamais le texte ; délai jusqu'au premier token + délai global ; coût des tentatives partielles comptabilisé | bascule sur la chaîne, y compris en cours de génération (aucun texte n'est encore sorti) | LLMOps, multicloud |
| 8 | Garde-fou de sortie | fuite du prompt système, PII, ancrage dans les passages ; la phrase de refus fixe « Je ne trouve pas cette information dans le CV. » est acceptée | **fermé** : aucun texte du LLM ne quitte le serveur | LLMSecOps |
| — | Comptabilité | tokens, coût, latence → registre des dépenses ; trace → Langfuse | non bloquant | AIOps, FinOps |

**Règles d'erreur :**
- Les portes de sécurité (2, 3, 8) échouent fermées.
- Le chemin LLM (4 à 7) se dégrade et bascule.
- Chaque étape a un délai maximal ; au-delà, son span se ferme en erreur.

**Protocole SSE vers le navigateur :**
- `stage.start {name, ts}`
- `stage.end {name, status: ok|blocked|error|fallback, duration_ms, attrs}`
- `llm.progress {tokens}` : progression de la génération, sans texte
- `answer {text}` : la réponse, émise **uniquement** après le garde-fou de sortie
- `done {tokens_in, tokens_out, cost_usd, latency_ms, sources[], answer_override, trace_id}` : `answer_override` est non nul quand un garde-fou ou une erreur remplace la réponse (aucun `answer` n'a alors été émis).

Le front n'a aucune logique métier : une nouvelle étape côté API apparaît automatiquement dans le diagramme.

**Vie privée :** ni l'IP ni la question brute ne partent dans les traces (Langfuse, CloudWatch) ni dans les journaux d'accès. Le visiteur est identifié par un HMAC-SHA256 de son IP (clé secrète, refus de démarrer en production avec la valeur par défaut) ; derrière CloudFront, l'IP vient de `CloudFront-Viewer-Address`, en-tête auquel on ne fait confiance que si l'API n'est joignable que par CloudFront (URL de fonction en `AWS_IAM` + OAC, plan 1c-2). Pour le suivi de dérive, seuls les scores du classifieur sont conservés. Aucun cookie, aucun traceur.

## 4. Cycle de vie hors requête (GitHub Actions)

| Piste | Étapes | Outils (open source, 0 $) |
|---|---|---|
| Chaque PR | tests et types ; sécurité du code ; IaC scannée + `terraform plan` en commentaire ; évaluations LLM déterministes | pytest, ruff, pyright, vitest, tsc, eslint ; semgrep, gitleaks, osv-scanner ; trivy config ; promptfoo avec faux LLM |
| Classifieur | sources épinglées (révision + sha256 + licence) → entraînement déterministe (TF-IDF caractères + régression logistique → ONNX) → porte d'éval (voir ci-dessous) → release GitHub signée (Sigstore keyless), model card, histogramme de référence des scores | scikit-learn, skl2onnx, onnxruntime, cosign |
| Release (main) | image + SBOM ; scan + signature keyless + attestation SBOM, vérifiées avant déploiement ; déploiement **par digest** via OIDC (pas de clé stockée) ; test de fumée de production, **retour arrière automatique** à l'image précédente en cas d'échec | syft (CycloneDX), trivy, cosign keyless (bundles, référents OCI) |
| Chaque nuit | red team et évaluations sur le vrai modèle, via CloudFront, avec un **jeton d'évaluation** (quota séparé, plafond de dépense conservé, requêtes marquées `xops.eval`) ; dérive du classifieur (PSI des scores de production contre l'histogramme du **domaine**, lus dans `aws/spans`) ; alerte → issue GitHub | promptfoo (fournisseur HTTP maison : SHA-256 du corps pour l'OAC), CloudWatch Logs Insights |

**Décisions du 2026-09-26 (plan 1d-1) :** pas de canary CodeDeploy (trafic de démo : test de fumée + retour arrière suffisent) ; `terraform apply` reste manuel (pas d'approbation d'environnement garantie sur un dépôt privé gratuit, et un rôle CI d'`apply` serait administrateur) ; provenance SLSA et `cosign verify` public reportés au passage en public (plan 1e).

**Réalisé (plan 1e-2a, 2026-09-27) :** dépôt public ; image miroir `ghcr.io/void911/ask-my-cv` signée (cosign) avec provenance SLSA et SBOM attestés, vérifiables sans identifiants ; environnements `production` / `nightly` et confiance OIDC par environnement ; `main` protégée (PR + 5 vérifications) ; CSP à empreintes ; Lighthouse en CI. Chaque tâche est une issue → PR → revue d'agent en commentaire.

**Porte d'évaluation du classifieur** (seuils fixés à partir d'une mesure réelle du 2026-09-25 : rappel 0,85 / FPR 0,00 sur deepset, 0,99 sur Gandalf, 100 % adverse) :
- `deepset/prompt-injections` (test) : rappel ≥ 0,80 et taux de faux positifs ≤ 0,05 ;
- `Lakera/gandalf_ignore_instructions` (attaques hors distribution, jamais vues à l'entraînement) : rappel ≥ 0,95 ;
- ensemble adverse écrit à la main (`must_block` / `must_allow`, FR/EN) : 100 % respecté ;
- parité ONNX / scikit-learn : écart de probabilité ≤ 1e-3 et mêmes décisions sur toutes les données d'évaluation (le convertisseur skl2onnx n'est garanti que pour l'analyseur `word`).

**Règles :**
- La signature Sigstore du modèle est vérifiée en CI avant le build de l'image (`cosign verify-blob`, identité exacte du workflow `train.yml` sur `main`) ; au démarrage, l'API vérifie le sha256 épinglé dans `models/prod.json` et refuse de charger un modèle différent. (Pas de vérification Sigstore à chaque démarrage à froid : elle exigerait un appel réseau vers la racine de confiance.)
- La promotion d'un modèle en production (`models/prod.json`) se fait par PR.
- Chaque étape produit un artefact public, affiché par le portfolio (§6).

## 5. Toolkit `xops-kit` (sous-projets 2 et 3)

```
xops-kit/
├── template/            # template copier (questions : llm, ml, cloud aws|azure|none, frontend)
├── .github/workflows/   # workflows réutilisables (workflow_call), tags v1, v2…
├── terraform/           # modules : lambda-api, static-site, budget-killswitch,
│                        #   dynamodb-vector, github-oidc, azure-foundry
├── packages/
│   ├── xops-core/       # PyPI : interfaces + adaptateurs, garde-fous, spans OTel → SSE, registre des dépenses
│   └── flow-viz/        # npm : composant React Flow du pipeline en direct
├── claude-plugin/       # plugin Claude Code « xops » + marketplace
└── scorecard/           # CLI « xops audit »
```

- **Template `copier` :** génère un projet déjà câblé (FastAPI, OTel, Dockerfile, compose, pre-commit, promptfoo, `CLAUDE.md`, workflows appelant ceux du kit). `copier update` propage les améliorations du kit à tous les projets.
- **Workflows réutilisables :** `python-ci`, `ts-ci`, `security-scan`, `iac-scan`, `llm-evals`, `build-sign-sbom`, `terraform-deploy`, `redteam-nightly`, `drift-check`.
- **Modules Terraform :** multicloud (AWS + Azure). Aucun module ne crée de service de la liste d'exclusion (§2.3).
- **Plugin Claude Code `xops` :**
  - sélection d'ECC reprise avec attribution MIT : plan, tdd-workflow, security-reviewer, relecteurs Python et TypeScript, eval-harness, canary-watch ;
  - nouvelles skills : `supply-chain`, `llm-guardrails`, `model-registry`, `otel-llm-tracing`, `cloud-cost-guard`, `promptfoo-evals` ;
  - hooks légers, sans GateGuard ;
  - budget de contexte fixe < 3k tokens (ECC complet : ~25k).

  Une fois le plugin opérationnel, ECC est désinstallé.
- **`xops audit` :** inspecte un dépôt et produit la matrice XOps (étapes × couverture : couvert / partiel / absent), en JSON, en badge SVG et en diagramme. C'est la matrice affichée sur le portfolio pour chaque projet.

## 6. Site portfolio (sous-projet 4)

- **Accueil :**
  - chat « Interroge mon CV » à gauche, diagramme `flow-viz` en direct à droite ;
  - sélecteur de modèle ;
  - questions suggérées ;
  - bouton « Essaie de m'attaquer » (attaques pré-remplies) ;
  - pied de démo : latence, tokens, coût.
- **/architecture :** comment tout est construit, revu et déployé : chemin d'une requête, infrastructure Terraform, chaîne du code à la production, cycle de vie du modèle ; diagrammes générés depuis les sources réelles, liens vers le code.
- **/xops :** la matrice XOps de l'application. Chaque case renvoie à sa preuve : SBOM, commande `cosign verify`, rapport d'éval, rapport de red team, historique canary, courbe de dérive.
- **/demos :** comparateur AWS / Azure, bac à sable d'injection, frise des canary et rollbacks, simulation du coupe-circuit (bac à sable, sans effet sur le service réel).
- **/projets :** autres projets avec leur matrice XOps.
- **/cv :** téléchargement et contact.

**Comportements :**
- **Mode rediffusion :** si l'API est indisponible (budget, panne, Azure coupé), le site rejoue des traces réelles enregistrées, avec la mention « rediffusion ».
- **Accessibilité :** équivalent textuel du diagramme annoncé aux lecteurs d'écran (`aria-live`), respect de `prefers-reduced-motion`.
- **Performance :** Lighthouse en CI avec budget de score.
- **Langues :** bilingue FR / EN (next-intl).

**Technique :** Next.js (export statique), Tailwind, React Flow.

**Réalisé (plan 1e-1, 2026-09-26) :** https://job.stevelang.net — direction « console + circuit » (carte électronique sombre, étapes en puces U1–U8, impulsion cyan de nœud en nœud, arrêt rouge sur blocage), CV public de Steve Lang, contact `job@stevelang.net`, site S3 derrière le CloudFront de l'API (`/api/*`), déployé par la CI.

## 7. Coûts

| Poste | Estimation mensuelle |
|---|---|
| Lambda, CloudFront, S3, DynamoDB (y compris vecteurs), ECR, CloudWatch | ~1 à 3 $ |
| Bedrock, Haiku 4.5 (~0,005 $ / question) | ~5 $ pour 1 000 questions |
| Azure Foundry serverless (seulement quand activé) | quelques $ |
| Langfuse Cloud gratuit, GitHub Actions (dépôt public), outils open source | 0 $ |
| Domaine (optionnel) | ~1 à 2 $ |

- **Cible :** 5 à 10 $ par mois.
- **Plafond dur configurable** (par défaut 15 $/mois), appliqué à tous les fournisseurs via le registre des dépenses, avec AWS Budgets et Azure Budgets en filet de sécurité.
- **Crédits :** 200 $ de crédits AWS (plan gratuit, expiration à 6 mois à vérifier) ; Azure : 200 $ sur 30 jours pour un nouveau compte.
- **Au-delà :** la portabilité (§2.1) permet de déménager avec `docker compose up`.

## 8. Points à vérifier au début de l'implémentation

1. ~~Support Terraform (provider AWS) de l'index vectoriel DynamoDB ; sinon, ressource CloudFormation appelée depuis Terraform.~~ Résolu (2026-09-26) : `hashicorp/aws` 6.66 ne gère pas les index vectoriels ; `awscc_dynamodb_table` (provider `awscc` 1.103, attribut `vector_indexes`) les gère nativement. Déployé et vérifié en production.
2. Tarifs Bedrock en vigueur, et prise en charge par les crédits AWS des modèles tiers facturés via le Marketplace. Haiku 4.5 facturé via AWS Marketplace ; couverture par les crédits à vérifier.
3. Date d'expiration réelle des crédits AWS (console Billing → Credits). (à vérifier par l'utilisateur ; non fait au 2026-09-26)
4. ~~Streaming SSE Python via Lambda Web Adapter + Function URL (mode `RESPONSE_STREAM`).~~ Résolu (2026-09-26) : Lambda Web Adapter 1.1.0 (`AWS_LWA_INVOKE_MODE=response_stream`) + Function URL `RESPONSE_STREAM`, streaming de bout en bout à travers CloudFront vérifié par le test de fumée réel de production.
5. ~~Disponibilité régionale commune : Bedrock (modèles choisis) + DynamoDB vector search dans la région retenue.~~ Résolu (2026-09-26) : Claude Haiku 4.5 accessible depuis `ca-central-1` via le profil d'inférence `us.` (régions de destination ca-central-1/us-east-1/us-east-2/us-west-2) ; Titan V2 embeddings en région `ca-central-1` ; recherche vectorielle DynamoDB native disponible et vérifiée en `ca-central-1`.
6. ~~Jeu de données public et licence pour l'entraînement du classifieur d'injection.~~ Résolu (2026-09-25) : `deepset/prompt-injections` (Apache-2.0, révision `4f61ecb`) pour l'entraînement et le test ; `Lakera/gandalf_ignore_instructions` (MIT, révision `04737b6`) pour l'évaluation hors distribution. `Horizon-Labs/mosscap-multilingual` écarté : accès restreint (401), incompatible avec une CI reproductible.

## 9. Critères de réussite

- Une question sur le site produit une réponse sourcée en streaming, et le diagramme s'anime étape par étape à partir des vrais spans.
- Une attaque par injection connue est bloquée à l'étape 3, en rouge, sans appel au LLM.
- Changer de modèle dans le sélecteur change réellement de fournisseur, coût affiché compris.
- `xops audit` sur `ask-my-cv` affiche toutes les cases de la matrice en vert, chaque case liée à un artefact vérifiable.
- `cosign verify` sur l'image publiée réussit en copiant-collant la commande du site.
- Un nouveau projet généré par `copier copy` passe la CI complète sans modification.
- Dépense mensuelle réelle ≤ plafond configuré ; au-delà, le site passe en mode démo sans tomber.
- Le plugin `xops` coûte < 3k tokens de contexte fixe.

## 10. Hors périmètre (YAGNI)

Kubernetes en production (manifests fournis au mieux en bonus), serveur MLflow, base vectorielle dédiée, authentification des visiteurs, fine-tuning de LLM, analytics.
