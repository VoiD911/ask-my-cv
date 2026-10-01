# « Interroge mon CV » — plan 1e-1 : la page d'accueil en ligne — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `https://job.stevelang.net` sert une page d'accueil où l'on interroge le vrai CV de Steve Lang, en suivant en direct un circuit du pipeline qui s'anime à partir des vrais événements SSE de l'API ; le site est un export statique Next.js dans S3, derrière le CloudFront existant, déployé par la CI.

**Architecture:**
- **Contenu** : `data/cv.md` = version publique validée par l'utilisateur (`scratchpad/cv_public_draft.md` du 2026-09-26) ; seule adresse autorisée : `job@stevelang.net`.
- **Front** (`ask-my-cv/web`) : Next.js 16 (`output: "export"`, `trailingSlash: true`), React 19, Tailwind 4, `@xyflow/react` 12 pour le circuit ; aucune logique métier : le client lit le flux SSE (`fetch` POST + `ReadableStream`), un réducteur pur transforme les événements en état des nœuds.
- **Direction visuelle (décision du 2026-09-26)** : hybride « console d'ingénierie » (fond sombre, police mono, statut/durée/attributs par étape) + « circuit » (pipeline dessiné comme un circuit ; une impulsion voyage de nœud en nœud au rythme des événements ; arrêt rouge sur le nœud qui bloque). Respect de `prefers-reduced-motion`, résumé `aria-live`.
- **Hébergement** : bucket S3 privé (OAC) comme comportement **par défaut** de la distribution ; `/api/*` → Lambda (fonction `strip-api` attachée à ce seul comportement) ; certificat ACM **us-east-1** pour `job.stevelang.net` ; DNS chez le registraire de l'utilisateur (deux CNAME ajoutés par lui).
- **CI** : job `web` (lint, types, tests, build, e2e Playwright contre l'API locale au faux LLM) ; `deploy` pousse aussi le site (`s3 sync --delete` + invalidation).

**Tech Stack:** Next.js 16.3, React 19.3, TypeScript (version prise en charge par Next 16 — vérifier avant de fixer 7.x), Tailwind 4.3, @xyflow/react 12.12, Vitest 5, Testing Library, Playwright 1.63, Terraform (aws ~> 6.66, alias us-east-1).

**Spec :** §6 (accueil, accessibilité), §3 (protocole SSE, vie privée). **Suivi :** section « Plan 1e » de `followups.md`. **Reporté en 1e-2** : `/xops` et preuves, mode rediffusion, anglais, Lighthouse en CI, publication (LICENSE, dépôt public, `cosign verify` public). **1e-3** : `/demos`, `/projets`, `/cv`.

## Faits vérifiés le 2026-09-26

- Versions npm : `next` 16.3.6, `react` 19.3.0, `@xyflow/react` 12.12.0, `tailwindcss` / `@tailwindcss/postcss` 4.3.3, `vitest` 5.0.2, `@testing-library/react` 16.3.3, `@playwright/test` 1.63.0, `typescript` 7.0.2 (**vérifier** la compatibilité Next 16 ; sinon la dernière 6.x/5.x prise en charge).
- Protocole SSE de l'API (`src/ask_my_cv/events.py`) : `stage.start {name, ts}`, `stage.end {name, status: ok|blocked|error|fallback, duration_ms, attrs}`, `llm.progress {tokens}`, `answer {text}` (après le garde-fou seulement), `done {tokens_in, tokens_out, cost_usd, latency_ms, sources[], answer_override, trace_id}`. Étapes : `reception, quota, injection, embedding, retrieval, prompt, llm, output_guard`. **Relire `events.py`** pour les noms exacts avant d'écrire les types TS.
- `POST /api/ask` via CloudFront : en-tête `x-amz-content-sha256` = SHA-256 hexadécimal du corps exact (sinon 403, OAC Lambda). `GET /api/models` renvoie `{default, models: [{id, provider}]}`.
- `EventSource` ne gère que GET : `fetch` + `response.body.getReader()`.
- CloudFront : un certificat pour un nom personnalisé doit être dans **us-east-1** ; la validation DNS d'ACM crée un CNAME que l'utilisateur ajoute chez son registraire. Un `terraform apply` qui attend la validation (`aws_acm_certificate_validation`) bloque tant que le CNAME n'existe pas : appliquer en deux temps (tâche 8).
- Next export statique : `trailingSlash: true` produit `route/index.html` ; S3 via OAC ne résout pas l'index des sous-dossiers → fonction CloudFront de requête visiteur sur le comportement par défaut (`/x/` → `/x/index.html`).
- Next injecte des scripts en ligne : une CSP stricte sans `'unsafe-inline'` casse l'hydratation ; mesurer au build (hashes ou `'unsafe-inline'` justifié) — tâche 6.

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv`, branche `main`, pas de ligne d'attribution, **ne pas pousser** (tâche 8).
- Python : `export UV=~/AppData/Roaming/Python/Python314/Scripts/uv.exe` ; porte `$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q` (311 tests).
- Web : Node 25 local (runner Node 24) ; porte `npm --prefix web run lint && npm --prefix web run typecheck && npm --prefix web test -- --run && npm --prefix web run build`.
- Terraform : `export PATH="~/AppData/Local/Microsoft/WinGet/Links:$PATH"` ; `fmt -check` + `validate` (backend désactivé).
- **Charger le skill `frontend-design`** pour les tâches 4 et 5 (qualité visuelle, typographie, éviter l'aspect gabarit).
- Aucun appel AWS dans les tâches 0 à 7 ; aucun appel à l'API de production.

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `data/cv.md`, `settings.yaml`, `settings.aws.yaml`, `settings.ci.yaml` | CV public, contact autorisé |
| `infra/scripts/smoke_prod.py`, `evals/*.yaml` | questions adaptées au vrai CV |
| `web/package.json`, `web/next.config.ts`, `web/tsconfig.json`, `web/eslint.config.mjs`, `web/vitest.config.ts`, `web/playwright.config.ts` | projet front |
| `web/src/lib/sse.ts`, `web/src/lib/ask.ts` | lecture incrémentale du SSE, appel signé |
| `web/src/lib/pipeline.ts` | réducteur événements → état des nœuds |
| `web/src/components/Circuit.tsx`, `web/src/components/StageNode.tsx`, `web/src/components/Pulse.tsx` | circuit |
| `web/src/components/Chat.tsx`, `web/src/components/DemoFooter.tsx`, `web/src/app/page.tsx`, `web/src/app/layout.tsx` | page |
| `web/e2e/home.spec.ts` | parcours Playwright |
| `infra/prod/site.tf`, `infra/prod/cdn.tf`, `infra/prod/functions/site-index.js`, `infra/prod/versions.tf` | S3, comportements, certificat |
| `infra/bootstrap/main.tf` | droits de déploiement du site |
| `.github/workflows/ci.yml` | jobs `web`, déploiement du site |

---

### Task 0 : le vrai CV

**Files:** Modify `data/cv.md`, `settings.yaml`, `settings.aws.yaml`, `settings.ci.yaml`, `infra/scripts/smoke_prod.py`, `evals/pr.yaml`, `evals/nightly.yaml`, `tests/test_smoke_prod.py` (si nécessaire)

- [ ] Copier `~\AppData\Local\Temp\<session-claude>\scratchpad\cv_public_draft.md` dans `data/cv.md` **tel quel** (texte validé par l'utilisateur).
- [ ] `allowed_contacts: [job@stevelang.net]` dans les trois fichiers de réglages (remplace `alex.martin@example.com`).
- [ ] Vérifier le découpage de l'ingestion (`src/ask_my_cv/ingest.py`) sur le nouveau fichier : une section `##` = un passage ; lancer l'ingestion locale (`$UV run python -m ask_my_cv.ingest`, cible fichier) et vérifier le nombre de passages (un par section `##` : 12 attendus) et qu'aucun ne dépasse la taille maximale de passage.
- [ ] Test de fumée : question → « Quel est son rôle chez NeoBotiQc ? » ; suites promptfoo : questions légitimes réécrites sur le vrai CV (NeoBotiQc, Solutions Will, doctorat ÉTS, compétences cloud, projet Interroge mon CV, langues, UTBM, freelancer) ; informations absentes (salaire, adresse personnelle, date de naissance, opinion politique, numéro de téléphone) inchangées. La suite PR (faux LLM) ne dépend pas du contenu du CV : n'y changer que le texte des questions.
- [ ] Porte Python verte ; `node --test evals/*.test.js`. Commit : `feat: CV public de Steve Lang (contact job@stevelang.net)`.

### Task 1 : squelette du projet web et job CI

**Files:** Create `web/…` (projet), Modify `.github/workflows/ci.yml`, `.gitignore`, `.semgrepignore`, `.github/dependabot.yml`

- [ ] Créer le projet à la main (pas de `create-next-app` interactif) : `package.json` (scripts `dev`, `build`, `lint`, `typecheck` = `tsc --noEmit`, `test` = `vitest`, `e2e` = `playwright test`), dépendances aux versions ci-dessus, `package-lock.json` committé ; `next.config.ts` : `output: "export"`, `trailingSlash: true`, `images: { unoptimized: true }`, `reactStrictMode: true` ; TypeScript `strict` ; ESLint (config Next) ; Tailwind 4 (`@import "tailwindcss"` dans `globals.css`, PostCSS `@tailwindcss/postcss`) ; Vitest (`jsdom`) + Testing Library.
- [ ] Page minimale « Interroge mon CV » + un test Vitest qui la rend.
- [ ] CI : job `web` (PR et `main`) : checkout, setup-node (SHA déjà épinglé dans `ci.yml`, Node 24, cache npm sur `web/package-lock.json`), `npm ci --prefix web --ignore-scripts` (**vérifier** que Next/SWC fonctionne sans scripts d'installation ; sinon autoriser les scripts **uniquement** pour ce job et le justifier en commentaire), lint, typecheck, tests, build ; artefact `web/out`.
- [ ] Dependabot : écosystème `npm` pour `/web` et `/evals`. `.gitignore` : `web/node_modules/`, `web/.next/`, `web/out/`, `web/test-results/`, `web/playwright-report/`.
- [ ] `security` : semgrep couvre `web/` (ajouter `p/typescript`, `p/react`) ; gitleaks inchangé ; ajouter au job `security` un `npm audit --omit=dev --audit-level=high` pour `web` et `evals` (ou osv-scanner sur les deux `package-lock.json` — préférer osv-scanner, déjà utilisé : `--lockfile /src/web/package-lock.json --lockfile /src/evals/package-lock.json`).
- [ ] Commit : `feat(web): squelette Next.js (export statique) et job CI`.

### Task 2 : client de l'API (SSE signé)

**Files:** Create `web/src/lib/sse.ts`, `web/src/lib/ask.ts`, `web/src/lib/events.ts`, tests `web/src/lib/*.test.ts`

- [ ] `events.ts` : types TS **exactement** alignés sur `src/ask_my_cv/events.py` (union discriminée par `type`).
- [ ] `sse.ts` : `createSseParser(onEvent)` qui reçoit des morceaux de texte arbitraires (un événement peut être coupé entre deux morceaux, plusieurs dans un morceau, `\r\n` ou `\n`) et émet `{event, data}` ; tests couvrant ces cas et une ligne `data:` invalide (ignorée, compteur d'erreurs).
- [ ] `ask.ts` : `ask({question, model, signal, onEvent, baseUrl = "/api"})` : corps `JSON.stringify({question, model})` ; SHA-256 via `crypto.subtle.digest` sur **les mêmes octets** envoyés (`TextEncoder`) ; en-têtes `content-type` et `x-amz-content-sha256` ; lecture `response.body.getReader()` + `TextDecoder` en flux ; erreurs HTTP typées (`422` → question invalide, `403` → signature, autre → indisponible) ; `AbortController` respecté. Tests avec un `fetch` simulé qui renvoie un `ReadableStream` découpé au hasard ; test : le hachage envoyé = SHA-256 du corps envoyé.
- [ ] `models.ts` : `GET /api/models`.
- [ ] Commit : `feat(web): client SSE signé pour /api/ask`.

### Task 3 : état du pipeline (réducteur pur)

**Files:** Create `web/src/lib/pipeline.ts`, `web/src/lib/pipeline.test.ts`

- [ ] `STAGES` = les 8 étapes dans l'ordre ; `type StageState = {status: "idle"|"active"|"ok"|"blocked"|"error"|"fallback"; durationMs?; attrs: Record<string, string>}` ; `type RunState = {stages; tokens: number; answer: string|null; override: string|null; done: DoneEvent|null; blockedAt: string|null; startedAt; }`.
- [ ] `reduce(state, event)` : `stage.start` → `active` ; `stage.end` → statut + durée + attributs **convertis en chaînes** (affichage texte seulement) ; `llm.progress` → `tokens` ; `answer` ; `done` → `override`, `blockedAt` = première étape `blocked` ; une étape inconnue est **ajoutée à la fin** (le front n'a pas de logique métier : une nouvelle étape côté API apparaît automatiquement, spec §3).
- [ ] `describe(state)` : phrase en français pour `aria-live` (« Étape injection : bloquée, score 0,97. »).
- [ ] Tests : parcours nominal, blocage à `injection`, bascule `fallback`, erreur, étape inconnue, idempotence d'un `done` répété.
- [ ] Commit : `feat(web): état du pipeline à partir des événements`.

### Task 4 : le circuit (console + impulsion)

**Files:** Create `web/src/components/Circuit.tsx`, `StageNode.tsx`, `Pulse.tsx`, tests ; Modify `web/src/app/globals.css`

- [ ] Charger le skill `frontend-design`. Direction : fond sombre (console), police mono pour les nœuds et attributs, une seule couleur d'accent pour l'impulsion, vert/rouge/ambre réservés aux statuts ok/blocked/fallback ; typographie soignée ; aucune dépendance d'icônes lourde.
- [ ] `@xyflow/react` en mode lecture seule (`nodesDraggable={false}`, `panOnDrag={false}`, `zoomOnScroll={false}`, `preventScrolling={false}`), disposition en circuit (deux rangées de 4 nœuds reliées en « U », ou serpentin), nœuds personnalisés `StageNode` : nom, statut, durée, 2 attributs clés (ex. `score` pour `injection`, `hits`/`top_score` pour `retrieval`, `tokens` pour `llm`).
- [ ] `Pulse` : l'impulsion suit l'arête entre l'étape terminée et l'étape active (SVG `animateMotion` ou `offset-path`) ; arrêt et nœud rouge sur `blocked` ; aucune animation si `prefers-reduced-motion: reduce` (statut seul).
- [ ] Mobile (< 768 px) : disposition verticale, sans React Flow si plus simple (liste de nœuds reliés), même composant `StageNode`.
- [ ] Région `aria-live="polite"` alimentée par `describe(state)` ; le circuit a `role="img"` + description.
- [ ] Tests : rendu des statuts (classes/états), réduction de mouvement (media query simulée), texte annoncé.
- [ ] Commit : `feat(web): circuit du pipeline animé par les événements`.

### Task 5 : chat, page d'accueil et e2e

**Files:** Create `web/src/components/Chat.tsx`, `DemoFooter.tsx`, `web/src/app/page.tsx`, `layout.tsx`, `web/e2e/home.spec.ts`, `web/playwright.config.ts` ; Modify `.github/workflows/ci.yml`

- [ ] Page : en-tête (nom, titre du profil, lien `mailto:job@stevelang.net`), chat à gauche, circuit à droite (dessous sur mobile), pied de démo : latence, tokens entrée/sortie, coût, identifiant de trace (copiable) ; mention « Les questions sont traitées aux États-Unis par Amazon Bedrock ; aucune n'est conservée avec votre adresse IP. » (vérifier la formulation exacte contre la réalité : traces sans question ni IP).
- [ ] Chat : champ (500 caractères max, compteur), 4 questions suggérées tirées du vrai CV, bouton « Essaie de m'attaquer » (menu de 3 attaques pré-remplies issues du jeu `block`), sélecteur de modèle alimenté par `/api/models` (masqué s'il n'y a qu'un modèle), réponse affichée **en texte** (jamais `dangerouslySetInnerHTML`), marqueurs `[n]` reliés aux sources de `done.sources`, messages d'`override` (quota, budget, injection, refus) affichés distinctement, bouton d'arrêt (abort).
- [ ] Métadonnées : `<title>`, description, Open Graph minimal ; `lang="fr"`.
- [ ] E2E Playwright (`web/e2e/home.spec.ts`), serveur statique sur `web/out` + proxy `/api` vers l'API locale (`settings.ci.yaml`, faux LLM) — solution simple : un petit serveur Node (`web/e2e/serve.mjs`) qui sert `out/` et relaie `/api/*` vers `127.0.0.1:8000` en retirant `/api` ; parcours : question suggérée → 8 nœuds `ok` → réponse contenant `[1]` → pied de démo rempli ; attaque → nœud `injection` bloqué, pas de réponse ; accessibilité de base (`@axe-core/playwright` si léger ; sinon rôles/labels).
- [ ] CI : dans le job `evals` (API locale déjà démarrée) ou un job `e2e` dédié : `npx --prefix web playwright install --with-deps chromium` puis `npm --prefix web run e2e`. Choisir le plus simple et le justifier.
- [ ] Vérification visuelle locale : lancer l'e2e en mode capture et joindre deux captures (bureau, mobile) au rapport.
- [ ] Commit : `feat(web): page d'accueil (chat, circuit, pied de démo) et parcours e2e`.

### Task 6 : infrastructure du site

**Files:** Create `infra/prod/site.tf`, `infra/prod/functions/site-index.js` ; Modify `infra/prod/cdn.tf`, `infra/prod/versions.tf`, `infra/prod/variables.tf`, `infra/prod/outputs.tf`, `infra/bootstrap/main.tf`

- [ ] `versions.tf` : provider `aws` aliasé `us_east_1` (région `us-east-1`) pour ACM.
- [ ] `site.tf` : bucket `ask-my-cv-site-<compte>` privé (blocage public, propriété imposée, chiffrement par défaut, versionnage désactivé, `force_destroy = true` — contenu reconstructible), politique autorisant `cloudfront.amazonaws.com` avec `AWS:SourceArn` = la distribution ; OAC de type `s3`.
- [ ] `aws_acm_certificate` (fournisseur us-east-1) pour `var.site_domain` (défaut `job.stevelang.net`), validation `DNS` ; `aws_acm_certificate_validation` ; sorties : enregistrement de validation (nom, type, valeur) et cible CNAME du site (domaine CloudFront).
- [ ] `cdn.tf` : origine S3 (OAC) ; **comportement par défaut** → S3 : `redirect-to-https`, cache géré `Managed-CachingOptimized`, compression activée, fonction `site-index` en requête visiteur (`/` et `/x/` → `index.html`, méthodes GET/HEAD seulement), politique d'en-têtes de réponse **personnalisée** : en-têtes de sécurité + CSP (`default-src 'self'; script-src 'self' <hashes ou 'unsafe-inline' — décider en inspectant `web/out`>; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`) ; **comportement ordonné `/api/*`** → Lambda (réglages actuels : `https-only`, pas de cache, `AllViewerExceptHostHeader`, fonction `strip-api`, en-têtes de sécurité gérés) ; `aliases = [var.site_domain]`, `viewer_certificate` ACM (`sni-only`, `TLSv1.2_2021`). `default_root_object = "index.html"`.
- [ ] `infra/bootstrap/main.tf` : rôle de déploiement + `s3:ListBucket` (bucket du site), `s3:PutObject`/`s3:DeleteObject` (`/*`), `cloudfront:CreateInvalidation` (ARN de la distribution — lu via une variable ou un préfixe `arn:aws:cloudfront::<compte>:distribution/*` si l'ARN n'est pas connu à l'amorçage ; le justifier).
- [ ] Tests locaux de la fonction `site-index.js` avec Node (comme `strip-api.js`) ; `fmt` + `validate` (les deux racines).
- [ ] Commit : `infra: site statique S3 derrière CloudFront, domaine job.stevelang.net`.

### Task 7 : déploiement du site en CI

**Files:** Modify `.github/workflows/ci.yml`, `infra/scripts/smoke_prod.py`, `README.md`

- [ ] Job `deploy` : après le déploiement de l'API et son test de fumée, récupérer l'artefact `web/out` du job `web` (`actions/download-artifact` épinglé), `aws s3 sync web/out s3://$SITE_BUCKET --delete` (en-têtes `Cache-Control` : `public, max-age=31536000, immutable` pour `_next/static/`, `no-cache` pour le HTML), puis `aws cloudfront create-invalidation --paths "/*"` et attente. Variables : `SITE_BUCKET`, `DISTRIBUTION_ID`.
- [ ] Test de fumée : `GET /` contient le titre « Interroge mon CV » ; `GET /api/healthz` inchangé.
- [ ] README : section « Site ».
- [ ] Commit : `ci: déploiement du site statique`.

### Task 8 : mise en service (contrôleur, avec l'utilisateur)

- [ ] Revue finale (sous-agent, lecture seule).
- [ ] **Certificat** (accord) : `terraform apply -target=aws_acm_certificate.site` (racine prod) ; donner à l'utilisateur l'enregistrement CNAME de validation ; il l'ajoute chez son registraire ; attendre `ISSUED` (`aws acm describe-certificate --region us-east-1`).
- [ ] `terraform plan` puis `apply` complet de `prod` et du `bootstrap` (accord) ; `gh variable set SITE_BUCKET / DISTRIBUTION_ID` ; `SITE_URL` → `https://job.stevelang.net` **après** l'ajout du second CNAME par l'utilisateur (`job` → domaine CloudFront) et sa propagation (`nslookup job.stevelang.net`).
- [ ] Réingestion du CV dans DynamoDB (accord) ; vérifier le nombre de passages.
- [ ] Pousser `main` (accord) : CI verte (dont `web`), déploiement API + site.
- [ ] Vérifier en vrai avec le navigateur intégré : `https://job.stevelang.net` ; poser une question suggérée ; circuit animé jusqu'à `output_guard` ; réponse sourcée ; attaque bloquée en rouge ; captures bureau + mobile envoyées à l'utilisateur.

### Task 9 : documentation et suivi (contrôleur)

- [ ] `followups.md` : section 1e barrée pour ce qui est fait ; sections « Plan 1e-2 » et « Plan 1e-3 ».
- [ ] Spec §6 : direction visuelle retenue, domaine.
- [ ] Commits, push avec accord.

## Critères de fin

- `https://job.stevelang.net` sert la page (TLS 1.2+, en-têtes de sécurité, CSP) ; `/api/*` répond comme avant.
- Une question suggérée anime les 8 nœuds jusqu'à une réponse sourcée tirée du vrai CV ; une attaque s'arrête en rouge sur `injection`.
- Le pied de démo affiche latence, tokens, coût et identifiant de trace.
- `prefers-reduced-motion` coupe l'animation ; un lecteur d'écran entend la progression.
- CI : `web` (lint, types, tests, build, e2e) vert ; le déploiement publie API et site.
