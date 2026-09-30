'use strict';

/**
 * Calibration du juge LLM (#122) sur un jeu étiqueté : evals/fixtures/judge_calibration.jsonl
 * (une ligne JSON par cas : id, source, absentSkills « | », label honest|invented|ambiguous,
 * split dev|test, adversarial, answer, note).
 * Contenu : cas positifs et négatifs de la règle « compétence absente » de job_ad.test.js,
 * paraphrases de #122, réponses réelles des nightlies (dont les 2 faux échecs du nightly
 * 36656267226) et cas adversariaux (injection contre le juge, revue de sécurité de #123).
 *
 * Partition figée dans le fichier : dev (≈ 60 %) et test tenu à l'écart (≈ 40 %), stratifiée
 * par étiquette (et à part pour les cas adversariaux), par tri sur sha256("judge-split-v1:"+id).
 * La consigne du juge ne s'ajuste que sur les échecs de dev ; test mesure la généralisation.
 * `ambiguous` : rapporté à part, exclu de l'accord et des critères d'acceptation.
 *
 * Appelle Bedrock (mêmes code, consigne et profils que la suite de nuit : judge.js) :
 *   AWS_PROFILE=… node evals/judge_calibration.js [--split dev|test|all] [--model haiku|sonnet]
 *                                                 [--file chemin.jsonl] [--json sortie.json]
 * Code de sortie 0, sauf jeu ou option invalide (2).
 */

const fs = require('node:fs');
const path = require('node:path');
const { judge, resolveModel, REGION } = require('./judge');

const LABELS = new Set(['honest', 'invented', 'ambiguous']);
const SPLITS = new Set(['dev', 'test']);

/** Lit le JSONL étiqueté ; lève une erreur précise (ligne) si un cas est invalide. */
function parseDataset(text) {
  const rows = [];
  const ids = new Set();
  text.split(/\r?\n/).forEach((line, i) => {
    if (!line.trim()) return;
    let row;
    try {
      row = JSON.parse(line);
    } catch (err) {
      throw new Error(`ligne ${i + 1} : JSON invalide (${err.message})`);
    }
    if (!row || typeof row.id !== 'string' || !row.id) throw new Error(`ligne ${i + 1} : id manquant`);
    if (ids.has(row.id)) throw new Error(`ligne ${i + 1} : id en double (${row.id})`);
    if (!LABELS.has(row.label)) throw new Error(`ligne ${i + 1} : label « ${row.label} » (honest|invented|ambiguous attendu)`);
    if (!SPLITS.has(row.split)) throw new Error(`ligne ${i + 1} : split « ${row.split} » (dev|test attendu)`);
    if (typeof row.answer !== 'string' || !row.answer.trim()) throw new Error(`ligne ${i + 1} : answer vide`);
    if (typeof row.absentSkills !== 'string' || !row.absentSkills.split('|').some((s) => s.trim())) {
      throw new Error(`ligne ${i + 1} : absentSkills vide`);
    }
    if (row.adversarial && row.label !== 'invented') throw new Error(`ligne ${i + 1} : cas adversarial non étiqueté invented`);
    ids.add(row.id);
    rows.push(row);
  });
  if (!rows.length) throw new Error('jeu de calibration vide');
  return rows;
}

function selectSplit(rows, split) {
  if (split === 'all') return rows;
  if (!SPLITS.has(split)) throw new Error(`--split « ${split} » (dev|test|all attendu)`);
  return rows.filter((r) => r.split === split);
}

/** Juge chaque cas (séquentiel : quelques dizaines d'appels, pas de rafale). */
async function runCalibration(rows, invoke, modelName) {
  const results = [];
  for (const row of rows) {
    try {
      const v = await judge(row.answer, row.absentSkills, invoke, modelName);
      const verdict = v.verdict === null ? null : v.pass ? 'honest' : 'invented';
      results.push({ ...row, verdict, rawVerdict: v.verdict, tripwire: v.tripwire, reason: v.reason, inputTokens: v.inputTokens, outputTokens: v.outputTokens });
    } catch (err) {
      const name = String((err && err.name) || 'Error').replace(/[^A-Za-z0-9_.-]/g, '');
      results.push({ ...row, verdict: 'error', reason: name, inputTokens: 0, outputTokens: 0 });
    }
  }
  return results;
}

/**
 * Agrégat. verdict (décision effective, fil-piège compris) : honest | invented | null
 * (illisible) | 'error'. Illisibles, erreurs et cas ambigus ne comptent pas dans l'accord.
 */
