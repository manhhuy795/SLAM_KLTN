import { useEffect, useState } from 'react';

import {
  getLocations,
  getNavigationPath,
  getNavigationStatus,
  getRobots,
  getRosMap,
  getRosPose,
  getRosState,
  getTasks,
} from '../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../services/realtime';
import SlamMap from './SlamMap';


const MAP_WIDTH_METERS = 12;
const MAP_HEIGHT_METERS = 8;

const SVG_LEFT = 15;
const SVG_TOP = 15;
const SVG_WIDTH = 610;
const SVG_HEIGHT = 310;

const TERMINAL_TASK_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function WarehouseMap() {
  const [locations, setLocations] = useState([]);
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [slamMap, setSlamMap] = useState(null);
  const [slamPose, setSlamPose] = useState(null);
  const [slamStatus, setSlamStatus] = useState(null);
  const [navigationStatus, setNavigationStatus] = useState(null);
  const [navigationPath, setNavigationPath] = useState(null);
  const [statusNow, setStatusNow] = useState(() => Date.now());

  const [error, setError] = useState(null);


  useEffect(() => {
    let cancelled = false;


    async function loadMap() {
      try {
        const [
          locationData,
          robotData,
          taskData,
          mapData,
          poseData,
          statusData,
          navigationStatusData,
          navigationPathData,
        ] = await Promise.all([
          getLocations(),
          getRobots(),
          getTasks(),
          getRosMap(),
          getRosPose(),
          getRosState(),
          getNavigationStatus(),
          getNavigationPath(),
        ]);

        if (cancelled) {
          return;
        }

        setLocations(locationData);
        setRobots(robotData);
        setTasks(taskData);
        setSlamMap(mapData);
        setSlamPose(poseData);
        setSlamStatus(statusData);
        setNavigationStatus(navigationStatusData);
        setNavigationPath(navigationPathData);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          console.error(
            'Không thể tải dữ liệu bản đồ:',
            err
          );

          setError(err.message);
        }
      }
    }


    loadMap();

    return () => {
      cancelled = true;
    };
  }, []);


  useEffect(() => {
    const interval = window.setInterval(
      () => setStatusNow(Date.now()),
      1000
    );

    return () => window.clearInterval(interval);
  }, []);


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

      if (message.type === 'SLAM_MAP_UPDATED') {
        setSlamMap(message.data);
      }

      if (message.type === 'ROBOT_POSE_UPDATED') {
        setSlamPose(message.data);
      }

      if (message.type === 'SLAM_STATUS_UPDATED') {
        setSlamStatus(message.data);
      }
      if (message.type === 'NAVIGATION_STATUS_UPDATED') {
        setNavigationStatus(message.data);
      }

      if (message.type === 'NAVIGATION_PATH_UPDATED') {
        setNavigationPath(message.data?.poses?.length ? message.data : null);
      }
    });

    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (!online || !isReconnect) {
          return;
        }

        Promise.all([
          getLocations(),
          getRobots(),
          getTasks(),
          getRosMap(),
          getRosPose(),
          getRosState(),
          getNavigationStatus(),
          getNavigationPath(),
        ]).then(([locationData, robotData, taskData, mapData, poseData, statusData, navigationStatusData, navigationPathData]) => {
          setLocations(locationData);
          setRobots(robotData);
          setTasks(taskData);
          setSlamMap(mapData);
          setSlamPose(poseData);
          setSlamStatus(statusData);
          setNavigationStatus(navigationStatusData);
          setNavigationPath(navigationPathData);
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


  const activeTasks = tasks.filter(
    (task) =>
      !TERMINAL_TASK_STATUSES.has(
        task.status
      )
  );


  const positionedRobots = robots.filter(
    hasPosition
  );


  const unpositionedCount =
    robots.length - positionedRobots.length;

  const visibleSlamStatus = getVisibleSlamStatus(
    slamStatus,
    statusNow
  );

  const mapTitle = slamMap
    ? 'SLAM MAP (OCCUPANCYGRID)'
    : 'WAREHOUSE MAP (TESTBED)';


  return (
    <section className="panel map-panel" aria-label={mapTitle}>
      <div className="section-header map-section-header">
        <div className="section-title-group">
          <span className="section-indicator section-indicator--orange" />

          <h2>
            TỔNG QUAN BẢN ĐỒ KHO (THỬ NGHIỆM)
          </h2>

          <span className="section-meta">
            12.0m × 8.0m
          </span>
        </div>


        <div className="map-legend">
          <Legend
            tone="orange"
            label="AMR"
          />

          <Legend
            tone="green"
            label="AGV theo vạch"
          />

          <Legend
            tone="rack"
            label="Vị trí / Kệ"
          />

          <Legend
            tone="amber"
            label="Khu vực hạn chế"
          />
        </div>
      </div>


      <SlamStatusStrip status={visibleSlamStatus} />


      {error && (
        <div className="map-error">
          Không thể cập nhật bản đồ: {error}
        </div>
      )}


      {slamMap ? (
        <SlamMap
          map={slamMap}
          pose={slamPose}
          goal={navigationStatus?.goal}
          path={navigationPath}
        />
      ) : (
      <div className="map-canvas">
        <svg
          viewBox="0 0 640 340"
          role="img"
          aria-label="Bản đồ tổng quan kho thử nghiệm"
        >
          <defs>
            <pattern
              id="grid-pattern"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="#12151B"
                strokeWidth="0.8"
              />
            </pattern>


            <pattern
              id="hazard-pattern"
              width="8"
              height="8"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line
                x1="0"
                y1="0"
                x2="0"
                y2="8"
                stroke="#F59E0B"
                strokeWidth="1.8"
                opacity="0.35"
              />
            </pattern>
          </defs>


          {/* Nền */}
          <rect
            width="640"
            height="340"
            fill="url(#grid-pattern)"
          />

          <rect
            x={SVG_LEFT}
            y={SVG_TOP}
            width={SVG_WIDTH}
            height={SVG_HEIGHT}
            fill="none"
            stroke="#1E2229"
            strokeWidth="1.5"
          />


          {/* Tọa độ */}
          <MapCoordinates />


          {/* Khu vực hạn chế:
              đây là geometry của testbed,
              không phải location point trong DB.
          */}
          <RestrictedZone />


          {/* Location thật từ DB */}
          {locations.map((location) => (
            <MapLocation
              key={location.id}
              location={location}
              task={findTaskAtLocation(
                location.id,
                activeTasks
              )}
            />
          ))}


          {/* Robot chỉ render khi có tọa độ thật */}
          {positionedRobots.map((robot) => (
            <RobotMarker
              key={robot.id}
              robot={robot}
              task={findRobotTask(
                robot.id,
                activeTasks
              )}
            />
          ))}
        </svg>


        {unpositionedCount > 0 && (
          <div className="map-telemetry-note">
            {unpositionedCount} robot chưa có
            dữ liệu vị trí
          </div>
        )}
      </div>
      )}
    </section>
  );
}


function getVisibleSlamStatus(status, now) {
  if (!status) {
    return null;
  }

  const stale = status.timestamp !== null
    && status.timestamp !== undefined
    && now / 1000 - status.timestamp > 3;

  if (!stale) {
    return status;
  }

  return {
    ...status,
    bridge_online: false,
    slam_online: false,
    lidar_online: false,
    localization_available: false,
    tf_available: false,
  };
}


function SlamStatusStrip({ status }) {
  const values = status || {
    bridge_online: false,
    slam_online: false,
    map_status: 'WAITING',
    lidar_online: false,
    localization_available: false,
    tf_available: false,
  };

  return (
    <div className="slam-status-strip" aria-label="SLAM status">
      <RosStatus label="ROS BRIDGE" online={values.bridge_online} />
      <RosStatus label="SLAM" online={values.slam_online} />
      <RosStatus
        label="MAP"
        online={values.map_status === 'RECEIVED'}
        value={values.map_status}
      />
      <RosStatus
        label="LIDAR"
        online={values.lidar_online}
        value={values.lidar_online && values.scan_rate_hz
          ? `${values.scan_rate_hz.toFixed(1)} Hz`
          : undefined}
      />
      <RosStatus
        label="LOCALIZATION"
        online={values.localization_available}
      />
      <RosStatus label="TF map→base" online={values.tf_available} />
    </div>
  );
}


function RosStatus({ label, online, value }) {
  return (
    <span className={`slam-status-item ${online ? 'slam-status-item--online' : ''}`}>
      <span className="slam-status-dot" />
      <span>{label}</span>
      <strong>{value || (online ? 'ONLINE' : 'OFFLINE')}</strong>
    </span>
  );
}


function MapCoordinates() {
  return (
    <>
      <MapText
        x="20"
        y="22"
        text="[0.0, 0.0]"
      />

      <MapText
        x="557"
        y="22"
        text="[12.0m, 0.0]"
      />

      <MapText
        x="20"
        y="314"
        text="[0.0, 8.0m]"
      />

      <MapText
        x="545"
        y="314"
        text="[12.0m, 8.0m]"
      />
    </>
  );
}


function MapText({
  x,
  y,
  text,
}) {
  return (
    <text
      x={x}
      y={y}
      fill="#94A3B8"
      fontFamily="JetBrains Mono, monospace"
      fontSize="7"
    >
      {text}
    </text>
  );
}


function RestrictedZone() {
  return (
    <g transform="translate(270 225)">
      <rect
        width="145"
        height="72"
        fill="#08090C"
        stroke="#F59E0B"
        strokeDasharray="4 2"
      />

      <rect
        width="145"
        height="72"
        fill="url(#hazard-pattern)"
        pointerEvents="none"
      />

      <rect
        x="8"
        y="8"
        width="129"
        height="20"
        fill="#08090C"
        stroke="#F59E0B"
        strokeWidth="0.8"
      />

      <text
        x="14"
        y="14"
        fill="#F59E0B"
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        KHU VỰC HẠN CHẾ
      </text>
    </g>
  );
}


function MapLocation({
  location,
  task,
}) {
  const x = toSvgX(location.x);
  const y = toSvgY(location.y);

  const config =
    getLocationConfig(
      location.location_type
    );


  const width =
    location.location_type === 'RACK'
      ? 72
      : 92;

  const height =
    location.location_type === 'RACK'
      ? 34
      : 42;


  return (
    <g
      transform={
        `translate(${
          x - width / 2
        } ${
          y - height / 2
        })`
      }
      opacity={
        location.is_active
          ? 1
          : 0.45
      }
    >
      <rect
        width={width}
        height={height}
        fill="#0E1014"
        stroke={
          task
            ? '#FF7300'
            : config.stroke
        }
        strokeWidth={
          task
            ? 1.4
            : 1
        }
      />


      <text
        x="7"
        y="7"
        fill={config.color}
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        {location.name}
      </text>


      <text
        x="7"
        y="20"
        fill="#94A3B8"
        fontFamily="JetBrains Mono, monospace"
        fontSize="6.3"
        dominantBaseline="hanging"
      >
        {location.code}
      </text>


      {task && (
        <>
          <rect
            x={width - 39}
            y={height - 14}
            width="35"
            height="10"
            fill="#08090C"
            stroke="#FF7300"
            strokeWidth="0.6"
          />

          <text
            x={width - 36}
            y={height - 12}
            fill="#FF7300"
            fontFamily="JetBrains Mono, monospace"
            fontSize="5.7"
            fontWeight="700"
            dominantBaseline="hanging"
          >
            {task.task_code}
          </text>
        </>
      )}
    </g>
  );
}


function RobotMarker({
  robot,
  task,
}) {
  const status = robot.status;

  const x = toSvgX(status.x);
  const y = toSvgY(status.y);

  const online =
    status.online ?? false;

  const isLine =
    robot.robot_type === 'LINE';

  const color =
    isLine
      ? '#8BA888'
      : '#FF7300';


  const yawDegrees =
    status.yaw === null ||
    status.yaw === undefined
      ? 0
      : status.yaw *
        (180 / Math.PI);


  return (
    <g
      transform={`translate(${x} ${y})`}
      opacity={online ? 1 : 0.5}
    >
      {isLine ? (
        <polygon
          points="0,-8 8,0 0,8 -8,0"
          fill={color}
          stroke="#000000"
          strokeWidth="1.2"
        />
      ) : (
        <>
          <circle
            cx="0"
            cy="0"
            r="10"
            fill={color}
            stroke="#FFFFFF"
            strokeWidth="1.1"
          />

          <polygon
            points="-3,-5 6,0 -3,5"
            fill="#000000"
            transform={
              `rotate(${yawDegrees})`
            }
          />

          <circle
            cx="0"
            cy="0"
            r="15"
            fill="none"
            stroke={color}
            strokeDasharray="2 2"
            strokeWidth="0.8"
          />
        </>
      )}


      <RobotLabel
        robot={robot}
        task={task}
        color={color}
        right={isLine}
      />
    </g>
  );
}


function RobotLabel({
  robot,
  task,
  color,
  right,
}) {
  const x =
    right
      ? 13
      : -82;

  const textX =
    x + 6;


  return (
    <>
      <rect
        x={x}
        y="-15"
        width="68"
        height="31"
        rx="2"
        fill="#08090C"
        stroke={color}
        strokeWidth="0.8"
      />


      <text
        x={textX}
        y="-10"
        fill={color}
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        {robot.robot_code}
      </text>


      <text
        x={textX}
        y="2"
        fill="#CBD5E1"
        fontFamily="JetBrains Mono, monospace"
        fontSize="6"
        dominantBaseline="hanging"
      >
        {task
          ? task.task_code
          : 'Không có task'}
      </text>
    </>
  );
}


function Legend({
  tone,
  label,
}) {
  return (
    <span
      className={
        `legend-item legend-item--${tone}`
      }
    >
      <span className="legend-swatch" />
      {label}
    </span>
  );
}


function getLocationConfig(type) {
  const configs = {
    HOME: {
      color: '#FF7300',
      stroke: '#FF7300',
    },

    RACK: {
      color: '#F1F5F9',
      stroke: '#2A313D',
    },

    PICKUP: {
      color: '#8BA888',
      stroke: '#8BA888',
    },

    DELIVERY: {
      color: '#8BA888',
      stroke: '#8BA888',
    },

    CHARGING: {
      color: '#8BA888',
      stroke: '#8BA888',
    },
  };


  return (
    configs[type] ?? {
      color: '#F1F5F9',
      stroke: '#2A313D',
    }
  );
}


function findTaskAtLocation(
  locationId,
  tasks
) {
  return tasks.find(
    (task) =>
      task.pickup_location_id ===
        locationId ||
      task.dropoff_location_id ===
        locationId
  );
}


function findRobotTask(
  robotId,
  tasks
) {
  return tasks.find(
    (task) =>
      task.robot_id === robotId
  );
}


function hasPosition(robot) {
  return (
    robot.status?.x !== null &&
    robot.status?.x !== undefined &&
    robot.status?.y !== null &&
    robot.status?.y !== undefined
  );
}


function toSvgX(x) {
  return (
    SVG_LEFT +
    (Number(x) /
      MAP_WIDTH_METERS) *
      SVG_WIDTH
  );
}


function toSvgY(y) {
  return (
    SVG_TOP +
    (Number(y) /
      MAP_HEIGHT_METERS) *
      SVG_HEIGHT
  );
}
