# « Interroge mon CV » — plan 1e-2a : preuves vérifiables par tous — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** n'importe qui peut vérifier, sans compte AWS, que l'image en production a été construite par la CI de ce dépôt public (provenance SLSA + signature cosign sur un miroir GHCR public) ; les rôles AWS sont liés à des environnements GitHub protégés ; `main` n'accepte que des PR vertes ; le site a une CSP sans `'unsafe-inline'` pour les scripts et un budget Lighthouse en CI.

**Méthode (nouveau, décidé le 2026-09-26) :** premier plan en **flux GitHub réel** : chaque tâche = une **issue** (créée par le contrôleur avec le texte de la tâche) ; l'implémenteur travaille sur une branche `t/<issue>-<slug>` et ouvre une **PR** « Closes #n » ; la CI tourne sur la PR ; le relecteur publie sa revue **en commentaire de la PR** (préfixe « Revue (agent de revue) ») ; le contrôleur fusionne (commit de fusion, pas de squash) quand la CI est verte et la revue sans point bloquant. Plus aucun push direct sur `main` après la tâche 0.

**Architecture:**
- **Gouvernance** : ensemble de règles (ruleset) sur `main` : PR obligatoire, vérifications `security`, `test`, `evals`, `web`, `terraform` requises, pas de push forcé ni de suppression. Environnements `production` (job `deploy`) et `nightly` (jobs `drift`, `redteam`), limités à la branche `main` ; `EVAL_TOKEN` déplacé en secret de l'environnement `nightly`. Confiance OIDC : rôle de déploiement ← `…:environment:production`, rôle de nuit ← `…:environment:nightly`.
- **Provenance et miroir** : le job `deploy` pousse la **même** image (même digest) dans ECR (production) et sur `ghcr.io/void911/ask-my-cv` (public ; nom en minuscules) ; signe les deux avec cosign (keyless) ; `actions/attest-build-provenance` (SLSA) et `actions/attest-sbom` sur le digest GHCR, `push-to-registry: true`. `train.yml` produit désormais la provenance des modèles (déjà prévue « si public »).
- **CSP** : balise `<meta http-equiv="Content-Security-Policy">` insérée au build dans chaque HTML avec `script-src 'self' 'sha256-…'` (empreintes des scripts en ligne de Next) ; l'en-tête CloudFront garde les autres directives (`frame-ancestors`, etc., non gérées par la balise). Deux politiques s'appliquent en intersection : les scripts ne passent que si les deux les autorisent.
- **Lighthouse** : `@lhci/cli` sur `web/out` (site statique) dans le job `web`, budgets mesurés puis fixés.
- **ECR public** : authentification `aws ecr-public get-login-password` dans `deploy` pour tirer l'adaptateur Lambda (quotas authentifiés, fin des échecs anonymes).

**Tech Stack:** GitHub rulesets / environments, `actions/attest-build-provenance` v4.2.2 (`4d101475d8b20a2381f78447822ac1eab6504dd8`), `actions/attest-sbom` v4.1.0 (`c604332985a26aa8cf1bdc465b92731239ec6b9e`), cosign 3.1.3, `@lhci/cli` 0.15.1, Terraform.

**Spec :** §4 (Release), §6. **Suivi :** « Plan 1e-2 → 1e-2a » de `followups.md`.

## Faits vérifiés le 2026-09-26

