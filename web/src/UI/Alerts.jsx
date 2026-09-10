import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
} from 'lucide-react';

import {
  acknowledgeAlert,
  getAlerts,
  getRobots,
  resolveAlert,
} from '../services/api';
import { subscribeRealtime } from '../services/realtime';


export default function Alerts({ operatorId }) {
  const [alerts, setAlerts] = useState([]);
  const [robotCodes, setRobotCodes] = useState({});
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);


  useEffect(() => {
    Promise.all([
      getAlerts(),
      getRobots(),
    ])
      .then(([alertData, robotData]) => {
        setAlerts(alertData);

        setRobotCodes(
          Object.fromEntries(
            robotData.map((robot) => [
              robot.id,
              robot.robot_code,
            ])
          )
        );
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
        replaceAlert(message.data);
      }
    });
  }, []);


  const filtered = useMemo(() => {
    if (filter === 'all') {
      return alerts;
    }

    return alerts.filter(
      (alert) =>
        alert.status === filter
    );
  }, [alerts, filter]);


  async function acknowledge(alert) {
    if (operatorId === null) {
      setError('Không có operator hoạt động để xác nhận cảnh báo.');
      return;
    }

    try {
      setBusyId(alert.id);
      setError(null);

      const updated =
        await acknowledgeAlert(
          alert.id,
          operatorId
        );

      replaceAlert(updated);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }


  async function resolve(alert) {
    if (operatorId === null) {
      setError('Không có operator hoạt động để xử lý cảnh báo.');
      return;
    }

    try {
      setBusyId(alert.id);
      setError(null);

      const updated =
        await resolveAlert(
          alert.id,
          operatorId
        );

      replaceAlert(updated);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }


  function replaceAlert(updated) {
    setAlerts((current) => {
      const exists = current.some(
        (alert) => alert.id === updated.id
      );

      return exists
        ? current.map((alert) =>
          alert.id === updated.id
            ? updated
            : alert
        )
        : [updated, ...current];
    });
  }


  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / CẢNH BÁO
          </span>

          <h1>Quản lý cảnh báo</h1>

          <p>
            Theo dõi và xử lý các sự kiện
            cần operator chú ý.
          </p>
        </div>
      </div>


      <div className="alert-summary-grid">
        <AlertSummary
          label="Mới"
          value={countStatus(alerts, 'NEW')}
          tone="red"
        />

        <AlertSummary
          label="Đã xác nhận"
          value={countStatus(
            alerts,
            'ACKNOWLEDGED'
          )}
          tone="amber"
        />

        <AlertSummary
          label="Đã xử lý"
          value={countStatus(
            alerts,
            'RESOLVED'
          )}
          tone="green"
        />
      </div>


      <section className="panel alerts-page-panel">
        <div className="tasks-toolbar">
          <div className="tasks-filters">
            <Filter
              active={filter === 'all'}
              onClick={() =>
                setFilter('all')
              }
            >
              Tất cả
            </Filter>

            <Filter
              active={filter === 'NEW'}
              onClick={() =>
                setFilter('NEW')
              }
            >
              Mới
            </Filter>

            <Filter
              active={
                filter === 'ACKNOWLEDGED'
              }
              onClick={() =>
                setFilter('ACKNOWLEDGED')
              }
            >
              Đã xác nhận
            </Filter>

            <Filter
              active={
                filter === 'RESOLVED'
              }
              onClick={() =>
                setFilter('RESOLVED')
              }
            >
              Đã xử lý
            </Filter>
          </div>
        </div>


        {error && (
          <p>
            Không thể xử lý cảnh báo:
            {' '}
            {error}
          </p>
        )}


        <div className="alerts-page-list">
          {loading && (
            <p>Đang tải cảnh báo...</p>
          )}


          {!loading &&
            filtered.length === 0 && (
              <p>
                Không có cảnh báo.
              </p>
            )}


          {!loading &&
            filtered.map((alert) => {
              const severity =
                alert.severity.toLowerCase();

              return (
                <article
                  key={alert.id}
                  className={
                    `alerts-page-item alerts-page-item--${severity}`
                  }
                >
                  <div className="alerts-page-icon">
                    {severity ===
                    'critical' ? (
                      <CircleAlert
                        size={18}
                      />
                    ) : (
                      <AlertTriangle
                        size={18}
                      />
                    )}
                  </div>


                  <div className="alerts-page-copy">
                    <div className="alerts-page-heading">
                      <div>
                        <strong>
                          {alert.alert_code}
                        </strong>

                        <span>
                          {robotCodes[
                            alert.robot_id
                          ] ??
                            `Robot #${alert.robot_id}`}
                        </span>

                        <span>
                          {getAlertTypeLabel(
                            alert.alert_type
                          )}
                        </span>
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


                    <div className="alerts-page-meta">
                      <span>
                        Số lần xuất hiện:
                        {' '}

                        <strong>
                          {
                            alert.occurrence_count
                          }
                        </strong>
                      </span>

                      <AlertState
                        state={alert.status}
                      />
                    </div>
                  </div>


                  <div className="alerts-page-actions">
                    {alert.status ===
                      'NEW' && (
                      <button
                        className="primary-button"
                        type="button"
                        disabled={
                          busyId === alert.id ||
                          operatorId === null
                        }
                        onClick={() =>
                          acknowledge(alert)
                        }
                      >
                        {busyId === alert.id
                          ? 'Đang xử lý...'
                          : 'Xác nhận'}
                      </button>
                    )}


                    {alert.status ===
                      'ACKNOWLEDGED' && (
                      <button
                        className="secondary-button"
                        type="button"
                        disabled={
                          busyId === alert.id ||
                          operatorId === null
                        }
                        onClick={() =>
                          resolve(alert)
                        }
                      >
                        <CheckCircle2
                          size={14}
                        />

                        {busyId === alert.id
                          ? 'Đang xử lý...'
                          : 'Đánh dấu đã xử lý'}
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
        </div>
      </section>
    </div>
  );
}


function countStatus(
  alerts,
  status
) {
  return alerts.filter(
    (alert) =>
      alert.status === status
  ).length;
}


function AlertSummary({
  label,
  value,
  tone,
}) {
  return (
    <div
      className={
        `alert-summary alert-summary--${tone}`
      }
    >
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


function AlertState({ state }) {
  const labels = {
    NEW: 'MỚI',
    ACKNOWLEDGED: 'ĐÃ XÁC NHẬN',
    RESOLVED: 'ĐÃ XỬ LÝ',
  };

  return (
    <span
      className={
        `alert-state alert-state--${state.toLowerCase()}`
      }
    >
      {labels[state] ?? state}
    </span>
  );
}


function Filter({
  active,
  children,
  onClick,
}) {
  return (
    <button
      className={
        `task-filter-button ${
          active
            ? 'task-filter-button--active'
            : ''
        }`
      }
      type="button"
      onClick={onClick}
    >
      {children}
    </button>
  );
}


function getAlertTypeLabel(type) {
  const labels = {
    OBSTACLE_DETECTED:
      'Vật cản',

    NAVIGATION_FAILED:
      'Điều hướng',

    LOCALIZATION_FAILED:
      'Định vị',

    LIDAR_ERROR:
      'LiDAR',

    MOTOR_ERROR:
      'Động cơ',

    COMMUNICATION_ERROR:
      'Kết nối',
  };

  return labels[type] ?? type;
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

  if (
    Number.isNaN(date.getTime())
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
