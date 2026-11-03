import {
  useEffect,
  useMemo,
  useState,
} from "react";

import Header from "./shared/ui/Header";
import Sidebar from "./shared/ui/Sidebar";
import RobotStatus from "./features/robots/shared/RobotStatus";
import ActiveTasks from "./features/dashboard/ActiveTasks";
import WarehouseMap from "./features/map/WarehouseMap";
import DashboardSidePanel from "./features/dashboard/DashboardSidePanel";

import Tasks from "./features/missions/Tasks";
import Robots from "./features/robots/shared/Robots";
import MapProducts from "./features/map/MapProducts";
import Alerts from "./features/alerts/Alerts";
import History from "./features/history/History";

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
const PAGES = new Set(['dashboard', 'tasks', 'robots', 'map-products', 'alerts', 'history']);

function readNavigation() {
  const params = new URLSearchParams(window.location.search);
  const page = params.get('page') || (params.has('robot') ? 'robots' : 'dashboard');
  return { page: PAGES.has(page) ? page : 'dashboard',
    robotCode: page === 'robots' ? params.get('robot') : null };
}


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

  const [navigation, setNavigation] = useState(readNavigation);
  const activePage = navigation.page;

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


  useEffect(() => {
    const restore = () => { setNavigation(readNavigation()); setSidebarOpen(false); };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);

  const handleNavigate = (page, robotCode = null) => {
    if (!window.dispatchEvent(new Event("planning:before-leave", { cancelable: true }))) return;
    const url = new URL(window.location.href);
    url.searchParams.set('page', page);
    if (page === 'robots' && robotCode) url.searchParams.set('robot', robotCode);
    else url.searchParams.delete('robot');
    if (url.href !== window.location.href) window.history.pushState(null, '', url);
    setNavigation({ page, robotCode: page === 'robots' ? robotCode : null });
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
              <RobotStatus onRobotDetails={(code) => handleNavigate('robots', code)} />

              <ActiveTasks operatorId={operator?.id ?? null} />

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
            <Robots backendOnline={backendOnline} selectedRobotCode={navigation.robotCode}
              onSelectRobot={(code) => handleNavigate('robots', code)} />
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
