/**
 * English text for /en/xops. Translates the French disciplines, practices and proof labels
 * without redefining the proofs themselves: paths, anchors and URLs stay in
 * `xops-content.ts`, the only file checked by `scripts/sync-xops.mjs`. `localizedDisciplines`
 * merges both and fails the build if a practice or a proof label is missing.
 */
import type { Locale } from "@/i18n/locales";

import type { Xops } from "./xops";
import {
  disciplines as frDisciplines,
  page as frPage,
  verify as frVerify,
  type Discipline,
  type XopsPageText,
  type XopsVerifyText,
} from "./xops-content";

type PracticeText = {
  title: string;
  claim: (x: Xops) => string;
  gap?: (x: Xops) => string;
  /** One label per French proof, in the same order. */
  proofs: string[];
};

type DisciplineText = { name: string; summary: string; practices: Record<string, PracticeText> };

const TRACING: Record<string, string> = { cloudwatch: "CloudWatch", langfuse: "Langfuse" };
const tracing = (x: Xops) => x.production.tracing.map((t) => TRACING[t] ?? t);

export const pageEn: XopsPageText = {
  title: "XOps — Ask my CV",
  description:
    "DevOps, DevSecOps, MLOps, LLMOps and FinOps applied to “Ask my CV”: every practice links to public, verifiable evidence (workflow, signed release, attestation, Terraform).",
  eyebrow: "Practices · verifiable public evidence",
  heading: "XOps",
  lede: "Five operations disciplines, practice by practice. Each card states what is done, whether it is fully or partly covered, and links to evidence you can open or verify yourself: code, workflow, signed release, attestation.",
  generated:
    "Links, versions and signing identities are read from the repository on every build; the build fails if a cited piece of evidence (file, job, step, resource) no longer exists.",
  tocLabel: "On this page",
  matrixTitle: "Overview",
  matrixCaption: "Practices by discipline, with their status",
  matrixCols: { discipline: "Discipline", practices: "Practices", covered: "Covered", partial: "Partial" },
  proofsLabel: "Evidence",
  gapLabel: "What's missing:",
  statusText: { couvert: "Covered", partiel: "Partial" },
  statsLabels: { disciplines: "Disciplines", practices: "Practices", proofs: "Evidence" },
  lineLabel: (line) => `line ${line}`,
  practicesLabel: (discipline) => `${discipline} practices`,
  matrixMeta: (covered, total) => `${covered}/${total} covered`,
  matrixAlt: (items) =>
    items
      .map(
        (d) =>
          `${d.name}: ${d.practices.map((p) => `${p.title} (${p.status === "couvert" ? "covered" : "partial"})`).join(", ")}`,
      )
      .join(". "),
};

export const verifyEn: XopsVerifyText = {
  title: "Verify it yourself",
  intro:
    "These commands need no access to the project: they query the public artifacts and the Sigstore transparency log. You need the GitHub CLI (gh) and cosign.",
  model: {
    id: frVerify.model.id,
    title: (tag) => `Promoted classifier (${tag})`,
    detail:
      "Downloads the model and its signature bundle from the release, checks that the signature was produced by the train workflow on main, then checks the SLSA provenance.",
  },
  image: {
    id: frVerify.image.id,
    title: "API image (GHCR)",
    detail:
      "The public image is tagged with the main commit that deployed it. The first line takes the latest commit on main; if its deployment has not finished yet, pick a tag on the package page.",
  },
  commandLabel: "Commands to copy",
  commandsAria: (title) => `Commands to copy: ${title}`,
};