- Sujet OIDC avec environnement (format immuable) : `repo:VoiD911@15268916/ask-my-cv@1389934708:environment:<nom>` ; sans environnement : `…:ref:refs/heads/main` (actuel).
- Environnements protégés et rulesets : disponibles sur un dépôt **public** en offre gratuite.
- Les attestations GitHub (`attest-build-provenance`) exigent un dépôt public (ou Enterprise) : désormais possible. Permissions : `id-token: write`, `attestations: write`, `packages: write` (GHCR). Vérification : `gh attestation verify oci://ghcr.io/void911/ask-my-cv@sha256:… -R VoiD911/ask-my-cv`.
- Un même manifeste poussé dans deux registres garde le **même digest** ; les signatures cosign sont stockées par registre (référents OCI).
- `<meta http-equiv="Content-Security-Policy">` ne gère ni `frame-ancestors` ni `report-uri` : ils restent dans l'en-tête.
- **Ne pas** produire de provenance a posteriori pour les modèles v1.0–v1.2 (elle affirmerait une construction par un run qui ne l'a pas faite) : la provenance commence au prochain entraînement.

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv` (public), identité git **noreply** (`15268916+VoiD911@users.noreply.github.com`, réglée dans le dépôt), pas de ligne d'attribution.
- Portes : Python (`$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q`), web (`npm --prefix web run lint && … typecheck && … test -- --run && … build && … e2e` — e2e nécessite l'API locale), Terraform (`fmt`/`validate`), YAML + actionlint.
- Les implémenteurs **ne touchent pas à AWS** ; la tâche 0 et les `terraform apply` sont faits par le contrôleur, avec l'accord de l'utilisateur.

---

### Task 0 : gouvernance du dépôt (contrôleur, avec accord)

- [ ] Environnements `production` et `nightly` : `gh api -X PUT repos/VoiD911/ask-my-cv/environments/<nom>` avec `deployment_branch_policy: {protected_branches: false, custom_branch_policies: true}` + politique de branche `main` ; déplacer `EVAL_TOKEN` : `gh secret set EVAL_TOKEN --env nightly` (valeur régénérée sans affichage, comme au 1d-3, et mise à jour dans SSM), puis `gh secret delete EVAL_TOKEN` au niveau du dépôt **après** la fusion de la tâche 1.
- [ ] Terraform (`infra/bootstrap/main.tf`) : confiance **transitoire** acceptant l'ancien et le nouveau sujet (`StringEquals` avec deux valeurs) pour chaque rôle : déploiement = `…:ref:refs/heads/main` **ou** `…:environment:production` ; nuit = `…:ref:refs/heads/main` **ou** `…:environment:nightly`. `plan` montré, `apply` (accord). Le retrait de l'ancien sujet se fait à la tâche 5.
- [ ] Ruleset sur `main` (après la fusion de la tâche 1, pour ne pas bloquer ce premier changement) : `gh api -X POST repos/VoiD911/ask-my-cv/rulesets` — `target: branch`, `include: ["~DEFAULT_BRANCH"]`, règles `pull_request` (0 approbation requise : l'utilisateur est seul), `required_status_checks` (`security`, `test`, `evals`, `web`, `terraform`), `non_fast_forward`, `deletion`. Contournement réservé à l'administrateur du dépôt.
- [ ] Étiquettes : `plan:1e-2a`, `historique`, `revue` ; créer une issue par tâche 1 à 4 (texte de la tâche, lien vers ce plan).

### Task 1 : jobs liés aux environnements (issue, PR)

**Files:** Modify `.github/workflows/ci.yml`, `.github/workflows/nightly.yml`, `README.md`

- [ ] `deploy` : `environment: production` (URL `https://job.stevelang.net`) ; `nightly.yml` : `environment: nightly` sur `redteam` (qui lit `EVAL_TOKEN`) et `drift` (qui prend le rôle AWS de nuit).
- [ ] README : section « Gouvernance » (PR obligatoires, vérifications requises, environnements, sujets OIDC).
- [ ] PR « Closes #… » ; CI verte ; revue en commentaire ; fusion par le contrôleur ; vérifier qu'un déploiement complet passe avec `environment: production` (nouveau sujet OIDC) et lancer `nightly.yml` à la main (accord).

### Task 2 : miroir GHCR signé, provenance SLSA, ECR public authentifié (issue, PR)

**Files:** Modify `.github/workflows/ci.yml`, `.github/workflows/train.yml`, `infra/bootstrap/main.tf`, `README.md`

- [ ] `deploy` : permissions `packages: write`, `attestations: write` (en plus de `id-token: write`) ; connexion `docker/login-action` (épinglée par SHA) à `ghcr.io` avec `GITHUB_TOKEN` ; après le push ECR, `docker tag` + `docker push ghcr.io/void911/ask-my-cv:<sha>` ; vérifier que le digest GHCR = digest ECR (sinon échec) ; `cosign sign --yes` sur `ghcr.io/…@<digest>` ; `actions/attest-build-provenance` (`subject-name: ghcr.io/void911/ask-my-cv`, `subject-digest`, `push-to-registry: true`) ; `actions/attest-sbom` avec le SBOM CycloneDX déjà produit.
- [ ] Quand l'image existe déjà (rejeu) : ne rien reconstruire, tirer depuis ECR et pousser vers GHCR si absente.
- [ ] Paquet GHCR **public** : après le premier push, `gh api -X PATCH /user/packages/container/ask-my-cv/visibility -f visibility=public` (contrôleur, accord) et lier le paquet au dépôt (label OCI `org.opencontainers.image.source=https://github.com/VoiD911/ask-my-cv` dans le Dockerfile).
- [ ] ECR public : `aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws` avant le build ; droits du rôle de déploiement : `ecr-public:GetAuthorizationToken`, `sts:GetServiceBearerToken` (Terraform bootstrap, `plan`/`apply` par le contrôleur).
- [ ] `train.yml` : vérifier que la provenance des modèles s'active maintenant que le dépôt est public (condition `if: ${{ !github.event.repository.private }}`) ; aucune provenance rétroactive.
- [ ] README : section « Vérifier l'image » avec les deux commandes copiables (`cosign verify ghcr.io/void911/ask-my-cv@sha256:… --certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main --certificate-oidc-issuer https://token.actions.githubusercontent.com` et `gh attestation verify oci://ghcr.io/void911/ask-my-cv@sha256:… -R VoiD911/ask-my-cv`).

### Task 3 : CSP stricte pour les scripts (issue, PR)

**Files:** Create `web/scripts/csp.mjs`, `web/scripts/csp.test.mjs` ; Modify `web/package.json` (`postbuild`), `web/e2e/*.spec.ts`, `infra/prod/variables.tf` (commentaire), `README.md`

- [ ] `csp.mjs` : parcourt `web/out/**/*.html`, calcule le SHA-256 (base64) de chaque `<script>` **en ligne** (sans `src`), insère en tête du `<head>` `<meta http-equiv="Content-Security-Policy" content="script-src 'self' 'sha256-…' …">` ; échoue si un script en ligne a un attribut `src` vide ou si l'insertion est impossible. Tests Node (`node --test`) sur des fichiers HTML d'exemple.
- [ ] E2E : écouter `securitypolicyviolation` (`page.on('console')` + `document.addEventListener` injecté) sur toutes les pages ; aucun événement toléré ; le serveur e2e (`serve.mjs`) sert aussi l'en-tête CSP de production (copie de la valeur Terraform) pour tester l'intersection réelle.
- [ ] L'en-tête Terraform `site_csp` garde `script-src 'self' 'unsafe-inline'` (inopérant dans l'intersection) : mettre à jour son commentaire pour l'expliquer.
- [ ] README : section CSP.

