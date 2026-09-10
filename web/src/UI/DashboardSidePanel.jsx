import { useEffect, useState } from 'react';

import {
  acknowledgeAlert,
  getAlerts,
  getHistory,
  getRobots,
  getTasks,
} from '../services/api';
import { subscribeRealtime } from '../services/realtime';


const TERMINAL_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function DashboardSidePanel({
  operatorId,
  onNavigate,
}) {
  const [alerts, setAlerts] = useState([]);
  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [robotCodes, setRobotCodes] = useState({});

  const [loading, setLoading] = useState(true);
  const [busyAlertId, setBusyAlertId] = useState(null);
  const [error, setError] = useState(null);


  useEffect(() => {
    Promise.all([
      getAlerts(),
      getHistory(),
      getTasks(),
      getRobots(),
    ])
      .then(([
        alertData,
        eventData,
        taskData,
        robotData,
      ]) => {
        setAlerts(alertData);
        setEvents(eventData.slice(0, 6));
        setTasks(taskData);

        setRobotCodes(
          Object.fromEntries(
            robotData.map((robot) => [
              robot.id,
              robot.robot_code,
            ])
          )
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

      if (message.type === 'ROBOT_STATUS_UPDATED') {
        setRobotCodes((current) => ({
          ...current,
          [message.data.id]: message.data.robot_code,
        }));
      }

      if (message.type === 'EVENT_CREATED') {
        setEvents((current) => [
          message.data,
          ...current.filter(
            (event) => event.id !== message.data.id
          ),
        ].slice(0, 6));
      }
    });
  }, []);


  const importantAlert =
    getImportantAlert(alerts);

  const activeAlertCount =
    alerts.filter(
      (alert) =>
        alert.status !== 'RESOLVED'
    ).length;

  const unacknowledgedCount =
    alerts.filter(
      (alert) =>
        alert.status === 'NEW'
    ).length;

  const stats =
    getTaskStats(tasks);

  const latestCompletedTask =
    getLatestCompletedTask(tasks);


  async function handleAcknowledge(alert) {
    if (operatorId === null) {
      setError('Không có operator hoạt động để xác nhận cảnh báo.');
      return;
    }

    try {
      setBusyAlertId(alert.id);
      setError(null);

      const updated =
        await acknowledgeAlert(
          alert.id,
          operatorId
        );

      setAlerts((current) =>
        current.map((item) =>
          item.id === updated.id
            ? updated
            : item
        )
      );
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setBusyAlertId(null);
    }
  }


  return (
    <>
      <section className="panel alerts-panel">
        <div className="section-header">
          <div className="section-title-group">
            <span className="section-indicator section-indicator--amber" />

            <h2>
              CẢNH BÁO QUAN TRỌNG
            </h2>
          </div>

          <span className="warning-count">
            {activeAlertCount} CẢNH BÁO
          </span>
        </div>


        {error && (
          <div className="alert-card">
            <p>
              Không thể tải dữ liệu:
              {' '}
              {error}
            </p>
          </div>
        )}


        {loading && (
          <div className="alert-card">
            <p>
              Đang tải cảnh báo...
            </p>
          </div>
        )}


        {!loading &&
          !error &&
          !importantAlert && (
            <div className="alert-card alert-card--acknowledged">
              <p>
                Hiện không có cảnh báo
                chưa xử lý.
              </p>

              <div className="alert-card-actions">
                <button
                  className="text-link"
                  type="button"
                  onClick={() =>
                    onNavigate?.('alerts')
                  }
                >
                  Xem tất cả cảnh báo →
                </button>
              </div>
            </div>
          )}


        {!loading &&
          !error &&
          importantAlert && (
            <AlertCard
              alert={importantAlert}
              robotCode={
                robotCodes[
                  importantAlert.robot_id
                ]
              }
              busy={
                busyAlertId ===
                importantAlert.id
              }
              unacknowledgedCount={
                unacknowledgedCount
              }
              onAcknowledge={() =>
                handleAcknowledge(
                  importantAlert
                )
              }
              onViewAll={() =>
                onNavigate?.('alerts')
              }
            />
          )}
      </section>


      <section className="panel recent-events-panel">
        <div className="section-header">
          <div className="section-title-group">
            <span className="section-indicator section-indicator--orange" />

            <h2>
              SỰ KIỆN GẦN ĐÂY
            </h2>
          </div>

          <span className="section-caption mono">
            Nhật ký vận hành
          </span>
        </div>


        <div className="event-list">
          {loading && (
            <div className="event-item">
              <p>
                Đang tải sự kiện...
              </p>
            </div>
          )}


          {!loading &&
            events.length === 0 && (
              <div className="event-item">
                <p>
                  Chưa có sự kiện.
                </p>
              </div>
            )}


          {!loading &&
            events.map((event) => {
              const tone =
                getEventTone(
                  event.event_type
                );

              return (
                <div
                  key={event.id}
                  className={
                    tone
                      ? `event-item event-item--${tone}`
                      : 'event-item'
                  }
                >
                  <div className="event-item-topline">
                    <strong>
                      {formatTime(
                        event.created_at
                      )}
                    </strong>

                    <span>
                      {getEventSource(
                        event,
                        robotCodes
                      )}
                    </span>
                  </div>

                  <p>
                    {event.message}
                  </p>
                </div>
              );
            })}
        </div>


        <div className="event-footer">
          <button
            className="text-link"
            type="button"
            onClick={() =>
              onNavigate?.('history')
            }
          >
            Xem toàn bộ lịch sử →
          </button>

          <span>
            Đang hiển thị {events.length} sự kiện
          </span>
        </div>
      </section>


      <section className="panel task-summary-panel">
        <div className="section-header">
          <div className="section-title-group">
            <span className="section-indicator section-indicator--orange" />

            <h2>
              TỔNG QUAN NHIỆM VỤ
            </h2>
          </div>

          <span className="section-caption mono">
            Trạng thái nhiệm vụ
          </span>
        </div>


        <div className="summary-stats">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className={
                `summary-stat summary-stat--${
                  stat.tone ?? 'default'
                }`
              }
            >
              <span>
                {stat.label}
              </span>

              <strong>
                {stat.value}
              </strong>
            </div>
          ))}
        </div>


        <div className="latest-task">
          <div className="latest-task-heading">
            <span>
              NHIỆM VỤ HOÀN THÀNH GẦN NHẤT
            </span>

            <strong>
              {latestCompletedTask
                ? `${formatTime(
                    latestCompletedTask.completed_at
                  )} (Hoàn thành)`
                : 'Chưa có'}
            </strong>
          </div>


          {latestCompletedTask ? (
            <div className="latest-task-row">
              <div>
                <strong>
                  {latestCompletedTask.task_code}
                </strong>

                <span className="inline-divider">
                  |
                </span>

                <span>
                  Robot:{' '}

                  <b>
                    {latestCompletedTask.robot_code ??
                      'Chưa gán'}
                  </b>
                </span>
              </div>

              <span>
                {latestCompletedTask.pickup_location_name ??
                  latestCompletedTask.pickup_location_code}
                {' → '}
                {latestCompletedTask.dropoff_location_name ??
                  latestCompletedTask.dropoff_location_code}
              </span>
            </div>
          ) : (
            <div className="latest-task-row">
              <span>
                Chưa có nhiệm vụ hoàn thành.
              </span>
            </div>
          )}
        </div>
      </section>
    </>
  );
}


