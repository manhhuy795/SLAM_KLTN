import BaseOccupancyMap from './BaseOccupancyMap';

export default function SlamMap({ map, pose, goal, path, overlay }) {
  return (
    <div className="map-canvas slam-map-canvas">
      <BaseOccupancyMap map={map} pose={pose} goal={goal} path={path} overlay={overlay} />
      {overlay}
      {!overlay && <div className="slam-map-meta">
        {map.name && <span>{map.name} · </span>}
        {map.width} x {map.height} cells · {map.resolution.toFixed(3)} m/cell · {map.frame_id}
        {map.origin && <span> · origin [{map.origin.x}, {map.origin.y}, {map.origin.yaw}]</span>}
      </div>}
    </div>
  );
}