function aggregate(results, price) {
  const scored = results.filter((r) => r.label !== 'ambiguous');
  const judged = scored.filter((r) => r.verdict === 'honest' || r.verdict === 'invented');
  const agree = judged.filter((r) => r.verdict === r.label);
  const falsePasses = judged.filter((r) => r.label === 'invented' && r.verdict === 'honest');
  const falseFails = judged.filter((r) => r.label === 'honest' && r.verdict === 'invented');
  const inputTokens = results.reduce((s, r) => s + (r.inputTokens || 0), 0);
  const outputTokens = results.reduce((s, r) => s + (r.outputTokens || 0), 0);
  const cost = price ? (inputTokens * price.input + outputTokens * price.output) / 1e6 : 0;
  return {
    total: results.length,
    honest: results.filter((r) => r.label === 'honest').length,
    invented: results.filter((r) => r.label === 'invented').length,
    adversarial: results.filter((r) => r.adversarial).length,
    judged: judged.length,
    agreement: judged.length ? agree.length / judged.length : 0,
    falsePasses,
    adversarialFalsePasses: falsePasses.filter((r) => r.adversarial),
    falseFails,
    tripwires: results.filter((r) => r.tripwire),
    ambiguous: results.filter((r) => r.label === 'ambiguous'),
    unreadable: scored.filter((r) => r.verdict === null || r.verdict === undefined),
    errors: results.filter((r) => r.verdict === 'error'),
    inputTokens,
    outputTokens,
    costUsd: cost,
    costPerCaseUsd: results.length ? cost / results.length : 0,
  };
}

function formatReport(agg, meta = {}) {
  const pct = (x) => `${(x * 100).toFixed(1)} %`;
  const item = (r) => `- ${r.id} [${r.absentSkills}] ${r.answer.replace(/\s+/g, ' ').slice(0, 160)} — ${r.verdict ?? 'illisible'} : ${r.reason || ''}`;
  return [
    `Juge : ${meta.modelId || '?'} (${REGION}) ; partition : ${meta.split || '?'}`,
    `Cas : ${agg.total} (${agg.honest} honest, ${agg.invented} invented dont ${agg.adversarial} adversariaux, ${agg.ambiguous.length} ambiguous) ; jugés : ${agg.judged}`,
    `Accord (hors ambiguous) : ${pct(agg.agreement)}`,
    `Fausses réussites (invention non détectée) : ${agg.falsePasses.length} (dont adversariales : ${agg.adversarialFalsePasses.length})`,
    ...agg.falsePasses.map(item),
    `Faux échecs (réponse honnête refusée) : ${agg.falseFails.length}`,
    ...agg.falseFails.map(item),
    `Fil-piège déclenché (honest du modèle renversé) : ${agg.tripwires.length}`,
    ...agg.tripwires.map(item),
    `Ambigus (hors critères) : ${agg.ambiguous.length}`,
    ...agg.ambiguous.map(item),
    `Verdicts illisibles : ${agg.unreadable.length}`,
    ...agg.unreadable.map(item),
    `Appels en échec : ${agg.errors.length}`,
    ...agg.errors.map(item),
    `Jetons : ${agg.inputTokens} en entrée, ${agg.outputTokens} en sortie`,
    `Coût estimé : ${agg.costUsd.toFixed(4)} USD (${agg.costPerCaseUsd.toFixed(5)} USD par cas, ` +
      `prix catalogue ${meta.price ? `${meta.price.input} $/${meta.price.output} $` : '?'} par million de jetons, à confirmer sur la page Bedrock)`,
  ].join('\n');
}

function argValue(argv, name, fallback) {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : fallback;
}

async function main(argv) {
  const file = argValue(argv, '--file', path.join(__dirname, 'fixtures', 'judge_calibration.jsonl'));
  const split = argValue(argv, '--split', 'all');
  let rows;
  let model;
  try {
    model = resolveModel(argValue(argv, '--model'));
    rows = selectSplit(parseDataset(fs.readFileSync(file, 'utf8')), split);
  } catch (err) {
    process.stderr.write(`Calibration impossible (${file}) : ${err.message}\n`);
    return 2;
  }
  const results = await runCalibration(rows, undefined, model.key);
  const agg = aggregate(results, model.price);
  process.stdout.write(formatReport(agg, { modelId: model.id, split, price: model.price }) + '\n');
  const out = argValue(argv, '--json');
  if (out) {
    const ids = (list) => list.map((r) => r.id);
    const summary = {
      ...agg,
      model: model.id,
      split,
      falsePasses: ids(agg.falsePasses),
      adversarialFalsePasses: ids(agg.adversarialFalsePasses),
      falseFails: ids(agg.falseFails),
      tripwires: ids(agg.tripwires),
      ambiguous: ids(agg.ambiguous),
      unreadable: ids(agg.unreadable),
      errors: ids(agg.errors),
    };
    fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
    fs.writeFileSync(out, JSON.stringify({ summary, results }, null, 2));
  }
  return 0;
}

if (require.main === module) {
  main(process.argv.slice(2)).then((code) => {
    process.exitCode = code;
  });
}

module.exports = { parseDataset, selectSplit, runCalibration, aggregate, formatReport, main };
