import test from 'node:test';
import assert from 'node:assert/strict';
import { toPercent } from './normalizeResults.js';
import { validateRun, isTerminal } from './runState.js';

test('scores never guess logits or percentages', () => {
  for (const value of [null, NaN, Infinity, -1, 2, '0.9']) assert.equal(toPercent(value), null);
  assert.equal(toPercent(0), 0);
  assert.equal(toPercent(.9), 90);
  assert.equal(toPercent(1), 100);
});
test('only declared terminal states stop polling', () => {
  for (const status of ['succeeded', 'insufficient_evidence', 'failed', 'cancelled']) assert.equal(isTerminal(status), true);
  for (const status of ['accepted', 'running']) assert.equal(isTerminal(status), false);
  assert.throws(() => validateRun({ id: '1', status: 'mystery' }));
  assert.throws(() => validateRun(null));
  assert.equal(validateRun({ id: '1', status: 'running' }).id, '1');
});
