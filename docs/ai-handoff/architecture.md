# SLAM_KLTN architecture handoff

Phase 1 audit baseline: `a1b4f67957491c6c281d6540ea508d8f37d9f3fd` on `ai/team-pilot`. See `progress.md` for the current worktree state.

## Existing architecture

- React: `web/src/App.jsx` owns page selection, shell metrics, and shared realtime state. Flat `web/src/UI/` components cover dashboard, robots, maps, missions, alerts, and history. `web/src/services/api.js` and `realtime.js` are shared clients. `web/src/styles/dashboard.css` defines the light theme tokens; `responsive.css` adds responsive rules.
- FastAPI: `web/backend/app/main.py` registers shared `/api/robots`, `/api/tasks`, `/api/maps`, `/api/planning`, `/api/alerts`, `/api/history`, `/ws`, plus robot routes. `models/`, `schemas/`, and `db/` are shared. A task has nullable `robot_id`; robots have unique `robot_code` and type `AMR` or `LINE`.
- AMR: `api/routes/{ros,map_session}.py` and `services/{ros_state,navigation,map_session}.py` handle ROS2, SLAM, and Nav2. React `UI/{NavigationPanel,SavedMapNavigation,SlamMap}.jsx` and `services/rosStatus.js` show AMR state and paths.
- AGV: `api/routes/agv.py` exposes `/{robot_code}` telemetry and commands; `services/{agv_runtime,agv_alignment}.py` handle per-robot state and alignment. React `UI/AgvTelemetryPanel.jsx` and `services/{agv,agvAlignment}.js` handle telemetry, commands, and map placement.
- Shared map: `UI/{WarehouseMap,MapEditor,SavedMapControls,MapProducts}.jsx` and `services/{slamMap,savedMap,planning}.js` coordinate live and saved maps, planning objects, and editing. `WarehouseMap.jsx` currently mixes these with both robot integrations.

## Target boundary

Keep repository roots `web/`, `firmware/`, `ros2_ws/`, and `scripts/`. Use `web/src/features/{dashboard,robots/{shared,amr,agv},map,missions,alerts,history}/`, `web/src/shared/ui/`, and the existing shared `services/` and `styles/`. The map feature owns base rendering, AMR and AGV visualization layers, restricted zones, locations, and controls. Robot features own their telemetry and command UI; neither imports the other's internals.

Keep public FastAPI route modules and database contracts stable. In Phase 3, separate shared task lifecycle from robot dispatch, with an AMR navigation adapter and an AGV command/runtime adapter only where dispatch needs them. Preserve different low-level command vocabularies.

## Invariants and decisions

- Keep existing REST paths, payloads, WebSocket event names, task states, and frontend API calls compatible. Use `robot_id` for ownership and `robot_code` for robot-specific routes; `LINE-01` remains a compatibility default, not a general routing rule.
- AGV odometry is local, with +Y down and yaw in degrees. It is **not** a ROS `map` pose. Place it on a saved map only after verified A/B/D alignment, matching `map_id` and `map_hash`, finite values, and bounds checks. Preserve ROS `frame_id`, origin, resolution, and yaw semantics.
- The fallback schematic has no map ID/hash for AGV alignment. It now withholds LINE markers and shows `POSITION_UNKNOWN / UNCALIBRATED`; AMR marker rendering and map transforms are unchanged. Saved-map AGV placement still requires verified alignment.
- Retain saved-map identity and localization freshness checks, planning revisions, edit/leave prompts, and all existing map tools.
- An AGV command ACK confirms transport only; it must not complete a mission. No motor control, navigation algorithm, firmware, ROS package, or physical hardware change belongs to this refactor.
