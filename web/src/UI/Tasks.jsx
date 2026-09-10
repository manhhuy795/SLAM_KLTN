import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  Camera,
  CheckCircle2,
  CirclePause,
  CirclePlay,
  ClipboardPlus,
  Package,
  RotateCcw,
  Search,
  XCircle,
} from 'lucide-react';

import {
  cancelTask,
  createTaskProof,
  createTask,
  getLocations,
  getProducts,
  getTaskProofs,
  getTasks,
  pauseTask,
  resumeTask,
} from '../services/api';
import { subscribeRealtime } from '../services/realtime';


const lifecycle = [
  'Đang chờ',
  'Đang đến điểm nhận',
  'Đã đến điểm nhận',
  'Đã xác nhận nhận hàng',
  'Đang vận chuyển',
  'Đã đến điểm giao',
  'Đã xác nhận giao hàng',
  'Hoàn thành',
];


const STATUS_CONFIG = {
  WAITING: {
    label: 'Đang chờ',
    stageIndex: 0,
    category: 'waiting',
    tone: 'muted',
  },

  MOVING_TO_PICKUP: {
    label: 'Đang đến điểm nhận',
    stageIndex: 1,
    category: 'active',
    tone: 'orange',
  },

  ARRIVED_AT_PICKUP: {
    label: 'Đã đến điểm nhận',
    stageIndex: 2,
    category: 'active',
    tone: 'orange',
  },

  PICKUP_CONFIRMED: {
    label: 'Đã xác nhận nhận hàng',
    stageIndex: 3,
    category: 'active',
    tone: 'orange',
  },

  TRANSPORTING: {
    label: 'Đang vận chuyển',
    stageIndex: 4,
    category: 'active',
    tone: 'orange',
  },

  ARRIVED_AT_DELIVERY: {
    label: 'Đã đến điểm giao',
    stageIndex: 5,
    category: 'active',
    tone: 'orange',
  },

  DELIVERY_CONFIRMED: {
    label: 'Đã xác nhận giao hàng',
    stageIndex: 6,
    category: 'active',
    tone: 'orange',
  },

  COMPLETED: {
    label: 'Hoàn thành',
    stageIndex: 7,
    category: 'completed',
    tone: 'green',
  },

  FAILED: {
    label: 'Thất bại',
    stageIndex: -1,
    category: 'failed',
    tone: 'red',
  },

  CANCELLED: {
    label: 'Đã hủy',
    stageIndex: -1,
    category: 'cancelled',
    tone: 'red',
  },
};


