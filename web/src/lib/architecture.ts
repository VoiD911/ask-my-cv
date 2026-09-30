/**
 * Données de la page /architecture : générées au build depuis les vraies sources du dépôt
 * par `scripts/sync-architecture.mjs` (la CI refuse un JSON périmé).
 */
import data from "./architecture.json";

export type InfraRole = "edge" | "compute" | "data" | "ai" | "security" | "observability" | "cost";
export type InfraResource = { type: string; name: string; file: string };
export type WorkflowJob = { id: string; needs: string[]; steps: string[]; layer: number };
export type Workflow = { file: string; name: string; triggers: string[]; jobs: WorkflowJob[] };

export type Architecture = {
  version: 1;
  repository: string;
  pipeline: { source: string; stages: string[]; guardrailMinChars: number };
  infra: { role: InfraRole; resources: InfraResource[] }[];
  workflows: Workflow[];
  model: {
    manifest: string;
    version: string;
    prompt: string;
    promptVersion: string;
    promptVersions: string[];
  };
};

const REPOSITORY = "VoiD911/ask-my-cv";

if (data.version !== 1 || data.repository !== REPOSITORY) {
  throw new Error("Données d'architecture non reconnues");
}

export const architecture = data as Architecture;

/** Lien GitHub vers un fichier du dépôt (chemin relatif, sans remontée ni schéma). */
export function sourceUrl(path: string, line?: number): string {
  if (!/^(?:[\w.@-]+\/)*[\w.@-]+$/.test(path) || path.split("/").includes("..")) {
    throw new Error(`Chemin de source inattendu : ${path}`);
  }
  return `https://github.com/${REPOSITORY}/blob/main/${path}${line ? `#L${line}` : ""}`;
}

export function workflow(file: string): Workflow {
  const found = architecture.workflows.find((w) => w.file === `.github/workflows/${file}`);
  if (!found) throw new Error(`Workflow absent : ${file}`);
  return found;
}

export function job(file: string, id: string): WorkflowJob {
  const found = workflow(file).jobs.find((j) => j.id === id);
  if (!found) throw new Error(`Job absent : ${file} → ${id}`);
  return found;
}

/** Jobs regroupés par rang dans le graphe des `needs`. */
export function layers(jobs: WorkflowJob[]): WorkflowJob[][] {
  const out: WorkflowJob[][] = [];
  for (const j of jobs) (out[j.layer] ??= []).push(j);
  return out;
}

/** « aws_cloudfront_distribution » → « cloudfront_distribution ». */
export function shortType(type: string): string {
  return type.replace(/^awscc?_/, "");
}
