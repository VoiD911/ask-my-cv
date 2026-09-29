'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const bounds = require('./bounds');

test('bornes : 10 000 et 10 001 points de code exacts', () => {
  const [ok, tooLong] = bounds();
  assert.equal(Array.from(ok.vars.question).length, bounds.MAX);
  assert.equal(Array.from(tooLong.vars.question).length, bounds.MAX + 1);
});

test('texte varié, pas un paragraphe répété', () => {
  const lines = bounds.textOf(bounds.MAX).split('\n').filter((l) => l.trim());
  assert.equal(new Set(lines).size, lines.length);
});
