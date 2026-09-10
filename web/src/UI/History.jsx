import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';

import {
  getHistory,
  getRobots,
  getTasks,
} from '../services/api';
import { subscribeRealtime } from '../services/realtime';


export default function History() {
  const [events, setEvents] = useState([]);
  const [search, setSearch] = useState('');
  const [robot, setRobot] = useState('all');
  const [type, setType] = useState('all');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);


  useEffect(() => {
    Promise.all([
      getHistory(),
      getRobots(),
      getTasks(),
    ])
      .then(([historyData, robotData, taskData]) => {
        const robotCodes = Object.fromEntries(
          robotData.map((item) => [
            item.id,
            item.robot_code,
          ])
        );

        const taskCodes = Object.fromEntries(
          taskData.map((item) => [
            item.id,
            item.task_code,
          ])
        );

        setEvents(
          historyData.map((event) => ({
            ...event,

            time: formatTime(event.created_at),

            type: getEventTypeLabel(
              event.event_type
            ),

            robot:
              event.robot_id === null
                ? '—'
                : robotCodes[event.robot_id] ??
                  `Robot #${event.robot_id}`,

            task:
              event.task_id === null
                ? '—'
                : taskCodes[event.task_id] ??
                  `Task #${event.task_id}`,
          }))
        );

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
    return subscribeRealtime((message) => {
      if (message.type !== 'EVENT_CREATED') {
        return;
      }

      const event = message.data;
      const decorated = {
        ...event,
        time: formatTime(event.created_at),
        type: getEventTypeLabel(event.event_type),
        robot: event.robot_id === null
          ? '—'
          : `Robot #${event.robot_id}`,
        task: event.task_id === null
          ? '—'
          : `Task #${event.task_id}`,
      };

      setEvents((current) => [
        decorated,
        ...current.filter(
          (item) => item.id !== decorated.id
        ),
      ]);
    });
  }, []);


  const query =
    search.trim().toLowerCase();


  const filtered = events.filter((event) => {
    const matchesRobot =
      robot === 'all' ||
      event.robot === robot;

    const matchesType =
      type === 'all' ||
      event.type === type;

    const matchesSearch =
      !query ||
      event.task
        .toLowerCase()
        .includes(query) ||
      event.message
        .toLowerCase()
        .includes(query);

    return (
      matchesRobot &&
      matchesType &&
      matchesSearch
    );
  });


  const robots = [
    ...new Set(
      events
        .map((event) => event.robot)
        .filter((value) => value !== '—')
    ),
  ];


  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / LỊCH SỬ
          </span>

          <h1>Lịch sử vận hành</h1>

          <p>
            Tra cứu nhiệm vụ, cảnh báo
            và sự kiện vận hành của hệ thống.
          </p>
        </div>
      </div>


      <section className="panel history-panel">
        <div className="history-toolbar">
          <div className="tasks-search">
            <Search size={15} />

            <input
              value={search}
              placeholder="Tìm Task ID hoặc nội dung sự kiện..."
              onChange={(event) =>
                setSearch(event.target.value)
              }
            />
          </div>


          <select
            value={robot}
            onChange={(event) =>
              setRobot(event.target.value)
            }
          >
            <option value="all">
              Tất cả robot
            </option>

            {robots.map((robotCode) => (
              <option
                key={robotCode}
                value={robotCode}
              >
                {robotCode}
              </option>
            ))}
          </select>


          <select
            value={type}
            onChange={(event) =>
              setType(event.target.value)
            }
          >
            <option value="all">
              Tất cả loại
            </option>

            <option value="Nhiệm vụ">
              Nhiệm vụ
            </option>

            <option value="Cảnh báo">
              Cảnh báo
            </option>

            <option value="Định vị">
              Định vị
            </option>

            <option value="Điều hướng">
              Điều hướng
            </option>

            <option value="Robot">
              Robot
            </option>

            <option value="Hệ thống">
              Hệ thống
            </option>
          </select>
        </div>


        {error && (
          <p>
            Không thể tải lịch sử: {error}
          </p>
        )}


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
                  <td colSpan="5">
                    Đang tải lịch sử...
                  </td>
                </tr>
              )}


              {!loading &&
                !error &&
                filtered.length === 0 && (
                  <tr>
                    <td colSpan="5">
                      Không có sự kiện.
                    </td>
                  </tr>
                )}


              {!loading &&
                filtered.map((event) => (
                  <tr key={event.id}>
                    <td className="mono">
                      {event.time}
                    </td>

                    <td>
                      {event.type}
                    </td>

                    <td>
                      {event.robot}
                    </td>

                    <td className="text-orange">
                      {event.task}
                    </td>

                    <td>
                      {event.message}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
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

  if (
    eventType.includes('NAVIGATION')
  ) {
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

  const date = new Date(
    hasTimezone
      ? value
      : `${value}Z`
  );

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString(
    'vi-VN',
    {
      hour12: false,
    }
  );
}
