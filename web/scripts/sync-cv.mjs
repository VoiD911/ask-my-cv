// Données des pages /cv et /en/cv, générées depuis le CV public en Markdown :
// data/cv.md (français, aussi source de l'index RAG) et data/cv.en.md (traduction anglaise,
// jamais indexée : l'ingestion ne lit que `cv_path`, soit data/cv.md).
//
//   node scripts/sync-cv.mjs          écrit web/src/lib/cv.json
//   node scripts/sync-cv.mjs --check  échoue si le JSON commité est périmé
//
// Les deux langues doivent avoir le même nombre de sections, dans le même ordre (même
// identifiant de section) et le même nombre de paragraphes par section : sinon le build échoue
// plutôt que de publier un CV anglais désynchronisé du français.
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const OUTPUT = "web/src/lib/cv.json";
export const SOURCES = { fr: "data/cv.md", en: "data/cv.en.md" };

/** Section « Contact » du Markdown : renvoie au site ; la page affiche le vrai contact. */
const OMITTED = new Set(["contact"]);

/** Identifiant stable d'une section, commun aux deux langues (titre FR → EN). */
const SECTION_IDS = {
  Profil: "profil",
  Profile: "profil",
  Compétences: "competences",
  Skills: "competences",
  "Projets académiques": "projets-academiques",
  "Academic projects": "projets-academiques",
  Formation: "formation",
  Education: "formation",
  Langues: "langues",
  Languages: "langues",
  "Centres d'intérêt": "interets",
  Interests: "interets",
  Contact: "contact",
};

export class CvError extends Error {}

/**
 * Identifiant d'une section : table ci-dessus, ou `experience-<employeur>` /
 * `projet-<n>` pour les titres « Expérience — X (dates) » et « Projet — X ».
 */
export function sectionId(title, index) {
  if (SECTION_IDS[title]) return SECTION_IDS[title];
  const exp = /^(?:Expérience|Experience) — (.+?)\s*\((\d{4})-(\d{4})\)$/.exec(title);
  if (exp) return `experience-${exp[2]}-${exp[3]}`;
  if (/^(?:Projet|Project) — /.test(title)) return "projet-site";
  throw new CvError(`section ${index + 1} sans identifiant connu : « ${title} »`);
}

/** Markdown du CV → { name, sections: [{ id, title, paragraphs }] }. */
export function parseCv(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let name = "";
  const sections = [];
  let current = null;
  let buffer = [];
  const flush = () => {
    if (!current) return;
    const text = buffer.join("\n").trim();
    current.paragraphs = text ? text.split(/\n\s*\n/).map((p) => p.replace(/\s*\n\s*/g, " ").trim()) : [];
    if (current.paragraphs.length === 0) throw new CvError(`section vide : « ${current.title} »`);
    sections.push(current);
  };
  for (const line of lines) {
    if (/^# /.test(line)) {
      if (name) throw new CvError("plusieurs titres de niveau 1");
      name = line.slice(2).trim();
    } else if (/^## /.test(line)) {
      flush();
      const title = line.slice(3).trim();
      current = { id: sectionId(title, sections.length), title, paragraphs: [] };
      buffer = [];
    } else if (/^#{3,} /.test(line)) {
      throw new CvError(`titre de niveau 3+ non géré : « ${line} »`);
    } else if (current) {
      buffer.push(line);
    } else if (line.trim()) {
      throw new CvError(`texte hors section : « ${line} »`);
    }
  }
  flush();
  if (!name) throw new CvError("titre de niveau 1 (nom) absent");
  if (sections.length === 0) throw new CvError("aucune section « ## »");
  const ids = new Set();
  for (const s of sections) {
    if (ids.has(s.id)) throw new CvError(`section en double : ${s.id}`);
    ids.add(s.id);
  }
  return { name, sections };
}

/** Même nom, mêmes sections dans le même ordre, même nombre de paragraphes. */
export function assertParity(fr, en) {
  if (fr.name !== en.name) throw new CvError(`nom différent : « ${fr.name} » / « ${en.name} »`);
  if (fr.sections.length !== en.sections.length) {
    throw new CvError(`nombre de sections différent : fr ${fr.sections.length}, en ${en.sections.length}`);
  }
  fr.sections.forEach((s, i) => {
    const e = en.sections[i];
    if (s.id !== e.id) throw new CvError(`section ${i + 1} : ordre différent (fr ${s.id}, en ${e.id})`);
    if (s.paragraphs.length !== e.paragraphs.length) {
      throw new CvError(`section ${s.id} : nombre de paragraphes différent`);
    }
  });
}

export function buildCv(sources) {
  const fr = parseCv(sources.fr);
  const en = parseCv(sources.en);
  assertParity(fr, en);
  const visible = (cv) => ({ ...cv, sections: cv.sections.filter((s) => !OMITTED.has(s.id)) });
  return { version: 1, sources: SOURCES, fr: visible(fr), en: visible(en) };
}

export function render(data) {
  return `${JSON.stringify(data, null, 2)}\n`;
}

function main(argv) {
  const root = resolve(import.meta.dirname, "../..");
  const read = (path) => readFileSync(resolve(root, path), "utf8");
  const expected = render(buildCv({ fr: read(SOURCES.fr), en: read(SOURCES.en) }));
  const target = resolve(root, OUTPUT);
  if (argv.includes("--check")) {
    let current = "";
    try {
      current = readFileSync(target, "utf8").replace(/\r\n/g, "\n");
    } catch {
      // absent : périmé
    }
    if (current !== expected) {
      console.error(`${OUTPUT} est périmé : lancer « node web/scripts/sync-cv.mjs »`);
      process.exit(1);
    }
    return;
  }
  writeFileSync(target, expected);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2));
}
