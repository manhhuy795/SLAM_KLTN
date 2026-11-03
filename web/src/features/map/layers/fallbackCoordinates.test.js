import assert from 'node:assert/strict';
import { test } from 'node:test';
import { canPlaceOnFallbackMap, toSvgX, toSvgY } from './fallbackCoordinates.js';

test('fallback schematic keeps its existing 12m by 8m scaling', () => {
  assert.equal(toSvgX(0), 15);
  assert.equal(toSvgX(12), 625);
  assert.equal(toSvgY(0), 15);
  assert.equal(toSvgY(8), 325);
});

test('AGV-local coordinates never qualify as fallback map position', () => {
  assert.equal(canPlaceOnFallbackMap({ robot_type: 'LINE', status: { x: 0.5, y: 0.7 } }), false);
  assert.equal(canPlaceOnFallbackMap({ robot_type: 'AMR', status: { x: 2, y: 1.5 } }), true);
  assert.equal(canPlaceOnFallbackMap({ robot_type: 'AMR', status: { x: null, y: 1.5 } }), false);
});
