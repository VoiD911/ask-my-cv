// Serveur de test : sert l'export statique (web/out) et relaie /api/* vers l'API locale
// en retirant le préfixe /api, comme le comportement CloudFront `/api/*` (fonction strip-api).
// Sert aussi l'en-tête CSP de production (valeur par défaut de `site_csp`, lue dans
// infra/prod/variables.tf) : le navigateur applique l'intersection avec la CSP meta insérée
// au build par scripts/csp.mjs, comme en production.
// Aucune dépendance : node: seulement. Réservé aux tests e2e et à la vérification visuelle.
import { createReadStream, readFileSync } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readSiteCsp } from "../scripts/csp.mjs";

const ROOT = path.resolve(fileURLToPath(new URL("../out", import.meta.url)));
const PORT = Number(process.env.E2E_PORT ?? 4173);
const API = new URL(process.env.E2E_API ?? "http://127.0.0.1:8000");
const SITE_CSP = readSiteCsp(readFileSync(new URL("../../infra/prod/variables.tf", import.meta.url), "utf8"));

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".pdf": "application/pdf",
  ".woff2": "font/woff2",
};

function proxy(req, res) {
  const target = req.url.slice("/api".length) || "/";
  const upstream = http.request(
    {
      hostname: API.hostname,
      port: API.port,
      path: target,
      method: req.method,
      headers: { ...req.headers, host: API.host },
    },
    (up) => {
      res.writeHead(up.statusCode ?? 502, up.headers);
      up.pipe(res);
    },
  );
  upstream.on("error", () => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end("API locale injoignable");
  });
  // Visiteur parti (bouton « Arrêter ») : on coupe aussi la requête vers l'API.
  res.on("close", () => upstream.destroy());
  req.pipe(upstream);
}

async function resolveFile(urlPath) {
  let rel = decodeURIComponent(urlPath.split("?")[0] ?? "/");
  if (rel.endsWith("/")) rel += "index.html";
  const file = path.resolve(ROOT, `.${rel}`);
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) return null;
  try {
    const info = await stat(file);
    if (info.isFile()) return file;
    if (info.isDirectory()) return resolveFile(`${rel}/`);
  } catch {
    return null;
  }
  return null;
}

const server = http.createServer(async (req, res) => {
  const url = req.url ?? "/";
  if (url === "/api" || url.startsWith("/api/")) return proxy(req, res);
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405).end();
    return;
  }
  const file = await resolveFile(url);
  if (!file) {
    const notFound = await resolveFile("/404.html");
    res.writeHead(404, { "content-type": TYPES[".html"], "content-security-policy": SITE_CSP });
    if (notFound) createReadStream(notFound).pipe(res);
    else res.end("introuvable");
    return;
  }
  res.writeHead(200, {
    "content-type": TYPES[path.extname(file)] ?? "application/octet-stream",
    "content-security-policy": SITE_CSP,
  });
  if (req.method === "HEAD") res.end();
  else createReadStream(file).pipe(res);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`web/out servi sur http://127.0.0.1:${PORT} (API : ${API.origin})`);
});
