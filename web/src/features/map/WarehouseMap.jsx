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
} from '../../services/api';
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from '../../services/realtime';
import SlamMap from './layers/SlamMap';
import { getAgvState } from '../robots/agv/agv';
import { agvToSharedMap } from '../robots/agv/agvAlignment';
import SavedMapControls from './SavedMapControls';
import MapEditor from './MapEditor';
import SavedMapNavigation from '../robots/amr/SavedMapNavigation';
import { mapView } from './savedMap';
import { getVisibleSlamStatus, receiveRosStatus } from '../robots/amr/rosStatus';
import FallbackWarehouseMap from './layers/FallbackWarehouseMap';


export default function WarehouseMap() {
  const [locations, setLocations] = useState([]);
  const [agvState,setAgvState] = useState(null);
  const [agvAlignment,setAgvAlignment] = useState(null);
  const [robots, setRobots] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [slamMap, setSlamMap] = useState(null);
  const [chosenMapMode, setMapMode] = useState(null);
  const [savedMap, setSavedMap] = useState(null);
  const mapMode = chosenMapMode ?? (savedMap ? 'saved' : 'live');
  const [mapSession,setMapSession]=useState(null);
  const [editingMap, setEditingMap] = useState(false);
  const [mapSourceBusy, setMapSourceBusy] = useState(false);
  const [slamPose, setSlamPose] = useState(null);
  const [slamStatus, setSlamStatus] = useState(null);
  const [navigationStatus, setNavigationStatus] = useState(null);
  const [navigationPath, setNavigationPath] = useState(null);
  const [statusNow, setStatusNow] = useState(() => performance.now());

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
        setSlamStatus(receiveRosStatus(statusData));
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
      () => setStatusNow(performance.now()),
      250
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
        setSlamStatus(receiveRosStatus(message.data));
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
          setSlamStatus(receiveRosStatus(statusData));
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


  useEffect(()=>{
    let active=true;
    const load=()=>getAgvState().then(v=>{if(active)setAgvState(v);}).catch(()=>{});
    load();const timer=window.setInterval(load,1000);
    return ()=>{active=false;window.clearInterval(timer);};
  },[]);

  useEffect(()=>{
    if(!savedMap?.map_hash){setAgvAlignment(null);return;}
    try {setAgvAlignment(JSON.parse(window.localStorage.getItem('wrms-agv-align-'+savedMap.map_hash)||'null'));}
    catch {setAgvAlignment(null);}
  },[savedMap?.map_hash]);

  const visibleSlamStatus = getVisibleSlamStatus(
    slamStatus,
    statusNow
  );

  const view = mapView(mapMode, slamMap, savedMap, slamPose, navigationStatus?.goal, navigationPath);
  const agvSharedPose = agvState?.connected && mapMode === 'saved' && savedMap
    ? agvToSharedMap(savedMap,agvAlignment,agvState.telemetry,agvState.robot_code) : null;
  const savedRosVisible = mapMode === 'saved' && savedMap?.id === mapSession?.map_id
    && mapSession?.state !== 'OFFLINE' && savedMap?.map_hash === mapSession?.map_hash && mapSession?.map_verified
    && mapSession?.localization_valid && Date.now()-mapSession.received_at<5000;
  const savedGoal = savedRosVisible && navigationStatus?.goal?.map_context?.map_id===savedMap.id
    ? navigationStatus.goal : null;
  const mapTitle = mapMode === 'saved' ? 'SAVED MAP (SERVER)' : slamMap
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
            {view.map ? `${(view.map.width * view.map.resolution).toFixed(2)}m × ${(view.map.height * view.map.resolution).toFixed(2)}m` : '12.0m × 8.0m'}
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


      <SavedMapControls onBusyChange={setMapSourceBusy} locked={editingMap} mode={mapMode} onModeChange={setMapMode} map={savedMap} onMapChange={setSavedMap} />
      {mapMode === "saved" && view.map && <SavedMapNavigation key={"nav-"+view.map.id} map={view.map} navigation={navigationStatus} onSession={setMapSession} disabled={editingMap || mapSourceBusy} />}
      <SlamStatusStrip status={visibleSlamStatus} />
      {mapMode==='saved' && savedMap && <div style={{padding:10,background:'var(--surface)',color:'var(--text-primary)',border:'1px solid var(--border)',borderRadius:8,marginBottom:10}}>
        <strong>Hai robot · Một bản đồ WRMS</strong>
        <p style={{fontSize:12,margin:'5px 0'}}>Căn chỉnh ba mốc AGV A, B, D bằng tọa độ mét của bản đồ đang chọn. Chỉ dùng sau khi đo thực tế; không tự kéo giãn 1.54 × 1.51 m.</p>
        <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
          {['a','b','d'].map(anchor=><label key={anchor} style={{fontSize:12}}>Mốc {anchor.toUpperCase()}:
            {['x','y'].map(axis=><input key={axis} aria-label={anchor.toUpperCase()+' '+axis} type="number" step="0.01" placeholder={axis}
              value={agvAlignment?.[anchor]?.[axis] ?? ''}
              onChange={event=>{
                const number=event.target.value===''?null:Number(event.target.value);
                const next={...(agvAlignment||{}),map_hash:savedMap.map_hash,map_id:savedMap.id,
                  [anchor]:{...(agvAlignment?.[anchor]||{}),[axis]:number}};
                setAgvAlignment(next);
                window.localStorage.setItem('wrms-agv-align-'+savedMap.map_hash,JSON.stringify(next));
              }} style={{width:75,marginLeft:4}}/>)}
          </label>)}
        </div>
        <p style={{fontSize:12,marginTop:5}}>{agvSharedPose?'AGV đã căn chỉnh: hiển thị vị trí thật trên bản đồ chung':
          'AGV chưa có phép căn chỉnh hợp lệ; không hiển thị vị trí sai lên bản đồ.'}</p>
      </div>}


      {error && (
        <div className="map-error">
          Không thể cập nhật bản đồ: {error}
        </div>
      )}


      {mapMode === 'saved' && !view.map ? (
        <div className="map-canvas saved-map-empty">Chưa chọn bản đồ đã lưu. Hãy upload hoặc chọn bản đồ từ danh sách.</div>
      ) : mapMode === 'saved' && view.map ? (
        <MapEditor key={view.map.id} agvPose={agvSharedPose} pose={savedRosVisible ? slamPose : null} goal={savedGoal} path={savedGoal ? navigationPath : null} sourceBusy={mapSourceBusy} map={view.map} onEditingChange={setEditingMap} />
      ) : view.map ? (
        <SlamMap {...view} />
      ) : (
      <FallbackWarehouseMap locations={locations} robots={robots} tasks={tasks} />
      )}
    </section>
  );
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
        label="ROS MAP"
        online={values.map_status === 'RECEIVED'}
        value={values.map_status}
      />
      <RosStatus
        label="LIDAR"
        online={values.lidar_online}
        value={values.lidar_status || 'OFFLINE'}
        stale={values.lidar_status === 'STALE'}
      >
        <span>SCAN {metric(values.scan_rate_hz, 1, 'Hz')}</span>
        <span title="Scan age at bridge send time + elapsed time since receipt in this browser">
          AGE {metric(values.last_scan_age_ms, 0, 'ms')}
        </span>
        <span>FRAME {values.scan_frame_id || '—'}</span>
        <span title="Valid finite ranges within LaserScan range_min / range_max">
          POINTS {values.lidar_online && values.scan_points_total != null
            ? `${values.scan_points_valid ?? '—'}/${values.scan_points_total}` : '—'}
        </span>
        <span>NEAREST {metric(values.lidar_online ? values.nearest_obstacle_m : null, 2, 'm')}</span>
        <span title="Gap between scans received by bridge; maximum since bridge start">
          GAP / MAX {metric(values.scan_gap_ms, 0, 'ms')} / {metric(values.scan_max_gap_ms, 0, 'ms')}
        </span>
        <span title="Time since this browser received a status update; not end-to-end sensor latency">
          UPDATE {metric(values.update_age_ms, 0, 'ms')}
        </span>
      </RosStatus>
      <RosStatus
        label="LOCALIZATION"
        online={values.localization_available}
      />
      <RosStatus label="TF map→base" online={values.tf_available} />
    </div>
  );
}


function metric(value, digits, unit) {
  return Number.isFinite(value) ? `${value.toFixed(digits)} ${unit}` : '—';
}


function RosStatus({ label, online, value, stale = false, children }) {
  return (
    <span className={`slam-status-item ${online ? 'slam-status-item--online' : ''} ${stale ? 'slam-status-item--stale' : ''} ${children ? 'slam-status-item--lidar' : ''}`}>
      <span className="slam-status-dot" />
      <span>{label}</span>
      <strong>{value || (online ? 'ONLINE' : 'OFFLINE')}</strong>
      {children}
    </span>
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


