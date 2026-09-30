// Données de la page /xops, générées depuis les vraies sources du dépôt : version du modèle
// promu, identités Sigstore exigées par la CI, image GHCR, réglages de production, budget
// Terraform, écosystèmes Dependabot. Vérifie aussi chaque preuve citée par les pages :
//
//   - tout `path: "…"` de xops-content.ts et architecture-content.ts doit exister dans le dépôt ;
//   - tout `anchor: "…"` de xops-content.ts doit se résoudre en fichier + ligne :
//       job:<workflow>:<job>              ligne du job
//       step:<workflow>:<job>:<texte>     première étape du job contenant <texte> (casse ignorée)
//       tf:<type>.<nom>                   bloc `resource` Terraform
//       text:<chemin>#<texte>             première ligne du fichier contenant <texte>
//
//   node scripts/sync-xops.mjs          écrit web/src/lib/xops.json
//   node scripts/sync-xops.mjs --check  échoue si le JSON commité est périmé
//
// Toute preuve introuvable fait échouer le build : la page ne peut pas citer un fichier,
// un job ou une étape qui n'existe plus.
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const OUTPUT = "web/src/lib/xops.json";
export const REPOSITORY = "VoiD911/ask-my-cv";

/** Fichiers de contenu dont les chemins et ancres sont vérifiés. */
export const CONTENT_FILES = ["web/src/lib/xops-content.ts", "web/src/lib/architecture-content.ts"];

export class XopsError extends Error {}

const posix = (root, file) => relative(root, file).split("\\").join("/");

/** Littéraux `path: "…"` et `anchor: "…"` d'un fichier de contenu TypeScript. */
export function extractRefs(text) {
  const grab = (key) => [...text.matchAll(new RegExp(`\\b${key}:\\s*"([^"]+)"`, "g"))].map((m) => m[1]);
  return { paths: grab("path"), anchors: grab("anchor") };
}

/** Chemin relatif au dépôt, sans remontée ni schéma. */
export function assertRepoPath(path) {
  if (!/^(?:[\w.@-]+\/)*[\w.@-]+$/.test(path) || path.split("/").some((p) => p === ".." || p === ".")) {
    throw new XopsError(`chemin inattendu : ${path}`);
  }
  return path;
}

/** Numéros de ligne (1-based) des jobs et de leurs étapes, indentation à deux espaces. */
export function indexWorkflow(text) {
  const lines = text.split(/\r?\n/);
  const jobs = new Map();
  let inJobs = false;
  let current = null;
  lines.forEach((raw, i) => {
    if (/^\S/.test(raw) && !/^#/.test(raw)) {
      inJobs = /^jobs:\s*$/.test(raw);
      current = null;
      return;
    }
    if (!inJobs) return;
    const job = /^ {2}([\w-]+):\s*$/.exec(raw);
    if (job) {
      current = { line: i + 1, steps: [] };
      jobs.set(job[1], current);
      return;
    }
    const step = /^ {6}- (?:name|run|uses):\s*(.+)$/.exec(raw);
    if (current && step) current.steps.push({ line: i + 1, text: step[1] });
  });
  return jobs;
}

