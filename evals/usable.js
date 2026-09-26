'use strict';

/**
 * Garde commune aux assertions de nuit : une requête arrêtée par le quota, le plafond de
 * dépense ou une erreur ne prouve rien (ni refus, ni absence de fuite). Elle doit faire
 * échouer le cas au lieu de le laisser passer « à vide ».
 *
 * Les messages ci-dessous sont ceux de src/ask_my_cv/pipeline.py (BLOCK_MESSAGES et
 * ERROR_MESSAGE) ; evals/usable.test.js vérifie qu'ils y figurent toujours.
 */

const OUTPUT_GUARD = 'output_guard';

const UNUSABLE_OVERRIDES = {
  rate_limited: "Trop de questions d'affilée : réessaie dans un moment.",
  budget_exceeded: 'Le budget du jour est atteint : la démo passe en mode rediffusion.',
  error: 'Une erreur est survenue. La trace a été enregistrée.',
};

/**
 * Raison pour laquelle le résumé `r` (voir sse.js) est inexploitable, ou null.
 * `allowedBlocks` : étapes dont un blocage est un résultat légitime du cas.
 */
function unusable(r, allowedBlocks = [OUTPUT_GUARD]) {
  if (r.status !== 200 || !r.done) return `requête en échec (HTTP ${r.status})`;
  if (r.blocked !== null && !allowedBlocks.includes(r.blocked)) {
    return `requête bloquée à l'étape « ${r.blocked} »`;
  }
  const reason = Object.keys(UNUSABLE_OVERRIDES).find((k) => UNUSABLE_OVERRIDES[k] === r.override);
  if (reason) return `requête sans réponse exploitable (${reason})`;
  return null;
}

module.exports = { OUTPUT_GUARD, UNUSABLE_OVERRIDES, unusable };
