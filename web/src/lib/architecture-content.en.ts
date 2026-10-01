/**
 * English text for /en/architecture. Same shape as the French content (`ArchitectureContent`);
 * source links reuse the French entries' paths (the only ones checked by
 * `scripts/sync-xops.mjs`), with translated labels.
 */
import type { Locale } from "@/i18n/locales";

import { fr, type ArchitectureContent, type SourceLink } from "./architecture-content";

/** Same links, translated labels (one per link, in order). */
function relabel(links: SourceLink[], labels: string[]): SourceLink[] {
  if (links.length !== labels.length) throw new Error("Source labels out of sync with the French content");
  return links.map((link, i) => ({ ...link, label: labels[i] ?? link.label }));
}

export const en: ArchitectureContent = {
  page: {
    title: "Architecture — Ask my CV",
    description:
      "How “Ask my CV” is built, verified, deployed and monitored: the path of a request, the AWS infrastructure, the CI/CD chain and the model lifecycle.",
    eyebrow: "Overview · diagrams generated from the code",
    heading: "Architecture",
    lede: "Four diagrams that show, in a few minutes, how a question becomes an answer ([[RAG]]), on which infrastructure, with which checks before going to production, and how the security model is trained and then monitored.",
    generated:
      "Every diagram is regenerated on each build from the repository files (workflows, Terraform, Python pipeline); CI rejects a page that no longer matches the code.",
    tocLabel: "On this page",
    sourcesLabel: "Source files",
    readingLabel: "Diagram description",
    statsLabels: { stages: "Stages", resources: "Resources", jobs: "CI/CD jobs" },
    requestMeta: (stages, version) => `${stages} stages · ONNX ${version}`,
    flowIn: "Inbound: from the browser to the Lambda",
    flowStages: "Pipeline stages, in order",
    flowOut: "Return: stream back to the interface",
    infraBoardTitle: "Terraform · infra/",
    resourcesMeta: (count) => `${count} resources`,
    workflowTitle: (name) => `workflow ${name}`,
    modelsBoardTitle: "Models",
    stepsCount: (count) => `${count} steps`,
  },
  stageText: {
    reception: { label: "Intake", detail: "Unicode normalization, length, allowed model" },
    quota: { label: "Quota and budget", detail: "DynamoDB ledger: per-visitor limit, daily cap" },
    injection: { label: "Injection detector", detail: "ONNX classifier, then Bedrock Guardrails on job postings" },
    embedding: { label: "Embedding", detail: "Question vector (Bedrock Titan)" },
    retrieval: { label: "Retrieval", detail: "Closest CV passages (DynamoDB vectors)" },
    prompt: { label: "Prompt", detail: "Versioned template, detected language, canary token" },
    llm: { label: "LLM", detail: "Claude on Amazon Bedrock, streamed, with fallback" },
    output_guard: { label: "Output guard", detail: "Prompt leaks, personal data, grounding in the CV" },
  },
  request: {
    id: fr.request.id,
    title: "The path of a request",
    paragraphs: [
      "The site is a static export served by CloudFront; the same distribution forwards /api/* calls to a Lambda function. The Lambda runs a FastAPI application through the Lambda Web Adapter, in streaming mode: the answer flows to the browser as it is produced ([[SSE]]).",
      "Every question goes through the stages below, in this order. Security gates come before any paid call: if the quota is exceeded or the injection classifier blocks, nothing is sent to the [[LLM]].",
      "Each stage emits a start and an end event; this stream drives the live circuit on the home page. Costs are recorded in a DynamoDB ledger that enforces a daily spending cap.",
    ],
    edgeIn: [
      { ref: "IN", label: "Browser", detail: "Question + chosen model" },
      { ref: "CDN", label: "CloudFront", detail: "Static site + /api/*" },
      { ref: "λ", label: "FastAPI Lambda", detail: "Lambda Web Adapter, streamed response" },
    ],
    edgeOut: [
      { ref: "SSE", label: "SSE stream", detail: "Stage events, tokens, answer" },
      { ref: "UI", label: "Interface", detail: "Circuit, answer, sources, cost" },
    ],
    boardTitle: "Pipeline",
    guardrailNote: (minChars) =>
      `Bedrock Guardrails second opinion for pasted texts of ${minChars} characters or more (job postings), only when the classifier has not already blocked.`,
    modelNote: (version) => `Promoted injection classifier: ${version}.`,
    alt: (stages) =>
      `The browser sends the question to CloudFront, which forwards it to the FastAPI Lambda. The pipeline runs ${stages.length} stages: ${stages.join(", ")}. Events stream back to the interface over SSE.`,
    sources: relabel(fr.request.sources, [
      "pipeline.py",
      "stages.py (stage order)",
      "app.py (FastAPI app)",
      "Dockerfile (Lambda Web Adapter)",
      "cdn.tf",
    ]),
  },
  roleText: {
    edge: { label: "Edge", detail: "CDN, TLS certificate, private static site" },
    compute: { label: "Compute", detail: "Container Lambda function and its registry" },
    data: { label: "Data", detail: "CV vectors, spending ledger, Terraform state" },
    ai: { label: "AI", detail: "Bedrock guardrail for job postings" },
    security: { label: "Security and identity", detail: "GitHub OIDC, least-privilege roles, encryption" },
    observability: { label: "Observability", detail: "Logs, metrics, alarms, alerts" },
    cost: { label: "Cost", detail: "Monthly budget with alerts" },
  },
  infra: {
    id: fr.infra.id,
    title: "Infrastructure",
    paragraphs: [
      "All AWS infrastructure is described in Terraform ([[IaC]]), in two layers: a foundation (Terraform state, OIDC identity for GitHub Actions, deployment roles) and production (CDN, Lambda, data, guardrail, observability).",
      "No long-lived access keys: GitHub obtains temporary credentials through [[OIDC]], with separate roles for deployment and for the nightly tests. The site bucket can only be read by CloudFront.",
      "Resources are grouped by role below. A monthly budget and CloudWatch alarms send email alerts if costs drift or the guardrail starts failing.",
    ],
    alt: (groups) => `Terraform resources by role: ${groups.map((g) => `${g.label} (${g.count})`).join(", ")}.`,
    sources: fr.infra.sources,
  },
  jobText: {
    security: "Scanners: secrets, code, dependencies, IaC",
    test: "Lint, types, Python tests, scanned Docker image + SBOM",
    evals: "promptfoo evaluations and end-to-end browser tests against the local API",
    web: "Lint, tests, build, CSP, Lighthouse",
    terraform: "Terraform formatting and validation",
    deploy: "Signed image, deployment by digest, smoke test, rollback",
    redteam: "Red team against production, scored by an LLM judge",
    drift: "Classifier drift (PSI over 7 days)",
    report: "Opens an issue if the nightly run fails",
    train: "Data, training, gate, signing, release",
    "lambda-adapter": "Verbatim copy of the Lambda Web Adapter to GHCR",
    summary: "Monday usage summary, sent by email (SNS)",
  },
  triggerText: {
    push: "push to main",
    pull_request: "pull request",
    schedule: "nightly",
    workflow_dispatch: "manual",
  },
  delivery: {
    id: fr.delivery.id,
    title: "From code to production",
    paragraphs: [
      "In [[CI/CD]], every pull request runs five jobs in parallel: security scanners, Python tests and the Docker image, LLM evaluations and browser tests, the website (tests, CSP, Lighthouse) and Terraform. Deployment waits only for all of them to succeed.",
      "On main, the image is rebuilt, signed with Sigstore ([[cosign]], keyless), shipped with [[SLSA]] provenance and an [[SBOM]], then verified before being deployed by its digest: signature, SBOM and provenance all target that exact digest.",
      "A smoke test then queries production; if it fails, the previous version is restored automatically. Other workflows run alongside: the nightly red team, model training, an image mirror and the Monday usage summary.",
    ],
    stepsLabel: (id) => `Steps of the ${id} job`,
    layerLabel: (n) => (n === 0 ? "In parallel" : `Then (after ${n} level${n > 1 ? "s" : ""})`),
    alt: (jobs, deploy) => `The ci workflow runs ${jobs.join(", ")} in parallel; the deploy job waits for ${deploy.join(", ")}.`,
    sources: fr.delivery.sources,
  },
  lifecycle: {
    id: fr.lifecycle.id,
    title: "Model lifecycle",
    paragraphs: [
      "The injection detector is a small [[ONNX]] model trained for this project. The train workflow generates training job postings from a versioned seed, trains, then applies an evaluation gate: recall and false-positive thresholds defined in gates.yaml.",
      "The selected model is signed (Sigstore) and published as a release. It is only used once promoted in models/prod.json through a reviewed pull request; CI and deployment check its hash and signature.",
      "In production, a nightly job measures the drift of its scores ([[PSI]]). On the [[LLM]] side, prompts are versioned, every pull request is evaluated with promptfoo, and a nightly red team attacks production, scored by an LLM judge.",
    ],
    classifierTitle: "Injection classifier (ONNX)",
    llmTitle: "LLM and prompts",
    classifierSteps: (version) => [
      { ref: "M1", label: "Data", detail: "Generated job postings, versioned seed" },
      { ref: "M2", label: "Signed training", detail: "train workflow, on main only" },
      { ref: "M3", label: "Evaluation gate", detail: "Recall and false positives (gates.yaml)" },
      { ref: "M4", label: "Release + cosign", detail: "Model, signature, provenance, card" },
      { ref: "M5", label: "Promotion", detail: `models/prod.json → ${version}` },
      { ref: "M6", label: "Monitoring", detail: "Nightly PSI drift" },
    ],
    llmSteps: (prompt, count) => [
      { ref: "P1", label: "Versioned prompt", detail: `${prompt} (${count} versions)` },
      { ref: "P2", label: "PR evaluations", detail: "promptfoo on every pull request" },
      { ref: "P3", label: "Nightly red team", detail: "Production, scored by an LLM judge" },
    ],
    alt: (version, prompt) =>
      `Classifier: data, signed training, evaluation gate, signed release, promotion (${version}), drift monitoring. LLM: prompt ${prompt}, evaluations on every pull request, nightly red team.`,
    sources: fr.lifecycle.sources,
  },
};

/** Content of /architecture in the requested language. */
export function architectureContent(locale: Locale): ArchitectureContent {
  return locale === "en" ? en : fr;
}
