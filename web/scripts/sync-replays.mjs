// Rediffusions livrées avec le site (issue #129) : valide src/lib/replays/{fr,en}.json,
// enregistrés sur la production par scripts/record-replays.mjs, et les copie dans
// public/replays/ (non versionné) pour l'export statique. La page les charge seulement quand
// le service en direct est en pause : aucun octet de plus au chargement normal.
//
// Fichiers absents : la rediffusion est masquée (la page garde son message d'erreur habituel)
// et le build continue, sauf avec REPLAYS_REQUIRED=1 (échec). Fichier présent mais invalide,
// fixture de test ou contenu non public : échec, toujours.
//
//   node scripts/sync-replays.mjs           # valide et copie (étape du build)
//   node scripts/sync-replays.mjs --check   # valide seulement
//
// Aucune dépendance : node: seulement.
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { findLeaks } from "./record-replays.mjs";

const WEB = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const SRC = path.join(WEB, "src/lib/replays");
const OUT = path.join(WEB, "public/replays");
export const LOCALES = ["fr", "en"];

export class ReplayFileError extends Error {}

const EVENT_TYPES = new Set(["stage.start", "stage.end", "llm.progress", "answer", "done"]);

/** Valide un fichier d'enregistrements de production pour la langue donnée. */
export function validateReplaySet(set, locale) {
  const fail = (msg) => {
    throw new ReplayFileError(`${locale}.json : ${msg}`);
  };
  if (set?.version !== 1) fail("version attendue : 1");
  if (set.source !== "prod") fail(`source « ${set.source} » : seules les rediffusions de production sont livrées`);
  if (!Array.isArray(set.replays) || set.replays.length === 0) fail("aucun échange enregistré");
  for (const r of set.replays) {
    if (r.locale !== locale) fail(`${r.id} : langue ${r.locale}`);
    if (!["question", "job_ad", "attack"].includes(r.kind)) fail(`${r.id} : genre ${r.kind}`);
    if (typeof r.question !== "string" || !r.question) fail(`${r.id} : question vide`);
    if (!Array.isArray(r.frames) || r.frames.length === 0) fail(`${r.id} : aucun événement`);
    let previous = 0;
    for (const f of r.frames) {
      if (typeof f.t !== "number" || f.t < previous) fail(`${r.id} : délais non croissants`);
      previous = f.t;
      if (!EVENT_TYPES.has(f.event?.type)) fail(`${r.id} : événement ${f.event?.type}`);
    }
    const done = r.frames.at(-1).event;
    if (done.type !== "done") fail(`${r.id} : le dernier événement n'est pas done`);
    if (done.trace_id !== null) fail(`${r.id} : trace_id conservé`);
  }
  const leaks = findLeaks(JSON.stringify(set), process.env.EVAL_TOKEN || undefined);
  if (leaks.length > 0) fail(`contenu non public (${leaks.join(", ")})`);
  return set;
}

async function readSet(locale) {
  let text;
  try {
    text = await readFile(path.join(SRC, `${locale}.json`), "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
  return { set: validateReplaySet(JSON.parse(text), locale) };
}

async function main() {
  const check = process.argv.includes("--check");
  const sets = await Promise.all(LOCALES.map(readSet));
  const missing = LOCALES.filter((_, i) => sets[i] === null);
  if (missing.length > 0) {
    const msg = `rediffusions absentes (${missing.join(", ")}) : mode rediffusion masqué pour ces langues`;
    if (process.env.REPLAYS_REQUIRED === "1") throw new ReplayFileError(msg);
    console.warn(`sync-replays : ${msg}`);
  }
  if (check) return;
  await rm(OUT, { recursive: true, force: true });
  await mkdir(OUT, { recursive: true });
  for (const [i, locale] of LOCALES.entries()) {
    const entry = sets[i];
    if (entry) await writeFile(path.join(OUT, `${locale}.json`), JSON.stringify(entry.set));
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    console.error(`sync-replays : ${error instanceof ReplayFileError ? error.message : error}`);
    process.exit(1);
  });
}
