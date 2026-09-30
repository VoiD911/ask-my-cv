/**
 * Textes français de la page /architecture (version anglaise : `architecture-content.en.ts`,
 * même forme imposée par le type `ArchitectureContent`). Les schémas, eux, viennent de
 * `architecture.json` (sources réelles). Les chemins `path` ne sont écrits qu'ici :
 * `scripts/sync-xops.mjs` vérifie qu'ils existent dans le dépôt.
 */
import type { InfraRole } from "./architecture";

export type SourceLink = { label: string; path: string };

export const page = {
  title: "Architecture — Interroge mon CV",
  description:
    "Comment « Interroge mon CV » est construit, vérifié, déployé et surveillé : chemin d'une requête, infrastructure AWS, chaîne CI/CD et cycle de vie du modèle.",
  eyebrow: "Vue d'ensemble · schémas générés depuis le code",
  heading: "Architecture",
  lede: "Quatre schémas pour comprendre en quelques minutes comment une question devient une réponse ([[RAG]]), sur quelle infrastructure, avec quelles vérifications avant la mise en production, et comment le modèle de sécurité est entraîné puis surveillé.",
  generated:
    "Chaque schéma est régénéré à chaque build depuis les fichiers du dépôt (workflows, Terraform, pipeline Python) ; la CI refuse une page qui ne correspond plus au code.",
  tocLabel: "Sommaire de la page",
  sourcesLabel: "Fichiers source",
  readingLabel: "Lecture du schéma",
  statsLabels: { stages: "Étapes", resources: "Ressources", jobs: "Jobs CI/CD" },
  requestMeta: (stages: number, version: string) => `${stages} étapes · ONNX ${version}`,
  flowIn: "Aller : du navigateur à la Lambda",
  flowStages: "Étapes du pipeline, dans l'ordre",
  flowOut: "Retour : flux vers l'interface",
  infraBoardTitle: "Terraform · infra/",
  resourcesMeta: (count: number) => `${count} ressources`,
  workflowTitle: (name: string) => `workflow ${name}`,
  modelsBoardTitle: "Modèles",
  stepsCount: (count: number) => `${count} étapes`,
};

/** Rôle de chaque étape du pipeline (clés = PIPELINE_STAGES de stages.py). */
export const stageText: Record<string, { label: string; detail: string }> = {
  reception: { label: "Réception", detail: "Normalisation Unicode, longueur, modèle autorisé" },
  quota: { label: "Quota et budget", detail: "Registre DynamoDB : limite par visiteur, plafond du jour" },
  injection: { label: "Détecteur d'injection", detail: "Classifieur ONNX, puis Bedrock Guardrails sur les annonces" },
  embedding: { label: "Embedding", detail: "Vecteur de la question (Bedrock Titan)" },
  retrieval: { label: "Recherche", detail: "Passages du CV les plus proches (vecteurs DynamoDB)" },
  prompt: { label: "Prompt", detail: "Gabarit versionné, langue détectée, jeton canari" },
  llm: { label: "LLM", detail: "Claude sur Amazon Bedrock, en flux, avec repli" },
  output_guard: { label: "Garde-fou de sortie", detail: "Fuite du prompt, données personnelles, ancrage au CV" },
};

export const request = {
  id: "requete",
  title: "Chemin d'une requête",
  paragraphs: [
    "Le site est un export statique servi par CloudFront ; la même distribution relaie les appels /api/* vers une fonction Lambda. La Lambda exécute une API FastAPI grâce au Lambda Web Adapter, en mode flux : la réponse part vers le navigateur au fil de l'eau ([[SSE]]).",
    "Chaque question traverse les étapes ci-dessous, dans cet ordre. Les portes de sécurité passent avant tout appel payant : si le quota est dépassé ou si le classifieur d'injection bloque, rien n'est envoyé au [[LLM]].",
    "Chaque étape émet un événement de début et de fin ; c'est ce flux qui anime le circuit en direct sur la page d'accueil. Les coûts sont enregistrés dans un registre DynamoDB qui fait respecter un plafond de dépense quotidien.",
  ],
  edgeIn: [
    { ref: "IN", label: "Navigateur", detail: "Question + modèle choisi" },
    { ref: "CDN", label: "CloudFront", detail: "Site statique + /api/*" },
    { ref: "λ", label: "Lambda FastAPI", detail: "Lambda Web Adapter, réponse en flux" },
  ],
  edgeOut: [
    { ref: "SSE", label: "Flux SSE", detail: "Événements d'étape, jetons, réponse" },
    { ref: "UI", label: "Interface", detail: "Circuit, réponse, sources, coût" },
  ],
  boardTitle: "Pipeline",
  guardrailNote: (minChars: number) =>
    `Seconde opinion Bedrock Guardrails pour les textes collés de ${minChars} caractères ou plus (annonces), seulement si le classifieur ne bloque pas déjà.`,
  modelNote: (version: string) => `Classifieur d'injection promu : ${version}.`,
  alt: (stages: string[]) =>
    `Le navigateur envoie la question à CloudFront, qui la relaie à la Lambda FastAPI. Le pipeline enchaîne ${stages.length} étapes : ${stages.join(", ")}. Les événements repartent en flux SSE vers l'interface.`,
  sources: [
    { label: "pipeline.py", path: "src/ask_my_cv/pipeline.py" },
    { label: "stages.py (ordre des étapes)", path: "src/ask_my_cv/stages.py" },
    { label: "app.py (API FastAPI)", path: "src/ask_my_cv/app.py" },
    { label: "Dockerfile (Lambda Web Adapter)", path: "Dockerfile" },
    { label: "cdn.tf", path: "infra/prod/cdn.tf" },
  ] satisfies SourceLink[],
};

