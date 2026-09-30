// Données de la page /architecture, générées depuis les vraies sources du dépôt :
// workflows GitHub Actions (jobs, needs, étapes nommées), ressources Terraform, étapes du
// pipeline (PIPELINE_STAGES dans src/ask_my_cv/stages.py), modèle promu et prompt servi.
//
//   node scripts/sync-architecture.mjs          écrit web/src/lib/architecture.json
//   node scripts/sync-architecture.mjs --check  échoue si le JSON commité est périmé
//
// Aucune dépendance : les formats lus sont simples et stables, et toute surprise (ressource
// sans rôle, job attendu absent) fait échouer le build plutôt que d'afficher un schéma faux.
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const OUTPUT = "web/src/lib/architecture.json";

export class ArchitectureError extends Error {}

const WORKFLOWS = [
  ".github/workflows/ci.yml",
  ".github/workflows/nightly.yml",
  ".github/workflows/train.yml",
  ".github/workflows/mirror.yml",
];

/** Rôle de chaque ressource, du plus spécifique au plus général. */
const ROLES = [
  ["edge", /^aws_(cloudfront_|acm_)/],
  ["edge", /^aws_s3_bucket(_[a-z_]+)?$/, /^site$/],
  ["compute", /^aws_(lambda_|ecr_)/],
  ["data", /^(aws|awscc)_dynamodb_/],
  ["data", /^aws_s3_bucket(_[a-z_]+)?$/],
  ["ai", /^aws_bedrock_/],
  ["security", /^aws_(iam_|kms_)/],
  ["observability", /^aws_(cloudwatch_|sns_)/],
  ["cost", /^aws_budgets_/],
];

export const ROLE_ORDER = ["edge", "compute", "data", "ai", "security", "observability", "cost"];

export function classifyResource(type, name) {
  for (const [role, typePattern, namePattern] of ROLES) {
    if (typePattern.test(type) && (!namePattern || namePattern.test(name))) return role;
  }
  throw new ArchitectureError(`ressource Terraform sans rôle : ${type}.${name}`);
}

/** Blocs `resource "type" "nom"` d'un fichier .tf (les blocs `data` sont des lectures). */
export function parseTerraform(text) {
  const resources = [];
  for (const match of text.matchAll(/^resource\s+"([\w-]+)"\s+"([\w-]+)"/gm)) {
    resources.push({ type: match[1], name: match[2] });
  }
  return resources;
}