export const disciplinesEn: Record<string, DisciplineText> = {
  devops: {
    name: "DevOps",
    summary: "Ship often without breaking things: everything goes through CI, infrastructure is code, production is monitored.",
    practices: {
      "integration-continue": {
        title: "Continuous integration",
        claim: () =>
          "Every pull request runs five jobs in parallel (security, tests, evaluations, website, Terraform); deployment waits for all of them to succeed.",
        proofs: ["ci.yml · deploy job (needs)", "Latest ci runs"],
      },
      iac: {
        title: "Infrastructure as Code",
        claim: () =>
          "All AWS infrastructure is in Terraform ([[IaC]]), in two layers (foundation and production); formatting and validation are checked on every PR, and terraform apply is run by hand.",
        proofs: ["infra/prod", "infra/bootstrap/main.tf", "ci.yml · terraform job"],
      },
      deploiement: {
        title: "Deployment and rollback",
        claim: () =>
          "On main, the image is rebuilt, signed, shipped with its SBOM and provenance, verified, then deployed by that exact digest; a smoke test hits production and the Lambda automatically rolls back to its previous image if it fails.",
        gap: () =>
          "No progressive (canary) deployment: the new version replaces the old one in one go; the deployed image is rebuilt rather than promoted from the tested one; rollback covers the Lambda only, not the static site.",
        proofs: ["ci.yml · Deploy (by digest)", "ci.yml · Rollback", "smoke_prod.py"],
      },
      gouvernance: {
        title: "Protected main branch",
        claim: () =>
          "GitHub ruleset on main: pull requests required, five required checks, no force pushes and no deletion.",
        proofs: ["Repository rules", "Environments restricted to main (plan)"],
      },
      observabilite: {
        title: "Observability",
        claim: (x) =>
          `OpenTelemetry traces for every stage (${tracing(x).join(", ")}), guardrail metrics and a CloudWatch alarm sent by email. A private dashboard of real usage (internal traffic excluded, no question text) and a weekly email summary.`,
        proofs: ["telemetry.py", "observability.tf · alarm", "dashboard.tf · dashboard", "weekly.yml · summary"],
      },
      journal: {
        title: "Public development journal",
        claim: () => "Plans, tasks, reviews and fixes published as the project went, each linked to its pull request.",
        proofs: ["Delivery tab", "docs/journal"],
      },
    },
  },
  devsecops: {
    name: "DevSecOps",
    summary: "Security is checked by CI on every change, all the way to signing what goes to production.",
    practices: {
      "secrets-code": {
        title: "Secrets and code",
        claim: () => "gitleaks scans the entire git history and semgrep analyzes the code; any finding blocks the pull request.",
        proofs: ["gitleaks", "semgrep"],
      },
      dependances: {
        title: "Dependencies",
        claim: (x) =>
          `osv-scanner checks for known vulnerabilities; Dependabot proposes updates every week (${x.dependabot.join(", ")}).`,
        proofs: ["osv-scanner", "dependabot.yml", "Dependabot PRs"],
      },
      "iac-image": {
        title: "Terraform and image",
        claim: () =>
          "trivy scans the Terraform configuration and the Docker image; high and critical vulnerabilities block (for the image, those with a fix available).",
        proofs: ["trivy config", "trivy image", ".trivyignore.yaml (justified exceptions)"],
      },
      "chaine-approvisionnement": {
        title: "Supply chain",
        claim: () =>
          "The image is signed with [[cosign]] (keyless), shipped with [[SLSA]] provenance and a CycloneDX [[SBOM]], all verified before deployment. You can verify it too.",
        proofs: ["Verification commands", "GHCR package", "Attestations", "ci.yml · verification before deployment"],
      },
      identite: {
        title: "Secretless identities",
        claim: () =>
          "GitHub Actions obtains temporary AWS credentials through [[OIDC]]; one least-privilege role per use (deployment, nightly), each restricted to its GitHub environment.",
        proofs: ["OIDC provider", "Deployment role", "Nightly role"],
      },
      csp: {
        title: "Hardened website",
        claim: () =>
          "Strict content security policy: only scripts whose hash is computed at build time can run; a browser test checks it on every page.",
        proofs: ["scripts/csp.mjs", "e2e/csp.spec.ts"],
      },
    },
  },
  mlops: {
    name: "MLOps",
    summary: "The injection detector is a real model: versioned data, an evaluation gate, a signed release, a reviewed promotion.",
    practices: {
      entrainement: {
        title: "Reproducible training",
        claim: () => "Data is generated from a versioned seed; training runs in a workflow, on main only.",
        proofs: ["train.yml · main-only guard", "ml/job_ads.py", "ml/train.py", "train runs"],
      },
      porte: {
        title: "Evaluation gate",
        claim: () =>
          "A model is only published if it meets the recall and false-positive thresholds; every threshold change is backed by measurements.",
        proofs: ["ml/gates.yaml", "ml/compare.py"],
      },
      registre: {
        title: "Signed model registry",
        claim: (x) =>
          `Every version is a ${x.model.tag.replace(x.model.version, "v*")} release: [[ONNX]] model, [[cosign]] signature and [[SLSA]] provenance, verifiable by anyone.`,
        proofs: ["Promoted release", "All releases", "Verification commands"],
      },
      fiche: {
        title: "Model card and metrics",
        claim: (x) => `Release ${x.model.version} publishes its model card (data, limitations, intended use) and its evaluation metrics.`,
        proofs: ["model_card.md", "metrics.json"],
      },
      promotion: {
        title: "Promotion and integrity",
        claim: (x) =>
          `The served model (${x.model.version}) is selected by a pull request in models/prod.json; CI verifies its signature and the service checks its hash before loading it.`,
        proofs: ["models/prod.json", "ci.yml · model signature", "Hash check"],
      },
      derive: {
        title: "Drift monitoring",
        claim: () =>
          "Every night, a job compares the last seven days of production scores with the release baseline ([[PSI]]); a failure opens an issue.",
        gap: () =>
          "The measurement still mixes model versions and text types (questions, job postings): a fix is in progress.",
        proofs: ["nightly.yml · drift job", "ml/drift.py", "PR #125 (fix)", "Nightly runs"],
      },
    },
  },
  llmops: {
    name: "LLMOps",
    summary: "The [[LLM]] is treated as a production dependency: prompts are versioned, evaluated, attacked and traced.",
    practices: {
      prompts: {
        title: "Versioned prompts",
        claim: (x) =>
          `Every prompt is a versioned file (${x.prompts.versions.length} versions); production serves ${x.prompts.current}, selected in the configuration.`,
        proofs: ["prompts/", "settings.aws.yaml · prompt_path"],
      },
      evaluations: {
        title: "Evaluations on every PR",
        claim: () =>
          "promptfoo replays a suite of cases (language, refusals, leaks, length) against the local API before any merge, plus browser tests.",
        proofs: ["evals/pr.yaml", "ci.yml · promptfoo suite"],
      },
      "red-team": {
        title: "Nightly red team and LLM judge",
        claim: () =>
          "Every night, attacks (instruction extraction, instructions hidden in job postings) target the real production; the answers are scored by an LLM judge.",
        proofs: ["evals/nightly.yaml", "evals/judge.js", "nightly.yml · redteam job", "Nightly runs"],
      },
      "garde-fous": {
        title: "Input and output guardrails",
        claim: () =>
          "Injection classifier, then Bedrock Guardrails on long job postings: a single failure keeps the classifier's decision, and a circuit breaker rejects job postings if failures repeat. On output, prompt leaks are detected with a canary token and citations of CV passages are required ([[RAG]]), without checking their content.",
        proofs: ["onnx_detector.py", "guardrail.py", "output_guard.py", "guardrail.tf"],
      },
      tracage: {
        title: "Call tracing",
        claim: (x) =>
          `Every question produces one trace per stage (status, duration, tokens used), exported to ${tracing(x).join(" and ")}.`,
        proofs: ["telemetry.py", "settings.aws.yaml · tracing"],
      },
      repli: {
        title: "Timeouts and model fallback",
        claim: () =>
          "Timeouts per stage and for the first token; a fallback chain tries the next model if a provider fails.",
        gap: (x) =>
          `In production, the fallback chain has a single model (${x.production.fallbackChain.join(", ")}): a provider outage results in a clean error, not a failover.`,
        proofs: ["pipeline.py · fallback", "settings.aws.yaml · fallback_chain"],
      },
    },
  },
  finops: {
    name: "FinOps",
    summary: "A public site that calls an LLM needs a cost that is capped, measured and alerted on.",
    practices: {
      plafond: {
        title: "Daily spending cap",
        claim: (x) =>
          `A DynamoDB ledger tracks the day's spending and cuts off at US$${x.production.dailyCapUsd}; each visitor gets ${x.production.perVisitorLimit} questions per ${x.production.visitorWindowS / 3600} h.`,
        proofs: ["budget.py", "DynamoDB ledger", "settings.aws.yaml · daily_cap_usd"],
      },
      "cout-requete": {
        title: "Cost per question",
        claim: () =>
          "The cost is computed for every answer from the tokens used and the model's pricing, then shown in the interface.",
        proofs: ["llm.py · pricing", "settings.aws.yaml · pricing", "Live demo"],
      },
      "aws-budgets": {
        title: "AWS budget and alerts",
        claim: (x) =>
          `Safety net: a monthly AWS Budget (US$${x.budget.monthlyUsdDefault} by default), with email alerts at 50% actual and 100% forecast. Measured daily cost and the month's bill against the budget on the dashboard, the week's cost in the Monday summary.`,
        proofs: ["observability.tf · budget", "variables.tf", "weekly_summary.py"],
      },
      "paiement-usage": {
        title: "Pay per use",
        claim: () => "No always-on server: Lambda, on-demand DynamoDB, old images purged from the registry.",
        proofs: ["lambda.tf", "data.tf · on demand", "ECR purge"],
      },
    },
  },
};

