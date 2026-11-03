import assert from 'node:assert/strict';
import { test } from 'node:test';
import { drawAmrMapLayer } from './AmrMapLayer.js';

const map = { width: 20, height: 20, resolution: 1, origin: { x: 0, y: 0, yaw: 0 }, frame_id: 'map' };

test('AMR path draws before a mismatched goal stops pose drawing', () => {
  const calls = [];
  const context = Object.fromEntries(['beginPath', 'moveTo', 'lineTo', 'stroke', 'arc', 'fill'].map(name => [name, () => calls.push(name)]));
  drawAmrMapLayer(context, map, { x: 2, y: 2, yaw: 0, frame_id: 'map' },
    { x: 3, y: 3, frame_id: 'odom' },
    { frame_id: 'map', poses: [{ x: 1, y: 1 }, { x: 2, y: 2 }] }, null);
  assert.deepEqual(calls, ['beginPath', 'moveTo', 'lineTo', 'stroke']);
});
