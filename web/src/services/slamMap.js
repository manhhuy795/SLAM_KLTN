export function mapOrigin(map) {
  return map.origin || {
    x: map.origin_x || 0,
    y: map.origin_y || 0,
    yaw: map.origin_yaw || 0,
  };
}

export function worldToMapCell(map, x, y) {
  const origin = mapOrigin(map);
  const dx = x - origin.x;
  const dy = y - origin.y;
  const cos = Math.cos(origin.yaw);
  const sin = Math.sin(origin.yaw);

  return {
    column: (cos * dx + sin * dy) / map.resolution,
    row: (-sin * dx + cos * dy) / map.resolution,
  };
}

export function mapCellToWorld(map, column, row) {
  const origin = mapOrigin(map);
  const localX = (column + 0.5) * map.resolution;
  const localY = (row + 0.5) * map.resolution;
  const cos = Math.cos(origin.yaw);
  const sin = Math.sin(origin.yaw);

  return {
    x: origin.x + cos * localX - sin * localY,
    y: origin.y + sin * localX + cos * localY,
  };
}

export function worldToCanvas(map, x, y, width, height) {
  const cell = worldToMapCell(map, x, y);

  return {
    x: (cell.column / map.width) * width,
    y: height - (cell.row / map.height) * height,
  };
}
