# « Interroge mon CV » — plan 1e-2b : archive publique du développement — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tout le développement du projet devient consultable publiquement et vérifiable : la spec, les plans et le suivi dans `ask-my-cv/docs`, un **journal** par plan reconstitué mot pour mot depuis le journal de session (rapports d'implémentation, revues et leur traitement, décisions), et une **issue GitHub fermée** par tâche réelle, étiquette `historique`, reliée aux vrais commits — sans rien inventer, avec masquage des données privées et relecture d'un échantillon par l'utilisateur avant publication.

**Méthode :** flux GitHub (issue → PR → revue d'agent en commentaire → fusion), comme au 1e-2a.

**Architecture:**
- **Sources (locales, privées, jamais publiées telles quelles)** :
  - journal de session principal `~/.claude/<session-claude>/<session-claude>.jsonl` (≈ 23 Mo) ;
  - 111 sous-agents : `…/<session-claude>…/subagents/agent-*.jsonl` + `agent-*.meta.json` (`agentType`, `description`, `model`) ;
  - table de correspondance des commits de la réécriture d'historique : `~/.claude/devlog-private/ask-my-cv-commit-map` (copie de `work.git/filter-repo/commit-map`, 130 commits) (ancien SHA → nouveau SHA) ;
  - documents : `<poste>\xops-kit\docs\superpowers\{specs,plans}\*.md`.
- **Outil public, testé** : `ask-my-cv/tools/devlog/` (Python, dans le dépôt, sans dépendance nouvelle) :
  - `redact.py` — masquage déterministe (liste ci-dessous), **appliqué à tout texte avant écriture** ;
  - `extract.py` — lit les sous-agents, produit un enregistrement par agent (date de début/fin, type, modèle, description, consigne, rapport final), rattache chaque agent à un plan (par fenêtre de dates du plan + description), traduit les SHA via `commit-map` ;
  - `render.py` — écrit `docs/journal/<plan>.md` (chronologie par tâche : implémentation → revue(s) → corrections → commits) et `docs/journal/index.json` (données pour l'onglet « Livraison ») ;
  - `issues.py` — produit, en **mode simulation par défaut**, la liste des issues historiques (titre, corps, étiquettes) ; création réelle seulement avec `--apply`.
- **Sorties publiques** : `docs/spec/`, `docs/plans/`, `docs/followups.md`, `docs/journal/`, issues `historique`.

**Masquage (obligatoire, testé) :**
- identifiant de compte AWS `<compte-aws>` → `<compte-aws>` (y compris dans les ARN et l'hôte ECR) ;
- adresses personnelles (`<adresse>`, `<adresse>`, toute adresse autre que `job@stevelang.net`, les adresses fictives des tests `*@example.com`/`*@evil.com`/`*@corp.com` et les adresses noreply GitHub) → `<adresse>` ;
- chemins locaux (`~\…`, `~/…`, `<poste>\…`) → `~/…` / `<poste>/…` ;
- contenu brut du CV `.docx` (extraction du 2026-09-26) : **exclu** ; seul le CV public (`data/cv.md`) peut apparaître ;
- jetons et secrets : garde-fou — toute chaîne ressemblant à un secret (clés `pk-lf-`, `sk-lf-`, `AKIA…`, jetons de 40+ caractères hexadécimaux ou base64 hors SHA de commit/digest connus) **fait échouer** le rendu au lieu d'être publiée ;
- **exclu entièrement** : les messages de l'utilisateur et les réponses du contrôleur de la conversation principale (échanges privés) — seules les **décisions** déjà consignées dans la spec, les plans et le suivi sont publiées.

**Tech Stack:** Python 3.12 (bibliothèque standard), pytest, `gh` CLI, GitHub Issues.

**Spec :** §6 (onglet Livraison). **Suivi :** « Plan 1e-2 → 1e-2b » de `followups.md`.

## Faits vérifiés le 2026-09-27

- 222 fichiers sous `subagents/` (111 agents ; métadonnées : `general-purpose` 94, `ecc:security-reviewer` 12, `ecc:code-reviewer` 3, `ecc:python-reviewer` 2). Chaque `agent-*.jsonl` : entrées `user` / `assistant` / `attachment` avec `timestamp` ; le rapport final = dernier bloc de texte de l'assistant.
- Les sous-agents d'avant la réécriture citent des SHA **anciens** ; `commit-map` permet la traduction. Les SHA absents de la table (branches abandonnées) restent affichés comme « commit hors de l'historique publié ».
- Les revues antérieures au 1e-2a ont été faites par des agents `general-purpose` (revue de conformité à la spec, puis de qualité) : leur rôle se déduit de la consigne (« spec compliance », « quality review », « final review »).

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv` (public, `main` protégée). Branche `t/<issue>-<slug>` depuis `origin/main`, PR « Closes #n ».
- Porte Python : `$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q`.
- **Les données réelles ne sont traitées que localement.** Les tests utilisent de petites fixtures synthétiques (`tests/devlog/fixtures/`), jamais d'extraits du vrai journal.
- Rien n'est publié (docs générés, issues) avant la **validation de l'échantillon par l'utilisateur** (tâche 4).

---

### Task 1 : masquage (issue, PR)

**Files:** Create `tools/devlog/__init__.py`, `tools/devlog/redact.py`, `tests/devlog/test_redact.py` ; Modify `pyproject.toml` (inclure `tools` dans pyright/ruff si besoin)

- [ ] Tests d'abord : chaque règle ci-dessus (identifiant de compte seul, dans un ARN, dans `<compte>.dkr.ecr…`) ; adresses (personnelles masquées, `job@stevelang.net` conservée) ; chemins Windows et Git Bash ; garde-fou des secrets (une fausse clé `sk-lf-…` et une fausse `AKIA…` font lever `SecretDetected` ; un SHA de commit de 40 caractères et un digest `sha256:` **ne** déclenchent **pas** le garde-fou) ; idempotence (`redact(redact(x)) == redact(x)`).
- [ ] `redact(text: str) -> str` et `assert_no_secret(text: str) -> None`.

### Task 2 : extraction et rattachement (issue, PR)

**Files:** Create `tools/devlog/extract.py`, `tests/devlog/test_extract.py`, `tests/devlog/fixtures/…`

- [ ] `load_agents(dir) -> list[AgentRecord]` (`id`, `type`, `model`, `description`, `started`, `ended`, `prompt`, `report`) depuis des fixtures synthétiques reproduisant la structure réelle (`user`/`assistant`/`attachment`, blocs `text`, `tool_use`, `tool_result`).
- [ ] `role(record)` : `implementation` / `review` / `fix` / `other`, déduit du type d'agent et de la consigne (mots-clés `implement`, `review`, `re-review`, `fix`, `address`…) — tests sur des consignes typiques.
- [ ] `assign_plan(record, plans)` : fenêtre de dates des plans (lue depuis `docs/plans/*.md` — date du nom de fichier + date du commit suivant) et description ; cas ambigus → `plan: "inconnu"` (jamais deviné en silence).
- [ ] `translate_shas(text, commit_map)` : remplace les SHA courts/longs anciens par les nouveaux, marque ceux qui sont absents.

### Task 3 : rendu du journal et des données (issue, PR)

**Files:** Create `tools/devlog/render.py`, `tools/devlog/__main__.py` (`python -m tools.devlog render --subagents … --commit-map … --out docs/journal`), `tests/devlog/test_render.py`

- [ ] `docs/journal/<plan>.md` : en-tête (objectif du plan, lien vers `docs/plans/…`), puis par tâche : « Implémentation » (date, modèle, rapport masqué), « Revues » (verdict, constats), « Corrections », « Commits » (liens `https://github.com/VoiD911/ask-my-cv/commit/<sha>`).
- [ ] `docs/journal/index.json` : liste des plans → tâches → événements (type, date, agent, verdict, commits, lien issue/PR le cas échéant) — schéma documenté dans `docs/journal/README.md`.
- [ ] **Chaque texte passe par `redact` puis `assert_no_secret`** ; test : un rapport contenant l'identifiant de compte et un chemin local sort masqué ; un rapport contenant une fausse clé fait échouer le rendu.

### Task 4 : génération locale et relecture par l'utilisateur (contrôleur)

- [ ] Copier la spec, les plans et `followups.md` de `xops-kit` vers `ask-my-cv/docs/{spec,plans}/` et `docs/followups.md`, en les faisant passer par `redact` (chemins du scratchpad, adresses).
- [ ] Lancer le rendu **en local** sur les vraies données ; contrôles automatiques : aucune occurrence de `<compte-aws>`, `<utilisateur>`, `<utilisateur>`, `<adresse>` dans `docs/` (grep) ; nombre d'agents rattachés par plan ; agents `inconnu` listés.
- [ ] **Échantillon pour l'utilisateur** (envoyé comme fichiers) : `docs/journal/1c-2.md` et `docs/journal/1d-3.md` + 3 issues simulées (`issues.py` sans `--apply`). Attendre sa validation ou ses corrections avant la tâche 5.

### Task 5 : publication (issue, PR ; issues réelles par le contrôleur avec accord)

**Files:** Create `docs/**` (générés), `tools/devlog/issues.py`, `tests/devlog/test_issues.py` ; Modify `README.md`

- [ ] `issues.py` : une issue par tâche réelle ; titre `<plan> · <tâche>` ; corps : « Issue reconstituée le 2026-09-27 depuis le journal de développement (date réelle : …) », liens plan/journal, commits, résumé du rapport et des revues (masqués) ; étiquettes `historique`, `plan:<id>` ; état **fermé** ; mode simulation par défaut ; idempotence (ne recrée pas une issue dont le titre existe déjà).
- [ ] PR avec `docs/` générés et l'outil ; revue d'agent ; fusion.
- [ ] Création réelle des issues (`--apply`, accord de l'utilisateur) ; vérification : nombre d'issues = nombre de tâches, toutes fermées, aucune donnée masquée visible (recherche GitHub sur `<compte-aws>` et `<utilisateur>` → 0 résultat).
- [ ] README : section « Comment ce projet a été construit » (méthode assumée : l'architecte fixe les objectifs et arbitre ; des agents implémentent et révisent ; la CI, les signatures et les évaluations vérifient) avec liens vers `docs/` et les issues `historique`.

### Task 6 : suivi (contrôleur)

- [ ] `followups.md` (xops-kit) : 1e-2b barré, points reportés (ex. masquage de l'identifiant de compte dans les journaux des Actions, relevé au 1e-2a).

## Critères de fin

- `docs/` du dépôt public contient la spec, tous les plans, le suivi et un journal par plan ; `docs/journal/index.json` est prêt pour l'onglet « Livraison ».
- Une issue fermée `historique` par tâche réelle, reliée aux vrais commits (SHA traduits), avec rapports et revues masqués.
- Aucune donnée privée (identifiant de compte, adresses personnelles, chemins locaux, échanges privés, CV brut) dans le dépôt ni dans les issues ; le garde-fou des secrets est testé.
- L'utilisateur a validé un échantillon avant toute publication.
