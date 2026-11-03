import { useState } from 'react';
import { exportAgvLogs, getAgvState, sendAgvCommand } from './agv';

const STATIONS = [{ id: 'A', x: 0, y: 0 }, { id: 'B', x: 0, y: 1.51 },
  { id: 'C', x: 1.54, y: 1.51 }, { id: 'D', x: 1.54, y: 0 }];
const ACTIONS = [
  ['start', 'Chạy chặng'], ['stop', 'DỪNG'], ['auto_loop_on', 'Vòng lặp A-B-C-D'],
  ['auto_loop_off', 'Tắt vòng lặp'], ['turn_left_90', 'Trái 90°'],
  ['turn_right_90', 'Phải 90°'], ['turn_180', 'Quay 180°'],
  ['calibrate_gyro', 'Hiệu chuẩn gyro'], ['reset_odom', 'Đặt lại gốc'],
];
const svgX = (x) => 50 + x / 1.54 * 340;
const svgY = (y) => 40 + y / 1.51 * 290;
const show = (value, unit = '') => value == null ? 'N/A' : `${value}${unit}`;

export default function AgvTelemetryPanel({ state, error }) {
  const connected = !!state?.connected;
  const data = connected ? state?.telemetry : null;
  const mask = data?.line_mask;
  const rows = [
    ['ESP32-S3', connected ? 'ONLINE' : 'OFFLINE'],
    ['Encoder trái', show(data?.ticks_l, ' ticks')],
    ['Encoder phải', show(data?.ticks_r, ' ticks')],
    ['RPM trái / phải', 'N/A — firmware chưa gửi RPM'],
    ['MPU6050 yaw', show(data?.yaw, '°')],
    ['MPU6050 raw', 'N/A — firmware chưa gửi raw IMU'],
    ['Odometry local X / Y', data?.x == null || data?.y == null ? 'N/A' : `${data.x} / ${data.y} m`],
    ['Quãng đường local', show(data?.dist, ' m')],
    ['Tốc độ', show(data?.speed, ' cm/s')],
    ['Line error', show(data?.line_err)],
    ['TCRT5000 mask', mask == null ? 'N/A' : `0b${mask.toString(2).padStart(5, '0')}`],
    ['PWM trái / phải', data?.pwm_l == null || data?.pwm_r == null ? 'N/A' : `${data.pwm_l} / ${data.pwm_r}`],
    ['Điện áp', 'N/A — firmware chưa gửi điện áp'],
  ];
  return <div className="robot-detail-content" aria-label="AGV telemetry">
    <section className="robot-info-section">
      <h3>TELEMETRY ESP32-S3</h3>
      <p>{connected ? 'ONLINE' : 'OFFLINE'} · Odometry là tọa độ local, không phải vị trí đã xác minh trên bản đồ ROS.</p>
      {error && <p role="alert">{error}</p>}
      <div className="robot-info-table">
        {rows.map(([label, value]) => <div className="robot-info-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <p>TCRT5000: {mask == null ? 'N/A' : ['L2', 'L1', 'C', 'R1', 'R2'].map((label, index) =>
        <span className="agv-line-bit" data-active={!!(mask & (1 << (4 - index)))} key={label}>{label}</span>)}</p>
    </section>
  </div>;
}

export function AgvDiagnosticsPanel({ robotCode, state, error, onState }) {
  const [busy, setBusy] = useState(false);
  const [commandError, setCommandError] = useState('');
  const connected = !!state?.connected;
  const data = connected ? state?.telemetry : null;
  const allowed = connected && state?.commands_enabled;

  async function command(action, missionId) {
    setBusy(true);
    setCommandError('');
    try {
      await sendAgvCommand(action, missionId, robotCode);
      onState(await getAgvState(robotCode));
    } catch (cause) {
      setCommandError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="robot-detail-content">
    <section className="robot-info-section">
      <h3>CHẨN ĐOÁN AGV</h3>
      <div className="robot-info-table">
        <div className="robot-info-row"><span>Kết nối</span><strong>{connected ? 'ONLINE' : 'OFFLINE'}</strong></div>
        <div className="robot-info-row"><span>Thời điểm telemetry cuối</span><strong>{state?.last_seen_ts == null ? 'N/A' : new Date(state.last_seen_ts * 1000).toLocaleString()}</strong></div>
        <div className="robot-info-row"><span>Độ cũ</span><strong>{show(state?.last_seen_age_ms, ' ms')}</strong></div>
        <div className="robot-info-row"><span>ACK cuối</span><strong>{state?.last_seen_ts == null ? 'N/A' : show(state?.last_ack_id)}</strong></div>
        <div className="robot-info-row"><span>Trạng thái lệnh</span><strong>{state?.command_status ?? 'N/A'}</strong></div>
        <div className="robot-info-row"><span>Lỗi kết nối</span><strong>{error || commandError || 'N/A'}</strong></div>
      </div>
      <h3>TELEMETRY JSON</h3>
      <pre className="agv-telemetry-json">{data ? JSON.stringify(data, null, 2) : 'N/A — không có telemetry mới'}</pre>
      <h3>SƠ ĐỒ THỬ NGHIỆM A-B-C-D (ODOMETRY LOCAL)</h3>
      <svg viewBox="0 0 440 380" role="img" aria-label="Sơ đồ thử nghiệm AGV A B C D, không phải bản đồ ROS" className="agv-test-schematic">
        <polyline points={STATIONS.map((point) => `${svgX(point.x)},${svgY(point.y)}`).join(' ') + ' 50,40'} fill="none" stroke="#2563eb" strokeWidth="4" />
        {STATIONS.map((point) => <g key={point.id}><circle cx={svgX(point.x)} cy={svgY(point.y)} r="7" fill="#f6ba48" /><text x={svgX(point.x) + 10} y={svgY(point.y) - 10} fill="#0f172a" fontSize="16">{point.id}</text></g>)}
        {connected && state?.trail?.length > 1 && <polyline points={state.trail.map((point) => `${svgX(point[0])},${svgY(point[1])}`).join(' ')} fill="none" stroke="#059669" strokeWidth="3" />}
        {data && <g transform={`translate(${svgX(data.x)} ${svgY(data.y)}) rotate(${data.yaw})`}><circle r="9" fill="#ff873a" /><path d="M0 0 L22 0" stroke="white" strokeWidth="3" /></g>}
      </svg>
      <p>Chỉ là sơ đồ test 1.54 × 1.51 m; không xác minh vị trí kho hay đích nhiệm vụ.</p>
      <h3>CÔNG CỤ THỬ NGHIỆM</h3>
      <p>Lệnh thử nghiệm chỉ khả dụng khi backend bật thủ công. ACK không chứng minh robot đã dừng hay tới trạm.</p>
      <div className="agv-test-actions">
        {ACTIONS.map(([action, label]) => <button key={action} type="button" disabled={busy || !state?.commands_enabled || (action !== 'stop' && !allowed)} onClick={() => command(action)}>{label}</button>)}
        {['M1', 'M2', 'M3', 'M4'].map((id) => <button key={id} type="button" disabled={busy || !allowed} onClick={() => command('mission', id)}>{id}</button>)}
        <button type="button" onClick={() => exportAgvLogs(robotCode)}>Xuất telemetry CSV</button>
      </div>
    </section>
  </div>;
}
