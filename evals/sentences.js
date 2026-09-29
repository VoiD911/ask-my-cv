'use strict';

/**
 * Comptage de phrases tolérant à la segmentation, pour la règle de longueur du prompt (v5 et suivants)
 * (3 phrases au plus pour une question, 5 pour une annonce). Avant de couper sur . ! ? :
 * citations [n] retirées, nombres décimaux et abréviations courantes (p. ex., e.g., inc.,
 * M., Dr, etc.) protégés. Un segment sans lettre ne compte pas.
 */

const ABBREVIATIONS = /\b(p\. ?ex|e\.g|i\.e|etc|inc|ltd|corp|m|mme|dr|st|vs|no|nº|cf|env)\./gi;

function countSentences(text) {
  const t = String(text ?? '')
    .replace(/\[\d+\]/g, '')
    .replace(/(\d)\.(\d)/g, '$1,$2')
    .replace(ABBREVIATIONS, (m) => m.replace(/\./g, ''))
    .replace(/\b([A-Z])\.(?=[A-Z]\.)/g, '$1'); // sigles pointés (U.S.)
  return t
    .split(/[.!?…]+(?=\s|$|["»”)])|\n+/)
    .filter((s) => /\p{L}/u.test(s)).length;
}

module.exports = { countSentences };
