// PDF du CV (FR et EN), générés APRÈS `npm run build` depuis les pages /cv/ et /en/cv/ de
// l'export statique (web/out), rendues en média `print` (feuille d'impression de
// globals.css) par Chromium via Playwright. Étape séparée (`npm run pdf`) : le build reste
// possible sans navigateur ; la CI l'exécute dans le job `web` avant de publier web/out.
//
//   npm run pdf           écrit web/out/cv/Steve-Lang-CV-fr.pdf et web/out/en/cv/Steve-Lang-CV-en.pdf
//
// Métadonnées : titre (depuis <title>, posé par Chromium) et auteur, ajouté par une mise à
// jour incrémentale du dictionnaire /Info (Chromium n'expose pas l'auteur). Texte
// sélectionnable (PDF balisé), format A4.
import { createReadStream, existsSync, statSync, writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const AUTHOR = "Steve Lang";
export const TARGETS = [
  { url: "/cv/", file: "cv/Steve-Lang-CV-fr.pdf", title: "CV — Steve Lang" },
  { url: "/en/cv/", file: "en/cv/Steve-Lang-CV-en.pdf", title: "Resume — Steve Lang" },
];

export class PdfError extends Error {}

/** Chaîne PDF en UTF-16BE (hexadécimal, BOM) : accents et tirets sans ambiguïté d'encodage. */
export function pdfText(text) {
  let hex = "FEFF";
  for (const unit of Buffer.from(text, "utf16le").swap16()) hex += unit.toString(16).padStart(2, "0").toUpperCase();
  return `<${hex}>`;
}

/**
 * Ajoute (mise à jour incrémentale, sans réécrire le fichier) un dictionnaire /Info avec le
 * titre, l'auteur et les champs existants conservés. Suppose une table xref classique
 * (`trailer`), ce que produit Chromium ; sinon échoue plutôt que de corrompre le PDF.
 */
export function withInfo(pdf, { title, author }) {
  const text = pdf.toString("latin1");
  const trailerAt = text.lastIndexOf("trailer");
  const startxrefAt = text.lastIndexOf("startxref");
  if (trailerAt < 0 || startxrefAt < trailerAt) throw new PdfError("PDF sans trailer classique");
  const trailer = text.slice(trailerAt, startxrefAt);
  const size = Number(/\/Size\s+(\d+)/.exec(trailer)?.[1]);
  const root = /\/Root\s+(\d+\s+\d+\s+R)/.exec(trailer)?.[1];
  const prev = Number(/startxref\s+(\d+)/.exec(text.slice(startxrefAt))?.[1]);
  if (!size || !root || !Number.isFinite(prev)) throw new PdfError("trailer PDF illisible");
  const id = /\/ID\s*(\[[^\]]*\])/.exec(trailer)?.[1];

  // Champs de l'ancien /Info (Creator, Producer, dates) repris tels quels, hors Title/Author.
  let kept = "";
  const infoRef = /\/Info\s+(\d+)\s+(\d+)\s+R/.exec(trailer);
  if (infoRef) {
    const obj = new RegExp(String.raw`(?:^|\s)${infoRef[1]}\s+${infoRef[2]}\s+obj\s*<<([\s\S]*?)>>\s*endobj`).exec(text);
    if (obj?.[1]) {
      kept = obj[1]
        .replace(/\/(Title|Author)\s*(\([^)]*\)|<[^>]*>)/g, "")
        .trim();
    }
  }
  const infoNum = size;
  const body = `\n${infoNum} 0 obj\n<< /Title ${pdfText(title)} /Author ${pdfText(author)}${kept ? ` ${kept}` : ""} >>\nendobj\n`;
  const objOffset = pdf.length + 1; // après le « \n » initial
  const xrefOffset = pdf.length + Buffer.byteLength(body, "latin1");
  const xref =
    `xref\n${infoNum} 1\n${String(objOffset).padStart(10, "0")} 00000 n \n` +
    `trailer\n<< /Size ${size + 1} /Root ${root} /Info ${infoNum} 0 R /Prev ${prev}${id ? ` /ID ${id}` : ""} >>\n` +
    `startxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.concat([pdf, Buffer.from(body + xref, "latin1")]);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

/** Serveur statique minimal de web/out (lecture seule, confiné au dossier). */
function serve(root) {
  const server = http.createServer((req, res) => {
    let rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
    if (rel.endsWith("/")) rel += "index.html";
    const file = path.resolve(root, `.${rel}`);
    if (!file.startsWith(root + path.sep) || !existsSync(file) || !statSync(file).isFile()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function main() {
  const out = path.resolve(fileURLToPath(new URL("../out", import.meta.url)));
  for (const t of TARGETS) {
    const html = path.join(out, t.url, "index.html");
    if (!existsSync(html)) throw new PdfError(`${html} absent : lancer « npm run build » d'abord`);
  }
  const { chromium } = await import("@playwright/test");
  const server = await serve(out);
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    for (const t of TARGETS) {
      await page.goto(`${base}${t.url}`, { waitUntil: "networkidle" });
      await page.emulateMedia({ media: "print" });
      await page.evaluate(() => document.fonts.ready);
      const title = await page.title();
      if (title !== t.title) throw new PdfError(`${t.url} : titre inattendu « ${title} »`);
      const pdf = await page.pdf({ format: "A4", preferCSSPageSize: true, printBackground: false, tagged: true, outline: true });
      const target = path.join(out, t.file);
      writeFileSync(target, withInfo(pdf, { title: t.title, author: AUTHOR }));
      const size = statSync(target).size;
      if (size < 10_000) throw new PdfError(`${t.file} : PDF anormalement petit (${size} octets)`);
      console.log(`${t.file} : ${size} octets`);
    }
  } finally {
    await browser.close();
    server.close();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
