'use strict';

// node --test evals/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { OUTPUT_GUARD, UNUSABLE_OVERRIDES } = require('./usable');

const PIPELINE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'ask_my_cv', 'pipeline.py'),
  'utf8',
);

test('les messages inexploitables sont ceux du pipeline', () => {
  for (const message of Object.values(UNUSABLE_OVERRIDES)) {
    assert.ok(PIPELINE.includes(JSON.stringify(message)) || PIPELINE.includes(`"${message}"`), message);
  }
});

test("l'étape du garde-fou de sortie porte ce nom dans le pipeline", () => {
  assert.ok(PIPELINE.includes(`stage("${OUTPUT_GUARD}"`));
});