export function resolveAnchor(root, anchor, cache = new Map()) {
  const read = (path) => {
    if (!cache.has(path)) cache.set(path, readFileSync(resolve(root, assertRepoPath(path)), "utf8"));
    return cache.get(path);
  };
  const [kind, ...rest] = anchor.split(":");
  if (kind === "job" || kind === "step") {
    const [wf, id, ...needleParts] = rest;
    const path = `.github/workflows/${wf}`;
    if (!existsSync(resolve(root, assertRepoPath(path)))) throw new XopsError(`ancre ${anchor} : workflow absent`);
    const job = indexWorkflow(read(path)).get(id);
    if (!job) throw new XopsError(`ancre ${anchor} : job absent`);
    if (kind === "job") return { path, line: job.line };
    const needle = needleParts.join(":").toLowerCase();
    const step = needle && job.steps.find((s) => s.text.toLowerCase().includes(needle));
    if (!step) throw new XopsError(`ancre ${anchor} : étape absente`);
    return { path, line: step.line };
  }
  if (kind === "tf") {
    const [type, name] = rest.join(":").split(".");
    const files = readdirSync(resolve(root, "infra"), { withFileTypes: true, recursive: true })
      .filter((e) => e.isFile() && e.name.endsWith(".tf") && !posix(root, resolve(e.parentPath)).includes("/."))
      .map((e) => posix(root, resolve(e.parentPath, e.name)))
      .sort();
    for (const path of files) {
      const index = read(path)
        .split(/\r?\n/)
        .findIndex((l) => new RegExp(`^resource\\s+"${type}"\\s+"${name}"`).test(l));
      if (index >= 0) return { path, line: index + 1 };
    }
    throw new XopsError(`ancre ${anchor} : ressource Terraform absente`);
  }
  if (kind === "text") {
    const spec = rest.join(":");
    const hash = spec.indexOf("#");
    if (hash <= 0) throw new XopsError(`ancre ${anchor} : forme text:<chemin>#<texte>`);
    const path = spec.slice(0, hash);
    const needle = spec.slice(hash + 1);
    if (!existsSync(resolve(root, assertRepoPath(path)))) throw new XopsError(`ancre ${anchor} : fichier absent`);
    const index = read(path)
      .split(/\r?\n/)
      .findIndex((l) => l.includes(needle));
    if (index < 0) throw new XopsError(`ancre ${anchor} : texte absent`);
    return { path, line: index + 1 };
  }
  throw new XopsError(`ancre inconnue : ${anchor}`);
}

function match(text, regex, what) {
  const found = regex.exec(text);
  if (!found) throw new XopsError(`${what} introuvable`);
  return found[1];
}

/** Clé scalaire `clé: valeur` d'un YAML plat (settings.aws.yaml). */
function yamlScalar(text, key) {
  return match(text, new RegExp(`^${key}:\\s*([^#\\n]+?)\\s*(?:#.*)?$`, "m"), `settings.aws.yaml : ${key}`);
}

