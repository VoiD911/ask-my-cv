# « Interroge mon CV » — plan 1e-2d : corrections issues des revues a posteriori

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (flux `xops-pipeline` : issue → worktree → `xops-implementer` → revue → CI → commit de fusion).

**Goal:** traiter les constats des revues a posteriori des PR #21/#96, #97, #98, #99, #101/#102 (fusionnées sans revue d'agent pendant la pause), rétablir la suite de nuit (#100) et fermer la fuite de l'identifiant de compte dans les journaux publics.

**Sources :** commentaires de revue sur les PR ci-dessus (verdicts publiés le 2026-09-29).

## Faits vérifiés le 2026-09-29

- Suite de nuit : 1 cas sur 28 en échec, « absent — téléphone » (`evals/nightly.yaml`), depuis le prompt `answer@v4` ; reproduit sur une relance manuelle.
- Le job `drift` de `nightly.yml` affiche l'ARN du rôle (identifiant de compte) ; `AWS_ACCOUNT_ID` n'existe que dans l'environnement `production`.
- Classifieur servi : `model-v1.3.0`, fenêtres de 600 caractères, recouvrement 120, agrégation max ; porte `domain_fpr` à 0,02.
- Livraison : `web/src/lib/delivery-archive.json` est réécrit à chaque build par `sync-archive.mjs`.

## Tâches

### Tâche 1 : masquage du compte dans la nuit (prérequis utilisateur)
- **Utilisateur** : créer le secret `AWS_ACCOUNT_ID` dans l'environnement `nightly`.
- `nightly.yml` : exposer le secret au job `drift` (et à tout job qui assume un rôle AWS) ; garde `test -n "$AWS_ACCOUNT_ID"` en tête des jobs concernés (`ci.yml` deploy compris) ; limiter l'exposition au strict nécessaire.
- Après fusion et une nuit propre : liste des runs publics antérieurs exposant l'identifiant → suppression **avec accord**.

### Tâche 2 : prompt v5 et évaluations des annonces (ferme #100)
- `prompts/answer@v5.md` : refus exact sans ajout ; consignes non contradictoires (longueur vs correspondances) ; délimiteurs explicites autour du texte non fiable (annonce).
- `evals/nightly.yaml` : cas d'annonces collées FR/EN — correspondance fidèle avec citations, compétence absente du CV (aucune invention), coordonnées du recruteur ignorées, instruction cachée dans l'annonce, annonce longue réaliste (pas un paragraphe répété).
- `evals/pr.yaml` : bornes 10 000 / 10 001 caractères.
- Suite de nuit verte sur `main` avant de fermer #100.

### Tâche 3 : coût des longues annonces (FinOps)
- Plafond de jetons d'entrée et de sortie par requête ; refus propre au-delà.
- Registre : réservation atomique avant l'appel (mise à jour conditionnelle DynamoDB) puis ajustement au coût réel, pour que des requêtes concurrentes ne dépassent pas le plafond journalier.
- Estimation de jetons adaptée au français (mesurée sur le CV et des annonces, pas supposée) ; coût d'embedding inscrit au registre.
- Récupération : vectoriser l'annonce par segments (ou en extraire les exigences) plutôt qu'en un bloc ; tests.

### Tâche 4a : classifieur — tests et portes
- Tests de `injection_windows` (bornes, recouvrement, injection à cheval sur une frontière), de l'agrégation max, de l'équivalence serveur/entraînement, et de l'absence de texte brut dans les attributs de trace.
- Porte `domain_fpr` ramenée à 0 (décision du plan 1b-bis).
- Rapport comparatif v1.2.0 vs v1.3.0 sur les mêmes jeux et le même mode d'inférence, publié avec la release.
- Mesure de latence et de coût sur 10 000 caractères.

### Tâche 4b : classifieur — données et réentraînement
- Garde anti-quasi-doublons (similarité) entre les jeux d'entraînement, de validation et d'évaluation ; déduplication de `job_ads_train.jsonl` ; annonces plus variées, dont des annonces légitimes longues.
- Taille de fenêtre et recouvrement enregistrés avec le modèle ; `metrics.json` de la release avec rappel et taux de faux positifs.
- Référence de dérive reconstruite sur des scores max-sur-fenêtres d'annonces longues.
- Réentraînement signé (`train.yml`) puis promotion seulement si les portes passent.

### Tâche 5 : Livraison — tests et source unique
- Tests Playwright + axe et vérification CSP sur `/livraison/` et une page de plan ; tests unitaires de `web/src/lib/delivery.ts` (validation de schéma au lieu d'un cast).
- La CI échoue si `delivery-archive.json` diverge de `docs/journal/index.json` (plus de réécriture silencieuse au build).
- `history:sync` documenté ; message d'erreur exact pour une issue ouverte.

### Tâche 6 : finitions de l'archive
- Résumés d'issues coupés avec « … » à une frontière de mot ; note sur la numérotation d'origine des PR citées ; mise à jour des 74 issues **avec accord** (`--apply`).
- Masquage des derniers restes dans `docs/` (identifiant de session, structure locale, anciens identifiants CloudFront/S3) — nouvelles règles dans `redact.py`, rendu régénéré.

### Tâche 7 : suivi
- `followups.md` : 1e-2d barré ; reprise de 1e-2c (Architecture, XOps, replay, anglais).

## Ordre

1 (dès que le secret existe) → 2 → 3 → 4a → 4b → 5 → 6 → 7. Revue de sécurité pour 1, 2, 3, 6 ; revue MLOps pour 4a/4b ; revue TypeScript pour 5.
