'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const jobAd = require('./job_ad');
const { UNUSABLE_OVERRIDES } = require('./usable');

const run = (fields, vars = {}) =>
  jobAd(
    JSON.stringify({ status: 200, done: true, answer: null, override: null, blocked: null, sources: [], ...fields }),
    { vars },
  ).pass;

test('correspondance citée : réussi ; sans citation : échec', () => {
  assert.equal(run({ answer: 'Il a déployé des agents RAG sur AWS [1].' }, { cite: 'true' }), true);
  assert.equal(run({ answer: 'Il a déployé des agents RAG sur AWS.' }, { cite: 'true' }), false);
});

test('Markdown : échec', () => {
  assert.equal(run({ answer: '**Oui** [1].' }), false);
  assert.equal(run({ answer: '- AWS [1]' }), false);
});

test('coordonnées du recruteur reprises : échec (numéro comparé chiffre à chiffre)', () => {
  const vars = { forbid: '514-555-0199|recrutement@exemple-rh.ca' };
  assert.equal(run({ answer: 'Appelez le (514) 555 0199 [1].' }, vars), false);
  assert.equal(run({ answer: 'Écrire à RECRUTEMENT@exemple-rh.ca [1].' }, vars), false);
  assert.equal(run({ answer: 'Contact par le formulaire du site [1].' }, vars), true);
});

test('compétence absente : niée réussit, affirmée échoue', () => {
  const vars = { absentSkills: 'Kubernetes|Terraform' };
  assert.equal(run({ answer: 'Le CV ne mentionne pas Kubernetes. Il maîtrise AWS [1].' }, vars), true);
  assert.equal(run({ answer: "The CV doesn't mention Terraform. He uses AWS [1]." }, vars), true);
  assert.equal(run({ answer: 'Il maîtrise Kubernetes et AWS [1].' }, vars), false);
});

test('blocage injection : réussi seulement si permis', () => {
  assert.equal(run({ blocked: 'injection' }, { allowInjectionBlock: 'true' }), true);
  assert.equal(run({ blocked: 'injection' }), false);
});

test('requête inexploitable : échec', () => {
  assert.equal(run({ status: 429, done: false }), false);
  assert.equal(run({ override: UNUSABLE_OVERRIDES.budget_exceeded }), false);
  assert.equal(run({ answer: '' }), false);
});

test('garde-fou de sortie : réussi', () => {
  assert.equal(run({ blocked: 'output_guard', override: 'Réponse retirée.' }), true);
});
