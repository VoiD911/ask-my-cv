'use strict';

/**
 * Calibration du juge LLM (#122) sur un jeu étiqueté : evals/fixtures/judge_calibration.jsonl
 * (une ligne JSON par cas : id, source, absentSkills « | », label honest|invented, answer, note).
 * Contenu : tous les cas positifs et négatifs de la règle « compétence absente » de
 * job_ad.test.js, les paraphrases citées dans #122 et les réponses réelles des nightlies
 * (evals/fixtures/nightly_*.json, toutes honnêtes, dont les 2 faux échecs du nightly 36656267226).
 *
 * Appelle Bedrock (mêmes code, prompt et modèle que la suite de nuit : judge.js) : identifiants
 * AWS requis (rôle autorisé à invoquer le profil US de Claude Haiku 4.5 depuis ca-central-1).
 *   AWS_PROFILE=… node evals/judge_calibration.js [--file chemin.jsonl] [--json sortie.json]
 * Sortie : accord, fausses réussites (invention non détectée), faux échecs, verdicts illisibles,
 * jetons et coût estimé. Code de sortie 0, sauf jeu illisible (2).
 */

const fs = require('node:fs');
const path = require('node:path');
const { judge, MODEL_ID, REGION } = require('./judge');

// Prix catalogue de Claude Haiku 4.5 (USD par million de jetons) : 1 $ en entrée, 5 $ en sortie
// (tarif Anthropic ; sur Bedrock, les profils géographiques comme `us.` peuvent coûter un peu
// plus que le profil global : vérifier https://aws.amazon.com/bedrock/pricing/).
const PRICE_PER_MTOK = { input: 1, output: 5 };
const LABELS = new Set(['honest', 'invented']);

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
    if (!LABELS.has(row.label)) throw new Error(`ligne ${i + 1} : label « ${row.label} » (honest|invented attendu)`);
    if (typeof row.answer !== 'string' || !row.answer.trim()) throw new Error(`ligne ${i + 1} : answer vide`);
    if (typeof row.absentSkills !== 'string' || !row.absentSkills.split('|').some((s) => s.trim())) {
      throw new Error(`ligne ${i + 1} : absentSkills vide`);
    }
    ids.add(row.id);
    rows.push(row);
  });
  if (!rows.length) throw new Error('jeu de calibration vide');
  return rows;
}

/** Juge chaque cas (séquentiel : quelques dizaines d'appels, pas de rafale). */
async function runCalibration(rows, invoke) {
  const results = [];
  for (const row of rows) {
    try {
      const v = await judge(row.answer, row.absentSkills, invoke);
      results.push({ ...row, verdict: v.verdict, reason: v.reason, inputTokens: v.inputTokens, outputTokens: v.outputTokens });
    } catch (err) {
      results.push({ ...row, verdict: 'error', reason: `${err.name || 'Error'} : ${err.message}`, inputTokens: 0, outputTokens: 0 });
    }
  }
  return results;
}

/**
 * Agrégat. verdict : honest | invented | null (illisible) | 'error' (appel en échec).
 * Illisibles et erreurs ne comptent ni en accord ni en désaccord : ils sont listés à part.
 */
function aggregate(results, price = PRICE_PER_MTOK) {
  const judged = results.filter((r) => r.verdict === 'honest' || r.verdict === 'invented');
  const agree = judged.filter((r) => r.verdict === r.label);
  const falsePasses = judged.filter((r) => r.label === 'invented' && r.verdict === 'honest');
  const falseFails = judged.filter((r) => r.label === 'honest' && r.verdict === 'invented');
  const unreadable = results.filter((r) => r.verdict === null || r.verdict === undefined);
  const errors = results.filter((r) => r.verdict === 'error');
  const inputTokens = results.reduce((s, r) => s + (r.inputTokens || 0), 0);
  const outputTokens = results.reduce((s, r) => s + (r.outputTokens || 0), 0);
  const cost = (inputTokens * price.input + outputTokens * price.output) / 1e6;
  return {
    total: results.length,
    honest: results.filter((r) => r.label === 'honest').length,
    invented: results.filter((r) => r.label === 'invented').length,
    judged: judged.length,
    agreement: judged.length ? agree.length / judged.length : 0,
    falsePasses,
    falseFails,
    unreadable,
    errors,
    inputTokens,
    outputTokens,
    costUsd: cost,
    costPerCaseUsd: results.length ? cost / results.length : 0,
  };
}

function formatReport(agg) {
  const pct = (x) => `${(x * 100).toFixed(1)} %`;
  const item = (r) => `- ${r.id} [${r.absentSkills}] ${r.answer.replace(/\s+/g, ' ').slice(0, 160)} — ${r.reason || ''}`;
  const lines = [
    `Juge : ${MODEL_ID} (${REGION}), température 0`,
    `Cas : ${agg.total} (${agg.honest} honest, ${agg.invented} invented) ; jugés : ${agg.judged}`,
    `Accord : ${pct(agg.agreement)}`,
    `Fausses réussites (invention non détectée) : ${agg.falsePasses.length}`,
    ...agg.falsePasses.map(item),
    `Faux échecs (réponse honnête refusée) : ${agg.falseFails.length}`,
    ...agg.falseFails.map(item),
    `Verdicts illisibles : ${agg.unreadable.length}`,
    ...agg.unreadable.map(item),
    `Appels en échec : ${agg.errors.length}`,
    ...agg.errors.map(item),
    `Jetons : ${agg.inputTokens} en entrée, ${agg.outputTokens} en sortie`,
    `Coût estimé : ${agg.costUsd.toFixed(4)} USD (${agg.costPerCaseUsd.toFixed(5)} USD par cas, ` +
      `${PRICE_PER_MTOK.input} $/${PRICE_PER_MTOK.output} $ par million de jetons)`,
  ];
  return lines.join('\n');
}

function argValue(argv, name) {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
}

async function main(argv) {
  const file = argValue(argv, '--file') || path.join(__dirname, 'fixtures', 'judge_calibration.jsonl');
  let rows;
  try {
    rows = parseDataset(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    process.stderr.write(`Jeu de calibration illisible (${file}) : ${err.message}\n`);
    return 2;
  }
  const results = await runCalibration(rows);
  const agg = aggregate(results);
  process.stdout.write(formatReport(agg) + '\n');
  const out = argValue(argv, '--json');
  if (out) fs.writeFileSync(out, JSON.stringify({ summary: { ...agg, falsePasses: agg.falsePasses.map((r) => r.id), falseFails: agg.falseFails.map((r) => r.id), unreadable: agg.unreadable.map((r) => r.id), errors: agg.errors.map((r) => r.id) }, results }, null, 2));
  return 0;
}

if (require.main === module) {
  main(process.argv.slice(2)).then((code) => {
    process.exitCode = code;
  });
}

module.exports = { parseDataset, runCalibration, aggregate, formatReport, PRICE_PER_MTOK };
