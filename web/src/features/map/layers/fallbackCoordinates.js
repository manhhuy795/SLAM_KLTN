const MAP_WIDTH_METERS = 12;
const MAP_HEIGHT_METERS = 8;

export const SVG_LEFT = 15;
export const SVG_TOP = 15;
export const SVG_WIDTH = 610;
export const SVG_HEIGHT = 310;

export function canPlaceOnFallbackMap(robot) {
  return robot.robot_type !== 'LINE'
    && robot.status?.x != null
    && robot.status?.y != null;
}

export function toSvgX(x) {
  return (
    SVG_LEFT +
    (Number(x) /
      MAP_WIDTH_METERS) *
      SVG_WIDTH
  );
}


export function toSvgY(y) {
  return (
    SVG_TOP +
    (Number(y) /
      MAP_HEIGHT_METERS) *
      SVG_HEIGHT
  );
}
