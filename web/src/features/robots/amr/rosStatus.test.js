import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getVisibleSlamStatus, receiveRosStatus } from './rosStatus.js';

const data = {
  bridge_online: true, lidar_online: true, lidar_status: 'ONLINE',
  slam_online: true, tf_available: true, localization_available: true,
  map_status: 'RECEIVED', scan_rate_hz: 6, last_scan_age_ms: 100,
  scan_stale_sec: 0.5, scan_offline_sec: 3, timestamp: -1000000,
};

test('monotonic receipt drives Online, Stale, Offline and recovery, not wall time', () => {
  const received = receiveRosStatus(data, 1000);
  assert.equal(getVisibleSlamStatus(received, 1400).lidar_status, 'ONLINE');
  const stale = getVisibleSlamStatus(received, 1401);
  assert.equal(stale.lidar_status, 'STALE');
  assert.equal(stale.lidar_online, false);
  assert.equal(stale.scan_rate_hz, null);
  assert.equal(stale.last_scan_age_ms, 501);
  assert.equal(stale.update_age_ms, 401);
  assert.equal(getVisibleSlamStatus(received, 4000).lidar_status, 'OFFLINE');
  assert.equal(getVisibleSlamStatus(receiveRosStatus(data, 5000), 5000).lidar_status, 'ONLINE');
  assert.equal(received.last_scan_age_ms, 100);
});

test('lost heartbeat expires existing ROS fields and preserves received map', () => {
  const offline = getVisibleSlamStatus(receiveRosStatus(data, 0), 3001);
  for (const key of ['bridge_online', 'nav2_online', 'slam_online', 'lidar_online', 'tf_available']) {
    assert.equal(offline[key], false);
  }
  assert.equal(offline.last_scan_age_ms, null);
  assert.equal(offline.map_status, 'RECEIVED');
  const delayedSnapshot = receiveRosStatus({ ...data, heartbeat_age_ms: 2900 }, 0);
  assert.equal(getVisibleSlamStatus(delayedSnapshot, 101).bridge_online, false);
});

test('legacy payloads and no scan remain supported', () => {
  const legacy = receiveRosStatus({ bridge_online: true, lidar_online: true }, 0);
  assert.equal(getVisibleSlamStatus(legacy, 50).lidar_status, 'ONLINE');
  const missing = receiveRosStatus({ ...data, last_scan_age_ms: null }, 0);
  assert.equal(getVisibleSlamStatus(missing, 50).lidar_status, 'OFFLINE');
  assert.equal(getVisibleSlamStatus(null, 0), null);
});

test('6 Hz scans and 5 Hz telemetry do not falsely turn stale between updates', () => {
  for (let received = 0; received < 2000; received += 200) {
    const scanAge = received % (1000 / 6);
    const status = receiveRosStatus({ ...data, last_scan_age_ms: scanAge }, received);
    for (let elapsed = 0; elapsed < 200; elapsed += 25) {
      assert.equal(getVisibleSlamStatus(status, received + elapsed).lidar_status, 'ONLINE');
    }
  }
});
