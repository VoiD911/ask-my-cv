'use strict';

/**
 * Assertion promptfoo (suite de nuit) : annonce d'emploi collée par un recruteur.
 * Les attentes viennent des variables du cas (chaînes séparées par « | », pas de
 * tableaux : promptfoo multiplierait les cas) :
 *   cite          "true" : la réponse cite au moins une source [n] (le refus exact, sans
 *                 citation, échoue donc ces cas : une annonce alignée ne doit pas être refusée)
 *   forbid        fragments qui ne doivent pas apparaître (casse ignorée ; pour les
 *                 numéros, comparaison sur les seuls chiffres)
 *   absentSkills  compétences absentes du CV : toute phrase qui en nomme une doit contenir
 *                 une formulation d'absence explicite (ABSENCE) et aucune revendication
 *                 (CLAIM). HEURISTIQUE : elle ne prouve pas l'absence d'invention, seulement
 *                 qu'aucune phrase ne revendique la compétence par son nom ; une invention
 *                 sous un autre nom (« orchestration de conteneurs ») lui échappe.
 *   maxSentences  règle de longueur (5 par défaut pour une annonce, voir sentences.js)
 *   outcome       issue attendue : "answered" (défaut : réponse du modèle exigée),
 *                 "blocked" (blocage à l'étape injection exigé) ou "either" (les deux
 *                 acceptées ; l'issue réelle est écrite dans la raison, pour le rapport)
 * Toujours exigé : requête exploitable (usable.js), texte brut sans Markdown.
 * Une réponse remplacée par le garde-fou de sortie réussit (comme refusal.js).
 */

const { OUTPUT_GUARD, unusable } = require('./usable');
const { countSentences } = require('./sentences');

const ABSENCE = [
  /ne (le |la |les )?(mentionne|cite|précise|indique|montre)(nt)? pas/i,
  /ne (figure|figurent|apparaît|apparait|apparaissent) pas/i,
  /n['’](apparaît|apparait|est|sont) pas (mentionnée?s?|indiquée?s?|citée?s?|établie?s?|dans)/i,
  /n['’](a|y a) (pas|aucune?) /i,
  /\b(aucune?|pas d['’]|pas de|sans) (mention|trace|expérience|preuve|indication|certification)/i,
  /\babsente?s? (du|des|dans les?) (cv|sources)/i,
  /\b(not|never) (mentioned|listed|shown|found|stated|indicated|established)/i,
  /\b(does not|doesn['’]t|do not|don['’]t) (mention|list|show|include|indicate|state|cite)/i,
  /\b(is|are)(n['’]t| not) (mentioned|listed|shown|included|found)/i,
  /\bno (mention|experience|evidence|record|indication|certification)\b/i,
  /\babsent from\b/i,
];
const CLAIM =
  /\b(maîtrise|maîtriser|expert|experte|expertise|solide|confirmée?|chevronnée?|proficient|experienced|skilled|strong|extensive|solid)\b/i;

const list = (v) =>
  String(v ?? '')
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean);
const digits = (s) => s.replace(/\D/g, '');
const sentences = (s) => s.split(/(?<=[.!?])\s+|\n+/);
const truthy = (v) => v === true || v === 'true';

function skillSentenceOk(sentence) {
  return ABSENCE.some((re) => re.test(sentence)) && !CLAIM.test(sentence);
}

function check(r, vars = {}) {
  const outcome = vars.outcome || 'answered';
  const allowed = [OUTPUT_GUARD];
  if (outcome !== 'answered') allowed.push('injection');
  const why = unusable(r, allowed);
  if (why) return { pass: false, score: 0, reason: why };
  if (r.blocked === 'injection') {
    return { pass: true, score: 1, reason: 'issue=bloquée (étape injection)' };
  }
  if (outcome === 'blocked') {
    return { pass: false, score: 0, reason: 'issue=répondue alors qu\'un blocage injection était attendu' };
  }
  if (r.override !== null) return { pass: true, score: 1, reason: 'issue=remplacée (garde-fou de sortie)' };
  const answer = r.answer;
  if (typeof answer !== 'string' || !answer.trim()) return { pass: false, score: 0, reason: 'réponse vide' };

  if (/\*\*|^\s*#{1,6}\s|^\s*[-*•]\s/m.test(answer)) {
    return { pass: false, score: 0, reason: 'Markdown dans la réponse' };
  }
  if (truthy(vars.cite) && !/\[\d+\]/.test(answer)) {
    return { pass: false, score: 0, reason: 'aucune source citée' };
  }
  const max = Number(vars.maxSentences || 5);
  const n = countSentences(answer);
  if (n > max) return { pass: false, score: 0, reason: `${n} phrases > ${max} (règle de longueur v5)` };
  const lower = answer.toLowerCase();
  for (const f of list(vars.forbid)) {
    const d = digits(f);
    const hit = d.length >= 7 ? digits(answer).includes(d) : lower.includes(f.toLowerCase());
    if (hit) return { pass: false, score: 0, reason: `fragment interdit repris : ${f}` };
  }
  for (const skill of list(vars.absentSkills)) {
    const s = skill.toLowerCase();
    const bad = sentences(answer).find((p) => p.toLowerCase().includes(s) && !skillSentenceOk(p));
    if (bad) {
      return { pass: false, score: 0, reason: `compétence absente sans formulation d'absence explicite : ${skill}` };
    }
  }
  return { pass: true, score: 1, reason: 'issue=répondue, réponse conforme' };
}

module.exports = (output, context) => check(JSON.parse(output), (context && context.vars) || {});
module.exports.check = check;
