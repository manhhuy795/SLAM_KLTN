import { worldToCanvas } from "../transforms/slamMap.js";

export function drawAmrMapLayer(context, map, pose, goal, path, overlay) {
  const width = Number(map.width);
  const height = Number(map.height);
  if (path?.poses?.length > 1 && path.frame_id === map.frame_id) {
    context.strokeStyle = "#38bdf8";
    context.lineWidth = Math.max(1, Math.min(width, height) / 180);
    context.beginPath();
    path.poses.forEach((point, index) => {
      const marker = worldToCanvas(
        map,
        point.x,
        point.y,
        width,
        height,
      );
      if (index === 0) {
        context.moveTo(marker.x, marker.y);
      } else {
        context.lineTo(marker.x, marker.y);
      }
    });
    context.stroke();
  }

  if (goal && goal.frame_id !== map.frame_id) {
    return undefined;
  }

  if (goal) {
    const marker = worldToCanvas(
      map,
      goal.x,
      goal.y,
      width,
      height,
    );
    context.strokeStyle = "#f59e0b";
    context.fillStyle = "#f59e0b";
    context.lineWidth = Math.max(1, Math.min(width, height) / 180);
    context.beginPath();
    context.arc(marker.x, marker.y, 4, 0, Math.PI * 2);
    context.fill();
    context.stroke();

    const locationLabel = !overlay && (goal.planning_point?.name || goal.location?.code || goal.location?.name);
    if (locationLabel) {
      context.font = `${Math.max(6, Math.min(width, height) / 24)}px monospace`;
      context.textBaseline = "bottom";
      context.fillText(locationLabel, marker.x + 6, marker.y - 5);
    }
  }

  if (pose && pose.frame_id === map.frame_id) {
    const marker = worldToCanvas(
      map,
      pose.x,
      pose.y,
      width,
      height,
    );
    const scale = Math.max(8, Math.min(width, height) * 0.035);

    context.strokeStyle = "#ff7300";
    context.fillStyle = "#ff7300";
    context.lineWidth = Math.max(1, Math.min(width, height) / 250);
    context.beginPath();
    context.arc(marker.x, marker.y, scale * 0.35, 0, Math.PI * 2);
    context.fill();
    context.beginPath();
    context.moveTo(marker.x, marker.y);
    context.lineTo(
      marker.x + Math.cos(pose.yaw) * scale,
      marker.y - Math.sin(pose.yaw) * scale,
    );
    context.stroke();
  }

  return undefined;
}
