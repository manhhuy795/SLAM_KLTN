import {
  useEffect,
  useState,
} from 'react';

import {
  AlertTriangle,
  Clock3,
  Menu,
  StopCircle,
  X,
} from 'lucide-react';

import { requestSafeStop } from '../services/api';
import { subscribeRealtime } from '../services/realtime';
import {
  aggregateSafeStopState,
  recordSafeStopResult,
} from '../services/safeStop';


export default function Header({
  metrics,
  backendOnline,
  operator,
  onMenuToggle,
}) {
  const [safeStopOpen, setSafeStopOpen] =
    useState(false);

  const [safeStopState, setSafeStopState] =
    useState('IDLE');

  const [safeStopResults, setSafeStopResults] =
    useState({});

  const [time, setTime] =
    useState(new Date());


  useEffect(() => {
    const timer = setInterval(
      () => setTime(new Date()),
      1000
    );

    return () => clearInterval(timer);
  }, []);


  useEffect(() => subscribeRealtime((message) => {
    if (![
      'COMMAND_ACKNOWLEDGED',
      'COMMAND_FAILED',
    ].includes(message.type)) {
      return;
    }

    const command = message.data;

    if (command.command !== 'SAFE_STOP') {
      return;
    }

    const result = message.type === 'COMMAND_FAILED'
      ? 'FAILED'
      : 'ACKNOWLEDGED';

    setSafeStopResults((current) => {
      return recordSafeStopResult(
        current,
        command.id,
        result,
      );
    });
  }), []);


  useEffect(() => {
    if (Object.keys(safeStopResults).length > 0) {
      setSafeStopState(
        aggregateSafeStopState(safeStopResults)
      );
    }
  }, [safeStopResults]);


  async function handleSafeStop() {
    if (
      safeStopState === 'SENDING'
      || safeStopState === 'PENDING'
    ) {
      return;
    }

    setSafeStopState('SENDING');

    try {
      const commands = await requestSafeStop();
      const results = Object.fromEntries(
        commands.map((command) => [
          command.id,
          'PENDING',
        ])
      );

      setSafeStopResults(results);
      setSafeStopState(
        commands.length > 0
          ? aggregateSafeStopState(results)
          : 'NO_TARGET'
      );
    } catch (error) {
      console.error('Không thể gửi yêu cầu Safe Stop:', error);
      setSafeStopState('FAILED');
    }
  }


  const safeStopMessage = {
    IDLE: 'Chưa gửi yêu cầu.',
    SENDING: 'Đang gửi yêu cầu dừng...',
    PENDING: 'Đã gửi yêu cầu. Đang chờ robot acknowledgement.',
    ACKNOWLEDGED: 'Robot đã xác nhận yêu cầu dừng.',
    FAILED: 'Yêu cầu dừng thất bại hoặc bị từ chối.',
    NO_TARGET: 'Không có robot online để nhận yêu cầu.',
  }[safeStopState];


  return (
    <>
      <header className="top-header">
        <div className="header-brand-zone">
          <button
            className="mobile-menu-button"
            type="button"
            onClick={onMenuToggle}
            aria-label="Mở menu"
          >
            <Menu size={18} />
          </button>


          <div className="brand-lockup">
            <span className="brand-mark" />

            <div className="brand-copy">
              <div className="brand-title-row">
                <span className="brand-title">
                  WRMS CONTROL
                </span>

                <span className="brand-divider">
                  |
                </span>

                <span className="brand-subtitle">
                  Warehouse Testbed
                </span>
              </div>
            </div>
          </div>


          <div className="header-separator" />


          <div className="system-badge">
            <span className="muted-label">
              System:
            </span>

            <span
              className={
                backendOnline
                  ? 'status-dot status-dot--green'
                  : 'status-dot'
              }
            />

            <span
              className={
                backendOnline
                  ? 'system-online'
                  : 'muted-label'
              }
            >
              {backendOnline
                ? 'ONLINE'
                : 'OFFLINE'}
            </span>
          </div>
        </div>


        <div className="quick-metrics">
          <Metric
            label="Robot"
            value={metrics.totalRobots}
          />

          <Metric
            label="Hoạt động"
            value={metrics.activeRobots}
            tone="green"
          />

          <Metric
            label="Đang rảnh"
            value={metrics.idleRobots}
            tone="muted"
          />

          <Metric
            label="Nhiệm vụ"
            value={metrics.activeTasks}
            tone="orange"
          />

          <Metric
            label="Cảnh báo"
            value={metrics.alerts}
            tone="amber"
          />
        </div>


        <div className="header-actions">
          <div className="time-chip">
            <Clock3 size={14} />

            <strong>
              {formatTime(time)}
            </strong>

            <span>LOCAL</span>
          </div>


          <button
            className="safe-stop-button"
            type="button"
            onClick={() =>
              setSafeStopOpen(true)
            }
          >
            <StopCircle size={15} />

            <span>
              DỪNG AN TOÀN
            </span>
          </button>


          <div className="operator-block">
            <div className="operator-avatar">
              OP
            </div>

            <div className="operator-copy">
              <strong>
                {operator?.full_name ?? 'Chưa có operator'}
              </strong>

              <span>
                {operator?.operator_code ?? 'Testbed'}
              </span>
            </div>
          </div>
        </div>
      </header>


      {safeStopOpen && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="safe-stop-title"
        >
          <div className="safe-stop-modal">
            <div className="modal-header">
              <div>
                <AlertTriangle size={17} />

                <strong id="safe-stop-title">
                  Yêu cầu dừng an toàn
                </strong>
              </div>

              <button
                type="button"
                onClick={() =>
                  setSafeStopOpen(false)
                }
                aria-label="Đóng"
              >
                <X size={17} />
              </button>
            </div>


            <p>
              Đây là yêu cầu dừng bằng phần mềm
              gửi đến bộ điều khiển robot.
              Robot phải tự xử lý điều kiện an toàn
              trước khi dừng.
            </p>

            <p>
              <strong>
                Đây KHÔNG phải nút E-STOP vật lý.
              </strong>
            </p>


            <div className="create-task-note">
              {safeStopMessage}
            </div>


            <div className="modal-actions">
              <button
                className="secondary-button modal-button"
                type="button"
                onClick={() =>
                  setSafeStopOpen(false)
                }
              >
                Đóng
              </button>

              <button
                className="danger-button modal-button"
                type="button"
                disabled={
                  safeStopState === 'SENDING'
                  || safeStopState === 'PENDING'
                }
                onClick={handleSafeStop}
              >
                Gửi yêu cầu dừng
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


function Metric({
  label,
  value,
  tone = 'default',
}) {
  return (
    <div className="metric-item">
      <span>
        {label}:
      </span>

      <strong
        className={
          `metric-value metric-value--${tone}`
        }
      >
        {String(value).padStart(2, '0')}
      </strong>
    </div>
  );
}


function formatTime(date) {
  return date.toLocaleTimeString(
    'vi-VN',
    {
      hour12: false,
    }
  );
}
