# « Interroge mon CV » — plan 1d-1 : sécurité de la chaîne de livraison — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chaque changement passe par des scans de sécurité (secrets, code, dépendances, IaC, image), chaque image déployée a un SBOM, une signature Sigstore vérifiée avant le déploiement, est déployée **par digest**, et un test de fumée raté remet automatiquement l'image précédente en service.

**Architecture:** tout se passe dans `ask-my-cv/.github/workflows/ci.yml`.
- Nouveau job `security` (PR et `main`) : gitleaks, semgrep, osv-scanner, trivy config. Les outils tournent dans leurs **images Docker officielles épinglées par digest**, pas via des actions tierces : moins de code tiers exécuté avec le jeton du dépôt.
- Job `test` : scan trivy de l'image construite, SBOM CycloneDX (syft) en artefact, vérification que chaque module d'exécution s'importe dans l'image.
- Job `deploy` : SBOM de l'image poussée, `cosign sign` + `cosign attest` (keyless, OIDC GitHub), `cosign verify` avec l'identité exacte de `ci.yml` sur `main`, déploiement par digest, retour arrière automatique si le test de fumée échoue.
- Toutes les actions épinglées par SHA de commit ; Dependabot tient les épinglages à jour.

**Tech Stack:** gitleaks 8.30.1, semgrep 1.178.0, osv-scanner 2.6.0, trivy 0.74.0, syft 1.52.0, cosign 3.1.3 (format *bundle*, référents OCI), uv 0.12.19, GitHub Actions.

**Spec :** §4 (piste « Chaque PR » et « Release »). **Suivi :** section « Plan 1d » de `followups.md`. Le plan **1d-2** (évaluations LLM, red team nocturne, dérive, coût exact, points applicatifs) suivra.

## Décisions (écarts à la spec §4, à reporter dans la spec à la tâche 7)

- **Pas de canary CodeDeploy à 10 %.** Pour un trafic de démo, le test de fumée de production + retour arrière automatique donne la même garantie sans alias, CodeDeploy ni alarmes. À revoir si le trafic devient réel.
- **`terraform apply` reste manuel.** Les environnements GitHub avec approbation ne sont pas garantis sur un dépôt privé du plan gratuit, et un rôle CI capable d'`apply` aurait des droits d'administrateur. `terraform plan` en commentaire de PR est aussi reporté : il faudrait un rôle de lecture qui ne puisse pas lire les secrets SSM (la politique gérée `ReadOnlyAccess` le permettrait via la clé `aws/ssm`).
- **Provenance SLSA (`attest-build-provenance`) reportée** : les attestations GitHub exigent un dépôt public (ou GitHub Enterprise) ; à activer quand le dépôt sera public (plan 1e / portfolio). La signature cosign et l'attestation SBOM, elles, fonctionnent sur un dépôt privé.
- **`cosign verify` « par copier-coller » depuis le site** (critère §9) : impossible tant que l'image est dans un ECR privé ; à traiter avec la publication (miroir public GHCR ou ECR Public) au plan 1e.

## Faits vérifiés le 2026-09-26

| Action | Version | SHA de commit |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `astral-sh/setup-uv` | v10.2.0 | `c18668ad3cf93ea998bef934396af7bb5c839dc7` |
| `sigstore/cosign-installer` | v4.1.2 | `6f9f17788090df1f26f669e9d70d6ae9567deba6` |
| `hashicorp/setup-terraform` | v4.0.1 | `dfe3c3f87815947d99a8997f908cb6525fc44e9e` |
| `aws-actions/configure-aws-credentials` | v6.3.0 | `e1253824e5c10ff9df46874f81ed3ec929e19cfd` |
| `aws-actions/amazon-ecr-login` | v2.1.7 | `03f1aad4c6c7ffd436567f42f9384779290529bd` |
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |

