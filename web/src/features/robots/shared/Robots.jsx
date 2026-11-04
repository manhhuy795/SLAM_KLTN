import { useEffect, useState } from 'react';
import {
  Battery,
  Bot,
  Camera,
  Cpu,
  MapPin,
  Navigation,
  Radio,
} from 'lucide-react';

import {
  getAlerts,
  getRobots,
  getTasks,
} from '../../../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../../../services/realtime';
import UsbCameraPreview from '../agv/UsbCameraPreview';
import { getAgvState } from '../agv/agv';
import AgvTelemetryPanel, { AgvDiagnosticsPanel } from '../agv/AgvTelemetryPanel';
import AgvMissionConfiguration from '../agv/AgvMissionConfiguration';
import AmrTelemetryPanel from '../amr/AmrTelemetryPanel';


const TERMINAL_TASK_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function Robots({ backendOnline, selectedRobotCode, operatorId, onNavigate, onSelectRobot }) {
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [alerts, setAlerts] = useState([]);

  const [tab, setTab] = useState('overview');
  const [agvState, setAgvState] = useState(null);
  const [agvError, setAgvError] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);


  useEffect(() => {
    Promise.all([
      getRobots(),
      getTasks(),
      getAlerts(),
    ])
      .then(([robotData, taskData, alertData]) => {
        setRobots(robotData);
        setTasks(taskData);
        setAlerts(alertData);

        setError(null);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);


  useEffect(() => {
    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === 'ROBOT_STATUS_UPDATED') {
        setRobots((current) => {
          const exists = current.some(
            (robot) => robot.id === message.data.id
          );

          return exists
            ? current.map((robot) =>
              robot.id === message.data.id
                ? message.data
                : robot
            )
            : [...current, message.data];
        });
      }

      if (message.type === 'TASK_UPDATED') {
        setTasks((current) => {
          const exists = current.some(
            (task) => task.id === message.data.id
          );

          return exists
            ? current.map((task) =>
              task.id === message.data.id
                ? message.data
                : task
            )
            : [...current, message.data];
        });
      }

      if (message.type === 'ALERT_UPDATED') {
        setAlerts((current) => {
          const exists = current.some(
            (alert) => alert.id === message.data.id
          );

          return exists
            ? current.map((alert) =>
              alert.id === message.data.id
                ? message.data
                : alert
            )
            : [message.data, ...current];
        });
      }
    });

    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (!online || !isReconnect) {
          return;
        }

        Promise.all([
          getRobots(),
          getTasks(),
          getAlerts(),
        ]).then(([robotData, taskData, alertData]) => {
          setRobots(robotData);
          setTasks(taskData);
          setAlerts(alertData);
        }).catch((err) => {
          setError(err.message);
        });
      }
    );

    return () => {
      unsubscribe();
      unsubscribeStatus();
    };
  }, []);


  const robot = selectedRobotCode
    ? robots.find((item) => item.robot_code === selectedRobotCode)
    : robots[0];

  useEffect(() => { setTab('overview'); }, [selectedRobotCode]);

  useEffect(() => {
    if (robot?.robot_type !== 'LINE') { setAgvState(null); return; }
    let active = true;
    setAgvState(null);
    const load = () => getAgvState(robot.robot_code).then((state) => {
      if (active) { setAgvState(state); setAgvError(''); }
    }).catch((error) => {
      if (active) { setAgvState((current) => current ? { ...current, connected: false } : null); setAgvError(error.message); }
    });
    load();
    const timer = window.setInterval(load, 1000);
    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === 'AGV_TELEMETRY_UPDATED' && message.data?.robot_code === robot.robot_code)
        setAgvState(message.data);
    });
    return () => { active = false; window.clearInterval(timer); unsubscribe(); };
  }, [robot?.robot_code, robot?.robot_type]);


  if (loading) {
    return (
      <div className="page-shell">
        <section className="panel">
          Đang tải dữ liệu robot...
        </section>
      </div>
    );
  }


  if (error) {
    return (
      <div className="page-shell">
        <section className="panel">
          Không thể tải dữ liệu robot: {error}
        </section>
      </div>
    );
  }


  if (!robot) {
    return (
      <div className="page-shell">
        <section className="panel">
          {selectedRobotCode ? `Robot ${selectedRobotCode} không tồn tại.` : 'Không có robot trong hệ thống.'}
        </section>
      </div>
    );
  }


  const activeTask = getActiveTask(
    robot.id,
    tasks
  );

  const robotAlerts = alerts.filter(
    (alert) =>
      alert.robot_id === robot.id &&
      alert.status !== 'RESOLVED'
  );


  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / ROBOT
          </span>

          <h1>Quản lý robot</h1>

          <p>
            Theo dõi trạng thái vận hành,
            nhiệm vụ và tình trạng robot.
          </p>
        </div>
      </div>


      <div className="robots-layout">
        <aside className="panel robot-list-panel">
          <div className="section-header">
            <div className="section-title-group">
              <span className="section-indicator section-indicator--orange" />
              <h2>DANH SÁCH ROBOT</h2>
            </div>

            <span className="section-caption mono">
              {robots.length} robot
            </span>
          </div>


          <div className="robot-list">
            {robots.map((item) => {
              const accent =
                getRobotAccent(item);

              const online = item.robot_type === 'LINE'
                ? item.id === robot.id && !!agvState?.connected
                : (item.status?.online ?? false);

              return (
                <button
                  key={item.id}
                  type="button"
                  className={
                    `robot-list-item ${
                      robot.id === item.id
                        ? 'robot-list-item--active'
                        : ''
                    }`
                  }
                  onClick={() => {
                    onSelectRobot(item.robot_code);
                    setTab('overview');
                  }}
                >
                  <div
                    className={
                      `robot-list-marker robot-list-marker--${accent}`
                    }
                  >
                    <Bot size={17} />
                  </div>

                  <div className="robot-list-copy">
                    <strong>
                      {item.robot_code}
                    </strong>

                    <span>
                      {getRobotDescription(
                        item.robot_type
                      )}
                    </span>
                  </div>

                  <span
                    className={
                      `online-badge ${
                        online
                          ? ''
                          : 'online-badge--offline'
                      }`
                    }
                  >
                    {online
                      ? 'TRỰC TUYẾN'
                      : 'NGOẠI TUYẾN'}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>


        <section className="panel robot-detail-page">
          <div className="robot-detail-page-header">
            <div>
              <span className="page-eyebrow">
                {robot.robot_type}
              </span>

              <h2>
                {robot.robot_code}
              </h2>

              <p>
                {getRobotDescription(
                  robot.robot_type
                )}
              </p>
            </div>

            <div className="robot-detail-state">
              <span
                className={
                  (robot.robot_type === 'LINE' ? agvState?.connected : robot.status?.online)
                    ? 'status-dot status-dot--green'
                    : 'status-dot'
                }
              />

              <strong>
                {(robot.robot_type === 'LINE' ? agvState?.connected : robot.status?.online)
                  ? 'TRỰC TUYẾN'
                  : 'NGOẠI TUYẾN'}
              </strong>
            </div>
          </div>


          <div className="robot-detail-tabs">
            <RobotTab
              active={tab === 'overview'}
              onClick={() =>
                setTab('overview')
              }
              label="Tổng quan"
            />

            {robot.robot_type === 'AMR' && <RobotTab
              active={tab === 'navigation'}
              onClick={() =>
                setTab('navigation')
              }
              label={
                robot.robot_type === 'AMR'
                  ? 'Điều hướng'
                  : 'Theo vạch'
              }
              />}

            {robot.robot_type === 'LINE' && <RobotTab
              active={tab === 'telemetry'}
              onClick={() => setTab('telemetry')}
              label="Telemetry"
            />}

            {robot.robot_type === 'AMR' && <RobotTab
              active={tab === 'sensors'}
              onClick={() =>
                setTab('sensors')
              }
              label="Cảm biến"
            />}

            <RobotTab
              active={tab === 'camera'}
              onClick={() =>
                setTab('camera')
              }
              label="Camera"
            />

            <RobotTab
              active={tab === 'diagnostics'}
              onClick={() =>
                setTab('diagnostics')
              }
              label="Chẩn đoán"
            />
          </div>


          {tab === 'overview' && (
            robot.robot_type === 'LINE' ? <AgvOverview robot={robot} task={activeTask} state={agvState}
              operatorId={operatorId} onNavigate={onNavigate} /> : <RobotOverview
              robot={robot}
              task={activeTask}
              alerts={robotAlerts}
            />
          )}

          {robot.robot_type === 'LINE' && tab === 'telemetry' &&
            <AgvTelemetryPanel state={agvState} error={agvError} />}

          {tab === 'navigation' && (
            <RobotNavigation
              robot={robot}
              task={activeTask}
            />
          )}

          {tab === 'sensors' && (
            <AmrTelemetryPanel robotId={robot.id} />
          )}

          {tab === 'camera' && (
            <RobotCamera robot={robot} />
          )}

          {tab === 'diagnostics' && (
            robot.robot_type === 'LINE' ? <AgvDiagnosticsPanel robotCode={robot.robot_code}
              state={agvState} error={agvError} onState={setAgvState} /> : <RobotDiagnostics
              robot={robot}
              alerts={robotAlerts}
              backendOnline={backendOnline}
            />
          )}
        </section>
      </div>
    </div>
  );
}


function AgvOverview({ robot, task, state, operatorId, onNavigate }) {
  return <div className="robot-detail-content">
    <div className="robot-overview-grid">
      <InfoCard icon={Radio} label="Kết nối ESP32-S3" value={state?.connected ? 'ONLINE' : 'OFFLINE'} />
      <InfoCard icon={Navigation} label="Nhiệm vụ" value={task?.status ?? 'N/A'} />
      <InfoCard icon={MapPin} label="Đích đến" value={getCurrentTarget(task) ?? 'N/A'} />
      <InfoCard icon={Battery} label="Pin" value="N/A" />
    </div>
    <section className="robot-info-section"><h3>THÔNG TIN ROBOT</h3>
      <div className="robot-info-table">
        <InfoRow label="Robot ID" value={robot.robot_code} />
        <InfoRow label="Task đang chạy" value={task?.task_code ?? 'N/A'} />
        <InfoRow label="Vị trí đã xác minh" value="N/A" />
      </div>
    </section>
    <AgvMissionConfiguration robot={robot} operatorId={operatorId} agvState={state}
      onOpenMap={() => onNavigate('map-products')} />
  </div>;
}


function RobotOverview({
  robot,
  task,
  alerts,
}) {
  return (
    <div className="robot-detail-content">
      <div className="robot-overview-grid">
        <InfoCard
          icon={Battery}
          label="Pin"
          value={formatBattery(
            robot.status?.battery_percent
          )}
        />

        <InfoCard
          icon={Navigation}
          label="Trạng thái"
          value={getRobotStateLabel(
            robot.status?.state
          )}
        />

        <InfoCard
          icon={MapPin}
          label="Vị trí"
          value={getRobotLocation(robot)}
        />

        <InfoCard
          icon={Cpu}
          label="Nhiệm vụ hiện tại"
          value={
            task?.task_code ??
            'Không có'
          }
          tone="orange"
        />
      </div>


      <section className="robot-info-section">
        <h3>THÔNG TIN VẬN HÀNH</h3>

        <div className="robot-info-table">
          <InfoRow
            label="Robot ID"
            value={robot.robot_code}
          />

          <InfoRow
            label="Loại robot"
            value={getRobotDescription(
              robot.robot_type
            )}
          />

          <InfoRow
            label="Model"
            value={robot.model ?? '—'}
          />

          <InfoRow
            label="Trạng thái kết nối"
            value={
              robot.status?.online
                ? 'Trực tuyến'
                : 'Ngoại tuyến'
            }
          />

          <InfoRow
            label="Chất lượng định vị"
            value={getLocalizationLabel(
              robot.status?.localization_quality
            )}
          />

          <InfoRow
            label="Nhiệm vụ hiện tại"
            value={
              task?.task_code ??
              'Không có'
            }
          />

          <InfoRow
            label="Cảnh báo chưa xử lý"
            value={
              alerts.length === 0
                ? 'Không có'
                : `${alerts.length} cảnh báo`
            }
          />
        </div>
      </section>
    </div>
  );
}


function RobotNavigation({
  robot,
  task,
}) {
  const target =
    getCurrentTarget(task);

  return (
    <div className="robot-detail-content">
      <section className="robot-info-section">
        <h3>
          {robot.robot_type === 'AMR'
            ? 'TRẠNG THÁI ĐIỀU HƯỚNG'
            : 'TRẠNG THÁI THEO VẠCH'}
        </h3>


        {robot.robot_type === 'AMR' ? (
          <div className="robot-info-table">
            <InfoRow
              label="Nav2"
              value="Chưa có telemetry"
            />

            <InfoRow
              label="Định vị"
              value={getLocalizationLabel(
                robot.status
                  ?.localization_quality
              )}
            />

            <InfoRow
              label="Vị trí hiện tại"
              value={getRobotLocation(robot)}
            />

            <InfoRow
              label="Mục tiêu hiện tại"
              value={target}
            />

            <InfoRow
              label="Trạng thái nhiệm vụ"
              value={
                task
                  ? getTaskStatusLabel(
                    task.status
                  )
                  : 'Không có nhiệm vụ'
              }
            />
          </div>
        ) : (
          <div className="robot-info-table">
            <InfoRow
              label="Đoạn đường"
              value={
                robot.status
                  ?.line_segment_id !== null &&
                robot.status
                  ?.line_segment_id !== undefined
                  ? `#${robot.status.line_segment_id}`
                  : 'Chưa có dữ liệu'
              }
            />

            <InfoRow
              label="Trạng thái bám vạch"
              value="Chưa có telemetry"
            />

            <InfoRow
              label="Định vị"
              value={getLocalizationLabel(
                robot.status
                  ?.localization_quality
              )}
            />

            <InfoRow
              label="Mục tiêu hiện tại"
              value={target}
            />
          </div>
        )}
      </section>
    </div>
  );
}


function RobotCamera({ robot }) {
  return (
    <div className="robot-detail-content">
      <section className="robot-info-section">
        <h3>CAMERA HÀNG HÓA</h3>

        {robot.robot_type === 'LINE' ? <UsbCameraPreview /> : <div className="camera-placeholder">
          <Camera size={28} />

          <strong>
            Chưa có hình ảnh trực tiếp
          </strong>

          <span>
            Camera stream chưa được kết nối.
          </span>
        </div>}
      </section>
    </div>
  );
}


function RobotDiagnostics({
  robot,
  alerts,
  backendOnline,
}) {
  return (
    <div className="robot-detail-content">
      <section className="robot-info-section">
        <h3>CHẨN ĐOÁN HỆ THỐNG</h3>

        <div className="robot-info-table">
          <InfoRow
            label="Kết nối robot"
            value={
              robot.status?.online
                ? 'Trực tuyến'
                : 'Ngoại tuyến'
            }
          />

          <InfoRow
            label="Backend API"
            value={backendOnline ? 'Đã kết nối' : 'Mất kết nối'}
          />

          <InfoRow
            label="WebSocket realtime"
            value={backendOnline ? 'Đang hoạt động' : 'Mất kết nối'}
          />

          <InfoRow
            label="Lỗi điều hướng"
            value={getAlertState(
              alerts,
              'NAVIGATION'
            )}
          />

          <InfoRow
            label="Lỗi động cơ"
            value={getAlertState(
              alerts,
              'MOTOR'
            )}
          />

          <InfoRow
            label="Lỗi giao tiếp"
            value={getAlertState(
              alerts,
              'COMMUNICATION'
            )}
          />

          <InfoRow
            label="Tổng cảnh báo chưa xử lý"
            value={String(alerts.length)}
          />
        </div>
      </section>
    </div>
  );
}


function RobotTab({
  active,
  label,
  onClick,
}) {
  return (
    <button
      type="button"
      className={
        `robot-tab ${
          active
            ? 'robot-tab--active'
            : ''
        }`
      }
      onClick={onClick}
    >
      {label}
    </button>
  );
}


function InfoCard({
  icon: Icon,
  label,
  value,
  tone,
}) {
  return (
    <div className="robot-info-card">
      <Icon size={17} />

      <span>{label}</span>

      <strong
        className={
          tone === 'orange'
            ? 'text-orange'
            : ''
        }
      >
        {value}
      </strong>
    </div>
  );
}


function InfoRow({
  label,
  value,
}) {
  return (
    <div className="robot-info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


function getActiveTask(
  robotId,
  tasks
) {
  return tasks.find(
    (task) =>
      task.robot_id === robotId &&
      !TERMINAL_TASK_STATUSES.has(
        task.status
      )
  );
}


function getRobotAccent(robot) {
  return robot.robot_type === 'LINE'
    ? 'green'
    : 'orange';
}


function getRobotDescription(type) {
  if (type === 'AMR') {
    return 'Robot di động tự hành';
  }

  if (type === 'LINE') {
    return 'AGV chạy theo vạch';
  }

  return type ?? 'Không xác định';
}


function getRobotStateLabel(state) {
  const labels = {
    UNKNOWN: 'Chưa xác định',
    IDLE: 'Đang rảnh',
    MOVING: 'Đang di chuyển',
    PICKING_UP: 'Đang nhận hàng',
    DELIVERING: 'Đang giao hàng',
    PAUSED: 'Tạm dừng',
    ERROR: 'Lỗi',
  };

  return labels[state] ??
    'Chưa xác định';
}


function getLocalizationLabel(value) {
  const labels = {
    GOOD: 'Tốt',
    MEDIUM: 'Trung bình',
    POOR: 'Kém',
  };

  return labels[value] ??
    'Chưa có dữ liệu';
}


function formatBattery(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return '—';
  }

  return `${Math.round(value)}%`;
}


function getRobotLocation(robot) {
  const status = robot.status;

  if (!status) {
    return 'Chưa có dữ liệu';
  }


  if (
    robot.robot_type === 'AMR' &&
    status.x !== null &&
    status.y !== null
  ) {
    return (
      `${status.x.toFixed(1)}, ` +
      `${status.y.toFixed(1)}m`
    );
  }


  if (
    robot.robot_type === 'LINE' &&
    status.line_segment_id !== null
  ) {
    return `Đoạn #${status.line_segment_id}`;
  }


  return 'Chưa có dữ liệu';
}


function getCurrentTarget(task) {
  if (!task) {
    return 'Không có';
  }

  if (
    [
      'WAITING',
      'MOVING_TO_PICKUP',
      'ARRIVED_AT_PICKUP',
    ].includes(task.status)
  ) {
    return task.pickup_location_code;
  }

  return task.dropoff_location_code;
}


function getTaskStatusLabel(status) {
  const labels = {
    WAITING: 'Đang chờ',
    MOVING_TO_PICKUP:
      'Đang đến điểm nhận',
    ARRIVED_AT_PICKUP:
      'Đã đến điểm nhận',
    PICKUP_CONFIRMED:
      'Đã xác nhận nhận hàng',
    TRANSPORTING:
      'Đang vận chuyển',
    ARRIVED_AT_DELIVERY:
      'Đã đến điểm giao',
    DELIVERY_CONFIRMED:
      'Đã xác nhận giao hàng',
    COMPLETED: 'Hoàn thành',
    FAILED: 'Thất bại',
    CANCELLED: 'Đã hủy',
  };

  return labels[status] ?? status;
}


function getAlertState(
  alerts,
  keyword
) {
  const found = alerts.some(
    (alert) =>
      alert.alert_type.includes(keyword)
  );

  return found
    ? 'Có cảnh báo'
    : 'Không có';
}
