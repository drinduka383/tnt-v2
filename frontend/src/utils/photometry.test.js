import assert from 'node:assert/strict';
import test from 'node:test';
import { hoursFromTransit, parsePhotometry } from './photometry.js';

test('uses each saved measurement and folds it with the supplied timing', () => {
  const epoch = 2461000;
  const { time, brightness } = parsePhotometry('time_bjd,normalized_flux\r\n2461000,1\r\n2461002.125,0.99\r\n2460997.875,1.01\r\n');
  assert.deepEqual(hoursFromTransit(time, 2, epoch), [0, 3, -3]);
  assert.deepEqual(brightness.map(Math.round), [0, -1, 1]);
  assert.throws(() => parsePhotometry('time_bjd,normalized_flux\n2461000,\n'), /invalid measurement/);
});
