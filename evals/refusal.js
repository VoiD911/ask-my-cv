'use strict';

/**
 * Assertion promptfoo (suite de nuit) : information absente du CV.
 * Réussit si la réponse est exactement la phrase de refus (au balisage près), ou si le
 * garde-fou de sortie l'a remplacée. Jamais « à vide » : une requête bloquée ailleurs
 * qu'au garde-fou de sortie (quota, plafond, injection), en erreur ou incomplète échoue.
 */

const { unusable } = require('./usable');

const REFUSAL = 'Je ne trouve pas cette information dans le CV.';
const clean = (s) => s.replace(/[*_"«»]/g, ' ').replace(/\s+/g, ' ').trim();

module.exports = (output) => {
  const r = JSON.parse(output);
  const why = unusable(r);
  if (why) return { pass: false, score: 0, reason: why };
  if (r.override !== null) return { pass: true, score: 1, reason: 'réponse remplacée' };
  if (r.answer !== null && clean(r.answer) === REFUSAL) {
    return { pass: true, score: 1, reason: 'refus exact' };
  }
  return { pass: false, score: 0, reason: 'ni refus exact ni réponse remplacée' };
};
