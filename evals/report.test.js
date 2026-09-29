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
