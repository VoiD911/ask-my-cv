'use strict';

/**
 * Assertion promptfoo (suite de nuit) : règle de longueur du prompt v5 pour une question,
 * au plus `maxSentences` phrases (variable du cas, 3 par défaut). Une requête sans
 * réponse exploitable n'est pas jugée ici (les autres assertions du cas la font échouer).
 */

const { countSentences } = require('./sentences');

module.exports = (output, context) => {
  const r = JSON.parse(output);
  if (typeof r.answer !== 'string') return { pass: true, score: 1, reason: 'pas de réponse à mesurer' };
  const max = Number((context && context.vars && context.vars.maxSentences) || 3);
  const n = countSentences(r.answer);
  return n <= max
    ? { pass: true, score: 1, reason: `${n} phrase(s) ≤ ${max}` }
    : { pass: false, score: 0, reason: `${n} phrases > ${max} (règle de longueur v5)` };
};
