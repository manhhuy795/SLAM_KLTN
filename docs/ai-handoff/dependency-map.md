# Dependency map

Paths below are relative to the repository root. `->` means imports or calls. This is the focused Phase 1 map, not an exhaustive import graph.

## Frontend

| Source and symbols | Depends on / used by | Phase 2 destination; tests |
|---|---|---|
| `web/src/App.jsx` (`App`) | `UI/{Header,Sidebar,RobotStatus,AgvTelemetryPanel,ActiveTasks,WarehouseMap,DashboardSidePanel,Tasks,Robots,MapProducts,Alerts,History}`; `services/{api,realtime}` | Keep shell; update imports. Build check. |
| `features/map/WarehouseMap.jsx` (`WarehouseMap`) | Shared `services/{api,realtime}`, AGV `{agv,agvAlignment}`, AMR `rosStatus` and `SavedMapNavigation`, map `{savedMap,SavedMapControls,MapEditor,layers/SlamMap,layers/FallbackWarehouseMap}`; used by `App` and `MapProducts` | Coordinator. Map and alignment tests. |
| `features/map/MapEditor.jsx` (`MapEditor`) | `layers/{SlamMap,AgvMapLayer}`, `services/{api,realtime}`, `transforms/slamMap`, `planning`; receives aligned `agvPose` | Preserve editor and planning overlay. `planning.test.js`. |
| `features/map/layers/SlamMap.jsx` (`SlamMap`) | `BaseOccupancyMap.jsx` and `AmrMapLayer.js`; used by `WarehouseMap` and `MapEditor` | Wrapper preserves map CSS/metadata; `AmrMapLayer.test.js`, `transforms/slamMap.test.js`, `savedMap.test.js`. |
| `features/map/layers/FallbackWarehouseMap.jsx` | `RestrictedZones.jsx`, `LocationsLayer.jsx`, `fallbackCoordinates.js`; draws AMR status only | LINE status is shown as `POSITION_UNKNOWN / UNCALIBRATED`; `fallbackCoordinates.test.js` covers gating and scaling. |
| `UI/{SavedMapControls,SavedMapNavigation,NavigationPanel}.jsx` | Shared `api` and `realtime`; navigation panel also uses `slamMap` bounds check | Map controls; AMR navigation. Build and interaction checks. |
| `UI/AgvTelemetryPanel.jsx` (`AgvTelemetryPanel`) | `services/agv.js` (`agvUrl`, `getAgvState`, `sendAgvCommand`, `exportAgvLogs`) and `realtime`; used by `App` | `features/robots/agv/`. Build and AGV state checks. |
| `services/agvAlignment.js` (`agvToSharedMap`) | `slamMap.js` (`isWorldPointInMap`); used by `WarehouseMap` | AGV adapter. `agvAlignment.test.js`. |
| `services/{slamMap,savedMap,planning,rosStatus}.js` | Map conversion, map selection, planning geometry, ROS freshness; imported by map and AMR UI | Move with owning feature; matching `*.test.js` files. |
| `services/{api,realtime,safeStop}.js` | Shared REST, WS, stop state; imported across features | Remain shared. `safeStop.test.js`. |
| `UI/{Header,Sidebar,DashboardSidePanel,RobotStatus,ActiveTasks,Robots,Tasks,MapProducts,Alerts,History}.jsx` | Shared API/realtime, with `MapProducts -> WarehouseMap` | Move by feature; update imports. Build and existing service tests. |

## Backend

| Source and symbols | Relationship / risk | Tests |
|---|---|---|
| `web/backend/app/main.py` | Registers shared, ROS, AGV routes and `/ws`; public paths stay fixed. | `tests/test_smoke.py` |
| `api/routes/tasks.py` (`task_query`, `build_task_response`, lifecycle routes) | Calls `services/task_executor.py`; helpers imported by `commands.py` and `ros.py`. | `test_smoke.py`, `test_navigation.py` |
| `services/task_executor.py` (`TaskExecutor`) | Task validation and dispatch depend on ROS bridge, Nav2, localization, matching `pose.robot_id` for every assigned robot. | `test_smoke.py`, `test_navigation.py` |
| `api/routes/agv.py` (`ingest_telemetry`, AGV state/command routes) | Calls `agv_runtime`, imports robot response helper from `robots.py`; stores AGV-local coordinates in generic status. | `test_agv_runtime.py` |
| `services/{agv_runtime,agv_alignment}.py` | Per-code mailbox and ACK; explicit local-to-map alignment. | `test_agv_runtime.py` and focused alignment coverage to verify in Phase 3 |
| `api/routes/{ros,map_session}.py`; `services/{ros_state,navigation,map_session}.py` | ROS/SLAM/Nav2 and saved-map session boundary; `ros.py` imports task response helper, and map routes share `find_map`. | `test_ros_state.py`, `test_navigation.py`, `test_map_session.py`, `test_saved_maps.py` |
| `models/{robot,robot_status,task,saved_map,planning_layer}.py`; `db/*` | Shared identity, status, ownership, map metadata, persistence. | `test_smoke.py`, `test_planning.py`, `test_saved_maps.py` |

## Coupling to resolve

1. `features/map/WarehouseMap.jsx` remains the coordinator for fetching, map mode, alignment, and editing. `App` and `MapProducts` remain its callers.
2. `features/map/MapEditor.jsx` uses `layers/AgvMapLayer.jsx` inside the shared planning overlay; `worldToCanvas` and editor behavior were preserved.
3. `features/robots/agv/{agv,agvAlignment}.js` and `AgvTelemetryPanel.jsx` accept a robot code with `LINE-01` as compatibility default. `layers/AgvMapLayer.jsx` labels from the aligned pose code. Backend AGV routes already accept `robot_code`.
4. `tasks.py -> task_executor.py` applies AMR navigation requirements to LINE tasks. Phase 3 must dispatch by robot capability while preserving ownership and lifecycle checks.
5. `features/map/layers/FallbackWarehouseMap.jsx` now excludes LINE robots from schematic markers because their generic `RobotStatus.x/y` contains local odometry. The fixed fallback schematic has no map identity for alignment. The saved-map AGV layer remains separately calibrated.