- `actions/checkout` passe de v4 à v7 et `astral-sh/setup-uv` de v6 à v10 : **lire les notes de version** des versions majeures intermédiaires (entrées renommées, valeurs par défaut) avant d'épingler.
- `actions/attest-build-provenance@v4` (dans `train.yml`) : relever son SHA de la même façon (`gh api repos/actions/attest-build-provenance/releases/latest --jq .tag_name`, puis `gh api repos/actions/attest-build-provenance/commits/<tag> --jq .sha`).
- **cosign 3.x** : signatures et attestations au format *bundle* Sigstore, poussées comme **référents OCI** (pas de tags `sha256-….sig`). ECR gère l'API des référents : aucun conflit avec le dépôt en tags `IMMUTABLE`. Si ECR refusait un push de signature pour cause d'immuabilité, repli prévu : `image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"` avec un filtre `sha256-*` (provider AWS ≥ 6.8, bloc `image_tag_mutability_exclusion_filter`).
- `cosign-installer@v4.1.2` installe cosign 3.0.6 par défaut : fixer `cosign-release: v3.1.3`.
- Image de base `python:3.12-slim` : digest actuel `sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` (à revérifier avec `docker buildx imagetools inspect python:3.12-slim` au moment de l'implémentation).
- Images d'outils : `zricethezav/gitleaks:v8.30.1`, `semgrep/semgrep:1.178.0`, `ghcr.io/google/osv-scanner:v2.6.0`, `aquasec/trivy:0.74.0`, `anchore/syft:v1.52.0`, `ghcr.io/astral-sh/uv:0.12.19`. **Relever le digest de chacune** (`docker buildx imagetools inspect <image>`) et l'écrire dans le workflow sous la forme `image:tag@sha256:…`.
- Lambda n'accepte pas la signature de code pour les images conteneur : la vérification se fait **en CI, juste avant `update-function-code`**, sur le digest exact qui sera déployé.

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv`, branche `main`, identité git réglée, pas de ligne d'attribution, **ne pas pousser** (le contrôleur pousse à la tâche 6).
- `export UV=~/AppData/Roaming/Python/Python314/Scripts/uv.exe` ; Terraform : `export PATH="~/AppData/Local/Microsoft/WinGet/Links:$PATH"`.
- Porte avant chaque commit : `$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q` (225 tests) ; YAML du workflow chargé sans erreur (`$UV run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"`).
- Docker 29.8 est disponible localement : **chaque scan est d'abord lancé en local** avec la même image et les mêmes options que dans la CI, pour trier les constats avant de committer.
- Sous Git Bash, préfixer les `docker run -v "$PWD:/src"` de `MSYS_NO_PATHCONV=1`.
- Aucun appel AWS dans les tâches 1 à 5.

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `.github/workflows/ci.yml` | jobs `security`, `test` (scan d'image, SBOM, imports), `deploy` (signature, vérification, digest, retour arrière) |
| `.github/workflows/train.yml` | actions épinglées |
| `.github/dependabot.yml` | mises à jour des actions, de `uv.lock`, du Dockerfile |
| `Dockerfile` | base par digest, uv copié depuis son image, pas de `chown -R` |
| `.gitleaks.toml` | exceptions justifiées (faux positifs des tests) |
| `.semgrepignore` | chemins exclus (données, modèles) |
| `.trivyignore.yaml` | constats IaC / image acceptés, chacun justifié et daté |
| `scripts/check_imports.py` | import de chaque module d'exécution dans l'image |
| `README.md` | section « Chaîne de sécurité » |

---

### Task 1 : actions épinglées par SHA, Dependabot, cosign fixé

**Files:** Modify `.github/workflows/ci.yml`, `.github/workflows/train.yml` ; Create `.github/dependabot.yml`

- [ ] **Step 1 : épingler** — remplacer chaque `uses: owner/action@vX` par `uses: owner/action@<sha> # vX.Y.Z` avec les SHA du tableau (et celui d'`attest-build-provenance`). Lire les notes de version de `actions/checkout` (v5→v7) et `astral-sh/setup-uv` (v7→v10) ; adapter les entrées si besoin. Ajouter `persist-credentials: false` à chaque `actions/checkout` (le jeton n'est pas réutilisé par git ensuite) **sauf** dans `train.yml` si ce workflow pousse avec git (vérifier).
- [ ] **Step 2 : cosign** — à chaque `sigstore/cosign-installer`, ajouter `with: { cosign-release: v3.1.3 }`.
- [ ] **Step 3 : `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }
    groups:
      actions: { patterns: ["*"] }
  - package-ecosystem: uv
    directory: /
    schedule: { interval: weekly }
    groups:
      python: { patterns: ["*"] }
  - package-ecosystem: docker
    directory: /
    schedule: { interval: weekly }
```

Vérifier dans la documentation GitHub que l'écosystème `uv` est bien pris en charge par Dependabot ; sinon, `pip` ne sait pas lire `uv.lock` : retirer ce bloc et le noter dans les followups.
- [ ] **Step 4 : vérifier** — `grep -n "uses:" .github/workflows/*.yml` : plus aucune référence `@v…` sans SHA. YAML valide. Suite Python verte (inchangée).
- [ ] **Step 5 : commit** — `ci: actions épinglées par SHA, Dependabot, cosign 3.1.3`

---

### Task 2 : Dockerfile durci et imports vérifiés dans l'image

**Files:** Modify `Dockerfile`, `.github/workflows/ci.yml` ; Create `scripts/check_imports.py`, `tests/test_check_imports.py`

- [ ] **Step 1 : test du script** — `tests/test_check_imports.py` :

```python
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_imports.py"
spec = importlib.util.spec_from_file_location("check_imports", SCRIPT)
assert spec and spec.loader
check_imports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_imports)


def test_lists_every_runtime_module() -> None:
    modules = check_imports.runtime_modules()
    assert "ask_my_cv.app" in modules
    assert "ask_my_cv.aws.sigv4" in modules
    assert not any(m.startswith("ask_my_cv.tests") for m in modules)


def test_all_runtime_modules_import() -> None:
    assert check_imports.main() == 0
```

- [ ] **Step 2 : vérifier l'échec** (`FileNotFoundError` / module absent).
- [ ] **Step 3 : `scripts/check_imports.py`**

```python
"""Importe chaque module d'exécution d'ask_my_cv : une dépendance manquante dans l'image échoue ici.

Lancé dans l'image construite (CI) : `docker run --rm --entrypoint .venv/bin/python <image> scripts/check_imports.py`.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import ask_my_cv


def runtime_modules() -> list[str]:
    return sorted(
        info.name
        for info in pkgutil.walk_packages(ask_my_cv.__path__, prefix="ask_my_cv.")
    )


def main() -> int:
    failures = []
    for name in runtime_modules():
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - on veut tout rapporter
            failures.append(f"{name} : {type(exc).__name__}: {exc}")
    for failure in failures:
        print(failure, file=sys.stderr)
    print(f"{len(runtime_modules()) - len(failures)} modules importés, {len(failures)} échec(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

Ajouter `scripts` à l'`include` de pyright si nécessaire ; `COPY scripts/check_imports.py ./scripts/` dans le Dockerfile (le script doit être dans l'image). Si un module ne s'importe qu'en mode AWS (import paresseux de boto3 déjà présent : ok), le noter.
- [ ] **Step 4 : Dockerfile**
  - `FROM python:3.12-slim@sha256:<digest relevé>` (garder le tag pour la lisibilité).
  - Remplacer `RUN pip install --no-cache-dir "uv>=0.5"` par `COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:<digest> /uv /uvx /bin/`.
  - Supprimer `chown -R app /app` : `RUN useradd --system --no-create-home app` seul. Les fichiers restent à root, lisibles par tous (vérifier que rien n'écrit sous `/app` à l'exécution : le démarrage local et le test de fumée CI le prouvent).
  - Lambda Web Adapter : `COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:<digest> …`.
- [ ] **Step 5 : CI (job `test`)** — après `docker build`, ajouter :

```yaml
      - name: Imports de chaque module dans l'image
        run: docker run --rm --entrypoint .venv/bin/python ask-my-cv:ci scripts/check_imports.py
```

- [ ] **Step 6 : vérifier en local** — `docker build -t ask-my-cv:local .`, puis la commande d'imports (attendu : `N modules importés, 0 échec(s)`), puis le démarrage (`/healthz` → `onnx-v1.1.0`, le modèle vérifié étant dans `models/`). **Contrôle du garde-fou :** retirer temporairement `requests` de `pyproject.toml`/`uv.lock` dans une copie de travail ou vérifier par raisonnement que `ask_my_cv.aws.sigv4` l'importe au niveau module ; le script l'aurait donc détecté. Ne pas committer ce contrôle.
- [ ] **Step 7 : commit** — `build: image de base et uv épinglés par digest, fichiers à root, imports vérifiés dans l'image`

---

### Task 3 : job `security` (secrets, code, dépendances, IaC)

**Files:** Modify `.github/workflows/ci.yml` ; Create `.gitleaks.toml`, `.semgrepignore`, `.trivyignore.yaml`

- [ ] **Step 1 : triage local** — lancer chaque outil depuis la racine du dépôt, noter chaque constat :

```bash
export MSYS_NO_PATHCONV=1
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.30.1 git /repo --redact --no-banner
docker run --rm -v "$PWD:/src" -w /src semgrep/semgrep:1.178.0 semgrep scan --metrics=off \
  --config p/python --config p/dockerfile --config p/github-actions --config p/secrets --error
docker run --rm -v "$PWD:/src" ghcr.io/google/osv-scanner:v2.6.0 scan source --lockfile /src/uv.lock
docker run --rm -v "$PWD:/src" aquasec/trivy:0.74.0 config --severity HIGH,CRITICAL --exit-code 1 /src/infra
```

  Règles de tri :
  - **Vrai problème corrigeable dans ce plan** (dépendance vulnérable avec version corrigée, IaC facile) → le corriger (commit séparé si c'est du code applicatif ; `uv lock --upgrade-package <nom>`).
  - **Faux positif** (clé factice des tests, ex. `valeur-LANGFUSE_SECRET_KEY`, `testing`) → exception ciblée (chemin + règle), jamais globale.
  - **Risque accepté** (ex. CloudFront sans WAF/journaux, DynamoDB sans PITR, chiffrement AWS géré plutôt que KMS client) → entrée dans `.trivyignore.yaml` avec `statement:` expliquant pourquoi et `expired_at:` à 6 mois ; si le point figure dans les followups, y renvoyer.
- [ ] **Step 2 : fichiers d'exceptions**
  - `.gitleaks.toml` : `[extend] useDefault = true` + `[[allowlists]]` avec `paths`/`regexes` ciblés et un `description` en français.
  - `.semgrepignore` : `data/`, `models/`, `ml/data/`, `uv.lock`, `.venv/`.
  - `.trivyignore.yaml` : format YAML de trivy (`misconfigurations: - id: AVD-AWS-XXXX, paths: [...], statement: ..., expired_at: 2027-03-26`) ; vérifier le format exact dans la documentation trivy 0.74.
- [ ] **Step 3 : job**

```yaml
  security:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<sha> # v7.0.1
        with:
          fetch-depth: 0 # gitleaks parcourt tout l'historique
          persist-credentials: false
      - name: Secrets (gitleaks, tout l'historique)
        run: docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.30.1@sha256:<digest> git /repo --redact --no-banner --exit-code 1
      - name: Code (semgrep)
        run: |
          docker run --rm -v "$PWD:/src" -w /src semgrep/semgrep:1.178.0@sha256:<digest> semgrep scan --metrics=off \
            --config p/python --config p/dockerfile --config p/github-actions --config p/secrets --error
      - name: Dépendances (osv-scanner)
        run: docker run --rm -v "$PWD:/src" ghcr.io/google/osv-scanner:v2.6.0@sha256:<digest> scan source --lockfile /src/uv.lock
      - name: IaC (trivy config)
        run: |
          docker run --rm -v "$PWD:/src" aquasec/trivy:0.74.0@sha256:<digest> config \
            --severity HIGH,CRITICAL --exit-code 1 --ignorefile /src/.trivyignore.yaml /src/infra
```

  `deploy` dépend désormais aussi de `security` : `needs: [test, terraform, security]`.
- [ ] **Step 4 : vérifier** — les quatre commandes, lancées en local exactement comme dans le job, sortent avec le code 0. YAML valide.
- [ ] **Step 5 : commit** — `ci: scans de secrets, de code, de dépendances et d'IaC à chaque changement`

---

### Task 4 : scan de l'image et SBOM (job `test`)

**Files:** Modify `.github/workflows/ci.yml`, `.trivyignore.yaml`

- [ ] **Step 1 : triage local** — sur l'image construite à la tâche 2 :

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.74.0 image \
  --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 ask-my-cv:local
```

  Sous Windows, le socket Docker Desktop se monte aussi avec `-v /var/run/docker.sock:/var/run/docker.sock` (préfixe `MSYS_NO_PATHCONV=1`). Si ça échoue, exporter l'image (`docker save ask-my-cv:local -o image.tar`, hors dépôt) et scanner avec `--input`.
  Tri : paquet Python vulnérable avec correctif → mise à jour ; paquet Debian corrigé → il suffit généralement de reconstruire sur le dernier digest de la base ; reste accepté → `.trivyignore.yaml` (section `vulnerabilities`, justification, `expired_at` à 3 mois).
- [ ] **Step 2 : CI** — dans `test`, après le contrôle des imports :

```yaml
      - name: Scan de l'image (trivy)
        run: |
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:/src" aquasec/trivy:0.74.0@sha256:<digest> image \
            --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 --ignorefile /src/.trivyignore.yaml ask-my-cv:ci
      - name: SBOM CycloneDX (syft)
        run: |
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:/out" anchore/syft:v1.52.0@sha256:<digest> \
            ask-my-cv:ci -o cyclonedx-json=/out/sbom.cdx.json
      - uses: actions/upload-artifact@<sha> # v7.0.1
        with:
          name: sbom-${{ github.sha }}
          path: sbom.cdx.json
          retention-days: 30
```

- [ ] **Step 3 : vérifier en local** — les deux commandes docker réussissent ; `sbom.cdx.json` contient `"bomFormat": "CycloneDX"` et au moins `fastapi`, `onnxruntime`, `boto3` (`$UV run python -c` pour le vérifier) ; ne pas committer le SBOM (`sbom.cdx.json` dans `.gitignore`).
- [ ] **Step 4 : commit** — `ci: scan de vulnérabilités de l'image et SBOM CycloneDX`

---

### Task 5 : déploiement signé, vérifié, par digest, avec retour arrière

**Files:** Modify `.github/workflows/ci.yml`, `README.md`

Le job `deploy` devient (étapes après `amazon-ecr-login`, le reste inchangé) :

```yaml
      - name: Construire et pousser l'image
        run: |
          IMAGE="$ECR_REPOSITORY_URL:$GITHUB_SHA"
          if aws ecr describe-images --repository-name ask-my-cv --image-ids imageTag="$GITHUB_SHA" >/dev/null 2>&1; then
            echo "image déjà présente"
          else
            docker build --platform linux/amd64 --provenance=false --sbom=false -t "$IMAGE" .
            docker push "$IMAGE"
          fi
          DIGEST=$(aws ecr describe-images --repository-name ask-my-cv --image-ids imageTag="$GITHUB_SHA" \
            --query 'imageDetails[0].imageDigest' --output text)
          echo "IMAGE_REF=$ECR_REPOSITORY_URL@$DIGEST" >> "$GITHUB_ENV"
      - name: SBOM de l'image poussée
        run: |
          docker run --rm -v "$HOME/.docker:/root/.docker:ro" -v "$PWD:/out" anchore/syft:v1.52.0@sha256:<digest> \
            "registry:$IMAGE_REF" -o cyclonedx-json=/out/sbom.cdx.json
      - name: Signer l'image et attester le SBOM (Sigstore keyless)
        run: |
          cosign sign --yes "$IMAGE_REF"
          cosign attest --yes --type cyclonedx --predicate sbom.cdx.json "$IMAGE_REF"
      - name: Vérifier signature et attestation avant déploiement
        run: |
          ID="https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@refs/heads/main"
          ISSUER=https://token.actions.githubusercontent.com
          cosign verify "$IMAGE_REF" --certificate-identity "$ID" --certificate-oidc-issuer "$ISSUER" >/dev/null
          cosign verify-attestation "$IMAGE_REF" --type cyclonedx \
            --certificate-identity "$ID" --certificate-oidc-issuer "$ISSUER" >/dev/null
          echo "signature et SBOM vérifiés pour $IMAGE_REF"
      - name: Déployer (par digest)
        run: |
          PREVIOUS=$(aws lambda get-function --function-name "$FUNCTION_NAME" --query Code.ImageUri --output text)
          echo "PREVIOUS_IMAGE=$PREVIOUS" >> "$GITHUB_ENV"
          aws lambda update-function-code --function-name "$FUNCTION_NAME" --image-uri "$IMAGE_REF" >/dev/null
          aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
      - name: Test de fumée de production
        id: smoke
        run: python3 infra/scripts/smoke_prod.py "${{ vars.SITE_URL }}"
      - name: Retour arrière si le test de fumée échoue
        if: failure() && steps.smoke.outcome == 'failure' && env.PREVIOUS_IMAGE != ''
        run: |
          echo "::error::test de fumée en échec : retour à $PREVIOUS_IMAGE"
          aws lambda update-function-code --function-name "$FUNCTION_NAME" --image-uri "$PREVIOUS_IMAGE" >/dev/null
          aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
```

Notes :
- Le job garde `permissions: id-token: write` (OIDC AWS **et** Sigstore).
- `cosign-installer` (épinglé, `cosign-release: v3.1.3`) est déjà dans le job pour le modèle.
- `amazon-ecr-login` écrit la configuration Docker dans `~/.docker/config.json` : cosign et syft la réutilisent pour ECR.
- Droits ECR du rôle de déploiement : `PutImage`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `BatchGetImage`, `GetDownloadUrlForLayer`, `DescribeImages` sont déjà accordés (amorçage) ; cosign pousse ses *bundles* comme artefacts OCI avec ces mêmes appels. Si l'API des référents exige `ecr:ListImages` ou autre, le premier déploiement le révélera : l'ajouter alors dans `infra/bootstrap/main.tf` (le contrôleur applique, tâche 6).
- Le retour arrière ne se déclenche que si **le test de fumée** échoue (pas si la construction échoue : rien n'a changé en production dans ce cas).

- [ ] **Step 1 : écrire le job** comme ci-dessus ; YAML valide ; relire l'ordre des étapes.
- [ ] **Step 2 : README** — section « Chaîne de sécurité » : les quatre scans et quand ils tournent, le SBOM (artefact + attestation), la signature keyless, la commande de vérification :

```bash
cosign verify <compte>.dkr.ecr.ca-central-1.amazonaws.com/ask-my-cv@sha256:<digest> \
  --certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

  (accès ECR requis tant que l'image est privée), le déploiement par digest et le retour arrière automatique, les décisions de la section « Décisions ».
- [ ] **Step 3 : commit** — `ci: images signées et vérifiées, déploiement par digest, retour arrière automatique`

---

### Task 6 : mise en service (contrôleur, avec accord)

- [ ] Pousser `main` (accord). Suivre la CI : `security`, `test`, `terraform`, `deploy` verts.
- [ ] Vérifier dans les journaux du job `deploy` : signature et attestation vérifiées, `IMAGE_REF` en `@sha256:`.
- [ ] Vérifier en local (identifiants de l'utilisateur, lecture seule) : `aws lambda get-function --function-name ask-my-cv-api --query Code.ImageUri` renvoie un URI **par digest** ; `cosign verify` de ce digest réussit depuis le poste.
- [ ] Si ECR refuse la signature (immutabilité) ou un droit manque : correctif dans `infra/bootstrap/main.tf`, `plan` montré puis `apply` (accord), relance du job.
- [ ] **Test du retour arrière** (accord ; quelques centimes) : sur une branche jetable, impossible (le déploiement ne tourne que sur `main`). Le tester donc par un rejeu contrôlé : lancer à la main, avec les identifiants de l'utilisateur, `update-function-code` vers le digest courant puis simuler l'étape de retour arrière avec `PREVIOUS_IMAGE` = digest précédent, et vérifier `/healthz`. Ou accepter la relecture du code comme preuve, et le noter.

### Task 7 : documentation et suivi (contrôleur)

- [ ] `followups.md` : barrer les points 1d traités (épinglage SHA, cosign fixé, Dockerfile, imports dans l'image, retour arrière, signature d'image) ; créer la section « Plan 1d-2 » avec les points restants (évaluations LLM, red team nocturne, dérive PSI, coût exact `metadata.usage`, `ledger.record`, modèle inconnu dans les traces, tests de télémétrie, test de vie privée étendu, quota en une lecture, v1.2.0 du classifieur, promptfoo « information absente », configuration `extra="forbid"`, LICENSE) ; garder en 1d-x : OIDC restreint à `ci.yml`, journaux CloudFront / WAF, `terraform plan` en PR (rôle de lecture sans accès aux secrets), provenance SLSA et miroir public (avec la publication).
- [ ] Spec §4 : piste « Release » mise à jour avec les décisions (retour arrière au lieu du canary, `apply` manuel, provenance reportée au passage en public).
- [ ] Commits séparés, push avec accord.

## Critères de fin

- Une PR déclenche `security` et `test` : gitleaks, semgrep, osv-scanner, trivy (IaC et image) passent ; toute exception est ciblée, justifiée et datée.
- Aucune action GitHub référencée autrement que par SHA ; Dependabot actif.
- L'image déployée est désignée **par digest**, signée keyless par `ci.yml@refs/heads/main`, avec une attestation SBOM CycloneDX, et `cosign verify` réussit sur ce digest.
- Un test de fumée raté remet l'image précédente en service (vérifié ou démontré).
- Le contrôle des imports dans l'image fait partie de la CI.
- 225 tests + les nouveaux, `ruff`, `pyright` : tout vert.
