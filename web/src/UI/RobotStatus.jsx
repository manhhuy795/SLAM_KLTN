import { useEffect, useState } from 'react';

import {
  getRobots,
  getTasks,
} from '../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../services/realtime';


const TERMINAL_TASK_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function RobotStatus() {
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);


  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);

        const [
          robotData,
          taskData,
        ] = await Promise.all([
          getRobots(),
          getTasks(),
        ]);

        setRobots(robotData);
        setTasks(taskData);

        setError(null);
      } catch (err) {
        console.error(
          'Không thể tải trạng thái robot:',
          err
        );

        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
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
    });

    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (!online || !isReconnect) {
          return;
        }

        Promise.all([
          getRobots(),
          getTasks(),
        ]).then(([robotData, taskData]) => {
          setRobots(robotData);
          setTasks(taskData);
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


  if (loading) {
    return (
      <section
        className="fleet-grid"
        aria-label="Trạng thái robot"
      >
        <p>Đang tải trạng thái robot...</p>
      </section>
    );
  }


  if (error) {
    return (
      <section
        className="fleet-grid"
        aria-label="Trạng thái robot"
      >
        <p>
          Không thể tải dữ liệu robot: {error}
        </p>
      </section>
    );
  }


  return (
    <section
      className="fleet-grid"
      aria-label="Trạng thái robot"
    >
      {robots.map((robot) => {
        const view = buildRobotViewModel(
          robot,
          tasks
        );

        return (
          <article
            className={
              `robot-card robot-card--${view.accent}`
            }
            key={robot.id}
          >
            <div className="robot-card-accent" />

            <div className="robot-card-header">
              <div className="robot-identity">
                <div
                  className={
                    `robot-marker robot-marker--${view.accent}`
                  }
                  aria-hidden="true"
                >
                  {view.marker}
                </div>

                <div>
                  <div className="robot-name-row">
                    <h2>{view.id}</h2>

                    <span className="online-badge">
                      {view.online
                        ? 'TRỰC TUYẾN'
                        : 'NGOẠI TUYẾN'}
                    </span>
                  </div>

                  <p>{view.type}</p>
                </div>
              </div>

              <div className="robot-battery">
                <strong>{view.battery}</strong>
                <span>({view.voltage})</span>
              </div>
            </div>

            <div className="robot-kpis">
              <RobotKpi
                label="TRẠNG THÁI"
                value={view.state}
              />

              <RobotKpi
                label="ĐÍCH ĐẾN"
                value={view.target}
                tone="orange"
              />

              <RobotKpi
                label="VỊ TRÍ"
                value={view.location}
              />
            </div>

            <div className="robot-card-footer">
              <div>
                <span>
                  Nhiệm vụ:{' '}

                  <strong className="text-orange">
                    {view.task}

                    {view.progress !== '—' &&
                      ` (${view.progress})`}
                  </strong>
                </span>

                <span className="inline-divider">
                  |
                </span>

                <span>
                  Thời gian dự kiến:{' '}

                  <strong>
                    {view.eta}
                  </strong>
                </span>
              </div>

              <span className="robot-route">
                {view.route}
              </span>
            </div>
          </article>
        );
      })}
    </section>
  );
}


function buildRobotViewModel(
  robot,
  tasks
) {
  const activeTask = tasks.find(
    (task) =>
      task.robot_id === robot.id &&
      !TERMINAL_TASK_STATUSES.has(
        task.status
      )
  );


  const status = robot.status;


  return {
    id: robot.robot_code,

    type: getRobotTypeLabel(
      robot.robot_type
    ),

    accent:
      robot.robot_type === 'LINE'
        ? 'green'
        : 'orange',

    marker:
      robot.robot_type === 'LINE'
        ? '◇'
        : '○►',

    online:
      status?.online ?? false,

    battery:
      formatBattery(
        status?.battery_percent
      ),

    voltage:
      formatVoltage(
        status?.voltage
      ),

    state:
      getRobotStateLabel(
        status?.state
      ),

    target:
      getTaskTarget(activeTask),

    location:
      getRobotLocation(
        robot.robot_type,
        status
      ),

    task:
      activeTask?.task_code ??
      'Không có',

    progress:
      activeTask
        ? `${activeTask.progress}%`
        : '—',

    /*
     * Backend hiện chưa tính ETA.
     * Không tạo số giả.
     */
    eta: '—',

    route:
      activeTask
        ? (
          `${activeTask.pickup_location_code}` +
          ` → ` +
          `${activeTask.dropoff_location_code}`
        )
        : 'Không có nhiệm vụ',
  };
}


function getRobotTypeLabel(
  robotType
) {
  const labels = {
    AMR: 'Robot di động tự hành',

    LINE:
      'AGV chạy theo vạch quang học',
  };

  return labels[robotType] ??
    robotType ??
    'Không xác định';
}


function getRobotStateLabel(
  state
) {
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


function getRobotLocation(
  robotType,
  status
) {
  if (!status) {
    return 'Chưa có dữ liệu';
  }


  /*
   * AMR dùng tọa độ x/y.
   */
  if (
    robotType === 'AMR' &&
    status.x !== null &&
    status.y !== null
  ) {
    return (
      `${status.x.toFixed(1)}, ` +
      `${status.y.toFixed(1)}m`
    );
  }


  /*
   * LINE robot hiện API chỉ trả
   * line_segment_id.
   *
   * Sau này ta sẽ trả segment_code
   * như SEG-03/L-03 từ backend.
   */
  if (
    robotType === 'LINE' &&
    status.line_segment_id !== null
  ) {
    return (
      `Đoạn #${status.line_segment_id}`
    );
  }


  return 'Chưa có dữ liệu';
}


function getTaskTarget(task) {
  if (!task) {
    return '—';
  }


  const goingToPickup = [
    'WAITING',
    'MOVING_TO_PICKUP',
    'ARRIVED_AT_PICKUP',
  ].includes(task.status);


  if (goingToPickup) {
    return task.pickup_location_code;
  }


  return task.dropoff_location_code;
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


function formatVoltage(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return '—';
  }

  return `${value.toFixed(1)}V`;
}


function RobotKpi({
  label,
  value,
  tone,
}) {
  return (
    <div className="robot-kpi">
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
