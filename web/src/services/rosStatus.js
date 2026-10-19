export function receiveRosStatus(status, now = performance.now()) {
  return status ? { ...status, receivedAt: now } : null;
}

export function getVisibleSlamStatus(status, now) {
  if (!status) return null;
  const elapsed = Math.max(0, now - status.receivedAt);
  const visible = {
    ...status,
    update_age_ms: elapsed,
    lidar_status: status.lidar_status || (status.lidar_online ? 'ONLINE' : 'OFFLINE'),
  };
  const heartbeatAge = (status.heartbeat_age_ms ?? 0) + elapsed;
  if (!status.bridge_online || heartbeatAge > (status.heartbeat_timeout_sec ?? 3) * 1000) {
    return {
      ...visible,
      bridge_online: false,
      nav2_online: false,
      slam_online: false,
      lidar_online: false,
      lidar_status: 'OFFLINE',
      localization_available: false,
      tf_available: false,
      scan_rate_hz: null,
      last_scan_age_ms: null,
    };
  }
  if (Number.isFinite(status.last_scan_age_ms)) {
    visible.last_scan_age_ms += elapsed;
  }
  if (Number.isFinite(status.scan_stale_sec) && Number.isFinite(status.scan_offline_sec)) {
    const age = visible.last_scan_age_ms;
    visible.lidar_status = age == null || age > status.scan_offline_sec * 1000
      ? 'OFFLINE'
      : age > status.scan_stale_sec * 1000 ? 'STALE' : 'ONLINE';
    visible.lidar_online = visible.lidar_status === 'ONLINE';
  }
  if (!visible.lidar_online) visible.scan_rate_hz = null;
  return visible;
}
