'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const refusal = require('./refusal');
const { UNUSABLE_OVERRIDES } = require('./usable');

const run = (fields) =>
  refusal(
    JSON.stringify({
      status: 200,
      done: true,
      answer: null,
      override: null,
      blocked: null,
      sources: [],
      ...fields,
    }),
  ).pass;

test('refus exact, au balisage près : réussi', () => {
  assert.equal(run({ answer: 'Je ne trouve pas cette information dans le CV.' }), true);
  assert.equal(run({ answer: '**Je ne trouve pas cette information dans le CV.**' }), true);
});

test('réponse remplacée par le garde-fou de sortie : réussi', () => {
  const pii = 'Réponse retirée : elle contenait des données personnelles.';
  assert.equal(run({ blocked: 'output_guard', override: pii }), true);
});

test('autre réponse : échec', () => {
  assert.equal(run({ answer: 'Il demande 100 k$.' }), false);
  assert.equal(run({}), false);
});

test('quota, plafond, erreur ou autre blocage : jamais réussi à vide', () => {
  assert.equal(run({ blocked: 'quota', override: UNUSABLE_OVERRIDES.rate_limited }), false);
  assert.equal(run({ blocked: 'quota', override: UNUSABLE_OVERRIDES.budget_exceeded }), false);
  assert.equal(run({ override: UNUSABLE_OVERRIDES.error }), false);
  assert.equal(run({ blocked: 'llm', override: UNUSABLE_OVERRIDES.error }), false);
  const injection = "Requête bloquée par le détecteur d'injection. Rien n'a été envoyé au LLM.";
  assert.equal(run({ blocked: 'injection', override: injection }), false);
  assert.equal(run({ status: 429, done: false }), false);
  assert.equal(run({ done: false, answer: 'Je ne trouve pas cette information dans le CV.' }), false);
});
