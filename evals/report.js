'use strict';

/**
 * Résumé Markdown d'un rapport promptfoo (evals/output/*.json) pour le résumé du run
 * GitHub Actions. Les cas portant `metadata.knownIssue` (ex. `known-fp-4b` : faux
 * positifs du classifieur, tâche 4b) sont listés à part, mais restent des échecs : ce
 * script ne change pas le verdict de la suite (il sort toujours avec le code 0).
 *   node evals/report.js evals/output/nightly.json >> "$GITHUB_STEP_SUMMARY"
 */

const fs = require('node:fs');

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
    for (const f of g.failed) lines.push(`- ${f.description} : ${String(f.reason).replace(/\s+/g, ' ').slice(0, 200)}`);
    lines.push('');
  }
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
