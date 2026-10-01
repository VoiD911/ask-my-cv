/**
 * Textes français de la page /xops ; la version anglaise (`xops-content.en.ts`) traduit les
 * mêmes disciplines, pratiques et libellés de preuves sans redéfinir les preuves. Chaque preuve est vérifiée au build par `scripts/sync-xops.mjs` : un `path` doit
 * exister dans le dépôt, une `anchor` doit se résoudre en fichier + ligne ; les URL externes
 * sont construites depuis `xops.json` (voir `xops.ts`), jamais écrites en dur.
 *
 * `[[SIGLE]]` insère un sigle défini dans le glossaire partagé.
 */
import type { Xops } from "./xops";

export type Status = "couvert" | "partiel";

export type External =
  | "modelRelease"
  | "modelCard"
  | "modelMetrics"
  | "releases"
  | "ghcrPackage"
  | "attestations"
  | "ciRuns"
  | "nightlyRuns"
  | "trainRuns"
  | "rules"
  | "dependabotPulls"
  | "site";

export type Proof =
  | { label: string; path: string }
  | { label: string; anchor: string }
  | { label: string; external: External }
  | { label: string; pull: number }
  | { label: string; internal: "/livraison/" | "/architecture/" | "#verifier-modele" | "#verifier-image" };

export type Practice = {
  id: string;
  title: string;
  claim: (x: Xops) => string;
  status: Status;
  /** Pour une case partielle : ce qui manque, dit franchement. */
  gap?: (x: Xops) => string;
  proofs: Proof[];
};

export type Discipline = { id: string; name: string; summary: string; practices: Practice[] };

const TRACING: Record<string, string> = { cloudwatch: "CloudWatch", langfuse: "Langfuse" };
const tracing = (x: Xops) => x.production.tracing.map((t) => TRACING[t] ?? t);

export const page = {
  title: "XOps — Interroge mon CV",
  description:
    "DevOps, DevSecOps, MLOps, LLMOps et FinOps appliqués à « Interroge mon CV » : chaque pratique renvoie à une preuve publique vérifiable (workflow, release signée, attestation, Terraform).",
  eyebrow: "Pratiques · preuves publiques vérifiables",
  heading: "XOps",
  lede: "Cinq disciplines d'exploitation, pratique par pratique. Chaque case dit ce qui est fait, s'il est couvert en entier ou en partie, et renvoie à une preuve que vous pouvez ouvrir ou vérifier vous-même : code, workflow, release signée, attestation.",
  generated:
    "Les liens, versions et identités de signature sont lus dans le dépôt à chaque build ; le build échoue si une preuve citée (fichier, job, étape, ressource) n'existe plus.",
  tocLabel: "Sommaire de la page",
  matrixTitle: "Vue d'ensemble",
  matrixCaption: "Pratiques par discipline, avec leur statut",
  matrixCols: { discipline: "Discipline", practices: "Pratiques", covered: "Couvertes", partial: "Partielles" },
  proofsLabel: "Preuves",
  gapLabel: "Ce qui manque :",
  statusText: { couvert: "Couvert", partiel: "Partiel" } satisfies Record<Status, string>,
  statsLabels: { disciplines: "Disciplines", practices: "Pratiques", proofs: "Preuves" },
  lineLabel: (line: number) => `ligne ${line}`,
  practicesLabel: (discipline: string) => `Pratiques ${discipline}`,
  matrixMeta: (covered: number, total: number) => `${covered}/${total} couverts`,
  matrixAlt: (items: { name: string; practices: { title: string; status: Status }[] }[]) =>
    items
      .map(
        (d) =>
          `${d.name} : ${d.practices.map((p) => `${p.title} (${p.status === "couvert" ? "couvert" : "partiel"})`).join(", ")}`,
      )
      .join(". "),
};

export const verify = {
  title: "Vérifier soi-même",
  intro:
    "Ces commandes n'exigent aucun accès au projet : elles interrogent les artefacts publics et le journal de transparence Sigstore. Il faut GitHub CLI (gh) et cosign.",
  model: {
    id: "verifier-modele",
    title: (tag: string) => `Classifieur promu (${tag})`,
    detail:
      "Télécharge le modèle et son paquet de signature depuis la release, vérifie que la signature a été produite par le workflow train sur main, puis la provenance SLSA.",
  },
  image: {
    id: "verifier-image",
    title: "Image de l'API (GHCR)",
    detail:
      "L'image publique est étiquetée par le commit de main qui l'a déployée. La première ligne prend le dernier commit de main ; si son déploiement n'est pas terminé, choisir une étiquette sur la page du paquet.",
  },
  commandLabel: "Commandes à copier",
  commandsAria: (title: string) => `Commandes à copier : ${title}`,
};