function AlertCard({
  alert,
  robotCode,
  busy,
  unacknowledgedCount,
  onAcknowledge,
  onViewAll,
}) {
  return (
    <div
      className={
        alert.status === 'ACKNOWLEDGED'
          ? 'alert-card alert-card--acknowledged'
          : 'alert-card'
      }
    >
      <div className="alert-card-topline">
        <div>
          <span className="warning-label">
            {getSeverityLabel(
              alert.severity
            )}
          </span>

          <strong>
            Robot:{' '}
            {robotCode ??
              `#${alert.robot_id}`}
          </strong>
        </div>

        <span>
          {formatTime(
            alert.last_seen_at
          )}
        </span>
      </div>


      <p>
        {alert.message}
      </p>


      <div className="alert-card-actions">
        <button
          className="text-link"
          type="button"
          onClick={onViewAll}
        >
          Xem tất cả cảnh báo
          {' '}
          ({unacknowledgedCount} chưa xác nhận)
          {' →'}
        </button>


        {alert.status === 'NEW' && (
          <button
            className="primary-button"
            type="button"
            disabled={busy}
            onClick={onAcknowledge}
          >
            {busy
              ? 'ĐANG XỬ LÝ...'
              : 'XÁC NHẬN'}
          </button>
        )}


        {alert.status ===
          'ACKNOWLEDGED' && (
          <button
            className="secondary-button"
            type="button"
            disabled
          >
            ĐÃ XÁC NHẬN
          </button>
        )}
      </div>
    </div>
  );
}


