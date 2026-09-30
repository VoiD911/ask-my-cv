'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { summarize } = require('./report');

test('les échecs connus sont listés à part, sans être comptés comme réussis', () => {
  const report = {
    results: {
      results: [
        { success: true, testCase: { description: 'a' } },
        { success: false, testCase: { description: 'b' }, gradingResult: { reason: 'raté' } },
        { success: false, testCase: { description: 'c', metadata: { knownIssue: 'known-fp-4b' } }, gradingResult: { reason: 'bloquée' } },
      ],
    },
  };
  const md = summarize(report);
  assert.match(md, /Cas sans problème connu\n\n1 réussi\(s\), 1 échec\(s\)\n\n- b : raté/);
  assert.match(md, /Échecs connus \(known-fp-4b\) — toujours comptés en échec\n\n0 réussi\(s\), 1 échec\(s\)\n\n- c : bloquée/);
  assert.ok(md.indexOf('sans problème') < md.indexOf('known-fp-4b'));
});

test('#122 : verdict du juge LLM mis en regard de la règle lexicale informative', () => {
  const { INFO_PREFIX } = require('./job_ad');
  const judge = { type: 'javascript', value: 'file://judge.js' };
  const rule = { type: 'javascript', value: 'file://job_ad.js' };
  const report = {
    results: {
      results: [
        {
          success: true,
          testCase: { description: 'annonce A' },
          gradingResult: {
            componentResults: [
              { pass: true, reason: `${INFO_PREFIX} Kubernetes : verbe « pratique »`, assertion: rule },
              { pass: true, reason: 'juge : honest — absence constatée', assertion: judge },
            ],
          },
        },
        {
          success: false,
          testCase: { description: 'annonce B' },
          gradingResult: {
            reason: 'juge : invented — paraphrase',
            componentResults: [
              { pass: true, reason: 'issue=répondue, réponse conforme', assertion: rule },
              { pass: false, reason: 'juge : invented — paraphrase', assertion: judge },
            ],
          },
        },
        { success: true, testCase: { description: 'sans juge' }, gradingResult: { componentResults: [{ pass: true, reason: 'ok', assertion: rule }] } },
      ],
    },
  };
  const md = summarize(report);
  assert.match(md, /### Compétences absentes : juge LLM \(bloquant\) et règle lexicale \(informative\)/);
  assert.match(md, /- annonce A — juge : réussi \(juge : honest — absence constatée\) ; règle : signale Kubernetes : verbe « pratique »/);
  assert.match(md, /- annonce B — juge : ÉCHEC \(juge : invented — paraphrase\) ; règle : rien à signaler/);
  assert.doesNotMatch(md, /sans juge —/);
  // sans cas jugé, pas de section
  assert.doesNotMatch(summarize({ results: { results: [] } }), /Compétences absentes/);
});

test('revue #123 : texte du juge expurgé (ARN, compte) et Markdown neutralisé dans le résumé', () => {
  const judge = { type: 'javascript', value: 'file://judge.js' };
  const reason = 'juge : invented — voir [clic](https://x.example) ![i](y) <img src=x> arn:aws:iam::123456789012:role/r 123456789012';
  const report = {
    results: {
      results: [
        {
          success: false,
          testCase: { description: 'annonce C' },
          gradingResult: { reason, componentResults: [{ pass: false, reason, assertion: judge }] },
        },
      ],
    },
  };
  const md = summarize(report);
  assert.doesNotMatch(md, /123456789012/);
  assert.doesNotMatch(md, /arn:aws:iam/);
  assert.doesNotMatch(md, /<img/);
  assert.ok(md.includes('\\[clic\\]\\(https://x.example\\)'), md);
  assert.ok(md.includes('\\!\\[i\\]\\(y\\)'), md);
});
