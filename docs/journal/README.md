# Journal de développement

Ce dossier publie l'historique complet du développement : pour chaque plan
(`docs/plans/`), le travail des sous-agents (implémentations, revues,
corrections) reconstitué mot pour mot depuis leurs journaux, avec les données
privées masquées.

Les fichiers sont générés par `python -m tools.devlog render` (voir
`tools/devlog/render.py`) ; ils ne sont pas édités à la main.

## Génération

```sh
python -m tools.devlog render \
  --subagents <dossier des journaux de sous-agents> \
  --commit-map <commit-map de git-filter-repo> \
  --plans-dir docs/plans \
  --out docs/journal \
  [--repo .] [--assignments rattachements.json] \
  [--github-flow-plans 1e-2a,1e-2b] [--report <rapport local>]
```

- La configuration de masquage est lue par `load_config(require_account_ids=True)`
  (environnement, puis `~/.claude/devlog-private/redact.json`) : sans
  identifiant de compte AWS configuré, le rendu refuse de démarrer.
- Chaque texte publié (rapport, description, titre, objectif, type d'agent,
  modèle) passe par : traduction des SHA d'avant la réécriture d'historique →
  masquage (`redact`) → détection bloquante des secrets (`assert_no_secret`)
  → détection heuristique (`find_suspects`).
- Un secret détecté interrompt tout le rendu (code de sortie 2) : aucun
  fichier n'est écrit, pas même partiellement, et la valeur n'est jamais
  affichée.
- Les consignes données aux sous-agents ne sont **jamais** publiées : elles
  servent seulement à classer chaque agent (rôle, plan, tâche). Les
  identifiants d'agent ne sont pas publiés non plus.
- Le rapport local (`--report`, par défaut
  `~/.claude/devlog-private/render-report.json`, refusé s'il se trouve dans le
  dépôt) liste les agents non rattachés à un plan (identifiant, description,
  date) et les suspects (type, aperçu opaque, champ, plan, tâche, agent) —
  jamais la valeur suspecte en clair.
- `--assignments` : objet JSON `{"<identifiant d'agent>": "<plan>"}` qui prime
  sur le rattachement automatique, pour résoudre localement les agents
  « inconnu ». Un agent non rattaché est exclu du journal.
- `--github-flow-plans` : plans pour lesquels les mentions explicites
  `PR #N` / `issue #N` deviennent des liens ; les plans plus anciens précèdent
  la numérotation actuelle du dépôt.

## `<plan>.md`

Un fichier par plan ayant au moins un agent rattaché :

- titre et objectif du plan, lien vers `../plans/<fichier>` ;
- une section par tâche, dans l'ordre numérique (`Tâche 0`, `Tâche 1`,
  `Tâches 8-9` classée à 8…), puis `Revue finale`, puis `Hors tâche` ;
- dans chaque tâche, les sous-sections `Implémentation`, `Revues`,
  `Corrections`, `Autres` ;
- pour chaque agent : date de début (UTC, `AAAA-MM-JJ HH:MM`), type d'agent,
  modèle, description, verdict (revues), commits publiés cités par le rapport
  (liens vers GitHub), liens de PR/issue le cas échéant, et le rapport masqué
  dans un bloc `<details>` replié. Les agents sont triés par date de début,
  puis par identifiant.

## `index.json`

Données structurées du journal, pour un rendu ou une analyse tiers. Le
fichier est déterministe (aucun horodatage de génération) : deux rendus des
mêmes données produisent le même octet pour octet.

```json
{
  "version": 1,
  "repository": "VoiD911/ask-my-cv",
  "plans": [
    {
      "id": "1e-2b",
      "title": "Titre du plan",
      "goal": "Objectif du plan",
      "plan_doc": "docs/plans/AAAA-MM-JJ-ask-my-cv-1e-2b-….md",
      "journal": "docs/journal/1e-2b.md",
      "tasks": [
        {
          "label": "Tâche 3",
          "events": [
            {
              "type": "review",
              "date": "2026-09-27T09:00:00Z",
              "agent_type": "general-purpose",
              "model": "…",
              "description": "Review Task 3 spec+quality",
              "verdict": "approuvé",
              "commits": ["<sha de 40 caractères>"],
              "links": ["https://github.com/VoiD911/ask-my-cv/pull/20"]
            }
          ]
        }
      ]
    }
  ]
}
```

| Champ | Description |
| --- | --- |
| `version` | Version du schéma (entier, actuellement `1`). |
| `repository` | Dépôt GitHub `propriétaire/nom`. |
| `plans[]` | Plans ayant au moins un agent, dans l'ordre chronologique des plans. |
| `plans[].id` | Identifiant du plan (`1b`, `1b-bis`, `1c-1a`, `1e-2b`…). |
| `plans[].title`, `plans[].goal` | Titre (première ligne `# `) et objectif (`**Goal:**`) du plan, masqués. |
| `plans[].plan_doc`, `plans[].journal` | Chemins, depuis la racine du dépôt, du plan et de son journal. |
| `tasks[]` | Même ordre que dans le Markdown. |
| `tasks[].label` | `Tâche N`, `Tâches N-M`, `Revue finale` ou `Hors tâche`. |
| `events[]` | Un par agent, trié par date de début puis par identifiant (non publié). |
| `events[].type` | Rôle : `implementation`, `review`, `fix` ou `other`. |
| `events[].date` | Début de l'agent, ISO 8601 UTC (`AAAA-MM-JJTHH:MM:SSZ`). |
| `events[].agent_type`, `events[].model` | Type d'agent et modèle. |
| `events[].description` | Description courte de l'agent, masquée. |
| `events[].verdict` | Revues seulement : `approuvé`, `corrections demandées` ou `non déterminé` ; `null` sinon. |
| `events[].commits` | SHA complets (40 caractères) de commits publiés cités par le rapport. |
| `events[].links` | URL de PR/issue explicitement citées (plans en flux GitHub seulement). |