### Task 4 : Lighthouse en CI (issue, PR)

**Files:** Create `web/lighthouserc.json` ; Modify `web/package.json` (dev dep `@lhci/cli` 0.15.1, lock régénéré avec npm 11.19 dans `node:24-slim`), `.github/workflows/ci.yml`

- [ ] Mesurer d'abord (3 passages, bureau et mobile) sur `web/out` servi en statique ; fixer les budgets juste sous les mesures (`categories:performance`, `accessibility`, `best-practices`, `seo`) ; `accessibility` ≥ 0,95 non négociable.
- [ ] Job `web` : `npx --prefix web lhci autorun` (`staticDistDir: ./out`), rapports en artefact ; aucun envoi vers un serveur public (`upload.target: filesystem`).

### Task 5 : mise en service et nettoyage (contrôleur, avec accord)

- [ ] Après fusion des tâches 1 à 4 et un déploiement vert : retirer l'ancien sujet OIDC (`ref:refs/heads/main`) des deux rôles (`plan`/`apply`), supprimer `EVAL_TOKEN` du niveau dépôt.
- [ ] Vérifier **depuis un poste sans accès AWS** (ou un conteneur sans identifiants) : `cosign verify` et `gh attestation verify` sur le digest en production ; noter les commandes et leur sortie dans le suivi.
- [ ] Vérifier la CSP en vrai (navigateur intégré, console sans violation) et le rapport Lighthouse du dernier run.
- [ ] `followups.md` et spec à jour ; issues fermées par leurs PR.

## Critères de fin

- `cosign verify` et `gh attestation verify` réussissent sur `ghcr.io/void911/ask-my-cv@<digest en production>` sans identifiants AWS.
- Le digest servi par la Lambda = le digest GHCR signé et attesté.
- `main` refuse les push directs ; chaque tâche de ce plan a une issue fermée par une PR avec une revue en commentaire.
- Le rôle de déploiement n'accepte que `environment:production`, celui de nuit que `environment:nightly`.
- Aucune violation CSP ; `script-src` sans `'unsafe-inline'` effectif ; budget Lighthouse en CI.
