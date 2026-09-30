// Tests de scripts/sync-cv.mjs et scripts/cv-pdf.mjs : `node --test web/scripts/*.test.mjs`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

import { pdfText, withInfo } from "./cv-pdf.mjs";
import { assertParity, buildCv, CvError, OUTPUT, parseCv, render, SOURCES } from "./sync-cv.mjs";

const ROOT = resolve(import.meta.dirname, "../..");
const read = (path) => readFileSync(resolve(ROOT, path), "utf8");

const FR = "# Steve Lang\n\n## Profil\nArchitecte.\n\n## Compétences\nPython.\n\nAWS.\n\n## Contact\nSite.\n";
const EN = "# Steve Lang\n\n## Profile\nArchitect.\n\n## Skills\nPython.\n\nAWS.\n\n## Contact\nSite.\n";

describe("parseCv", () => {
  test("nom, sections, paragraphs", () => {
    const cv = parseCv(FR);
    assert.equal(cv.name, "Steve Lang");
    assert.deepEqual(
      cv.sections.map((s) => [s.id, s.title, s.paragraphs.length]),
      [
        ["profil", "Profil", 1],
        ["competences", "Compétences", 2],
        ["contact", "Contact", 1],
      ],
    );
  });

  test("sections d'expérience et de projet : identifiants communs FR/EN", () => {
    const fr = parseCv("# A\n## Expérience — X (2022-2025)\nt\n## Projet — Interroge mon CV (ce site)\nt\n");
    const en = parseCv("# A\n## Experience — X (2022-2025)\nt\n## Project — Ask my CV (this site)\nt\n");
    assert.deepEqual(fr.sections.map((s) => s.id), ["experience-2022-2025", "projet-site"]);
    assert.deepEqual(en.sections.map((s) => s.id), fr.sections.map((s) => s.id));
  });

  test("refuse section inconnue, vide, texte hors section", () => {
    assert.throws(() => parseCv("# A\n## Divers\nx\n"), CvError);
    assert.throws(() => parseCv("# A\n## Profil\n\n## Formation\nx\n"), CvError);
    assert.throws(() => parseCv("# A\nintro\n## Profil\nx\n"), CvError);
  });
});

describe("parité FR/EN", () => {
  test("mêmes sections : OK, section Contact omise", () => {
    const cv = buildCv({ fr: FR, en: EN });
    assert.deepEqual(cv.fr.sections.map((s) => s.id), ["profil", "competences"]);
    assert.deepEqual(cv.en.sections.map((s) => s.title), ["Profile", "Skills"]);
  });

  test("nombre, ordre ou paragraphes différents : échec", () => {
    assert.throws(() => buildCv({ fr: FR, en: EN.replace("## Skills\nPython.\n\nAWS.\n\n", "") }), /nombre de sections/);
    const swapped = "# Steve Lang\n## Skills\nPython.\n\nAWS.\n## Profile\nA.\n## Contact\nS.\n";
    assert.throws(() => buildCv({ fr: FR, en: swapped }), /ordre différent/);
    assert.throws(() => buildCv({ fr: FR, en: EN.replace("Python.\n\nAWS.", "Python, AWS.") }), /paragraphes/);
    assert.throws(() => assertParity(parseCv(FR), parseCv(EN.replace("Steve Lang", "S. Lang"))), /nom/);
  });

  test("vrais fichiers du dépôt : parité et JSON commité à jour", () => {
    const expected = render(buildCv({ fr: read(SOURCES.fr), en: read(SOURCES.en) }));
    assert.equal(read(OUTPUT).replace(/\r\n/g, "\n"), expected);
  });
});

describe("métadonnées PDF", () => {
  test("chaîne UTF-16BE", () => {
    assert.equal(pdfText("É"), "<FEFF00C9>");
  });

  test("mise à jour incrémentale : /Info avec titre et auteur, ancien trailer chaîné", () => {
    const base = Buffer.from(
      "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n2 0 obj\n<< /Producer (Skia) /Title (x) >>\nendobj\n" +
        "xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000048 00000 n \n" +
        "trailer\n<< /Size 3 /Root 1 0 R /Info 2 0 R >>\nstartxref\n90\n%%EOF\n",
      "latin1",
    );
    const out = withInfo(base, { title: "CV — Steve Lang", author: "Steve Lang" }).toString("latin1");
    assert.ok(out.startsWith(base.toString("latin1")));
    assert.match(out, /3 0 obj\n<< \/Title <FEFF[0-9A-F]+> \/Author <FEFF[0-9A-F]+> \/Producer \(Skia\) >>/);
    assert.match(out, /\/Size 4 \/Root 1 0 R \/Info 3 0 R \/Prev 90/);
    const objAt = Number(/xref\n3 1\n(\d{10})/.exec(out)[1]);
    assert.ok(out.slice(objAt).startsWith("3 0 obj"));
    const xrefAt = Number(/startxref\n(\d+)\n%%EOF\n$/.exec(out)[1]);
    assert.ok(out.slice(xrefAt).startsWith("xref\n3 1"));
  });

  test("PDF sans trailer classique : refus", () => {
    assert.throws(() => withInfo(Buffer.from("%PDF-1.7\nstartxref\n0\n%%EOF"), { title: "t", author: "a" }));
  });
});
