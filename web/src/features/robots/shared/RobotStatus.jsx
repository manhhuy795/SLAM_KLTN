import { useEffect, useState } from 'react';

import {
  getRobots,
  getRosPose,
  getTasks,
} from '../../../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../../../services/realtime';
import { getAgvState } from '../agv/agv';


const TERMINAL_TASK_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function RobotStatus({ onRobotDetails }) {
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [agvConnections, setAgvConnections] = useState({});
  const [amrPose, setAmrPose] = useState(null);
  const [now, setNow] = useState(Date.now());
  const lineCodes = robots.filter((robot) => robot.robot_type === 'LINE')
    .map((robot) => robot.robot_code).join(',');

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
    getRosPose().then(setAmrPose).catch(() => {});
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    if (!lineCodes) return;
    let active = true;
    const load = () => lineCodes.split(',').forEach((code) => {
      getAgvState(code).then((state) => {
        if (active) setAgvConnections((current) => current[code] === !!state.connected
          ? current : { ...current, [code]: !!state.connected });
      }).catch(() => {
        if (active) setAgvConnections((current) => current[code] === false
          ? current : { ...current, [code]: false });
      });
    });
    load();
    const timer = window.setInterval(load, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [lineCodes]);


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

      if (message.type === 'ROBOT_POSE_UPDATED') setAmrPose(message.data);
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
          tasks,
          agvConnections[robot.robot_code],
          amrPose,
          now
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

            </div>

            <div className="robot-kpis">
              <RobotKpi
                label="NHIỆM VỤ"
                value={view.mission}
              />

              <RobotKpi
                label="ĐÍCH ĐẾN"
                value={view.target}
                tone="orange"
              />

              <RobotKpi
                label="VỊ TRÍ ĐÃ XÁC MINH"
                value={view.verifiedPosition}
              />
            </div>

            <div className="robot-card-footer">
              <div>
                <span>
                  Nhiệm vụ:{' '}

                  <strong className="text-orange">
                    {view.task}
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

              <button type="button" className="text-link" onClick={() => onRobotDetails(robot.robot_code)}>
                Xem chi tiết robot
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
}


function buildRobotViewModel(
  robot,
  tasks,
  agvConnected,
  amrPose,
  now
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

    online: robot.robot_type === 'LINE' ? (agvConnected ?? false) : (status?.online ?? false),

    mission: activeTask?.status ?? 'N/A',

    target:
      getTaskTarget(activeTask),

    verifiedPosition: robot.robot_type === 'AMR' && status?.online
      && status?.localization_quality === 'GOOD' && amrPose?.robot_id === robot.id
      && amrPose.frame_id === 'map' && Number.isFinite(amrPose.x) && Number.isFinite(amrPose.y)
      && Number.isFinite(amrPose.timestamp) && now / 1000 - amrPose.timestamp >= 0
      && now / 1000 - amrPose.timestamp <= 5
      ? `${amrPose.x.toFixed(1)}, ${amrPose.y.toFixed(1)} m` : 'N/A',

    task:
      activeTask?.task_code ??
      'Không có',

    /*
     * Backend hiện chưa tính ETA.
     * Không tạo số giả.
     */
    eta: 'N/A',
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


function getTaskTarget(task) {
  if (!task) {
    return 'N/A';
  }


  const goingToPickup = [
    'WAITING',
    'MOVING_TO_PICKUP',
    'ARRIVED_AT_PICKUP',
  ].includes(task.status);


  if (goingToPickup) {
    return task.pickup_location_code ?? 'N/A';
  }


  return task.dropoff_location_code ?? 'N/A';
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
