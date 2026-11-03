export function mapView(mode, liveMap, savedMap, pose, goal, path) {
  if (mode === 'saved') return { map: savedMap, pose: null, goal: null, path: null };
  return { map: liveMap, pose, goal, path };
}
