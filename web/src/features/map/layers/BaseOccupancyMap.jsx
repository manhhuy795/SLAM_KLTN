import { useEffect, useRef } from "react";
import { drawAmrMapLayer } from './AmrMapLayer';

function occupancyColor(value) {
  if (value < 0) {
    return [8, 11, 15, 255];
  }

  if (value >= 65) {
    return [220, 226, 232, 255];
  }

  return [39, 55, 67, 255];
}


export default function BaseOccupancyMap({ map, pose, goal, path, overlay }) {
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

    drawAmrMapLayer(context, map, pose, goal, path, overlay);

    return undefined;
  }, [map, pose, goal, path]);

  return <canvas ref={canvasRef} role="img" aria-label="SLAM occupancy grid and robot pose" />;
}