export const roleText: Record<InfraRole, { label: string; detail: string }> = {
  edge: { label: "Bordure", detail: "CDN, certificat TLS, site statique privé" },
  compute: { label: "Calcul", detail: "Fonction Lambda en conteneur et son registre" },
  data: { label: "Données", detail: "Vecteurs du CV, registre des dépenses, état Terraform" },
  ai: { label: "IA", detail: "Garde-fou Bedrock des annonces" },
  security: { label: "Sécurité et identité", detail: "OIDC GitHub, rôles au moindre privilège, chiffrement" },
  observability: { label: "Observabilité", detail: "Journaux, métriques, alarmes, alertes" },
  cost: { label: "Coûts", detail: "Budget mensuel avec alertes" },
};

export const infra = {
  id: "infrastructure",
  title: "Infrastructure",
  paragraphs: [
    "Toute l'infrastructure AWS est décrite en Terraform ([[IaC]]), en deux couches : un socle (état Terraform, identité OIDC pour GitHub Actions, rôles de déploiement) et la production (CDN, Lambda, données, garde-fou, observabilité).",
    "Aucune clé d'accès longue durée : GitHub obtient des identifiants temporaires par [[OIDC]], avec un rôle distinct pour le déploiement et pour les tests de nuit. Le bucket du site n'est lisible que par CloudFront.",
    "Les ressources sont regroupées ci-dessous par rôle. Un budget mensuel et des alarmes CloudWatch préviennent par courriel en cas de dérive des coûts ou d'erreurs du garde-fou.",
  ],
  alt: (groups: { label: string; count: number }[]) =>
    `Ressources Terraform par rôle : ${groups.map((g) => `${g.label} (${g.count})`).join(", ")}.`,
  sources: [
    { label: "infra/bootstrap/main.tf", path: "infra/bootstrap/main.tf" },
    { label: "infra/prod/cdn.tf", path: "infra/prod/cdn.tf" },
    { label: "infra/prod/lambda.tf", path: "infra/prod/lambda.tf" },
    { label: "infra/prod/data.tf", path: "infra/prod/data.tf" },
    { label: "infra/prod/guardrail.tf", path: "infra/prod/guardrail.tf" },
    { label: "infra/prod/observability.tf", path: "infra/prod/observability.tf" },
  ] satisfies SourceLink[],
};

export const jobText: Record<string, string> = {
  security: "Scanners : secrets, code, dépendances, IaC",
  test: "Lint, types, tests Python, image Docker scannée + SBOM",
  evals: "Évaluations promptfoo et parcours e2e contre l'API locale",
  web: "Lint, tests, build, CSP, Lighthouse",
  terraform: "Format et validation Terraform",
  deploy: "Image signée, déploiement par digest, test de fumée, retour arrière",
  redteam: "Red team sur la production, notée par un juge LLM",
  drift: "Dérive du classifieur (PSI sur 7 jours)",
  report: "Ouvre une issue si la nuit échoue",
  train: "Données, entraînement, porte, signature, release",
  "lambda-adapter": "Copie à l'identique du Lambda Web Adapter vers GHCR",
};

export const triggerText: Record<string, string> = {
  push: "push sur main",
  pull_request: "pull request",
  schedule: "chaque nuit",
  workflow_dispatch: "manuel",
};

