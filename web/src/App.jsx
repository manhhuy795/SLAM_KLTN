import {
  useEffect,
  useMemo,
  useState,
} from "react";

import Header from "./UI/Header";
import Sidebar from "./UI/Sidebar";
import RobotStatus from "./UI/RobotStatus";
import ActiveTasks from "./UI/ActiveTasks";
import WarehouseMap from "./UI/WarehouseMap";
import DashboardSidePanel from "./UI/DashboardSidePanel";

import Tasks from "./UI/Tasks";
import Robots from "./UI/Robots";
import MapProducts from "./UI/MapProducts";
import Alerts from "./UI/Alerts";
import History from "./UI/History";

import {
  getAlerts,
  getOperators,
  getRobots,
  getTasks,
} from "./services/api";
import {
  connectRealtime,
  subscribeRealtime,
  subscribeRealtimeStatus,
} from "./services/realtime";


const TERMINAL_TASK_STATUSES = new Set([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);


function replaceItem(setter, item) {
  setter((current) => {
    const exists = current.some(
      (value) => value.id === item.id
    );

    if (!exists) {
      return [...current, item];
    }

    return current.map((value) =>
      value.id === item.id ? item : value
    );
  });
}


export default function App() {
  const [sidebarOpen, setSidebarOpen] =
    useState(false);

  const [activePage, setActivePage] =
    useState("dashboard");

  const [backendOnline, setBackendOnline] =
    useState(false);

  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [operator, setOperator] = useState(null);


  useEffect(() => {
    let loadedOnce = false;

    async function loadShellMetrics() {
      try {
        const [
          robots,
          tasks,
          alerts,
          operators,
        ] = await Promise.all([
          getRobots(),
          getTasks(),
          getAlerts(),
          getOperators(),
        ]);


        setRobots(robots);
        setTasks(tasks);
        setAlerts(alerts);
        setOperator(operators[0] ?? null);


        setBackendOnline(true);
        loadedOnce = true;
      } catch (error) {
        console.error(
          "Không thể tải trạng thái hệ thống:",
          error
        );

        setBackendOnline(false);
      }
    }


    loadShellMetrics();

    const unsubscribe = subscribeRealtime((message) => {
      if (
        message.type ===
        "ROBOT_STATUS_UPDATED"
      ) {
        replaceItem(setRobots, message.data);
      }

      if (message.type === "TASK_UPDATED") {
        replaceItem(setTasks, message.data);
      }

      if (message.type === "ALERT_UPDATED") {
        replaceItem(setAlerts, message.data);
      }
    });

    const unsubscribeStatus =
      subscribeRealtimeStatus((online, isReconnect) => {
        setBackendOnline(online);

        if (online && (!loadedOnce || isReconnect)) {
          loadShellMetrics();
        }
      });
    const disconnect = connectRealtime();

    return () => {
      unsubscribe();
      unsubscribeStatus();
      disconnect();
    };
  }, []);


  const shellMetrics = useMemo(() => ({
    totalRobots: robots.length,

    activeRobots: robots.filter(
      (robot) => robot.status?.online
    ).length,

    idleRobots: robots.filter(
      (robot) =>
        robot.status?.online &&
        robot.status?.state === "IDLE"
    ).length,

    activeTasks: tasks.filter(
      (task) =>
        !TERMINAL_TASK_STATUSES.has(task.status) &&
        task.status !== "WAITING"
    ).length,

    alerts: alerts.filter(
      (alert) => alert.status !== "RESOLVED"
    ).length,
  }), [robots, tasks, alerts]);


  const handleNavigate = (page) => {
    setActivePage(page);
    setSidebarOpen(false);
  };


  return (
    <div className="app-shell">
      <Header
        metrics={shellMetrics}
        backendOnline={backendOnline}
        operator={operator}
        onMenuToggle={() =>
          setSidebarOpen(
            (value) => !value
          )
        }
      />


      <div className="app-body">
        <Sidebar
          open={sidebarOpen}
          activePage={activePage}
          alertCount={
            shellMetrics.alerts
          }
          onNavigate={
            handleNavigate
          }
        />


        {sidebarOpen && (
          <button
            className="sidebar-backdrop"
            type="button"
            aria-label="Đóng menu"
            onClick={() =>
              setSidebarOpen(false)
            }
          />
        )}


        {/* =========================
            TRANG TỔNG QUAN
        ========================== */}
        {activePage ===
          "dashboard" && (
          <main className="dashboard-grid">
            <section className="dashboard-main-column">
              <RobotStatus />

              <ActiveTasks />

              <WarehouseMap />
            </section>


            <section className="dashboard-side-column">
              <DashboardSidePanel
                operatorId={operator?.id ?? null}
                onNavigate={
                  handleNavigate
                }
              />
            </section>
          </main>
        )}


        {/* =========================
            TRANG NHIỆM VỤ
        ========================== */}
        {activePage === "tasks" && (
          <main className="page-content">
            <Tasks operatorId={operator?.id ?? null} />
          </main>
        )}


        {/* =========================
            TRANG ROBOT
        ========================== */}
        {activePage === "robots" && (
          <main className="page-content">
            <Robots backendOnline={backendOnline} />
          </main>
        )}


        {/* =========================
            TRANG BẢN ĐỒ & SẢN PHẨM
        ========================== */}
        {activePage ===
          "map-products" && (
          <main className="page-content">
            <MapProducts />
          </main>
        )}


        {/* =========================
            TRANG CẢNH BÁO
        ========================== */}
        {activePage === "alerts" && (
          <main className="page-content">
            <Alerts operatorId={operator?.id ?? null} />
          </main>
        )}


        {/* =========================
            TRANG LỊCH SỬ
        ========================== */}
        {activePage === "history" && (
          <main className="page-content">
            <History />
          </main>
        )}
      </div>
    </div>
  );
}