export type XopsPageText = typeof page;
export type XopsVerifyText = typeof verify;

export const disciplines: Discipline[] = [
  {
    id: "devops",
    name: "DevOps",
    summary: "Livrer souvent, sans casser : tout passe par la CI, l'infrastructure est du code, la production est surveillée.",
    practices: [
      {
        id: "integration-continue",
        title: "Intégration continue",
        claim: () =>
          "Chaque pull request lance cinq jobs en parallèle (sécurité, tests, évaluations, site, Terraform) ; le déploiement attend leur succès à tous.",
        status: "couvert",
        proofs: [
          { label: "ci.yml · job deploy (needs)", anchor: "job:ci.yml:deploy" },
          { label: "Derniers runs de ci", external: "ciRuns" },
        ],
      },
      {
        id: "iac",
        title: "Infrastructure as Code",
        claim: () =>
          "Toute l'infrastructure AWS est en Terraform ([[IaC]]), en deux couches (socle et production) ; format et validation vérifiés à chaque PR, application (terraform apply) lancée à la main.",
        status: "couvert",
        proofs: [
          { label: "infra/prod", path: "infra/prod" },
          { label: "infra/bootstrap/main.tf", path: "infra/bootstrap/main.tf" },
          { label: "ci.yml · job terraform", anchor: "job:ci.yml:terraform" },
        ],
      },
      {
        id: "deploiement",
        title: "Déploiement et retour arrière",
        claim: () =>
          "Sur main, l'image est reconstruite, signée, accompagnée de son SBOM et de sa provenance, vérifiée, puis déployée par ce digest exact ; test de fumée sur la production, puis retour automatique à l'image précédente de la Lambda s'il échoue.",
        status: "partiel",
        gap: () =>
          "Pas de déploiement progressif (canary) : la nouvelle version remplace l'ancienne d'un coup ; l'image déployée est reconstruite, pas promue depuis celle des tests ; le retour arrière ne concerne que la Lambda, pas le site statique.",
        proofs: [
          { label: "ci.yml · Déployer (par digest)", anchor: "step:ci.yml:deploy:Déployer (par digest)" },
          { label: "ci.yml · Retour arrière", anchor: "step:ci.yml:deploy:Retour arrière" },
          { label: "smoke_prod.py", path: "infra/scripts/smoke_prod.py" },
        ],
      },
      {
        id: "gouvernance",
        title: "Branche main protégée",
        claim: () =>
          "Ensemble de règles GitHub sur main : pull request obligatoire, cinq vérifications requises, ni push forcé ni suppression.",
        status: "couvert",
        proofs: [
          { label: "Règles du dépôt", external: "rules" },
          { label: "Environnements limités à main (plan)", path: "docs/plans/2026-09-26-ask-my-cv-1e-2a-public-proofs.md" },
        ],
      },
      {
        id: "observabilite",
        title: "Observabilité",
        claim: (x) =>
          `Traces OpenTelemetry de chaque étape (${tracing(x).join(", ")}), métriques du garde-fou et alarme CloudWatch envoyée par courriel. Tableau de bord privé de l'usage réel (trafic interne exclu, sans texte de question) et résumé hebdomadaire par courriel.`,
        status: "couvert",
        proofs: [
          { label: "telemetry.py", path: "src/ask_my_cv/telemetry.py" },
          { label: "observability.tf · alarme", anchor: "tf:aws_cloudwatch_metric_alarm.guardrail_errors" },
          { label: "dashboard.tf · tableau de bord", anchor: "tf:aws_cloudwatch_dashboard.usage" },
          { label: "weekly.yml · résumé", anchor: "job:weekly.yml:summary" },
        ],
      },
      {
        id: "journal",
        title: "Journal de développement public",
        claim: () =>
          "Plans, tâches, revues et corrections publiés au fil du projet, chacun relié à sa pull request.",
        status: "couvert",
        proofs: [
          { label: "Onglet Livraison", internal: "/livraison/" },
          { label: "docs/journal", path: "docs/journal" },
        ],
      },
    ],
  },
  {
    id: "devsecops",
    name: "DevSecOps",
    summary: "La sécurité est vérifiée par la CI à chaque changement, jusqu'à la signature de ce qui part en production.",
    practices: [
      {
        id: "secrets-code",
        title: "Secrets et code",
        claim: () =>
          "gitleaks parcourt tout l'historique git, semgrep analyse le code ; un constat bloque la pull request.",
        status: "couvert",
        proofs: [
          { label: "gitleaks", anchor: "step:ci.yml:security:gitleaks" },
          { label: "semgrep", anchor: "step:ci.yml:security:semgrep" },
        ],
      },
      {
        id: "dependances",
        title: "Dépendances",
        claim: (x) =>
          `osv-scanner vérifie les vulnérabilités connues ; Dependabot propose chaque semaine les mises à jour (${x.dependabot.join(", ")}).`,
        status: "couvert",
        proofs: [
          { label: "osv-scanner", anchor: "step:ci.yml:security:osv-scanner" },
          { label: "dependabot.yml", path: ".github/dependabot.yml" },
          { label: "PR Dependabot", external: "dependabotPulls" },
        ],
      },
      {
        id: "iac-image",
        title: "Terraform et image",
        claim: () =>
          "trivy analyse la configuration Terraform et l'image Docker ; les vulnérabilités élevées et critiques bloquent (pour l'image, celles qui ont un correctif).",
        status: "couvert",
        proofs: [
          { label: "trivy config", anchor: "step:ci.yml:security:trivy config" },
          { label: "trivy image", anchor: "step:ci.yml:test:Scan de l'image" },
          { label: ".trivyignore.yaml (exceptions justifiées)", path: ".trivyignore.yaml" },
        ],
      },
      {
        id: "chaine-approvisionnement",
        title: "Chaîne d'approvisionnement",
        claim: () =>
          "L'image est signée avec [[cosign]] (sans clé), accompagnée d'une provenance [[SLSA]] et d'un [[SBOM]] CycloneDX, tout vérifié avant le déploiement. Vous pouvez le vérifier aussi.",
        status: "couvert",
        proofs: [
          { label: "Commandes de vérification", internal: "#verifier-image" },
          { label: "Paquet GHCR", external: "ghcrPackage" },
          { label: "Attestations", external: "attestations" },
          { label: "ci.yml · vérification avant déploiement", anchor: "step:ci.yml:deploy:Vérifier signature et attestation" },
        ],
      },
      {
        id: "identite",
        title: "Identités sans secret",
        claim: () =>
          "GitHub Actions obtient des identifiants AWS temporaires par [[OIDC]] ; un rôle au moindre privilège par usage (déploiement, nuit), chacun limité à son environnement GitHub.",
        status: "couvert",
        proofs: [
          { label: "Fournisseur OIDC", anchor: "tf:aws_iam_openid_connect_provider.github" },
          { label: "Rôle de déploiement", anchor: "tf:aws_iam_role.deploy" },
          { label: "Rôle de nuit", anchor: "tf:aws_iam_role.nightly" },
        ],
      },
      {
        id: "csp",
        title: "Site durci",
        claim: () =>
          "Politique de sécurité du contenu stricte : seuls les scripts dont l'empreinte est calculée au build s'exécutent ; un test navigateur le vérifie sur chaque page.",
        status: "couvert",
        proofs: [
          { label: "scripts/csp.mjs", path: "web/scripts/csp.mjs" },
          { label: "e2e/csp.spec.ts", path: "web/e2e/csp.spec.ts" },
        ],
      },
    ],
  },
  {
    id: "mlops",
    name: "MLOps",
    summary: "Le détecteur d'injection est un vrai modèle : données versionnées, porte d'évaluation, release signée, promotion relue.",
    practices: [
      {
        id: "entrainement",
        title: "Entraînement reproductible",
        claim: () =>
          "Données générées depuis une graine versionnée ; l'entraînement tourne dans un workflow, sur main uniquement.",
        status: "couvert",
        proofs: [
          { label: "train.yml · garde main", anchor: "step:train.yml:train:branche autre que main" },
          { label: "ml/job_ads.py", path: "ml/job_ads.py" },
          { label: "ml/train.py", path: "ml/train.py" },
          { label: "Runs de train", external: "trainRuns" },
        ],
      },
      {
        id: "porte",
        title: "Porte d'évaluation",
        claim: () =>
          "Un modèle n'est publié que s'il passe les seuils de rappel et de faux positifs ; chaque changement de seuil est justifié par des mesures.",
        status: "couvert",
        proofs: [
          { label: "ml/gates.yaml", path: "ml/gates.yaml" },
          { label: "ml/compare.py", path: "ml/compare.py" },
        ],
      },
      {
        id: "registre",
        title: "Registre de modèles signés",
        claim: (x) =>
          `Chaque version est une release ${x.model.tag.replace(x.model.version, "v*")} : modèle [[ONNX]], signature [[cosign]] et provenance [[SLSA]], vérifiables par tous.`,
        status: "couvert",
        proofs: [
          { label: "Release promue", external: "modelRelease" },
          { label: "Toutes les releases", external: "releases" },
          { label: "Commandes de vérification", internal: "#verifier-modele" },
        ],
      },
      {
        id: "fiche",
        title: "Fiche du modèle et métriques",
        claim: (x) => `La release ${x.model.version} publie sa fiche (données, limites, usage) et ses métriques d'évaluation.`,
        status: "couvert",
        proofs: [
          { label: "model_card.md", external: "modelCard" },
          { label: "metrics.json", external: "modelMetrics" },
        ],
      },
      {
        id: "promotion",
        title: "Promotion et intégrité",
        claim: (x) =>
          `Le modèle servi (${x.model.version}) est choisi par une pull request dans models/prod.json ; la CI vérifie sa signature, le service son empreinte avant de le charger.`,
        status: "couvert",
        proofs: [
          { label: "models/prod.json", path: "models/prod.json" },
          { label: "ci.yml · signature du modèle", anchor: "step:ci.yml:test:Vérifier la signature du modèle" },
          { label: "Contrôle d'empreinte", anchor: "text:src/ask_my_cv/onnx_detector.py#class ModelIntegrityError" },
        ],
      },
      {
        id: "derive",
        title: "Surveillance de la dérive",
        claim: () =>
          "Chaque nuit, un job compare les scores de production des sept derniers jours à la référence de la release ([[PSI]]) ; un échec ouvre une issue.",
        status: "partiel",
        gap: () =>
          "La mesure mélange encore les versions du modèle et les types de texte (questions, annonces) : correctif en cours.",
        proofs: [
          { label: "nightly.yml · job drift", anchor: "job:nightly.yml:drift" },
          { label: "ml/drift.py", path: "ml/drift.py" },
          { label: "PR #125 (correctif)", pull: 125 },
          { label: "Runs de nuit", external: "nightlyRuns" },
        ],
      },
    ],
  },
  {
    id: "llmops",
    name: "LLMOps",
    summary: "Le [[LLM]] est traité comme une dépendance de production : prompts versionnés, évalués, attaqués et tracés.",
    practices: [
      {
        id: "prompts",
        title: "Prompts versionnés",
        claim: (x) =>
          `Chaque prompt est un fichier versionné (${x.prompts.versions.length} versions) ; la production sert ${x.prompts.current}, choisi dans la configuration.`,
        status: "couvert",
        proofs: [
          { label: "prompts/", path: "prompts" },
          { label: "settings.aws.yaml · prompt_path", anchor: "text:settings.aws.yaml#prompt_path:" },
        ],
      },
      {
        id: "evaluations",
        title: "Évaluations à chaque PR",
        claim: () =>
          "promptfoo rejoue une suite de cas (langue, refus, fuites, longueur) contre l'API locale avant toute fusion ; parcours navigateur en plus.",
        status: "couvert",
        proofs: [
          { label: "evals/pr.yaml", path: "evals/pr.yaml" },
          { label: "ci.yml · suite promptfoo", anchor: "step:ci.yml:evals:Suite promptfoo" },
        ],
      },
      {
        id: "red-team",
        title: "Red team de nuit et juge LLM",
        claim: () =>
          "Chaque nuit, des attaques (extraction des consignes, instructions cachées dans des annonces) visent la vraie production ; les réponses sont notées par un juge LLM.",
        status: "couvert",
        proofs: [
          { label: "evals/nightly.yaml", path: "evals/nightly.yaml" },
          { label: "evals/judge.js", path: "evals/judge.js" },
          { label: "nightly.yml · job redteam", anchor: "job:nightly.yml:redteam" },
          { label: "Runs de nuit", external: "nightlyRuns" },
        ],
      },
      {
        id: "garde-fous",
        title: "Garde-fous d'entrée et de sortie",
        claim: () =>
          "Classifieur d'injection, puis Bedrock Guardrails sur les longues annonces : un échec isolé garde la décision du classifieur, un disjoncteur refuse les annonces si les échecs se répètent. En sortie, fuite du prompt détectée par jeton canari et citation des passages du CV exigée ([[RAG]]), sans vérification de leur contenu.",
        status: "couvert",
        proofs: [
          { label: "onnx_detector.py", path: "src/ask_my_cv/onnx_detector.py" },
          { label: "guardrail.py", path: "src/ask_my_cv/guardrail.py" },
          { label: "output_guard.py", path: "src/ask_my_cv/output_guard.py" },
          { label: "guardrail.tf", path: "infra/prod/guardrail.tf" },
        ],
      },
      {
        id: "tracage",
        title: "Traçage des appels",
        claim: (x) =>
          `Chaque question produit une trace par étape (statut, durée, jetons consommés), exportée vers ${tracing(x).join(" et ")}.`,
        status: "couvert",
        proofs: [
          { label: "telemetry.py", path: "src/ask_my_cv/telemetry.py" },
          { label: "settings.aws.yaml · tracing", anchor: "text:settings.aws.yaml#tracing:" },
        ],
      },
      {
        id: "repli",
        title: "Délais et repli de modèle",
        claim: () =>
          "Délais par étape et pour le premier jeton ; une chaîne de repli essaie le modèle suivant si un fournisseur échoue.",
        status: "partiel",
        gap: (x) =>
          `En production, la chaîne de repli ne compte qu'un modèle (${x.production.fallbackChain.join(", ")}) : une panne du fournisseur se traduit par une erreur propre, pas par une bascule.`,
        proofs: [
          { label: "pipeline.py · repli", anchor: "text:src/ask_my_cv/pipeline.py#tous les fournisseurs ont échoué" },
          { label: "settings.aws.yaml · fallback_chain", anchor: "text:settings.aws.yaml#fallback_chain:" },
        ],
      },
    ],
  },
  {
    id: "finops",
    name: "FinOps",
    summary: "Un site public qui appelle un LLM doit avoir un coût borné, mesuré et alerté.",
    practices: [
      {
        id: "plafond",
        title: "Plafond de dépense quotidien",
        claim: (x) =>
          `Un registre DynamoDB compte la dépense du jour et coupe à ${x.production.dailyCapUsd} $ US ; chaque visiteur a ${x.production.perVisitorLimit} questions par ${x.production.visitorWindowS / 3600} h.`,
        status: "couvert",
        proofs: [
          { label: "budget.py", path: "src/ask_my_cv/budget.py" },
          { label: "Registre DynamoDB", anchor: "text:src/ask_my_cv/aws/dynamo.py#class DynamoLedger" },
          { label: "settings.aws.yaml · daily_cap_usd", anchor: "text:settings.aws.yaml#daily_cap_usd:" },
        ],
      },
      {
        id: "cout-requete",
        title: "Coût par question",
        claim: () =>
          "Le coût est calculé à chaque réponse d'après les jetons consommés et le tarif du modèle, puis affiché dans l'interface.",
        status: "couvert",
        proofs: [
          { label: "llm.py · tarif", anchor: "text:src/ask_my_cv/llm.py#input_per_mtok" },
          { label: "settings.aws.yaml · tarifs", anchor: "text:settings.aws.yaml#input_per_mtok:" },
          { label: "Démo en direct", external: "site" },
        ],
      },
      {
        id: "aws-budgets",
        title: "Budget AWS et alertes",
        claim: (x) =>
          `Filet de sécurité : AWS Budgets mensuel (${x.budget.monthlyUsdDefault} $ US par défaut), alertes par courriel à 50 % réel et 100 % prévu. Coût mesuré par jour et facture du mois contre le budget sur le tableau de bord, coût de la semaine dans le résumé du lundi.`,
        status: "couvert",
        proofs: [
          { label: "observability.tf · budget", anchor: "tf:aws_budgets_budget.monthly" },
          { label: "variables.tf", anchor: "text:infra/prod/variables.tf#monthly_budget_usd" },
          { label: "weekly_summary.py", path: "infra/scripts/weekly_summary.py" },
        ],
      },
      {
        id: "paiement-usage",
        title: "Paiement à l'usage",
        claim: () =>
          "Aucun serveur allumé en permanence : Lambda, DynamoDB à la demande, anciennes images purgées du registre.",
        status: "couvert",
        proofs: [
          { label: "lambda.tf", path: "infra/prod/lambda.tf" },
          { label: "data.tf · à la demande", anchor: "text:infra/prod/data.tf#PAY_PER_REQUEST" },
          { label: "Purge ECR", anchor: "tf:aws_ecr_lifecycle_policy.api" },
        ],
      },
    ],
  },
];
