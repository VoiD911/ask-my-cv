# « Interroge mon CV » — plan 1e-2c : onglets Architecture et XOps, anglais, rediffusion

> **For agentic workers:** flux `xops-pipeline` (issue → worktree → `xops-implementer` → revue → CI → commit de fusion).

**Goal:** ce qu'un recruteur voit : comprendre en quelques minutes comment le site est construit, revu, déployé et surveillé, avec des preuves vérifiables, en français et en anglais.

**Spec :** §6 (`/architecture`, `/xops`, mode rediffusion, bilingue). L'onglet Livraison est déjà en ligne (#98).

## Règle de périmètre

- Chaque tâche a des critères de fin visibles sur le site ; rien d'autre n'entre dans la PR.
- **Deux passages de revue au plus** par PR ; au-delà, seuls les constats **Critique** bloquent, le reste va dans `followups.md`.
- Pas de nouvel outil d'évaluation ni de refonte du pipeline dans ce plan.

## Tâches

### Tâche 1 : onglet Architecture (`/architecture`)
Quatre parties, chacune avec un diagramme et des liens vers le code :
1. **Chemin d'une requête** : CloudFront → Lambda (FastAPI) → étapes (garde, classifieur, garde-fou Bedrock pour les annonces, recherche vectorielle DynamoDB, LLM Bedrock, garde de sortie) → SSE → interface.
2. **Infrastructure** : ressources Terraform principales (`infra/prod`, `infra/bootstrap`) regroupées par rôle.
3. **Du code à la production** : jobs de `ci.yml` (sécurité, tests, évals, web, terraform, déploiement signé, rollback) et workflows de nuit.
4. **Cycle de vie du modèle** : données → entraînement signé → portes → release → promotion → dérive.
- Diagrammes générés au build depuis les sources réelles (workflows YAML, liste des ressources Terraform, étapes du pipeline), pas dessinés à la main ; test qui échoue si une source change sans que le diagramme suive.
- **Fin :** page en ligne, lisible sur mobile, axe sans violation, CSP inchangée.

### Tâche 2 : onglet XOps (`/xops`)
- Matrice DevOps / DevSecOps / MLOps / LLMOps / FinOps × pratiques ; chaque case renvoie à une preuve publique réelle (release signée, commande `cosign verify` copiable, SBOM, provenance SLSA, workflow et dernier run, rapport de nuit, model card, budget).
- Aucune case sans preuve ; les cases « partielles » le disent.
- **Fin :** page en ligne, chaque lien vérifié par un test au build (URL construites depuis les données du dépôt, pas codées en dur).

### Tâche 3 : anglais
- next-intl, `/en/...` pour toutes les pages (accueil, architecture, xops, livraison) ; sélecteur de langue ; textes du chat et messages de blocage traduits ; le CV reste la source française (l'API répond déjà dans la langue de la question).
- **Fin :** toutes les pages existent en anglais, Lighthouse et axe verts.

### Tâche 4 : mode rediffusion
- Si l'API est indisponible (budget atteint, panne), l'accueil rejoue des échanges réels enregistrés (masqués), avec la mention « rediffusion ».
- **Fin :** démontrable en coupant l'API en local ; test e2e.

### Tâche 5 : suivi
- `followups.md` : 1e-2c barré ; ce qui a été reporté (y compris la PR #125 sur la dérive, en attente).

## Ordre

1 → 2 → 3 → 4 → 5.