const TERMINAL_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function Tasks({ operatorId }) {
  const [tasks, setTasks] = useState([]);
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);

  const [selectedTaskId, setSelectedTaskId] =
    useState(null);

  const [statusFilter, setStatusFilter] =
    useState('all');

  const [search, setSearch] =
    useState('');

  const [createOpen, setCreateOpen] =
    useState(false);

  const [retryTask, setRetryTask] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState(null);

  const [actionTaskId, setActionTaskId] =
    useState(null);


  const loadTasks = useCallback(async () => {
    const data = await getTasks();

    setTasks(data);

    setSelectedTaskId((current) => {
      if (
        current !== null &&
        data.some((task) => task.id === current)
      ) {
        return current;
      }

      return data[0]?.id ?? null;
    });

    return data;
  }, []);


  const loadInitialData = useCallback(async () => {
    try {
      setLoading(true);

      const [
        taskData,
        productData,
        locationData,
      ] = await Promise.all([
        getTasks(),
        getProducts(),
        getLocations(),
      ]);

      setTasks(taskData);
      setProducts(productData);
      setLocations(locationData);

      setSelectedTaskId(
        taskData[0]?.id ?? null
      );

      setError(null);
    } catch (err) {
      console.error(err);

      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);


  useEffect(() => {
    loadInitialData();

    return subscribeRealtime((message) => {
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
  }, [
    loadInitialData,
  ]);


  const selectedTask = tasks.find(
    (task) =>
      task.id === selectedTaskId
  );


  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const config =
        getStatusConfig(task);

      const matchesStatus =
        statusFilter === 'all' ||
        config.category === statusFilter;

      const searchValue =
        search.trim().toLowerCase();

      const matchesSearch =
        !searchValue ||
        task.task_code
          .toLowerCase()
          .includes(searchValue) ||
        task.product_code
          .toLowerCase()
          .includes(searchValue) ||
        task.product_name
          .toLowerCase()
          .includes(searchValue) ||
        (task.robot_code ?? 'chưa gán')
          .toLowerCase()
          .includes(searchValue);

      return (
        matchesStatus &&
        matchesSearch
      );
    });
  }, [
    tasks,
    search,
    statusFilter,
  ]);


  async function togglePause(task) {
    try {
      setActionTaskId(task.id);

      if (task.is_paused) {
        await resumeTask(task.id);
      } else {
        await pauseTask(task.id);
      }

      await loadTasks();
    } catch (err) {
      console.error(err);

      window.alert(
        `Không thể cập nhật nhiệm vụ: ${err.message}`
      );
    } finally {
      setActionTaskId(null);
    }
  }


  async function requestCancel(task) {
    const confirmed = window.confirm(
      `Bạn có chắc muốn yêu cầu hủy ${task.task_code}?`
    );

    if (!confirmed) {
      return;
    }

    try {
      setActionTaskId(task.id);

      await cancelTask(task.id);

      await loadTasks();
    } catch (err) {
      console.error(err);

      window.alert(
        `Không thể yêu cầu hủy nhiệm vụ: ${err.message}`
      );
    } finally {
      setActionTaskId(null);
    }
  }


  function openCreateModal() {
    setRetryTask(null);
    setCreateOpen(true);
  }


  function openRetryModal(task) {
    setRetryTask(task);
    setCreateOpen(true);
  }


  async function handleCreated(task) {
    setCreateOpen(false);
    setRetryTask(null);

    await loadTasks();

    setSelectedTaskId(task.id);
  }


  return (
    <div className="tasks-page">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / NHIỆM VỤ
          </span>

          <h1>
            Quản lý nhiệm vụ vận chuyển
          </h1>

          <p>
            Tạo, theo dõi và điều khiển
            vòng đời nhiệm vụ của robot
            trong kho.
          </p>
        </div>


        <button
          className="primary-button tasks-create-button"
          type="button"
          onClick={openCreateModal}
        >
          <ClipboardPlus size={16} />

          Tạo nhiệm vụ
        </button>
      </div>


      <TaskStats tasks={tasks} />


      {error && (
        <section className="panel">
          Không thể tải nhiệm vụ: {error}
        </section>
      )}


      <div className="tasks-workspace">
        <section className="panel tasks-list-panel">
          <div className="tasks-toolbar">
            <div className="tasks-search">
              <Search size={15} />

              <input
                type="text"
                value={search}
                placeholder="Tìm Task ID, sản phẩm hoặc robot..."
                onChange={(event) =>
                  setSearch(event.target.value)
                }
              />
            </div>


            <div className="tasks-filters">
              <FilterButton
                active={
                  statusFilter === 'all'
                }
                onClick={() =>
                  setStatusFilter('all')
                }
              >
                Tất cả
              </FilterButton>


              <FilterButton
                active={
                  statusFilter === 'waiting'
                }
                onClick={() =>
                  setStatusFilter('waiting')
                }
              >
                Đang chờ
              </FilterButton>


              <FilterButton
                active={
                  statusFilter === 'active'
                }
                onClick={() =>
                  setStatusFilter('active')
                }
              >
                Đang thực hiện
              </FilterButton>


              <FilterButton
                active={
                  statusFilter === 'completed'
                }
                onClick={() =>
                  setStatusFilter('completed')
                }
              >
                Hoàn thành
              </FilterButton>
            </div>
          </div>


          <div className="tasks-table-wrapper">
            <table className="tasks-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Sản phẩm</th>
                  <th>Robot</th>
                  <th>Tuyến</th>
                  <th>Trạng thái</th>
                  <th>Tiến độ</th>
                  <th>ETA</th>
                </tr>
              </thead>


              <tbody>
                {loading && (
                  <tr>
                    <td colSpan="7">
                      Đang tải nhiệm vụ...
                    </td>
                  </tr>
                )}


                {!loading &&
                  filteredTasks.length === 0 && (
                    <tr>
                      <td colSpan="7">
                        Không tìm thấy nhiệm vụ.
                      </td>
                    </tr>
                  )}


                {!loading &&
                  filteredTasks.map((task) => {
                    const view =
                      getTaskView(task);

                    return (
                      <tr
                        key={task.id}
                        className={
                          selectedTaskId === task.id
                            ? 'tasks-table-row tasks-table-row--selected'
                            : 'tasks-table-row'
                        }
                        onClick={() =>
                          setSelectedTaskId(task.id)
                        }
                      >
                        <td>
                          <strong className="text-orange">
                            {task.task_code}
                          </strong>
                        </td>


                        <td>
                          {task.product_code}{' '}
                          {task.product_name}
                        </td>


                        <td>
                          {task.robot_code ??
                            'Chưa gán'}
                        </td>


                        <td>
                          <span className="task-route-cell">
                            {task.pickup_location_name ??
                              task.pickup_location_code}

                            <span>→</span>

                            {task.dropoff_location_name ??
                              task.dropoff_location_code}
                          </span>
                        </td>


                        <td>
                          <TaskStatus
                            task={task}
                          />
                        </td>


                        <td>
                          <div className="task-progress-cell">
                            <div className="task-progress-track">
                              <span
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


                        <td>
                          {view.eta}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>


        {selectedTask && (
          <TaskDetail
            task={selectedTask}
            operatorId={operatorId}
            actionBusy={
              actionTaskId ===
              selectedTask.id
            }
            onTogglePause={() =>
              togglePause(selectedTask)
            }
            onCancel={() =>
              requestCancel(selectedTask)
            }
            onRetry={() =>
              openRetryModal(selectedTask)
            }
          />
        )}
      </div>


      {createOpen && (
        <CreateTaskModal
          products={products}
          locations={locations}
          retryTask={retryTask}
          onClose={() => {
            setCreateOpen(false);
            setRetryTask(null);
          }}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}


function TaskStats({ tasks }) {
  const waiting = tasks.filter(
    (task) =>
      task.status === 'WAITING'
  ).length;


  const active = tasks.filter(
    (task) =>
      !TERMINAL_STATUSES.has(
        task.status
      ) &&
      task.status !== 'WAITING'
  ).length;


  const completed = tasks.filter(
    (task) =>
      task.status === 'COMPLETED'
  ).length;


  const failed = tasks.filter(
    (task) =>
      task.status === 'FAILED'
  ).length;


  const stats = [
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
      tone: 'red',
    },
  ];


  return (
    <div className="tasks-stats">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className={
            `task-stat-card task-stat-card--${
              stat.tone || 'default'
            }`
          }
        >
          <span>{stat.label}</span>
          <strong>{stat.value}</strong>
        </div>
      ))}
    </div>
  );
}


function TaskStatus({ task }) {
  const view =
    getTaskView(task);


  return (
    <span
      className={
        `task-status task-status--${view.tone}`
      }
    >
      {view.statusLabel}
    </span>
  );
}


function TaskDetail({
  task,
  operatorId,
  actionBusy,
  onTogglePause,
  onCancel,
  onRetry,
}) {
  const [proofs, setProofs] = useState([]);
  const [proofType, setProofType] = useState(null);
  const [proofError, setProofError] = useState(null);

  useEffect(() => {
    let active = true;
    setProofError(null);
    getTaskProofs(task.id)
      .then((data) => {
        if (active) {
          setProofs(data);
        }
      })
      .catch((err) => {
        if (active) {
          setProofError(err.message);
        }
      });

    return () => {
      active = false;
    };
  }, [task.id]);


  async function saveProof(data) {
    const created = await createTaskProof(task.id, data);
    setProofs((current) => [...current, created]);
    setProofType(null);
  }


  const view =
    getTaskView(task);


  const canPause =
    !TERMINAL_STATUSES.has(task.status) &&
    task.robot_id !== null &&
    task.status !== 'WAITING' &&
    !task.cancel_requested;


  const canCancel =
    !TERMINAL_STATUSES.has(task.status) &&
    !task.cancel_requested;


  return (
    <aside className="panel task-detail-panel">
      <div className="task-detail-header">
        <div>
          <span>
            CHI TIẾT NHIỆM VỤ
          </span>

          <h2>
            {task.task_code}
          </h2>
        </div>

        <TaskStatus task={task} />
      </div>


      <div className="task-detail-info">
        <DetailRow
          label="Sản phẩm"
          value={
            `${task.product_code} ${task.product_name}`
          }
        />

        <DetailRow
          label="Robot"
          value={
            task.robot_code ??
            'Chưa gán'
          }
        />

        <DetailRow
          label="Điểm nhận"
          value={
            task.pickup_location_name ??
            task.pickup_location_code
          }
        />

        <DetailRow
          label="Điểm giao"
          value={
            task.dropoff_location_name ??
            task.dropoff_location_code
          }
        />

        <DetailRow
          label="Thời gian tạo"
          value={
            formatDateTime(
              task.created_at
            )
          }
        />

        <DetailRow
          label="Thời gian dự kiến"
          value="—"
        />
      </div>


      <div className="task-detail-section">
        <div className="task-detail-section-title">
          VÒNG ĐỜI NHIỆM VỤ
        </div>

        <div className="task-lifecycle">
          {lifecycle.map(
            (stage, index) => {
              const completed =
                view.stageIndex >= 0 &&
                index < view.stageIndex;

              const current =
                index ===
                view.stageIndex;

              return (
                <div
                  key={stage}
                  className={
                    `lifecycle-step ${
                      completed
                        ? 'lifecycle-step--completed'
                        : ''
                    } ${
                      current
                        ? 'lifecycle-step--current'
                        : ''
                    }`
                  }
                >
                  <div className="lifecycle-marker">
                    {completed ? (
                      <CheckCircle2 size={15} />
                    ) : (
                      <span>
                        {index + 1}
                      </span>
                    )}
                  </div>

                  <div>
                    <strong>
                      {stage}
                    </strong>

                    {current && (
                      <span className="lifecycle-current-label">
                        Trạng thái hiện tại
                      </span>
                    )}
                  </div>
                </div>
              );
            }
          )}
        </div>
      </div>


      <div className="task-detail-section">
        <div className="task-detail-section-title">
          XÁC NHẬN HÀNG HÓA
        </div>

        <div className="camera-proof-grid">
          <ProofBox
            title="Xác nhận nhận hàng"
            status={getProofLabel(proofs, 'PICKUP', view.stageIndex >= 3)}
            completed={
              view.stageIndex >= 3
            }
            onCreate={
              task.status === 'ARRIVED_AT_PICKUP'
                ? () => setProofType('PICKUP')
                : null
            }
          />

          <ProofBox
            title="Xác nhận giao hàng"
            status={getProofLabel(proofs, 'DELIVERY', view.stageIndex >= 6)}
            completed={
              view.stageIndex >= 6
            }
            onCreate={
              task.status === 'ARRIVED_AT_DELIVERY'
                ? () => setProofType('DELIVERY')
                : null
            }
          />
        </div>

        {proofError && (
          <div className="create-task-note">{proofError}</div>
        )}

        {proofType && (
          <ProofForm
            taskId={task.id}
            proofType={proofType}
            operatorId={operatorId}
            onClose={() => setProofType(null)}
            onSaved={saveProof}
          />
        )}
      </div>


      {(canPause || canCancel) && (
        <div className="task-detail-actions">
          {canPause && (
            <button
              className="secondary-button"
              type="button"
              disabled={actionBusy}
              onClick={onTogglePause}
            >
              {task.is_paused ? (
                <>
                  <CirclePlay size={15} />
                  Tiếp tục
                </>
              ) : (
                <>
                  <CirclePause size={15} />
                  Tạm dừng
                </>
              )}
            </button>
          )}


          {canCancel && (
            <button
              className="danger-outline-button"
              type="button"
              disabled={actionBusy}
              onClick={onCancel}
            >
              <XCircle size={15} />

              Yêu cầu hủy
            </button>
          )}
        </div>
      )}


      {task.cancel_requested &&
        !TERMINAL_STATUSES.has(
          task.status
        ) && (
          <div className="create-task-note">
            Đã gửi yêu cầu hủy.
            Đang chờ robot dừng an toàn.
          </div>
        )}


      {task.status === 'FAILED' && (
        <button
          className="secondary-button"
          type="button"
          onClick={onRetry}
        >
          <RotateCcw size={15} />

          Tạo nhiệm vụ mới từ nhiệm vụ này
        </button>
      )}
    </aside>
  );
}


function DetailRow({
  label,
  value,
}) {
  return (
    <div className="task-detail-row">
      <span>{label}</span>

      <strong>
        {value || '—'}
      </strong>
    </div>
  );
}


function ProofBox({
  title,
  status,
  completed,
  onCreate,
}) {
  return (
    <div
      className={
        `proof-box ${
          completed
            ? 'proof-box--completed'
            : ''
        }`
      }
    >
      <div className="proof-camera">
        <Camera size={20} />
      </div>

      <div>
        <strong>{title}</strong>
        <span>{status}</span>
        {onCreate && (
          <button
            className="text-link"
            type="button"
            onClick={onCreate}
          >
            Tạo proof
          </button>
        )}
      </div>
    </div>
  );
}


function FilterButton({
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


function CreateTaskModal({
  products,
  locations,
  retryTask,
  onClose,
  onCreated,
}) {
  const destinations = useMemo(
    () =>
      locations.filter(
        (location) =>
          location.location_type ===
            'DELIVERY' &&
          location.is_active
      ),
    [locations]
  );


  const initialProductId =
    retryTask?.product_id ??
    products[0]?.id ??
    '';


  const initialDestinationId =
    retryTask?.dropoff_location_id ??
    destinations[0]?.id ??
    '';


  const [
    productId,
    setProductId,
  ] = useState(
    String(initialProductId)
  );


  const [
    destinationId,
    setDestinationId,
  ] = useState(
    String(initialDestinationId)
  );


  const [
    submitting,
    setSubmitting,
  ] = useState(false);


  const [
    submitError,
    setSubmitError,
  ] = useState(null);


  const selectedProduct =
    products.find(
      (product) =>
        product.id ===
        Number(productId)
    );


  async function handleSubmit() {
    if (
      !productId ||
      !destinationId
    ) {
      setSubmitError(
        'Vui lòng chọn sản phẩm và điểm giao hàng.'
      );

      return;
    }

    try {
      setSubmitting(true);
      setSubmitError(null);

      const created =
        await createTask({
          product_id:
            Number(productId),

          dropoff_location_id:
            Number(destinationId),

          robot_id: null,

          retry_of_task_id:
            retryTask?.status ===
            'FAILED'
              ? retryTask.id
              : null,
        });

      await onCreated(created);
    } catch (err) {
      console.error(err);

      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  }


  return (
    <div className="modal-backdrop">
      <div className="create-task-modal">
        <div className="modal-header">
          <div>
            <Package size={17} />

            <strong>
              {retryTask
                ? 'Tạo lại nhiệm vụ'
                : 'Tạo nhiệm vụ vận chuyển'}
            </strong>
          </div>

          <button
            type="button"
            onClick={onClose}
          >
            <XCircle size={17} />
          </button>
        </div>


        <div className="create-task-form">
          <label>
            <span>Sản phẩm</span>

            <select
              value={productId}
              onChange={(event) =>
                setProductId(
                  event.target.value
                )
              }
            >
              {products.map(
                (product) => (
                  <option
                    key={product.id}
                    value={product.id}
                  >
                    {product.product_code}
                    {' — '}
                    {product.name}
                  </option>
                )
              )}
            </select>
          </label>


          <label>
            <span>
              Điểm nhận hàng
            </span>

            <input
              value={
                selectedProduct
                  ? (
                    selectedProduct
                      .default_rack_name ??
                    selectedProduct
                      .default_rack_code
                  )
                  : ''
              }
              readOnly
            />

            <small>
              Tự động lấy từ vị trí
              mặc định của sản phẩm.
            </small>
          </label>


          <label>
            <span>
              Điểm giao hàng
            </span>

            <select
              value={destinationId}
              onChange={(event) =>
                setDestinationId(
                  event.target.value
                )
              }
            >
              {destinations.map(
                (location) => (
                  <option
                    key={location.id}
                    value={location.id}
                  >
                    {location.name}
                    {' — '}
                    {location.code}
                  </option>
                )
              )}
            </select>
          </label>


          <div className="create-task-note">
            Robot hiện chưa được gán
            ở bước tạo nhiệm vụ.
            Hệ thống điều phối sẽ
            thực hiện việc gán robot.
          </div>


          {retryTask && (
            <div className="create-task-note">
              Nhiệm vụ mới sẽ tham
              chiếu đến{' '}
              {retryTask.task_code}
              {' '}
              thông qua
              retry_of_task_id.
            </div>
          )}


          {submitError && (
            <div className="create-task-note">
              {submitError}
            </div>
          )}
        </div>


        <div className="modal-actions">
          <button
            className="secondary-button"
            type="button"
            disabled={submitting}
            onClick={onClose}
          >
            Hủy
          </button>

          <button
            className="primary-button"
            type="button"
            disabled={
              submitting ||
              !productId ||
              !destinationId
            }
            onClick={handleSubmit}
          >
            {submitting
              ? 'Đang tạo...'
              : 'Tạo nhiệm vụ'}
          </button>
        </div>
      </div>
    </div>
  );
}


function getStatusConfig(task) {
  return (
    STATUS_CONFIG[
      task.status
    ] ?? {
      label: task.status,
      stageIndex: -1,
      category: 'active',
      tone: 'neutral',
    }
  );
}


function getTaskView(task) {
  const config =
    getStatusConfig(task);


  if (task.cancel_requested) {
    return {
      ...config,

      statusLabel:
        'Đang yêu cầu hủy',

      tone: 'red',

      eta: '—',
    };
  }


  if (task.is_paused) {
    return {
      ...config,

      statusLabel:
        'Tạm dừng',

      tone: 'muted',

      eta: '—',
    };
  }


  return {
    ...config,

    statusLabel:
      config.label,

    eta: '—',
  };
}


function formatDateTime(value) {
  if (!value) {
    return '—';
  }

  try {
    /*
     * SQLite CURRENT_TIMESTAMP
     * lưu theo UTC nhưng FastAPI
     * hiện trả datetime không có Z.
     */
    const hasTimezone =
      value.endsWith('Z') ||
      /[+-]\d{2}:\d{2}$/.test(value);

    const normalized =
      hasTimezone
        ? value
        : `${value}Z`;

    return new Date(
      normalized
    ).toLocaleString(
      'vi-VN',
      {
        hour12: false,
      }
    );
  } catch {
    return value;
  }
}


function ProofForm({
  taskId,
  proofType,
  operatorId,
  onClose,
  onSaved,
}) {
  const [imagePath, setImagePath] = useState('');
  const [verificationStatus, setVerificationStatus] = useState('PENDING');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();

    if (!imagePath.trim()) {
      setError('Nhập image_path cho proof.');
      return;
    }

    if (verificationStatus === 'MANUAL_CONFIRMED' && operatorId === null) {
      setError('Không có operator để xác nhận thủ công.');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      await onSaved({
        proof_type: proofType,
        image_path: imagePath.trim(),
        verification_status: verificationStatus,
        confirmed_by: verificationStatus === 'MANUAL_CONFIRMED'
          ? operatorId
          : null,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="create-task-form create-task-note" onSubmit={submit}>
      <strong>{proofType} proof — task #{taskId}</strong>
      <input
        value={imagePath}
        placeholder="/proofs/task-pickup.jpg"
        onChange={(event) => setImagePath(event.target.value)}
      />
      <select
        value={verificationStatus}
        onChange={(event) => setVerificationStatus(event.target.value)}
      >
        <option value="PENDING">PENDING</option>
        <option value="AUTO_VERIFIED">AUTO_VERIFIED</option>
        <option value="MANUAL_CONFIRMED">MANUAL_CONFIRMED</option>
        <option value="FAILED">FAILED</option>
      </select>
      {error && <span>{error}</span>}
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onClose}>Hủy</button>
        <button className="primary-button" type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu proof'}</button>
      </div>
    </form>
  );
}


function getProofLabel(proofs, proofType, taskConfirmed) {
  const proof = proofs.filter((item) => item.proof_type === proofType).at(-1);

  if (taskConfirmed || proof?.verification_status === 'AUTO_VERIFIED' || proof?.verification_status === 'MANUAL_CONFIRMED') {
    return 'Đã xác nhận';
  }

  if (proof?.verification_status) {
    return proof.verification_status;
  }

  return 'Chưa có proof';
}
