// Tests de scripts/sync-architecture.mjs : `node --test web/scripts/*.test.mjs`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

import {
  ArchitectureError,
  buildArchitecture,
  classifyResource,
  OUTPUT,
  parseStages,
  parseTerraform,
  parseWorkflow,
  render,
} from "./sync-architecture.mjs";

const ROOT = resolve(import.meta.dirname, "../..");

describe("parseWorkflow", () => {
  const yaml = [
    "name: ci",
    "on:",
    "  push:",
    "    branches: [main]",
    "  pull_request:",
    "jobs:",
    "  # commentaire",
    "  a:",
    "    runs-on: ubuntu-latest",
    "    steps:",
    "      - name: Première étape (#11)",
    "        run: |",
    "          echo - name: piège",
    "      - run: npm test",
    "      - uses: actions/checkout@abc # v1",
    "  b:",
    "    needs: a",
    "    steps:",
    '      - name: "Citée"',
    "  c:",
    "    needs:",
    "      - a",
    "      - b",
    "    steps: []",
    "  d:",
    "    needs: [a, c]",
  ].join("\n");

  test("nom, déclencheurs, jobs, needs sous toutes les formes et rangs", () => {
    const wf = parseWorkflow(yaml);
    assert.equal(wf.name, "ci");
    assert.deepEqual(wf.triggers, ["push", "pull_request"]);
    assert.deepEqual(
      wf.jobs.map((j) => [j.id, j.needs, j.layer]),
      [
        ["a", [], 0],
        ["b", ["a"], 1],
        ["c", ["a", "b"], 2],
        ["d", ["a", "c"], 3],
      ],
    );
    assert.deepEqual(wf.jobs[0].steps, ["Première étape (#11)", "npm test"]);
    assert.deepEqual(wf.jobs[1].steps, ["Citée"]);
  });

  test("déclencheurs en ligne", () => {
    assert.deepEqual(parseWorkflow("name: x\non: [push, workflow_dispatch]\njobs:\n  a:\n").triggers, [
      "push",
      "workflow_dispatch",
    ]);
  });

  test("needs inconnu ou cyclique : erreur", () => {
    assert.throws(() => parseWorkflow("name: x\njobs:\n  a:\n    needs: z\n"), ArchitectureError);
    assert.throws(
      () => parseWorkflow("name: x\njobs:\n  a:\n    needs: b\n  b:\n    needs: a\n"),
      /cycle/,
    );
  });
});

describe("Terraform", () => {
  test("ne garde que les blocs resource", () => {
    const tf = 'data "aws_iam_policy_document" "p" {}\nresource "aws_lambda_function" "api" {\n  # resource "x" "y"\n}\n';
    assert.deepEqual(parseTerraform(tf), [{ type: "aws_lambda_function", name: "api" }]);
  });

  test("rôles : bucket du site en bordure, état Terraform en données, inconnu refusé", () => {
    assert.equal(classifyResource("aws_s3_bucket_policy", "site"), "edge");
    assert.equal(classifyResource("aws_s3_bucket", "state"), "data");
    assert.equal(classifyResource("awscc_dynamodb_table", "chunks"), "data");
    assert.equal(classifyResource("aws_bedrock_guardrail", "annonces"), "ai");
    assert.throws(() => classifyResource("aws_sqs_queue", "q"), /sans rôle/);
  });
});

test("parseStages lit le tuple Python", () => {
  const py = 'PIPELINE_STAGES: tuple[str, ...] = (\n    "reception",\n    "llm",\n)\n';
  assert.deepEqual(parseStages(py), ["reception", "llm"]);
  assert.throws(() => parseStages("STAGES = ()"), ArchitectureError);
});

describe("dépôt réel", () => {
  const data = buildArchitecture(ROOT);

  test(`${OUTPUT} est à jour`, () => {
    const committed = readFileSync(resolve(ROOT, OUTPUT), "utf8").replace(/\r\n/g, "\n");
    assert.equal(committed, render(data));
  });

  test("le déploiement attend tous les autres jobs de la CI", () => {
    const ci = data.workflows.find((w) => w.file.endsWith("ci.yml"));
    const deploy = ci.jobs.find((j) => j.id === "deploy");
    assert.deepEqual(
      [...deploy.needs].sort(),
      ci.jobs
        .filter((j) => j.id !== "deploy")
        .map((j) => j.id)
        .sort(),
    );
  });

  test("aucun identifiant de compte AWS dans les données publiées", () => {
    assert.doesNotMatch(render(data), /\b\d{12}\b/);
  });
});
