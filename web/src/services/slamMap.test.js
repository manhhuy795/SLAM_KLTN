import assert from "node:assert/strict";

import {
  isWorldPointInMap,
  mapCellToWorld,
  worldToCanvas,
  worldToMapCell,
} from "./slamMap.js";


const map = {
  width: 10,
  height: 8,
  resolution: 0.5,
  origin: { x: -2, y: -1, yaw: 0 },
};

const cell = worldToMapCell(map, -1.75, -0.75);
assert.deepEqual(cell, { column: 0.5, row: 0.5 });

const world = mapCellToWorld(map, 0, 0);
assert.deepEqual(world, { x: -1.75, y: -0.75 });

const pixel = worldToCanvas(map, -1.75, -0.75, 1000, 800);
assert.deepEqual(pixel, { x: 50, y: 750 });

assert.equal(isWorldPointInMap(map, -1.75, -0.75), true);
assert.equal(isWorldPointInMap(map, 2.99, 2.99), true);
assert.equal(isWorldPointInMap(map, 3, 0), false);
assert.equal(isWorldPointInMap(map, -2.01, 0), false);

const rotatedMap = {
  width: 2,
  height: 1,
  resolution: 1,
  origin: { x: 5, y: 5, yaw: Math.PI / 2 },
};
assert.equal(isWorldPointInMap(rotatedMap, 4.5, 5.5), true);
assert.equal(isWorldPointInMap(rotatedMap, 5.5, 5.5), false);

console.log("SLAM map coordinate helpers: OK");
