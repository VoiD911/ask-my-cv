'use strict';

/**
 * Résumé Markdown d'un rapport promptfoo (evals/output/*.json) pour le résumé du run
 * GitHub Actions. Les cas portant `metadata.knownIssue` (ex. `known-fp-annonce-en` : faux
 * positifs connus du classifieur promu) sont listés à part, mais restent des échecs : ce
 * script ne change pas le verdict de la suite (il sort toujours avec le code 0).
 * Compétences absentes (#122) : pour chaque cas jugé par judge.js, le verdict du juge LLM est
 * mis en regard de la règle lexicale de job_ad.js, devenue informative (préfixe INFO_PREFIX).
 *   node evals/report.js evals/output/nightly.json >> "$GITHUB_STEP_SUMMARY"
 */

const fs = require('node:fs');
const { INFO_PREFIX } = require('./job_ad');
const { redact } = require('./judge');

// texte de modèle ou d'erreur inséré dans le résumé public : ARN et numéros de compte
// expurgés, Markdown et HTML neutralisés (pas de lien, d'image ni de balise arbitraires)
const escapeMd = (text) =>
  text.replace(/[\\`*_[\]()!|#~]/g, '\\$&').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const oneLine = (text) => escapeMd(redact(String(text).replace(/\s+/g, ' ').slice(0, 200)));

/** Juge LLM vs règle lexicale, pour les cas passés par judge.js. */
function skillComparison(rows) {
  const lines = [];
  for (const row of rows) {
    const parts = (row.gradingResult && row.gradingResult.componentResults) || [];
    const judged = parts.find((c) => c.assertion && /judge\.js$/.test(String(c.assertion.value)));
    if (!judged) continue;
    const rule = parts.find((c) => typeof c.reason === 'string' && c.reason.startsWith(INFO_PREFIX));
    const verdict = judged.pass ? 'réussi' : 'ÉCHEC';
    const ruleText = rule ? `signale ${oneLine(rule.reason.slice(INFO_PREFIX.length).trim())}` : 'rien à signaler';
    const tc = row.testCase || {};
    lines.push(`- ${tc.description || '(sans description)'} — juge : ${verdict} (${oneLine(judged.reason)}) ; règle : ${ruleText}`);
  }
  if (!lines.length) return [];
  return ['### Compétences absentes : juge LLM (bloquant) et règle lexicale (informative)', '', ...lines, ''];
}

function summarize(report) {
  const rows = (report.results && report.results.results) || [];
  const groups = new Map();
  for (const row of rows) {
    const tc = row.testCase || {};
    const key = (tc.metadata && tc.metadata.knownIssue) || '';
    if (!groups.has(key)) groups.set(key, { passed: 0, failed: [] });
    const g = groups.get(key);
    if (row.success) g.passed += 1;
    else g.failed.push({ description: tc.description || '(sans description)', reason: (row.gradingResult && row.gradingResult.reason) || row.error || '' });
  }
  const lines = ['## Évaluation promptfoo', ''];
  const order = [...groups.keys()].sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)));
  for (const key of order) {
    const g = groups.get(key);
    const title = key ? `Échecs connus (${key}) — toujours comptés en échec` : 'Cas sans problème connu';
    lines.push(`### ${title}`, '', `${g.passed} réussi(s), ${g.failed.length} échec(s)`, '');
    for (const f of g.failed) lines.push(`- ${f.description} : ${oneLine(f.reason)}`);
    lines.push('');
  }
  lines.push(...skillComparison(rows));
  return lines.join('\n');
}

if (require.main === module) {
  const file = process.argv[2];
  try {
    process.stdout.write(summarize(JSON.parse(fs.readFileSync(file, 'utf8'))) + '\n');
  } catch (err) {
    process.stdout.write(`Rapport promptfoo illisible (${file}) : ${err.message}\n`);
  }
}

module.exports = { summarize };