export const delivery = {
  id: "livraison-continue",
  title: "Du code à la production",
  paragraphs: [
    "En [[CI/CD]], chaque pull request passe par cinq jobs en parallèle : scanners de sécurité, tests Python et image Docker, évaluations du LLM et parcours navigateur, site web (tests, CSP, Lighthouse) et Terraform. Le déploiement n'attend rien d'autre que leur succès à tous.",
    "Sur main, l'image est reconstruite, signée avec Sigstore ([[cosign]], sans clé), accompagnée d'une provenance [[SLSA]] et d'un [[SBOM]], puis vérifiée avant d'être déployée par son digest : signature, SBOM et provenance visent ce digest exact.",
    "Un test de fumée interroge ensuite la production ; s'il échoue, la version précédente est restaurée automatiquement. D'autres workflows tournent à côté : la red team de nuit, l'entraînement du modèle et un miroir d'image.",
  ],
  stepsLabel: (id: string) => `Étapes du job ${id}`,
  layerLabel: (n: number) => (n === 0 ? "En parallèle" : `Puis (après ${n} niveau${n > 1 ? "x" : ""})`),
  alt: (jobs: string[], deploy: string[]) =>
    `Le workflow ci lance en parallèle ${jobs.join(", ")} ; le job deploy attend ${deploy.join(", ")}.`,
  sources: [
    { label: "ci.yml", path: ".github/workflows/ci.yml" },
    { label: "nightly.yml", path: ".github/workflows/nightly.yml" },
    { label: "train.yml", path: ".github/workflows/train.yml" },
    { label: "mirror.yml", path: ".github/workflows/mirror.yml" },
    { label: "smoke_prod.py", path: "infra/scripts/smoke_prod.py" },
  ] satisfies SourceLink[],
};

export const lifecycle = {
  id: "cycle-du-modele",
  title: "Cycle de vie du modèle",
  paragraphs: [
    "Le détecteur d'injection est un petit modèle [[ONNX]] entraîné pour ce projet. Le workflow train génère des annonces d'entraînement à partir d'une graine versionnée, entraîne, puis applique une porte d'évaluation : seuils de rappel et de faux positifs définis dans gates.yaml.",
    "Le modèle retenu est signé (Sigstore) et publié en release. Il n'est utilisé qu'une fois promu dans models/prod.json, par une pull request relue ; la CI et le déploiement vérifient son empreinte et sa signature.",
    "En production, un job de nuit mesure la dérive de ses scores ([[PSI]]). Côté [[LLM]], les prompts sont versionnés, chaque pull request est évaluée avec promptfoo, et une red team nocturne attaque la production, notée par un juge LLM.",
  ],
  classifierTitle: "Classifieur d'injection (ONNX)",
  llmTitle: "LLM et prompts",
  classifierSteps: (version: string) => [
    { ref: "M1", label: "Données", detail: "Annonces générées, graine versionnée" },
    { ref: "M2", label: "Entraînement signé", detail: "workflow train, sur main uniquement" },
    { ref: "M3", label: "Porte d'évaluation", detail: "Rappel et faux positifs (gates.yaml)" },
    { ref: "M4", label: "Release + cosign", detail: "Modèle, signature, provenance, fiche" },
    { ref: "M5", label: "Promotion", detail: `models/prod.json → ${version}` },
    { ref: "M6", label: "Surveillance", detail: "Dérive PSI chaque nuit" },
  ],
  llmSteps: (prompt: string, count: number) => [
    { ref: "P1", label: "Prompt versionné", detail: `${prompt} (${count} versions)` },
    { ref: "P2", label: "Évaluations PR", detail: "promptfoo à chaque pull request" },
    { ref: "P3", label: "Red team de nuit", detail: "Production, notée par un juge LLM" },
  ],
  alt: (version: string, prompt: string) =>
    `Classifieur : données, entraînement signé, porte d'évaluation, release signée, promotion (${version}), surveillance de dérive. LLM : prompt ${prompt}, évaluations à chaque pull request, red team de nuit.`,
  sources: [
    { label: "train.yml", path: ".github/workflows/train.yml" },
    { label: "ml/gates.yaml", path: "ml/gates.yaml" },
    { label: "ml/train.py", path: "ml/train.py" },
    { label: "models/prod.json", path: "models/prod.json" },
    { label: "ml/drift.py", path: "ml/drift.py" },
    { label: "evals/pr.yaml", path: "evals/pr.yaml" },
    { label: "evals/nightly.yaml", path: "evals/nightly.yaml" },
    { label: "evals/judge.js", path: "evals/judge.js" },
  ] satisfies SourceLink[],
};

export const fr = { page, stageText, request, roleText, infra, jobText, triggerText, delivery, lifecycle };

export type ArchitectureContent = typeof fr;