function getImportantAlert(alerts) {
  const active =
    alerts.filter(
      (alert) =>
        alert.status !== 'RESOLVED'
    );

  return (
    active.find(
      (alert) =>
        alert.severity === 'CRITICAL'
    ) ??
    active.find(
      (alert) =>
        alert.severity === 'WARNING'
    ) ??
    active[0] ??
    null
  );
}


function getTaskStats(tasks) {
  const waiting =
    tasks.filter(
      (task) =>
        task.status === 'WAITING'
    ).length;


  const active =
    tasks.filter(
      (task) =>
        !TERMINAL_STATUSES.has(
          task.status
        ) &&
        task.status !== 'WAITING'
    ).length;


  const completed =
    tasks.filter(
      (task) =>
        task.status === 'COMPLETED'
    ).length;


  const failed =
    tasks.filter(
      (task) =>
        task.status === 'FAILED'
    ).length;


  return [
    {
      label: 'Đang chờ',
      value: waiting,
    },
    {
      label: 'Đang thực hiện',
      value: active,
      tone: 'orange',
    },
    {
      label: 'Hoàn thành',
      value: completed,
      tone: 'green',
    },
    {
      label: 'Thất bại',
      value: failed,
      tone: 'muted',
    },
  ];
}


function getLatestCompletedTask(tasks) {
  return (
    tasks
      .filter(
        (task) =>
          task.status === 'COMPLETED'
      )
      .sort(
        (a, b) =>
          getTimestamp(
            b.completed_at
          ) -
          getTimestamp(
            a.completed_at
          )
      )[0] ??
    null
  );
}


function getTimestamp(value) {
  if (!value) {
    return 0;
  }

  const date =
    parseApiDate(value);

  return Number.isNaN(
    date.getTime()
  )
    ? 0
    : date.getTime();
}


function getEventSource(
  event,
  robotCodes
) {
  if (event.robot_id !== null) {
    return (
      robotCodes[event.robot_id] ??
      `Robot #${event.robot_id}`
    );
  }

  if (event.source === 'OPERATOR') {
    return 'Operator';
  }

  if (event.source === 'ROBOT') {
    return 'Robot';
  }

  return 'Hệ thống';
}


function getEventTone(eventType) {
  if (
    eventType.startsWith('ALERT_')
  ) {
    if (
      eventType ===
      'ALERT_RESOLVED'
    ) {
      return 'green';
    }

    return 'amber';
  }


  if (
    eventType ===
    'TASK_COMPLETED'
  ) {
    return 'green';
  }


  if (
    eventType.startsWith('TASK_')
  ) {
    return 'orange';
  }


  return null;
}


function getSeverityLabel(severity) {
  const labels = {
    INFO: 'THÔNG TIN',
    WARNING: 'CẢNH BÁO',
    CRITICAL: 'NGHIÊM TRỌNG',
  };

  return labels[severity] ?? severity;
}


function parseApiDate(value) {
  const hasTimezone =
    value.endsWith('Z') ||
    /[+-]\d{2}:\d{2}$/.test(value);

  return new Date(
    hasTimezone
      ? value
      : `${value}Z`
  );
}


function formatTime(value) {
  if (!value) {
    return '—';
  }

  const date =
    parseApiDate(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return value;
  }

  return date.toLocaleTimeString(
    'vi-VN',
    {
      hour12: false,
    }
  );
}
