'use strict';

/**
 * Cas promptfoo (suite PR) : bornes de longueur du texte soumis (MAX_QUESTION_CHARS de
 * src/ask_my_cv/pipeline.py). Le texte est tiré des annonces réalistes de fixtures/,
 * mises bout à bout puis coupées au caractère près (points de code, comme Python) :
 *   10 000 caractères -> accepté à la réception (HTTP 200, flux complet, pas de blocage
 *     `reception`) ; le traitement complet n'est pas exigé : le classifieur peut bloquer ;
 *   10 001 caractères -> refusé par la validation (HTTP 422).
 */

const fs = require('node:fs');
const path = require('node:path');

const MAX = 10_000;
const FIXTURES = ['annonce_longue_fr.txt', 'job_ad_long_en.txt'].map((f) =>
  path.join(__dirname, 'fixtures', f),
);

function textOf(length) {
  const chars = Array.from(FIXTURES.map((f) => fs.readFileSync(f, 'utf8')).join('\n\n'));
  if (chars.length < length) throw new Error(`annonces trop courtes pour ${length} caractères`);
  return chars.slice(0, length).join('');
}

module.exports = function boundsTests() {
  return [
    {
      description: `annonce de ${MAX} caractères (borne) — acceptée à la réception (pas de 422)`,
      vars: { question: textOf(MAX) },
      assert: [
        {
          type: 'javascript',
          value: '((r) => r.status === 200 && r.done && r.blocked !== "reception")(JSON.parse(output))',
        },
      ],
    },
    {
      description: `annonce de ${MAX + 1} caractères — refusée (422)`,
      vars: { question: textOf(MAX + 1) },
      assert: [
        {
          type: 'javascript',
          value: '((r) => r.status === 422 && r.answer === null)(JSON.parse(output))',
        },
      ],
    },
  ];
};

module.exports.textOf = textOf;
module.exports.MAX = MAX;
