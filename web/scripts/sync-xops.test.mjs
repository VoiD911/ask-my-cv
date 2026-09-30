// Tests de scripts/sync-xops.mjs : `node --test web/scripts/*.test.mjs`.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { describe, test } from "node:test";

import {
  assertRepoPath,
  buildXops,
  extractRefs,
  indexWorkflow,
  OUTPUT,
  render,
  REPOSITORY,
  resolveAnchor,
  XopsError,
} from "./sync-xops.mjs";

const ROOT = resolve(import.meta.dirname, "../..");

function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), "xops-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  return root;
}

const WF = [
  "name: ci",
  "on: [push]",
  "jobs:",
  "  security:",
  "    steps:",
  "      - name: Secrets (gitleaks)",
  "        run: |",
  "          echo - name: piège semgrep",
  "      - run: semgrep scan",
  "  deploy:",
  "    needs: security",
  "    steps:",
  "      - uses: actions/checkout@abc # v1",
].join("\n");

describe("références du contenu", () => {
  test("extrait les chemins et les ancres littéraux", () => {
    const ts = '{ label: "a", path: "ml/drift.py" }, { label: "b", anchor: "job:ci.yml:deploy" }, pathname: "x"';
    assert.deepEqual(extractRefs(ts), { paths: ["ml/drift.py"], anchors: ["job:ci.yml:deploy"] });
  });

  test("chemins : relatifs au dépôt seulement", () => {
    assert.equal(assertRepoPath("infra/prod"), "infra/prod");
    for (const bad of ["../x", "/abs", "https://evil.test/x", "a b", "a/./b"]) {
      assert.throws(() => assertRepoPath(bad), XopsError);
    }
  });
});

describe("ancres", () => {
  const root = fixture({
    ".github/workflows/ci.yml": WF,
    "infra/prod/main.tf": 'data "aws_x" "y" {}\nresource "aws_budgets_budget" "monthly" {\n}\n',
    "infra/prod/.terraform/modules/m.tf": 'resource "aws_sqs_queue" "cache" {}\n',
    "settings.aws.yaml": "a: 1\ndaily_cap_usd: 0.5\n",
  });

  test("indexWorkflow : lignes des jobs et des étapes, blocs run ignorés", () => {
    const jobs = indexWorkflow(WF);
    assert.equal(jobs.get("security").line, 4);
    assert.deepEqual(
      jobs.get("security").steps.map((s) => s.line),
      [6, 9],
    );
    assert.equal(jobs.get("deploy").line, 10);
  });

  test("job, étape, ressource Terraform, texte", () => {
    assert.deepEqual(resolveAnchor(root, "job:ci.yml:deploy"), { path: ".github/workflows/ci.yml", line: 10 });
    assert.deepEqual(resolveAnchor(root, "step:ci.yml:security:GITLEAKS"), { path: ".github/workflows/ci.yml", line: 6 });
    assert.deepEqual(resolveAnchor(root, "step:ci.yml:security:semgrep"), { path: ".github/workflows/ci.yml", line: 9 });
    assert.deepEqual(resolveAnchor(root, "tf:aws_budgets_budget.monthly"), { path: "infra/prod/main.tf", line: 2 });
    assert.deepEqual(resolveAnchor(root, "text:settings.aws.yaml#daily_cap_usd:"), { path: "settings.aws.yaml", line: 2 });
  });

  test("toute preuve introuvable échoue", () => {
    for (const bad of [
      "job:ci.yml:absent",
      "job:absent.yml:deploy",
      "step:ci.yml:security:trivy",
      "tf:aws_budgets_budget.autre",
      "tf:aws_sqs_queue.cache", // dossier caché .terraform ignoré
      "text:settings.aws.yaml#absent",
      "text:absent.yaml#a",
      "text:../etc/passwd#root",
      "inconnu:x",
    ]) {
      assert.throws(() => resolveAnchor(root, bad), XopsError, bad);
    }
  });
});

describe("dépôt réel", () => {
  const data = buildXops(ROOT);

  test(`${OUTPUT} est à jour`, () => {
    const committed = readFileSync(resolve(ROOT, OUTPUT), "utf8").replace(/\r\n/g, "\n");
    assert.equal(committed, render(data));
  });

  test("identités Sigstore : workflows du dépôt sur main, émetteur GitHub", () => {
    assert.equal(data.repository, REPOSITORY);
    assert.equal(data.image, `ghcr.io/${REPOSITORY.toLowerCase()}`);
    assert.equal(data.signing.modelIdentity, `https://github.com/${REPOSITORY}/.github/workflows/train.yml@refs/heads/main`);
    assert.equal(data.signing.imageIdentity, `https://github.com/${REPOSITORY}/.github/workflows/ci.yml@refs/heads/main`);
    assert.equal(data.signing.signerWorkflow, `${REPOSITORY}/.github/workflows/ci.yml`);
    assert.equal(data.signing.issuer, "https://token.actions.githubusercontent.com");
  });

  test("release : tag du modèle promu et fichiers publiés", () => {
    const manifest = JSON.parse(readFileSync(resolve(ROOT, "models/prod.json"), "utf8"));
    assert.equal(data.model.version, manifest.version);
    assert.equal(data.model.tag, `model-${manifest.version}`);
    for (const f of ["model.onnx", "model.onnx.sigstore.json", "metrics.json", "model_card.md"]) {
      assert.ok(data.model.assets.includes(f), f);
    }
  });

  test("chaque preuve citée est vérifiée (chemins des deux pages, ancres)", () => {
    const refs = ["web/src/lib/xops-content.ts", "web/src/lib/architecture-content.ts"].map((f) =>
      extractRefs(readFileSync(resolve(ROOT, f), "utf8")),
    );
    for (const r of refs) {
      for (const p of r.paths) assert.ok(data.paths[p], p);
      for (const a of r.anchors) assert.ok(data.anchors[a]?.line > 0, a);
    }
    assert.ok(Object.keys(data.anchors).length >= 20);
  });

  test("aucun identifiant de compte AWS dans les données publiées", () => {
    assert.doesNotMatch(render(data), /\b\d{12}\b/);
  });
});
