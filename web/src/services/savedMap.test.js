import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mapView } from './savedMap.js';
import { mapCellToWorld, worldToMapCell } from './slamMap.js';

test('live updates cannot replace saved map or project unrelated robot overlays', () => {
  const saved = { map_hash: 'saved', resolution: .05, origin: { x: -2, y: 1, yaw: .8 } };
  let live = { map_hash: 'live-1' };
  const pose = { x: 10, y: 20, frame_id: 'map' };
  const path = { poses: [pose] };
  assert.equal(mapView('live', live, saved, pose, pose, path).map, live);
  live = { map_hash: 'live-2' }; // A later SLAM_MAP_UPDATED event.
  assert.deepEqual(mapView('saved', live, saved, pose, pose, path),
    { map: saved, pose: null, goal: null, path: null });
  assert.equal(mapView('live', live, saved, pose, pose, path).path, path);
  assert.equal(mapView('saved', live, null, pose, pose, path).map, null);
  const world = mapCellToWorld(saved, 3, 5);
  const cell = worldToMapCell(saved, world.x, world.y);
  assert.ok(Math.abs(cell.column - 3.5) < 1e-10);
  assert.ok(Math.abs(cell.row - 5.5) < 1e-10);
});
