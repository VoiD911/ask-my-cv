'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseEvents, summarize, transformResponse } = require('./sse');

const sse = (type, data) => `event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`;

const ANSWERED =
  sse('stage.start', { name: 'reception', ts: 1 }) +
  sse('stage.end', { name: 'reception', status: 'ok', duration_ms: 1, attrs: {} }) +
  sse('stage.end', { name: 'injection', status: 'ok', duration_ms: 1, attrs: { score: 0.01 } }) +
  sse('llm.progress', { tokens: 3 }) +
  sse('answer', { text: "D'après le CV [1], oui." }) +
  sse('done', { tokens_in: 1, tokens_out: 3, cost_usd: 0, latency_ms: 5, sources: ['[1] Profil'] });

const BLOCKED =
  sse('stage.end', { name: 'reception', status: 'ok', duration_ms: 1, attrs: {} }) +
  sse('stage.end', { name: 'injection', status: 'blocked', duration_ms: 1, attrs: {} }) +
  sse('stage.end', { name: 'output', status: 'blocked', duration_ms: 1, attrs: {} }) +
  sse('done', {
    tokens_in: 0,
    tokens_out: 0,
    cost_usd: 0,
    latency_ms: 2,
    sources: [],
    answer_override: 'Requête bloquée.',
  });

test('réponse normale : texte, sources, rien de bloqué', () => {
  assert.deepEqual(summarize(ANSWERED), {
    answer: "D'après le CV [1], oui.",
    override: null,
    blocked: null,
    sources: ['[1] Profil'],
    done: true,
  });
});

test('requête bloquée : première étape bloquée, remplacement, pas de réponse', () => {
  const s = summarize(BLOCKED);
  assert.equal(s.blocked, 'injection');
  assert.equal(s.answer, null);
  assert.equal(s.override, 'Requête bloquée.');
  assert.deepEqual(s.sources, []);
});

test('fins de ligne CRLF et blocs illisibles tolérés', () => {
  const raw = ANSWERED.replace(/\n/g, '\r\n') + 'event: answer\r\ndata: {pas du json\r\n\r\n';
  assert.equal(summarize(raw).answer, "D'après le CV [1], oui.");
  assert.equal(parseEvents(raw).length, 6);
});

test('corps vide ou absent : résumé nul, done faux', () => {
  for (const raw of ['', undefined, null]) {
    assert.deepEqual(summarize(raw), {
      answer: null,
      override: null,
      blocked: null,
      sources: [],
      done: false,
    });
  }
});

test('transformResponse renvoie une chaîne JSON du résumé', () => {
  assert.deepEqual(JSON.parse(transformResponse(null, BLOCKED)), summarize(BLOCKED));
});
