import { useEffect, useState } from 'react';
import { getAmrHardwareTelemetry } from '../../../services/api';
import { subscribeRealtime } from '../../../services/realtime';

function measured(value, unit, digits = 2) {
  return Number.isFinite(value) ? `${value.toFixed(digits)} ${unit}` : 'N/A';
}

export default function AmrTelemetryPanel({ robotId }) {
  const [source, setSource] = useState('HARDWARE');
  const [telemetry, setTelemetry] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setTelemetry(null);
    const load = () => getAmrHardwareTelemetry(robotId, source).then((data) => {
      if (active) { setTelemetry(data); setError(''); }
    }).catch((cause) => {
      if (active) {
        setTelemetry((current) => current && { ...current, state: 'OFFLINE',
          diagnostics_state: 'OFFLINE', odometry_state: 'OFFLINE' });
        setError(cause.message);
      }
    });
    load();
    const timer = window.setInterval(load, 1000);
    const unsubscribe = subscribeRealtime((message) => {
      if (active && message.type === 'AMR_HARDWARE_TELEMETRY_UPDATED'
          && message.data?.robot_id === robotId && message.data?.source === source)
        setTelemetry(message.data);
    });
    return () => { active = false; window.clearInterval(timer); unsubscribe(); };
  }, [robotId, source]);

  const diagnostics = telemetry?.diagnostics_state === 'ONLINE' ? telemetry.diagnostics : null;
  const odometry = telemetry?.odometry_state === 'ONLINE' ? telemetry.odometry : null;
  const rows = [
    ['Telemetry stream', telemetry?.state ?? 'OFFLINE'],
    ['ESP32 connection', diagnostics?.serial_connected == null ? 'N/A'
      : diagnostics.serial_connected ? 'CONNECTED' : 'DISCONNECTED'],
    ['Encoder state', diagnostics?.encoder_online == null
      ? telemetry?.diagnostics_state ?? 'OFFLINE'
      : diagnostics.encoder_online ? 'ONLINE' : 'OFFLINE'],
    ['Left encoder', Number.isInteger(diagnostics?.left_encoder_count)
      ? `${diagnostics.left_encoder_count} ticks` : 'N/A'],
    ['Right encoder', Number.isInteger(diagnostics?.right_encoder_count)
      ? `${diagnostics.right_encoder_count} ticks` : 'N/A'],
    ['Odometry stream', telemetry?.odometry_state ?? 'OFFLINE'],
    ['Odometry X / Y — UNCALIBRATED', odometry
      ? `${measured(odometry.x, 'm')} / ${measured(odometry.y, 'm')}` : 'N/A'],
    ['Odometry yaw — UNCALIBRATED', measured(odometry?.yaw, 'rad')],
    ['Linear velocity — UNCALIBRATED', measured(odometry?.linear_mps, 'm/s')],
    ['Angular velocity — UNCALIBRATED', measured(odometry?.angular_radps, 'rad/s')],
    ['E-STOP', diagnostics?.emergency_stop == null ? 'UNKNOWN'
      : diagnostics.emergency_stop ? 'ACTIVE' : 'INACTIVE'],
    ['Fault', diagnostics?.fault_reason || diagnostics?.serial_error || 'N/A'],
    ['Last update', telemetry?.last_update
      ? new Date(telemetry.last_update * 1000).toLocaleString() : 'N/A'],
  ];

  return <div className="robot-detail-content" aria-label="AMR telemetry">
    <section className="robot-info-section">
      <h3>AMR-01 TELEMETRY · READ ONLY</h3>
      <label>Source <select value={source} onChange={(event) => setSource(event.target.value)}>
        <option value="HARDWARE">HARDWARE</option>
        <option value="SIMULATION">SIMULATION</option>
      </select></label>
      <p>Odometry is local to the odom frame; it is not a verified map position.</p>
      {error && <p role="alert">{error}</p>}
      <div className="robot-info-table">{rows.map(([label, value]) =>
        <div className="robot-info-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
    </section>
  </div>;
}
