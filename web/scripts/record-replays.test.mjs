// Tests de scripts/record-replays.mjs et scripts/sync-replays.mjs : `node --test web/scripts/*.test.mjs`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, test } from "node:test";

import {
  checkAttacks,
  checkOutcome,
  findLeaks,
  parseSseBlocks,
  PLAN,
  RecordError,
  sanitizeEvent,
} from "./record-replays.mjs";
import { ReplayFileError, validateReplaySet } from "./sync-replays.mjs";

const ROOT = resolve(import.meta.dirname, "../..");
const FIXTURE = JSON.parse(readFileSync(resolve(ROOT, "web/e2e/fixtures/replays/fr.json"), "utf8"));

const done = (override = null) => ({
  type: "done",
  tokens_in: 1,
  tokens_out: 1,
  cost_usd: 0,
  latency_ms: 1,
  sources: [],
  answer_override: override,
  trace_id: null,
});

describe("record-replays", () => {
  test("plan : FR et EN, questions, annonce et attaque de chaque langue", () => {
    for (const locale of ["fr", "en"]) {
      const kinds = PLAN.filter((e) => e.locale === locale).map((e) => e.kind);
      assert.ok(kinds.filter((k) => k === "question").length >= 3);
      assert.ok(kinds.includes("job_ad"));
      assert.ok(kinds.includes("attack"));
    }
    assert.equal(new Set(PLAN.map((e) => e.id)).size, PLAN.length);
  });

  test("les attaques du plan sont des lignes block de ml/data/adversarial.jsonl", () => {
    const jsonl = readFileSync(resolve(ROOT, "ml/data/adversarial.jsonl"), "utf8");
    checkAttacks(PLAN, jsonl);
    assert.throws(
      () => checkAttacks([{ id: "x", kind: "attack", question: "inventée" }], jsonl),
      RecordError,
    );
  });

  test("SSE : blocs data: (CRLF compris), commentaires ignorés", () => {
    const text = 'data: {"type":"answer","text":"a"}\r\n\r\n: ping\n\ndata: {"type":"llm.progress","tokens":2}\n\n';
    assert.deepEqual(parseSseBlocks(text), [
      { type: "answer", text: "a" },
      { type: "llm.progress", tokens: 2 },
    ]);
  });

  test("nettoyage : trace_id retiré, marqueur eval retiré", () => {
    assert.equal(sanitizeEvent({ ...done(), trace_id: "abc" }).trace_id, null);
    const end = { type: "stage.end", name: "quota", status: "ok", duration_ms: 1, attrs: { eval: true, spent_today_usd: 0.1 } };
    assert.deepEqual(sanitizeEvent(end).attrs, { spent_today_usd: 0.1 });
    assert.deepEqual(end.attrs.eval, true); // l'événement d'origine n'est pas modifié
  });

  test("issue attendue : réponse pour une question, blocage à l'injection pour une attaque", () => {
    const answered = [{ t: 0, event: { type: "answer", text: "ok" } }, { t: 1, event: done() }];
    checkOutcome({ id: "q", kind: "question" }, answered);
    const budget = [
      { t: 0, event: { type: "stage.end", name: "quota", status: "blocked", duration_ms: 1, attrs: {} } },
      { t: 1, event: done("Le budget du jour est atteint : la démo passe en mode rediffusion.") },
    ];
    assert.throws(() => checkOutcome({ id: "q", kind: "question" }, budget), /budget atteint/);
    assert.throws(() => checkOutcome({ id: "a", kind: "attack" }, answered), /injection/);
    const blocked = [
      { t: 0, event: { type: "stage.end", name: "injection", status: "blocked", duration_ms: 1, attrs: {} } },
      { t: 1, event: done("Requête bloquée") },
    ];
    checkOutcome({ id: "a", kind: "attack" }, blocked);
    assert.throws(() => checkOutcome({ id: "q", kind: "question" }, []), /done/);
  });

  test("contenu public seulement : contact public admis, autres courriels, IP, jeton et clé AWS refusés", () => {
    assert.deepEqual(findLeaks("écrire à job@stevelang.net", "t".repeat(32)), []);
    // Clé factice assemblée à l'exécution : aucun motif de clé en clair dans le dépôt.
    const fakeKey = ["AK", "IA", "X".repeat(16)].join("");
    const leaks = findLeaks(`x@y.com 10.0.0.1 ${fakeKey} ${"t".repeat(32)}`, "t".repeat(32));
    assert.equal(leaks.length, 4);
    assert.ok(leaks.includes("EVAL_TOKEN"));
  });
});

describe("sync-replays", () => {
  const prod = { ...FIXTURE, source: "prod" };

  test("un jeu de production valide passe", () => {
    assert.equal(validateReplaySet(prod, "fr"), prod);
  });

  test("la fixture de test n'est jamais livrée", () => {
    assert.throws(() => validateReplaySet(FIXTURE, "fr"), ReplayFileError);
  });

  test("refuse : mauvaise langue, jeu vide, délais décroissants, trace_id, contenu non public", () => {
    assert.throws(() => validateReplaySet(prod, "en"), /langue/);
    assert.throws(() => validateReplaySet({ ...prod, replays: [] }, "fr"), /aucun échange/);
    const [first] = prod.replays;
    const frames = [...first.frames];
    frames.splice(1, 0, { t: 10_000_000, event: frames[1].event });
    assert.throws(() => validateReplaySet({ ...prod, replays: [{ ...first, frames }] }, "fr"), /croissants/);
    const traced = [...first.frames.slice(0, -1), { ...first.frames.at(-1), event: { ...done(), trace_id: "x" } }];
    assert.throws(() => validateReplaySet({ ...prod, replays: [{ ...first, frames: traced }] }, "fr"), /trace_id/);
    const leaky = { ...first, question: "écris à quelqu.un@exemple.com" };
    assert.throws(() => validateReplaySet({ ...prod, replays: [leaky] }, "fr"), /non public/);
  });
});
