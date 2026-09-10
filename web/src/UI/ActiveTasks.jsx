import { useCallback, useEffect, useState } from 'react';

import {
  getTasks,
  pauseTask,
  resumeTask,
  cancelTask,
} from '../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../services/realtime';


const TERMINAL_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


const TASK_STAGE_MAP = {
  WAITING: {
    label: 'Đang chờ',
    step: 1,
    tone: 'amber',
  },

  MOVING_TO_PICKUP: {
    label: 'Đang đến điểm nhận',
    step: 2,
    tone: 'amber',
  },

  ARRIVED_AT_PICKUP: {
    label: 'Đã đến điểm nhận',
    step: 3,
    tone: 'amber',
  },

  PICKUP_CONFIRMED: {
    label: 'Đã xác nhận nhận hàng',
    step: 4,
    tone: 'green',
  },

  TRANSPORTING: {
    label: 'Đang vận chuyển',
    step: 5,
    tone: 'green',
  },

  ARRIVED_AT_DELIVERY: {
    label: 'Đã đến điểm giao',
    step: 6,
    tone: 'green',
  },

  DELIVERY_CONFIRMED: {
    label: 'Đã xác nhận giao hàng',
    step: 7,
    tone: 'green',
  },

  COMPLETED: {
    label: 'Hoàn thành',
    step: 8,
    tone: 'green',
  },
};


export default function ActiveTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [actionTaskId, setActionTaskId] = useState(null);


  const loadTasks = useCallback(async () => {
    try {
      const data = await getTasks();

      setTasks(data);
      setError(null);
    } catch (err) {
      console.error(
        'Không thể tải nhiệm vụ:',
        err
      );

      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);


  useEffect(() => {
    loadTasks();

    const unsubscribe = subscribeRealtime((message) => {
      if (message.type !== 'TASK_UPDATED') {
        return;
      }

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
    });

    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (online && isReconnect) {
          loadTasks();
        }
      }
    );

    return () => {
      unsubscribe();
      unsubscribeStatus();
    };
  }, [loadTasks]);


  async function handlePauseResume(task) {
    try {
      setActionTaskId(task.id);

      const updated = task.is_paused
        ? await resumeTask(task.id)
        : await pauseTask(task.id);

      setTasks((current) =>
        current.map((item) =>
          item.id === updated.id
            ? updated
            : item
        )
      );
    } catch (err) {
      console.error(err);

      window.alert(
        `Không thể cập nhật nhiệm vụ: ${err.message}`
      );
    } finally {
      setActionTaskId(null);
    }
  }


  async function handleCancel(task) {
    const confirmed = window.confirm(
      `Bạn có chắc muốn yêu cầu hủy ${task.task_code}?`
    );

    if (!confirmed) {
      return;
    }

    try {
      setActionTaskId(task.id);

      const updated = await cancelTask(task.id);

      setTasks((current) =>
        current.map((item) =>
          item.id === updated.id
            ? updated
            : item
        )
      );
    } catch (err) {
      console.error(err);

      window.alert(
        `Không thể yêu cầu hủy nhiệm vụ: ${err.message}`
      );
    } finally {
      setActionTaskId(null);
    }
  }


  const activeTasks = tasks.filter(
    (task) =>
      !TERMINAL_STATUSES.has(task.status)
  );


  return (
    <section className="panel active-tasks-panel">
      <div className="section-header">
        <div className="section-title-group">
          <span className="section-indicator section-indicator--orange" />

          <h2>ACTIVE TASKS</h2>

          <span className="section-meta section-meta--green">
            [{activeTasks.length} Đang thực hiện]
          </span>
        </div>

        <span className="section-caption">
          Vòng đời & Tiến độ
        </span>
      </div>


      <div className="task-table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Sản phẩm</th>
              <th>ROBOT</th>
              <th>Điểm lấy hàng</th>
              <th>Điểm đến</th>
              <th>Trạng thái</th>
              <th>TIẾN ĐỘ</th>
              <th>ETA</th>

              <th className="text-right">
                Thao tác
              </th>
            </tr>
          </thead>


          <tbody>
            {loading && (
              <tr>
                <td colSpan="9">
                  Đang tải nhiệm vụ...
                </td>
              </tr>
            )}


            {!loading && error && (
              <tr>
                <td colSpan="9">
                  Không thể tải nhiệm vụ: {error}
                </td>
              </tr>
            )}


            {!loading &&
              !error &&
              activeTasks.length === 0 && (
                <tr>
                  <td colSpan="9">
                    Hiện không có nhiệm vụ đang thực hiện.
                  </td>
                </tr>
              )}


            {!loading &&
              !error &&
              activeTasks.map((task) => {
                const view =
                  buildTaskViewModel(task);

                const isProcessing =
                  actionTaskId === task.id;

                return (
                  <tr key={task.id}>
                    <td className="task-id">
                      {task.task_code}
                    </td>


                    <td>
                      {task.product_code}{' '}
                      {task.product_name}
                    </td>


                    <td>
                      <span
                        className={
                          `robot-cell robot-cell--${view.robotTone}`
                        }
                      >
                        <span aria-hidden="true">
                          {view.marker}
                        </span>{' '}

                        {task.robot_code ??
                          'Chưa gán'}
                      </span>
                    </td>


                    <td>
                      {task.pickup_location_code}
                    </td>


                    <td>
                      {task.dropoff_location_code}
                    </td>


                    <td
                      className={
                        `stage-text stage-text--${view.stageTone}`
                      }
                    >
                      {view.stage}
                    </td>


                    <td>
                      <div className="progress-cell">
                        <div
                          className="progress-track"
                          aria-hidden="true"
                        >
                          <div
                            className="progress-bar"
                            style={{
                              width:
                                `${task.progress}%`,
                            }}
                          />
                        </div>

                        <strong>
                          {task.progress}%
                        </strong>
                      </div>
                    </td>


                    <td className="eta-cell">
                      —
                    </td>


                    <td className="text-right">
                      <div className="task-actions">
                        <button
                          className="secondary-button"
                          type="button"
                          disabled={
                            isProcessing ||
                            task.cancel_requested
                          }
                          onClick={() =>
                            handlePauseResume(task)
                          }
                        >
                          {isProcessing
                            ? '...'
                            : task.is_paused
                              ? 'Tiếp tục'
                              : 'Dừng'}
                        </button>


                        <button
                          className="danger-outline-button"
                          type="button"
                          disabled={
                            isProcessing ||
                            task.cancel_requested
                          }
                          onClick={() =>
                            handleCancel(task)
                          }
                        >
                          {task.cancel_requested
                            ? 'Đang hủy'
                            : 'Hủy'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </section>
  );
}


function buildTaskViewModel(task) {
  const stageInfo =
    TASK_STAGE_MAP[task.status] ?? {
      label: task.status,
      step: null,
      tone: 'amber',
    };


  let stage = stageInfo.label;
  let stageTone = stageInfo.tone;


  if (stageInfo.step !== null) {
    stage += ` (Bước ${stageInfo.step}/8)`;
  }


  if (task.is_paused) {
    stage = 'Tạm dừng';
    stageTone = 'amber';
  }


  if (task.cancel_requested) {
    stage = 'Đang chờ hủy an toàn';
    stageTone = 'amber';
  }


  const isLineRobot =
    task.robot_code?.startsWith('LINE');


  return {
    marker: isLineRobot
      ? '◇'
      : '○',

    robotTone: isLineRobot
      ? 'green'
      : 'orange',

    stage,
    stageTone,
  };
}
