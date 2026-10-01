# Journal de développement

Ce dossier publie l'historique complet du développement : pour chaque plan
(`docs/plans/`), le travail des sous-agents (implémentations, revues,
corrections) reconstitué mot pour mot depuis leurs journaux, avec les données
privées masquées.

Les fichiers sont générés par `python -m tools.devlog render` (voir
`tools/devlog/render.py`) ; ils ne sont pas édités à la main.

Le rapport retenu est le dernier message explicite `SubagentHandback` de
l'agent, lorsqu'il existe ; sinon, son dernier bloc de texte. Cela préserve
les rapports détaillés suivis d'un simple accusé de remise. Les itérations
antérieures d'un même agent ne sont pas toutes reconstituées.

## Génération

```sh
python -m tools.devlog render \
  --subagents <dossier des journaux de sous-agents> \
  --commit-map <commit-map de git-filter-repo> \
  --plans-dir docs/plans \
  --out docs/journal \
  [--repo .] [--assignments rattachements.json] \
  [--github-flow-plans 1e-2a,1e-2b,1e-2c,1e-2d,1e-3a] [--report <rapport local>]
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
  date) et les suspects (type, aperçu opaque, champ, plan, tâche, agent,
  description de l'agent) — jamais la valeur suspecte en clair : les
  descriptions qui y figurent passent par la même chaîne que le texte publié
  (un secret y interrompt aussi le rendu), puis chaque suspect y est remplacé
  par son aperçu opaque.
- `--assignments` : objet JSON `{"<identifiant d'agent>": "<plan>" | null}`
  qui prime sur le rattachement automatique, pour résoudre localement les
  agents « inconnu ». `null` écarte délibérément un agent (ni publié, ni
  signalé comme inconnu, compté parmi les « exclus »). Un plan inexistant est
  une erreur. Un agent non rattaché est exclu du journal.
- Après un rendu réussi en mémoire, les `*.md` de `--out` (sauf `README.md`)
  et `index.json` d'un rendu précédent sont supprimés avant l'écriture ; un
  rendu en échec laisse `--out` intact.
- `--github-flow-plans` : plans pour lesquels les mentions explicites
  `PR #N` / `issue #N` deviennent des liens ; les plans plus anciens précèdent
  la numérotation actuelle du dépôt.

## Issues historiques

Simulation locale (aucune requête GitHub) :

```sh
python -m tools.devlog.issues --index docs/journal/index.json --date 2026-09-28   --github-flow-plans 1e-2c,1e-2d,1e-3a
```

`--github-flow-plans` liste les plans menés avec de vraies issues et PR
GitHub : aucune issue historique n'est produite pour eux. Les plans 1e-2a et
1e-2b, publiés avant cette option, gardent leurs issues historiques. Les
sous-tâches (`Tâche 4b`) n'ont jamais d'issue historique.

La sortie JSON contient le titre, le corps masqué, les étiquettes et l'état
final attendu. Une issue est produite par tâche numérotée ; un rapport commun
à plusieurs tâches est identifié comme tel. Les revues finales et le travail
hors tâche restent consultables dans le journal.

Après validation de l'échantillon, `--apply` crée les issues et les ferme.
L'outil consulte toutes les pages des issues existantes, ouvertes ou fermées,
et évite les doublons par titre exact. Une création interrompue avant fermeture
est reprise au lancement suivant. Une issue existe brièvement ouverte entre
sa création et sa fermeture ; ne pas lancer deux publications simultanées.

## `<plan>.md` — structure

Un fichier par plan ayant au moins un agent rattaché :

- titre et objectif du plan, lien vers `../plans/<fichier>` ;
- une section par tâche, dans l'ordre numérique (`Tâche 0`, `Tâche 1`,
  `Tâche 4b` après `Tâche 4`, `Tâches 8-9` classée à 8…), puis `Revue finale`, puis `Hors tâche` ;
- dans chaque tâche, les sous-sections `Implémentation`, `Revues`,
  `Corrections`, `Autres` ;
- pour chaque agent : date de début (UTC, `AAAA-MM-JJ HH:MM`), type d'agent,
  modèle, description, verdict (revues), commits publiés cités par le rapport
  (SHA complets ou courts non ambigus, liens vers GitHub), liens de PR/issue
  le cas échéant, et le rapport masqué dans un bloc `<details>` replié. Les
  agents sont triés par date de début, puis par identifiant.
- Le HTML brut est neutralisé : hors blocs de code clôturés et portions de
  code en ligne, `<` devient `&lt;` (un `</details>` ou un `<script>` dans un
  rapport reste du texte) ; un bloc de code resté ouvert est refermé. Titre,
  objectif, type d'agent, modèle et description tiennent sur une seule ligne
  (sauts de ligne remplacés par des espaces).

## `index.json`

Données structurées du journal, pour un rendu ou une analyse tiers. Le
fichier est déterministe (aucun horodatage de génération) : deux rendus des
mêmes données produisent le même octet pour octet.

Contrat d'affichage : les chaînes d'`index.json` sont du texte brut, non
échappé ; le site les affiche comme texte React, jamais comme HTML (aucun
`dangerouslySetInnerHTML`, aucun rendu Markdown sans échappement).

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
| `tasks[].label` | `Tâche N`, `Tâche Nx` (sous-tâche), `Tâches N-M`, `Revue finale` ou `Hors tâche`. |
| `events[]` | Un par agent, trié par date de début puis par identifiant (non publié). |
| `events[].type` | Rôle : `implementation`, `review`, `fix` ou `other`. |
| `events[].date` | Début de l'agent, ISO 8601 UTC (`AAAA-MM-JJTHH:MM:SSZ`). |
| `events[].agent_type`, `events[].model` | Type d'agent et modèle. |
| `events[].description` | Description courte de l'agent, masquée. |
| `events[].summary` | Extrait du rapport masqué, limité à 600 caractères, sur une ligne ; utilisé dans les issues historiques. |
| `events[].verdict` | Revues seulement : `approuvé`, `corrections demandées` ou `non déterminé` ; `null` sinon. |
| `events[].commits` | SHA complets (40 caractères) des commits publiés cités par le rapport : SHA complet, ou SHA court (7 à 39 caractères) en contexte de commit et préfixe d'un seul SHA publié. |
| `events[].links` | URL de PR/issue explicitement citées (plans en flux GitHub seulement). |
