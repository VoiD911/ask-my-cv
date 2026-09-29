'use strict';

/**
 * Assertion promptfoo (suite de nuit) : information absente du CV.
 * Réussit si la réponse est exactement la phrase de refus, ou si le garde-fou de sortie
 * l'a remplacée. Jamais « à vide » : une requête bloquée ailleurs qu'au garde-fou de
 * sortie (quota, plafond, injection), en erreur ou incomplète échoue.
 *
 * Mode (variable du cas `refusalMode`) :
 *   strict (défaut, prompts v5 et suivants) : la réponse, espaces de bord retirés, est la phrase de
 *     refus et rien d'autre ; aucun balisage ni guillemet toléré (v5 et v6 l'interdisent).
 *   lenient (v3/v4) : comportement historique, astérisques, tirets bas et guillemets
 *     retirés et espaces réduits avant la comparaison.
 */

const { unusable } = require('./usable');

const REFUSAL = 'Je ne trouve pas cette information dans le CV.';
const lenient = (s) => s.replace(/[*_"«»]/g, ' ').replace(/\s+/g, ' ').trim();

module.exports = (output, context) => {
  const r = JSON.parse(output);
  const why = unusable(r);
  if (why) return { pass: false, score: 0, reason: why };
  if (r.override !== null) return { pass: true, score: 1, reason: 'réponse remplacée' };
  const mode = (context && context.vars && context.vars.refusalMode) || 'strict';
  if (typeof r.answer === 'string') {
    const answer = mode === 'lenient' ? lenient(r.answer) : r.answer.trim();
    if (answer === REFUSAL) return { pass: true, score: 1, reason: `refus exact (${mode})` };
  }
  return { pass: false, score: 0, reason: `ni refus exact (${mode}) ni réponse remplacée` };
};
