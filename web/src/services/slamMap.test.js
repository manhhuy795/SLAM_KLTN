import assert from "node:assert/strict";

import {
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

console.log("SLAM map coordinate helpers: OK");