function unquote(value) {
  const v = value.trim();
  return /^(["']).*\1$/.test(v) ? v.slice(1, -1) : v;
}

function parseList(value) {
  const v = value.trim();
  if (v.startsWith("[")) {
    if (!v.endsWith("]")) throw new ArchitectureError(`liste non fermée : ${v}`);
    return v
      .slice(1, -1)
      .split(",")
      .map((item) => unquote(item))
      .filter(Boolean);
  }
  return v ? [unquote(v)] : [];
}

/**
 * Lecture minimale d'un workflow : nom, déclencheurs (clés de `on:`), jobs dans l'ordre du
 * fichier avec `needs` (en ligne ou en liste) et les noms des étapes (`- name:` d'étape).
 * Suppose l'indentation à deux espaces des workflows du dépôt.
 */
export function parseWorkflow(text) {
  const lines = text.split(/\r?\n/);
  let name = "";
  const triggers = [];
  const jobs = [];
  let section = "";
  let job = null;
  let inNeedsList = false;
  for (const raw of lines) {
    const line = raw.replace(/\s+#.*$/, "");
    if (!line.trim() || /^\s*#/.test(raw)) continue;
    const top = /^([\w-]+):\s*(.*)$/.exec(line);
    if (top) {
      section = top[1];
      job = null;
      if (section === "name") name = unquote(top[2]);
      if (section === "on" && top[2]) triggers.push(...parseList(top[2]));
      continue;
    }
    if (section === "on") {
      const key = /^ {2}([\w-]+):/.exec(line);
      if (key) triggers.push(key[1]);
      continue;
    }
    if (section !== "jobs") continue;
    const jobKey = /^ {2}([\w-]+):\s*$/.exec(line);
    if (jobKey) {
      job = { id: jobKey[1], needs: [], steps: [] };
      jobs.push(job);
      inNeedsList = false;
      continue;
    }
    if (!job) continue;
    const needs = /^ {4}needs:\s*(.*)$/.exec(line);
    if (needs) {
      job.needs.push(...parseList(needs[1]));
      inNeedsList = !needs[1].trim();
      continue;
    }
    if (inNeedsList) {
      const item = /^ {6}- (.+)$/.exec(line);
      if (item) {
        job.needs.push(unquote(item[1]));
        continue;
      }
      inNeedsList = false;
    }
    // étape nommée, ou commande d'une ligne sans nom (`- run: uv run pytest -q`)
    const step = /^ {6}- (name|run):\s*(.+)$/.exec(raw.trimEnd());
    if (step && !/^[|>]/.test(step[2])) job.steps.push(unquote(step[2]));
  }
  if (!name) throw new ArchitectureError("workflow sans nom");
  const ids = new Set(jobs.map((j) => j.id));
  for (const j of jobs) {
    for (const need of j.needs) {
      if (!ids.has(need)) throw new ArchitectureError(`job ${j.id} : needs inconnu ${need}`);
    }
  }
  return { name, triggers, jobs: withLayers(jobs) };
}

/** Rang de chaque job dans le graphe des `needs` (0 = sans prérequis). */
function withLayers(jobs) {
  const byId = new Map(jobs.map((j) => [j.id, j]));
  const layer = new Map();
  const visit = (id, seen) => {
    if (layer.has(id)) return layer.get(id);
    if (seen.has(id)) throw new ArchitectureError(`cycle dans les needs : ${id}`);
    seen.add(id);
    const needs = byId.get(id).needs;
    const value = needs.length ? 1 + Math.max(...needs.map((n) => visit(n, seen))) : 0;
    layer.set(id, value);
    return value;
  };
  return jobs.map((j) => ({ ...j, layer: visit(j.id, new Set()) }));
}

/** Tuple PIPELINE_STAGES de src/ask_my_cv/stages.py. */
export function parseStages(python) {
  const match = /^PIPELINE_STAGES[^=]*=\s*\(([^)]*)\)/m.exec(python);
  if (!match) throw new ArchitectureError("PIPELINE_STAGES introuvable");
  const stages = [...match[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  if (stages.length === 0) throw new ArchitectureError("PIPELINE_STAGES vide");
  return stages;
}

function requireJob(workflow, id) {
  if (!workflow.jobs.some((j) => j.id === id)) {
    throw new ArchitectureError(`job attendu absent : ${workflow.file} → ${id}`);
  }
}

function listFiles(dir, predicate) {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && predicate(entry.name))
    .map((entry) => resolve(entry.parentPath, entry.name));
}

const posix = (root, file) => relative(root, file).split("\\").join("/");

export function buildArchitecture(root) {
  const read = (path) => readFileSync(resolve(root, path), "utf8");

  const workflows = WORKFLOWS.map((file) => ({ file, ...parseWorkflow(read(file)) }));
  const byFile = Object.fromEntries(workflows.map((w) => [w.file.split("/").pop(), w]));
  for (const id of ["security", "test", "evals", "web", "terraform", "deploy"]) requireJob(byFile["ci.yml"], id);
  for (const id of ["redteam", "drift"]) requireJob(byFile["nightly.yml"], id);
  requireJob(byFile["train.yml"], "train");

  const resources = listFiles(resolve(root, "infra"), (n) => n.endsWith(".tf"))
    .sort()
    .flatMap((file) =>
      parseTerraform(readFileSync(file, "utf8")).map((r) => ({
        ...r,
        file: posix(root, file),
        role: classifyResource(r.type, r.name),
      })),
    );
  const infra = ROLE_ORDER.map((role) => ({
    role,
    resources: resources.filter((r) => r.role === role).map(({ type, name, file }) => ({ type, name, file })),
  }));

  const manifest = JSON.parse(read("models/prod.json"));
  if (!/^v\d+\.\d+\.\d+$/.test(manifest.version ?? "")) {
    throw new ArchitectureError("models/prod.json : version invalide");
  }
  const promptPath = /^prompt_path:\s*(\S+)/m.exec(read("settings.aws.yaml"))?.[1];
  const promptVersion = /@(v\d+)\.md$/.exec(promptPath ?? "")?.[1];
  if (!promptPath || !promptVersion) throw new ArchitectureError("settings.aws.yaml : prompt_path illisible");
  const prompts = readdirSync(resolve(root, "prompts"))
    .map((n) => /^answer@v(\d+)\.md$/.exec(n)?.[1])
    .filter(Boolean)
    .map(Number)
    .sort((a, b) => a - b)
    .map((n) => `v${n}`);
  const minChars = /guardrail_min_chars:\s*int\s*=\s*Field\(default=(\d+)/.exec(read("src/ask_my_cv/settings.py"))?.[1];
  if (!minChars) throw new ArchitectureError("guardrail_min_chars introuvable");

  return {
    version: 1,
    repository: "VoiD911/ask-my-cv",
    pipeline: {
      source: "src/ask_my_cv/stages.py",
      stages: parseStages(read("src/ask_my_cv/stages.py")),
      guardrailMinChars: Number(minChars),
    },
    infra,
    workflows,
    model: {
      manifest: "models/prod.json",
      version: manifest.version,
      prompt: promptPath,
      promptVersion,
      promptVersions: prompts,
    },
  };
}

export function render(data) {
  return `${JSON.stringify(data, null, 2)}\n`;
}

function main(argv) {
  const root = resolve(import.meta.dirname, "../..");
  const expected = render(buildArchitecture(root));
  const target = resolve(root, OUTPUT);
  if (argv.includes("--check")) {
    let current = "";
    try {
      current = readFileSync(target, "utf8").replace(/\r\n/g, "\n");
    } catch {
      // absent : périmé
    }
    if (current !== expected) {
      console.error(`${OUTPUT} est périmé : lancer « node web/scripts/sync-architecture.mjs »`);
      process.exit(1);
    }
    return;
  }
  writeFileSync(target, expected);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2));
}
