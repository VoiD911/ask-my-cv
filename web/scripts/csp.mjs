// CSP stricte des scripts, calculée au build (postbuild) : pour chaque page de web/out,
// hache (SHA-256, base64) le texte de chaque <script> en ligne et insère en tête du <head>
//   <meta http-equiv="Content-Security-Policy" content="script-src 'self' 'sha256-…' …">
// L'en-tête CSP de CloudFront (infra/prod/variables.tf, `site_csp`) garde
// script-src 'self' 'unsafe-inline' : le navigateur applique les deux politiques (intersection),
// donc un script en ligne n'est exécuté que si son hash figure dans la balise meta.
// Aucune dépendance : node: seulement.
import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// <script …>…</script> ; les valeurs d'attribut entre guillemets peuvent contenir « > ».
const SCRIPT_RE = /<script\b((?:[^>"']|"[^"]*"|'[^']*')*)>([\s\S]*?)<\/script\s*>/gi;
const ATTR_RE = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
const HEAD_RE = /<head(?:\s(?:[^>"']|"[^"]*"|'[^']*')*)?>/i;
const CSP_META_RE = /<meta\b[^>]*http-equiv\s*=\s*["']?content-security-policy/i;
const CHARSET_RE = /<meta\b[^>]*charset\s*=/i;

export class CspError extends Error {}

/** Valeur de l'attribut `src` (chaîne vide s'il n'a pas de valeur), ou undefined s'il est absent. */
function srcAttribute(attrs) {
  for (const m of attrs.matchAll(ATTR_RE)) {
    if (m[1]?.toLowerCase() === "src") return m[2] ?? m[3] ?? m[4] ?? "";
  }
  return undefined;
}

/** Hash CSP d'un texte de script tel que le navigateur le voit (fins de ligne normalisées). */
export function hashScript(text) {
  // Le prétraitement HTML convertit CRLF et CR isolé en LF avant que le script n'existe.
  const normalized = text.replace(/\r\n?/g, "\n");
  return `sha256-${createHash("sha256").update(normalized, "utf8").digest("base64")}`;
}

/** Hashes (uniques, dans l'ordre du document) des scripts en ligne d'une page. */
export function inlineScriptHashes(html) {
  const hashes = [];
  for (const match of html.matchAll(SCRIPT_RE)) {
    const attrs = match[1] ?? "";
    const src = srcAttribute(attrs);
    if (src !== undefined) {
      if (src.trim() === "") {
        throw new CspError(`script avec attribut src vide : <script${attrs}>`);
      }
      continue; // script externe : couvert par 'self'
    }
    const hash = hashScript(match[2] ?? "");
    if (!hashes.includes(hash)) hashes.push(hash);
  }
  return hashes;
}

export function scriptPolicy(hashes) {
  return ["script-src 'self'", ...hashes.map((h) => `'${h}'`)].join(" ");
}

/** Insère la balise meta CSP en premier élément du <head>. */
export function injectCsp(html) {
  if (CSP_META_RE.test(html)) {
    throw new CspError("une balise meta Content-Security-Policy est déjà présente (reconstruire)");
  }
  const head = HEAD_RE.exec(html);
  if (!head) throw new CspError("aucune balise <head> : insertion impossible");
  const at = head.index + head[0].length;
  const firstScript = html.search(/<script\b/i);
  if (firstScript !== -1 && firstScript < at) {
    throw new CspError("un script précède le <head> : la CSP meta ne le couvrirait pas");
  }
  const hashes = inlineScriptHashes(html);
  const meta = `<meta http-equiv="Content-Security-Policy" content="${scriptPolicy(hashes)}"/>`;
  const out = html.slice(0, at) + meta + html.slice(at);
  // La déclaration de jeu de caractères doit rester dans les 1024 premiers octets.
  const charset = CHARSET_RE.exec(out);
  if (charset) {
    const end = out.indexOf(">", charset.index) + 1;
    if (Buffer.byteLength(out.slice(0, end), "utf8") > 1024) {
      throw new CspError("la meta charset sortirait des 1024 premiers octets");
    }
  }
  return { html: out, hashes };
}

async function htmlFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true, recursive: true });
  return entries
    .filter((e) => e.isFile() && e.name.endsWith(".html"))
    .map((e) => path.join(e.parentPath, e.name))
    .sort();
}

/** Traite toutes les pages HTML d'un export ; renvoie [{ file, hashes }]. */
export async function applyToDir(dir) {
  const files = await htmlFiles(dir);
  if (files.length === 0) throw new CspError(`aucune page HTML dans ${dir}`);
  const results = [];
  for (const file of files) {
    let injected;
    try {
      injected = injectCsp(await readFile(file, "utf8"));
    } catch (err) {
      if (err instanceof CspError) throw new CspError(`${path.relative(dir, file)} : ${err.message}`);
      throw err;
    }
    await writeFile(file, injected.html, "utf8");
    results.push({ file: path.relative(dir, file).split(path.sep).join("/"), hashes: injected.hashes });
  }
  return results;
}

/** Valeur par défaut de la variable Terraform `site_csp` (en-tête CSP de production). */
export function readSiteCsp(tf) {
  const m = /variable\s+"site_csp"\s*\{[\s\S]*?\bdefault\s*=\s*"((?:[^"\\]|\\.)*)"/.exec(tf);
  if (!m?.[1]) throw new CspError("variable site_csp introuvable");
  return m[1];
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const dir = path.resolve(process.argv[2] ?? fileURLToPath(new URL("../out", import.meta.url)));
  try {
    for (const { file, hashes } of await applyToDir(dir)) {
      console.log(`csp: ${file} : ${hashes.length} script(s) en ligne haché(s)`);
    }
  } catch (err) {
    console.error(`csp: ${err instanceof Error ? err.message : err}`);
    process.exit(1);
  }
}
