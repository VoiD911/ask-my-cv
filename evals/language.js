'use strict';

/**
 * Langue d'une réponse, par proportion de mots-outils (heuristique simple, sans service
 * externe). Citations [n] et nombres ignorés. `isEnglish` exige plus de mots-outils
 * anglais que français et au moins 15 % de mots-outils anglais parmi les mots.
 */

const EN = new Set(
  'the a an and or of to in on at for with by from as is are was were has have had his her he she it this that these those which who not no does did be been can will would their its'.split(' '),
);
const FR = new Set(
  'le la les l un une des de du d et ou en au aux à dans pour par sur avec est sont a ont il elle son sa ses leur qui que qu ne pas ce cette ces se'.split(' '),
);

function stopwordRatios(text) {
  const words = String(text ?? '')
    .replace(/\[\d+\]/g, ' ')
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .filter(Boolean);
  const total = words.length || 1;
  const en = words.filter((w) => EN.has(w)).length;
  const fr = words.filter((w) => FR.has(w)).length;
  return { en: en / total, fr: fr / total, words: words.length };
}

function isEnglish(text) {
  const { en, fr } = stopwordRatios(text);
  return en > fr && en >= 0.15;
}

module.exports = { isEnglish, stopwordRatios };
