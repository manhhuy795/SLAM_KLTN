import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';

import {
  getHistory,
  getRobots,
  getTasks,
} from '../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../services/realtime';


const EVENT_TYPES = [
  'TASK_CREATED',
  'TASK_STATUS_CHANGED',
  'TASK_FAILED',
  'TASK_COMPLETED',
  'TASK_PROOF_CREATED',
  'TASK_PICKUP_CONFIRMED',
  'TASK_DELIVERY_CONFIRMED',
  'ROBOT_STATUS_UPDATED',
  'ROBOT_COMMAND_CREATED',
  'ROBOT_COMMAND_ACKNOWLEDGED',
  'ROBOT_COMMAND_FAILED',
  'ALERT_CREATED',
  'ALERT_REPEATED',
  'ALERT_ACKNOWLEDGED',
  'ALERT_RESOLVED',
  'SAFE_STOP_REQUESTED',
];


export default function History() {
  const [events, setEvents] = useState([]);
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);

  const [search, setSearch] = useState('');
  const [robot, setRobot] = useState('all');
  const [task, setTask] = useState('all');
  const [type, setType] = useState('all');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      getRobots(),
      getTasks(),
    ])
      .then(([robotData, taskData]) => {
        setRobots(robotData);
        setTasks(taskData);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);

  const filters = {
    robot_id: robot === 'all' ? undefined : robot,
    task_id: task === 'all' ? undefined : task,
    event_type: type === 'all' ? undefined : type,
    created_from: fromDate
      ? `${fromDate}T00:00:00`
      : undefined,
    created_to: toDate
      ? `${toDate}T23:59:59.999999`
      : undefined,
  };

  useEffect(() => {
    let active = true;

    setLoading(true);
    getHistory(filters)
      .then((historyData) => {
        if (active) {
          setEvents(historyData.map(decorateEvent));
          setError(null);
        }
      })
      .catch((err) => {
        if (active) {
          console.error(err);
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [robot, task, type, fromDate, toDate]);

  useEffect(() => {
    let active = true;

    const refresh = () => {
      getHistory(filters)
        .then((historyData) => {
          if (active) {
            setEvents(historyData.map(decorateEvent));
          }
        })
        .catch((err) => {
          if (active) {
            setError(err.message);
          }
        });
    };

    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === 'EVENT_CREATED') {
        refresh();
      }
    });
    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (online && isReconnect) {
          refresh();
        }
      }
    );

    return () => {
      active = false;
      unsubscribe();
      unsubscribeStatus();
    };
  }, [robot, task, type, fromDate, toDate]);

  const query = search.trim().toLowerCase();
  const filtered = events.filter((event) => {
    if (!query) {
      return true;
    }

    return [
      event.task,
      event.message,
      event.event_type,
    ].some((value) =>
      value?.toLowerCase().includes(query)
    );
  });

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / LỊCH SỬ
          </span>
          <h1>Lịch sử vận hành</h1>
          <p>
            Tra cứu nhiệm vụ, cảnh báo và sự kiện vận hành của hệ thống.
          </p>
        </div>
      </div>

      <section className="panel history-panel">
        <div className="history-toolbar">
          <div className="tasks-search">
            <Search size={15} />
            <input
              value={search}
              placeholder="Tìm task hoặc nội dung sự kiện..."
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <select
            value={robot}
            onChange={(event) => setRobot(event.target.value)}
          >
            <option value="all">Tất cả robot</option>
            {robots.map((item) => (
              <option key={item.id} value={item.id}>
                {item.robot_code}
              </option>
            ))}
          </select>

          <select
            value={task}
            onChange={(event) => setTask(event.target.value)}
          >
            <option value="all">Tất cả task</option>
            {tasks.map((item) => (
              <option key={item.id} value={item.id}>
                {item.task_code}
              </option>
            ))}
          </select>

          <select
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <option value="all">Tất cả event</option>
            {EVENT_TYPES.map((eventType) => (
              <option key={eventType} value={eventType}>
                {eventType}
              </option>
            ))}
          </select>

          <input
            className="history-date-input"
            type="date"
            aria-label="Từ ngày"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
          <input
            className="history-date-input"
            type="date"
            aria-label="Đến ngày"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
        </div>

        {error && <p>Không thể tải lịch sử: {error}</p>}

        <div className="history-table-wrapper">
          <table className="management-table history-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Loại</th>
                <th>Robot</th>
                <th>Nhiệm vụ</th>
                <th>Sự kiện</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan="5">Đang tải lịch sử...</td>
                </tr>
              )}

              {!loading && !error && filtered.length === 0 && (
                <tr>
                  <td colSpan="5">Không có sự kiện.</td>
                </tr>
              )}

              {!loading && filtered.map((event) => (
                <tr key={event.id}>
                  <td className="mono">{event.time}</td>
                  <td>{event.type}</td>
                  <td>{event.robot}</td>
                  <td className="text-orange">{event.task}</td>
                  <td>{event.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}


function decorateEvent(event) {
  return {
    ...event,
    time: formatTime(event.created_at),
    type: getEventTypeLabel(event.event_type),
    robot: event.robot_code ?? '—',
    task: event.task_code ?? '—',
  };
}


function getEventTypeLabel(eventType) {
  if (eventType.startsWith('TASK_')) {
    return 'Nhiệm vụ';
  }

  if (eventType.startsWith('ALERT_')) {
    return 'Cảnh báo';
  }

  if (
    eventType.includes('LOCALIZATION') ||
    eventType.includes('APRILTAG')
  ) {
    return 'Định vị';
  }

  if (eventType.includes('NAVIGATION')) {
    return 'Điều hướng';
  }

  if (eventType.startsWith('ROBOT_')) {
    return 'Robot';
  }

  return 'Hệ thống';
}


function formatTime(value) {
  if (!value) {
    return '—';
  }

  const hasTimezone =
    value.endsWith('Z') ||
    /[+-]\d{2}:\d{2}$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('vi-VN', {
    hour12: false,
  });
}