export function buildXops(root) {
  const read = (path) => readFileSync(resolve(root, path), "utf8");
  const ci = read(".github/workflows/ci.yml");
  const train = read(".github/workflows/train.yml");
  const settings = read("settings.aws.yaml");

  // Dépôt : constante recoupée avec l'image GHCR publiée par la CI.
  const image = match(ci, /^\s+GHCR_IMAGE:\s*(\S+)\s*$/m, "ci.yml : GHCR_IMAGE");
  if (image !== `ghcr.io/${REPOSITORY.toLowerCase()}`) {
    throw new XopsError(`GHCR_IMAGE ${image} ne correspond pas au dépôt ${REPOSITORY}`);
  }
  const site = match(ci, /^\s+url:\s*(https:\/\/[\w.-]+)\s*$/m, "ci.yml : URL de l'environnement production");

  // Identités Sigstore exigées par la CI (${GITHUB_REPOSITORY} / ${{ github.repository }} → dépôt).
  const withRepo = (s) => s.replace(/\$\{\{\s*github\.repository\s*\}\}|\$\{GITHUB_REPOSITORY\}|\$GITHUB_REPOSITORY\b/g, REPOSITORY);
  const modelIdentity = withRepo(match(ci, /cosign verify-blob[\s\S]*?--certificate-identity "([^"]+)"/, "identité du modèle"));
  const imageIdentity = withRepo(match(ci, /^\s+SIGNER_ID:\s*(.+?)\s*$/m, "ci.yml : SIGNER_ID"));
  const issuer = match(ci, /^\s+OIDC_ISSUER:\s*(\S+)\s*$/m, "ci.yml : OIDC_ISSUER");
  const signerWorkflow = withRepo(match(ci, /--signer-workflow "([^"]+)"/, "ci.yml : --signer-workflow"));
  const sbomType = match(ci, /cosign verify-attestation "\$IMAGE_REF" --type (\S+)/, "ci.yml : type de SBOM cosign");
  const sbomPredicate = match(ci, /--predicate-type (https:\/\/\S+)/, "ci.yml : prédicat du SBOM");
  for (const [what, value] of [
    ["identité du modèle", modelIdentity],
    ["identité de l'image", imageIdentity],
  ]) {
    if (!value.startsWith(`https://github.com/${REPOSITORY}/.github/workflows/`) || /\$/.test(value)) {
      throw new XopsError(`${what} inattendue : ${value}`);
    }
  }
  if (issuer !== "https://token.actions.githubusercontent.com") throw new XopsError(`émetteur OIDC inattendu : ${issuer}`);

  // Release du modèle promu : préfixe de tag et fichiers publiés par train.yml.
  const manifest = JSON.parse(read("models/prod.json"));
  if (!/^v\d+\.\d+\.\d+$/.test(manifest.version ?? "")) throw new XopsError("models/prod.json : version invalide");
  const release = match(train, /(gh release create "[^"]+" \\\r?\n[^\n]*)/, "train.yml : gh release create");
  const tagPrefix = match(release, /create "([\w-]+)\$VERSION"/, "train.yml : préfixe du tag");
  const assets = [...release.matchAll(/dist\/([\w.-]+)/g)].map((m) => m[1]);
  for (const needed of ["model.onnx", "model.onnx.sigstore.json", "metrics.json", "model_card.md"]) {
    if (!assets.includes(needed)) throw new XopsError(`train.yml : ${needed} absent de la release`);
  }

  const promptPath = yamlScalar(settings, "prompt_path");
  const promptVersion = match(promptPath, /@(v\d+)\.md$/, "prompt_path");
  const promptVersions = readdirSync(resolve(root, "prompts"))
    .map((n) => /^answer@v(\d+)\.md$/.exec(n)?.[1])
    .filter(Boolean)
    .map(Number)
    .sort((a, b) => a - b)
    .map((n) => `v${n}`);
  const list = (key) =>
    match(settings, new RegExp(`^${key}:\\s*\\[([^\\]]*)\\]`, "m"), `settings.aws.yaml : ${key}`)
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

  const monthly = match(
    read("infra/prod/variables.tf"),
    /variable "monthly_budget_usd"\s*\{[^}]*default\s*=\s*(\d+(?:\.\d+)?)/,
    "variables.tf : monthly_budget_usd",
  );

  const ecosystems = [...read(".github/dependabot.yml").matchAll(/package-ecosystem:\s*([\w-]+)/g)]
    .map((m) => m[1])
    .filter((n, i, all) => all.indexOf(n) === i);
  if (!ecosystems.length) throw new XopsError("dependabot.yml sans écosystème");

  // Preuves citées par les pages : chemins existants, ancres résolues.
  const paths = {};
  const anchors = {};
  const cache = new Map();
  for (const file of CONTENT_FILES) {
    const refs = extractRefs(read(file));
    for (const path of refs.paths) {
      const full = resolve(root, assertRepoPath(path));
      if (!existsSync(full)) throw new XopsError(`${file} : chemin absent du dépôt : ${path}`);
      paths[path] = statSync(full).isDirectory() ? "dir" : "file";
    }
    for (const anchor of refs.anchors) anchors[anchor] = resolveAnchor(root, anchor, cache);
  }
  const sorted = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)));

  return {
    version: 1,
    repository: REPOSITORY,
    site,
    image,
    model: {
      version: manifest.version,
      tag: `${tagPrefix}${manifest.version}`,
      assets,
    },
    signing: { issuer, modelIdentity, imageIdentity, signerWorkflow, sbomType, sbomPredicate },
    prompts: { current: promptVersion, versions: promptVersions },
    production: {
      dailyCapUsd: Number(yamlScalar(settings, "daily_cap_usd")),
      perVisitorLimit: Number(yamlScalar(settings, "per_visitor_limit")),
      visitorWindowS: Number(yamlScalar(settings, "visitor_window_s")),
      fallbackChain: list("fallback_chain"),
      tracing: list("tracing"),
    },
    budget: { monthlyUsdDefault: Number(monthly) },
    dependabot: ecosystems,
    paths: sorted(paths),
    anchors: sorted(anchors),
  };
}

export function render(data) {
  return `${JSON.stringify(data, null, 2)}\n`;
}

function main(argv) {
  const root = resolve(import.meta.dirname, "../..");
  let expected;
  try {
    expected = render(buildXops(root));
  } catch (error) {
    if (error instanceof XopsError) {
      console.error(`sync-xops : ${error.message}`);
      process.exit(1);
    }
    throw error;
  }
  const target = resolve(root, OUTPUT);
  if (argv.includes("--check")) {
    let current = "";
    try {
      current = readFileSync(target, "utf8").replace(/\r\n/g, "\n");
    } catch {
      // absent : périmé
    }
    if (current !== expected) {
      console.error(`${OUTPUT} est périmé : lancer « node web/scripts/sync-xops.mjs »`);
      process.exit(1);
    }
    return;
  }
  writeFileSync(target, expected);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2));
}
