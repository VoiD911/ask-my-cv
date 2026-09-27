// Tests de scripts/csp.mjs : `node --test web/scripts/*.test.mjs`.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";

import {
  applyToDir,
  CspError,
  hashScript,
  injectCsp,
  inlineScriptHashes,
  readSiteCsp,
  scriptPolicy,
} from "./csp.mjs";

// Valeurs de référence : printf '…' | openssl dgst -sha256 -binary | base64
const ALERT = "sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI=";
const A_LF_B = "sha256-fhj3NzEbLcOy8mndeDlrA1HxT7Zu+oefdoyyMYGIPHg=";

const page = (head, body = "") =>
  `<!DOCTYPE html><html lang="fr"><head><meta charSet="utf-8"/>${head}</head><body>${body}</body></html>`;

describe("hashScript", () => {
  test("SHA-256 base64 du texte exact", () => {
    assert.equal(hashScript("alert(1)"), ALERT);
  });
  test("fins de ligne normalisées comme le fait le parseur HTML", () => {
    assert.equal(hashScript("a\nb"), A_LF_B);
    assert.equal(hashScript("a\r\nb"), A_LF_B);
    assert.equal(hashScript("a\rb"), A_LF_B);
  });
});

describe("inlineScriptHashes", () => {
  test("ignore les scripts externes, hache les scripts en ligne dans l'ordre, sans doublon", () => {
    const html = page(
      `<script src="/_next/a.js" async=""></script>`,
      `<script>alert(1)</script><script id="x">a\nb</script><script>alert(1)</script>`,
    );
    assert.deepEqual(inlineScriptHashes(html), [ALERT, A_LF_B]);
  });
  test("attribut contenant « > » ou « src » dans sa valeur", () => {
    const html = page("", `<script data-x="a > src=b" data-src="/y.js">alert(1)</script>`);
    assert.deepEqual(inlineScriptHashes(html), [ALERT]);
  });
  test("script en ligne vide haché aussi", () => {
    assert.deepEqual(inlineScriptHashes(page("", "<script></script>")), [hashScript("")]);
  });
  for (const tag of [`<script src="">x</script>`, `<script src='  '></script>`, `<script src></script>`]) {
    test(`échoue sur un src vide : ${tag}`, () => {
      assert.throws(() => inlineScriptHashes(page("", tag)), CspError);
    });
  }
});

describe("injectCsp", () => {
  test("balise meta en premier élément du <head>", () => {
    const html = page(`<script src="/a.js"></script>`, `<script>alert(1)</script>`);
    const out = injectCsp(html);
    assert.deepEqual(out.hashes, [ALERT]);
    assert.ok(
      out.html.startsWith(
        `<!DOCTYPE html><html lang="fr"><head><meta http-equiv="Content-Security-Policy" content="script-src 'self' '${ALERT}'"/><meta charSet="utf-8"/>`,
      ),
    );
  });
  test("<head> avec attributs", () => {
    const out = injectCsp(`<html><head data-x="1>2"><title>t</title></head></html>`);
    assert.match(out.html, /^<html><head data-x="1>2"><meta http-equiv="Content-Security-Policy" content="script-src 'self'"\/><title>/);
  });
  test("échoue sans <head>", () => {
    assert.throws(() => injectCsp("<html><body><script>x</script></body></html>"), /aucune balise <head>/);
  });
  test("échoue si un script précède le <head>", () => {
    assert.throws(() => injectCsp("<script>x</script><html><head></head></html>"), /précède le <head>/);
  });
  test("échoue si une meta CSP est déjà présente (double passage)", () => {
    const once = injectCsp(page("", "<script>alert(1)</script>")).html;
    assert.throws(() => injectCsp(once), /déjà présente/);
  });
  test("échoue si la meta charset sort des 1024 premiers octets", () => {
    const html = `<html class="${"x".repeat(900)}"><head><meta charset="utf-8"></head><body>${Array.from(
      { length: 10 },
      (_, i) => `<script>${i}</script>`,
    ).join("")}</body></html>`;
    assert.throws(() => injectCsp(html), /1024/);
  });
});

describe("scriptPolicy", () => {
  test("'self' seul sans script en ligne", () => {
    assert.equal(scriptPolicy([]), "script-src 'self'");
  });
});

describe("applyToDir", () => {
  let dir;
  after(async () => {
    if (dir) await rm(dir, { recursive: true, force: true });
  });

  test("traite chaque page (hashes par page), y compris les sous-dossiers", async () => {
    dir = await mkdtemp(path.join(tmpdir(), "csp-"));
    await mkdir(path.join(dir, "404"));
    await mkdir(path.join(dir, "_next"));
    await writeFile(path.join(dir, "index.html"), page("", "<script>alert(1)</script>"));
    await writeFile(path.join(dir, "404", "index.html"), page("", "<script>a\nb</script>"));
    await writeFile(path.join(dir, "_next", "a.js"), "<head>");

    const results = await applyToDir(dir);
    assert.deepEqual(results, [
      { file: "404/index.html", hashes: [A_LF_B] },
      { file: "index.html", hashes: [ALERT] },
    ]);
    assert.match(await readFile(path.join(dir, "index.html"), "utf8"), new RegExp(`'${ALERT.replace(/[+]/g, "\\+")}'`));
    assert.equal(await readFile(path.join(dir, "_next", "a.js"), "utf8"), "<head>");
  });

  test("échoue sur un dossier sans page HTML", async () => {
    const empty = await mkdtemp(path.join(tmpdir(), "csp-empty-"));
    try {
      await assert.rejects(applyToDir(empty), /aucune page HTML/);
    } finally {
      await rm(empty, { recursive: true, force: true });
    }
  });
});

describe("readSiteCsp", () => {
  test("lit la valeur par défaut de site_csp dans infra/prod/variables.tf", async () => {
    const tf = await readFile(new URL("../../infra/prod/variables.tf", import.meta.url), "utf8");
    const csp = readSiteCsp(tf);
    assert.match(csp, /^default-src 'self'; /);
    assert.match(csp, /script-src 'self' 'unsafe-inline'/);
  });
  test("échoue si la variable est absente", () => {
    assert.throws(() => readSiteCsp('variable "autre" { default = "x" }'), CspError);
  });
});