/** French disciplines with the text of the requested language; proofs are unchanged. */
export function localizedDisciplines(locale: Locale): Discipline[] {
  if (locale === "fr") return frDisciplines;
  return frDisciplines.map((d) => {
    const text = disciplinesEn[d.id];
    if (!text) throw new Error(`Missing English discipline: ${d.id}`);
    return {
      ...d,
      name: text.name,
      summary: text.summary,
      practices: d.practices.map((p) => {
        const t = text.practices[p.id];
        if (!t) throw new Error(`Missing English practice: ${d.id}/${p.id}`);
        if (t.proofs.length !== p.proofs.length) throw new Error(`Proof labels out of sync: ${d.id}/${p.id}`);
        if (Boolean(t.gap) !== Boolean(p.gap)) throw new Error(`Gap out of sync: ${d.id}/${p.id}`);
        return {
          ...p,
          title: t.title,
          claim: t.claim,
          ...(t.gap ? { gap: t.gap } : {}),
          proofs: p.proofs.map((proof, i) => ({ ...proof, label: t.proofs[i] ?? proof.label })),
        };
      }),
    };
  });
}

export function xopsText(locale: Locale): { page: XopsPageText; verify: XopsVerifyText } {
  return locale === "fr" ? { page: frPage, verify: frVerify } : { page: pageEn, verify: verifyEn };
}
