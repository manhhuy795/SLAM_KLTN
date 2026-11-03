export default function AgvMapLayer({ agvPose, map, marker, canvasPoint }) {
  const label = `AGV ${agvPose.robot_code || 'LINE-01'}`;
  return <g aria-label={label} pointerEvents="none">
    <circle cx={canvasPoint(agvPose).x} cy={canvasPoint(agvPose).y} r={marker*1.35} fill="#17d6a4" stroke="#052e27" strokeWidth={marker*.3}/>
    <line x1={canvasPoint(agvPose).x} y1={canvasPoint(agvPose).y}
      x2={canvasPoint(agvPose).x+Math.cos(agvPose.yaw-(map.origin?.yaw||0))*marker*3}
      y2={canvasPoint(agvPose).y-Math.sin(agvPose.yaw-(map.origin?.yaw||0))*marker*3}
      stroke="#17d6a4" strokeWidth={marker*.6}/>
    <text x={canvasPoint(agvPose).x+marker*2} y={canvasPoint(agvPose).y-marker*1.8}
      fill="#17d6a4" fontSize={marker*1.25}>{label}</text>
  </g>;
}
