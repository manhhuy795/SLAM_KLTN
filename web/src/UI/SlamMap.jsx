import { useEffect, useRef } from "react";

import { worldToCanvas } from "../services/slamMap";


function occupancyColor(value) {
  if (value < 0) {
    return [8, 11, 15, 255];
  }

  if (value >= 65) {
    return [220, 226, 232, 255];
  }

  return [39, 55, 67, 255];
}


export default function SlamMap({ map, pose }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !map) {
      return undefined;
    }

    const context = canvas.getContext("2d");
    const width = Number(map.width);
    const height = Number(map.height);
    const image = context.createImageData(width, height);

    for (let row = 0; row < height; row += 1) {
      for (let column = 0; column < width; column += 1) {
        const sourceIndex = row * width + column;
        const targetRow = height - 1 - row;
        const targetIndex = (targetRow * width + column) * 4;
        const color = occupancyColor(map.data[sourceIndex] ?? -1);

        image.data[targetIndex] = color[0];
        image.data[targetIndex + 1] = color[1];
        image.data[targetIndex + 2] = color[2];
        image.data[targetIndex + 3] = color[3];
      }
    }

    canvas.width = width;
    canvas.height = height;
    context.imageSmoothingEnabled = false;
    context.putImageData(image, 0, 0);

    if (pose && pose.frame_id === map.frame_id) {
      const marker = worldToCanvas(
        map,
        pose.x,
        pose.y,
        width,
        height
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
        marker.y - Math.sin(pose.yaw) * scale
      );
      context.stroke();
    }

    return undefined;
  }, [map, pose]);

  return (
    <div className="map-canvas slam-map-canvas">
      <canvas
        ref={canvasRef}
        role="img"
        aria-label="OccupancyGrid SLAM và vị trí robot"
      />
      <div className="slam-map-meta">
        {map.width} × {map.height} ô · {map.resolution.toFixed(3)} m/ô · {map.frame_id}
      </div>
    </div>
  );
}
