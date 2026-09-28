// Next.js builds from web/, so keep the public journal in its source tree.
// Refresh this snapshot from the canonical docs on every production build.
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const source = readFileSync(resolve(root, "docs/journal/index.json"), "utf8");
const archive = JSON.parse(source);
if (archive.version !== 1 || archive.repository !== "VoiD911/ask-my-cv") {
  throw new Error("Journal public incompatible");
}
writeFileSync(resolve(root, "web/src/lib/delivery-archive.json"), source);
