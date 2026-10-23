// Apply measured AGV A,B,D anchors to the *same* map used by AMR.
// Never scale local odometry or assume it already is ROS 'map' coordinates.
import { isWorldPointInMap } from "./slamMap";

export function agvToSharedMap(map, alignment, localPose) {
  if (!map || !alignment || !localPose) return null;
  if (alignment.map_hash !== map.map_hash || alignment.map_id !== map.id && map.id) return null;
  const { a, b, d } = alignment;
  if (!a || !b || !d) return null;
  const values = [a.x,a.y,b.x,b.y,d.x,d.y,localPose.x,localPose.y,localPose.yaw];
  if (!values.every(Number.isFinite)) return null;
  const theta = Math.atan2(d.y-a.y,d.x-a.x);
  if (Math.abs(Math.hypot(d.x-a.x,d.y-a.y)-1.54)>0.15) return null;
  if (Math.hypot(b.x-(a.x+1.51*Math.sin(theta)),b.y-(a.y-1.51*Math.cos(theta)))>0.15) return null;
  const result = {
    x:a.x+localPose.x*Math.cos(theta)+localPose.y*Math.sin(theta),
    y:a.y+localPose.x*Math.sin(theta)-localPose.y*Math.cos(theta),
    yaw:theta-localPose.yaw*Math.PI/180,
    frame_id:map.frame_id,
    robot_code:"LINE-01",
  };
  if (!isWorldPointInMap(map,result.x,result.y)) return null;
  return result;
}
