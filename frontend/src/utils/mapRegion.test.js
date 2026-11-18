import test from 'node:test';
import assert from 'node:assert/strict';
import { mapRegion, sameRegion } from './mapRegion.js';

test('map region covers the whole rectangular viewport, in degrees', () => {
  assert.deepEqual(mapRegion(359.99, -89, [.6, .8]), { ra: 359.99, dec: -89, radius: .5 });
  assert.equal(mapRegion(0, 0, [0, 1]), null);
  assert.equal(mapRegion(NaN, 0, [1, 1]), null);
  assert.equal(mapRegion(0, 91, [1, 1]), null);
  assert.equal(mapRegion(0, 0, null), null);
});
test('camera noise does not invalidate a request, but a moved view does', () => {
  const region = { ra: 10, dec: 20, radius: .2 };
  assert.equal(sameRegion(region, { ...region, ra: 10.00000001 }), true);
  assert.equal(sameRegion(region, { ...region, ra: 11 }), false);
  assert.equal(sameRegion(null, region), false);
});
