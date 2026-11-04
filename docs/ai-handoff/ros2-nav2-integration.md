# Phase 4C — AMR ROS2/Nav2 integration

## Traced path (static and mocked verification)

1. React `web/src/features/robots/amr/NavigationPanel.jsx` and `SavedMapNavigation.jsx` call `web/src/services/api.js`; `WarehouseMap.jsx` renders live/saved map, pose, path and status. `rosStatus.js` expires stale heartbeat data. Saved-map overlays require matching map ID/hash and a fresh verified map session.
2. FastAPI `app/api/routes/ros.py` serves `/api/ros/{state,map,pose,navigation/*}` and publishes existing WebSocket events. `services/navigation.py` owns in-memory goal IDs, claim, status, path and cancel state. `services/map_session.py` binds managed goals to a verified saved-map ID/hash, session ID and planning revision. `services/task_executor.py` loads `Task.robot_id` from the DB and requires an active AMR before Nav2 task dispatch or callback mutation. LINE tasks are rejected from this path.
3. `ros2_ws/src/web_bridge/web_bridge/web_bridge_node.py` subscribes to `/scan`, `/map` and `/plan`, looks up `map -> base_link` through TF, posts telemetry to FastAPI, claims navigation commands, and sends `NavigateToPose` goals to `/navigate_to_pose`. The Nav2 action result, not goal acceptance, supplies terminal status; cancellation remains pending until an action result. `managed_maps.py` verifies the Map Server grid against the Saved Map, AMCL covariance and TF freshness, Nav2 lifecycle nodes, costmap/keepouts and the current planning revision before dispatch.
4. Gazebo `amr_sim/config/bridge.yaml` bridges `/scan`, `/odom`, `/tf` and `/clock`; `simulation.launch.py` publishes the static `base_link -> laser_link` transform on `/tf_static`. `saved_map_navigation.launch.py` starts Map Server, AMCL, Nav2 and the managed Web Bridge. `/odom` stays odometry frame data; map-frame pose comes from TF after localization. The simulated world floor is 12 × 8 m. The physical map is 2.38 × 1.68 m; no transform or shared identity between them has been verified.

The local SQLite `robots` row for `AMR-01` is active, type `AMR`, ID 1, matching `web_bridge/config/bridge.yaml` `robot_id: 1` at this checkpoint. Recheck this ID when using another database. The bridge's `backend_url` defaults to `http://127.0.0.1:8000`; use a reachable host when ROS2 and FastAPI run on different machines.

## Confirmed fix

The direct `POST /api/ros/navigation/goal` endpoint previously queued a command even when the bridge was offline. It now requires a fresh ROS heartbeat with both `bridge_online` and `nav2_online`; otherwise it returns HTTP 409 before creating a command. AMR task starts already had a live ROS/robot guard. The map-session and smoke fixtures now provide explicit mocked heartbeats and verify no command is queued on rejection.

## Startup and read-only checks (Ubuntu/ROS2; **not run** in this Windows session)

```bash
# Terminal 1: backend (from web/backend; configure WRMS_DATABASE_URL as needed)
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: frontend (from web)
npm run dev -- --host 127.0.0.1 --port 5173

# Ubuntu ROS2 terminal (from ros2_ws)
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-up-to amr_sim web_bridge
source install/setup.bash
ros2 launch amr_sim simulation.launch.py

# Separate Ubuntu ROS2 terminal, after sourcing the same setup files
ros2 launch amr_sim saved_map_navigation.launch.py

# Read-only observation; never substitute a physical map for the Gazebo map
ros2 topic hz /scan
ros2 topic hz /odom
ros2 topic echo /tf_static --once
ros2 run tf2_ros tf2_echo map base_link
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /bt_navigator
ros2 action info /navigate_to_pose
curl http://127.0.0.1:8000/api/ros/state
curl http://127.0.0.1:8000/api/ros/map-session
```

The saved map must be compared with the **running Gazebo world** before applying it in the existing Map UI. A managed goal remains blocked until map identity, localization, Nav2 and keepouts report ready. These commands only start or inspect services; this Phase 4C session did not launch Gazebo or send a goal.

## Test evidence and blockers

- Windows Python 3.11 backend regression: **100/100 passed** with `PYTHONIOENCODING=utf-8`. Focused HTTP navigation and map-session tests passed. Frontend Node tests **18/18**, Playwright Chromium **18/18**, production build and `git diff --check` passed.
- ROS2 runtime, Gazebo topics/TF rates, lifecycle transitions, real goal/result/cancel round trip and physical map alignment: **NOT RUN / NOT VERIFIED** on Windows. ROS2 CLI is unavailable here. CV integration: **PENDING**. AGV auto dispatch remains disabled.
- The ROS command queue and map session are process-local; run one FastAPI worker for this integration path until multi-worker ownership/recovery is designed. ROS bridge POST endpoints are not independently authenticated in the current code; isolate the backend network before any deployment. A bridge failure immediately after an accepted goal still needs runtime recovery verification. No physical or simulated movement was executed in this phase.

## Phase 4C.1 live simulation runbook — NOT RUN here

On 2026-11-04, this host had no Ubuntu WSL distribution (`wsl --list --verbose` showed only stopped `docker-desktop`) and no `ros2` or `colcon` executable. No Gazebo, ROS2 node or browser-to-Nav2 goal was started. The commands below are for an **Ubuntu 24.04 / ROS2 Jazzy simulation host only**. Set `WRMS_ROOT` to that host's checkout (for a future Ubuntu WSL install, `/mnt/f/SLAM_KLTN-agent-pilot`). Keep the backend reachable at `127.0.0.1:8000` from the Web Bridge; if services are split across hosts, explicitly configure the bridge backend URL before starting. Do not point these commands at a physical robot or production database.

```bash
# Terminal 1 — isolated simulation backend; save the printed directory for all terminals.
export WRMS_ROOT=/mnt/f/SLAM_KLTN-agent-pilot
export WRMS_SIM_DIR="$(mktemp -d /tmp/wrms-nav2-4c1-XXXXXX)"
printf 'WRMS_SIM_DIR=%s\n' "$WRMS_SIM_DIR"
export WRMS_DATABASE_URL="sqlite:///$WRMS_SIM_DIR/wrms.db"
export WRMS_MAPS_DIR="$WRMS_SIM_DIR/maps"
export WRMS_AGV_AUTO_DISPATCH_ENABLED=0
export WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED=0
cd "$WRMS_ROOT/web/backend"
python3 -m venv "$WRMS_SIM_DIR/venv"
source "$WRMS_SIM_DIR/venv/bin/activate"
python -m pip install -r requirements.txt
python init_db.py && python seed.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | tee "$WRMS_SIM_DIR/backend.log"

# Terminal 2 — React; use the same WRMS_ROOT.
export WRMS_ROOT=/mnt/f/SLAM_KLTN-agent-pilot
cd "$WRMS_ROOT/web"
npm ci
npm run dev -- --host 127.0.0.1 --port 5173

# Terminal 3 — Gazebo only; source ROS2 and the local build.
export WRMS_ROOT=/mnt/f/SLAM_KLTN-agent-pilot
source /opt/ros/jazzy/setup.bash
cd "$WRMS_ROOT/ros2_ws"
colcon build --symlink-install --packages-up-to amr_sim web_bridge
source install/setup.bash
ros2 launch amr_sim simulation.launch.py 2>&1 | tee /tmp/wrms-gazebo-4c1.log

# Terminal 4 — managed Saved Map/Nav2/Web Bridge (same sourced ROS2 setup).
export WRMS_ROOT=/mnt/f/SLAM_KLTN-agent-pilot
source /opt/ros/jazzy/setup.bash
source "$WRMS_ROOT/ros2_ws/install/setup.bash"
ros2 launch amr_sim saved_map_navigation.launch.py 2>&1 | tee /tmp/wrms-nav2-4c1.log
```

Use one backend worker. The seed provides robot records for the **isolated** database; do not treat seeded locations as verified navigation targets. Confirm `GET /api/robots` identifies active `AMR-01` with the same numeric ID as `web_bridge/config/bridge.yaml` (currently 1). Confirm Gazebo is the 12 × 8 m `warehouse.sdf` world. The 2.38 × 1.68 m physical map is out of scope.

In a fifth Ubuntu terminal, source ROS2 and the workspace setup as above. Save read-only evidence before any goal:

```bash
ros2 topic hz /scan
ros2 topic hz /odom
ros2 topic echo /tf_static --once
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo map odom
ros2 run tf2_ros tf2_echo base_link laser_link
ros2 topic echo /amcl_pose --once
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
ros2 lifecycle get /bt_navigator
ros2 action info /navigate_to_pose
curl -fsS http://127.0.0.1:8000/api/ros/state | jq .
curl -fsS http://127.0.0.1:8000/api/ros/map-session | jq .
```

Each topic/TF/lifecycle check requires its own running terminal or timeout. Expect nonzero `/scan` and `/odom` rates, the `map → odom → base_link → laser_link` chain, fresh AMCL covariance, active Map Server/AMCL/Nav2 nodes, and `/navigate_to_pose` action availability. A topic name in a launch file is **not** live evidence. Save terminal output alongside the backend, Gazebo and Nav2 logs.

For a simulation-only Saved Map, generate the repo's `warehouse.sdf` geometry fixture and inspect it against the running world before loading. It is not a physical LiDAR survey. Set `WRMS_SIM_DIR` to the path printed by Terminal 1:

```bash
export WRMS_ROOT=/mnt/f/SLAM_KLTN-agent-pilot
export WRMS_SIM_DIR=/tmp/REPLACE_WITH_TERMINAL_1_DIRECTORY
python3 "$WRMS_ROOT/ros2_ws/src/amr_sim/test/make_warehouse_map.py" \
  --output "$WRMS_SIM_DIR/warehouse"
sha256sum "$WRMS_ROOT/ros2_ws/src/amr_sim/worlds/warehouse.sdf" | tee "$WRMS_SIM_DIR/world.sha256"
# Confirm the fixture reports 240 × 160 cells at 0.05 m/cell (12 × 8 m), then inspect the map in WRMS.
```

After an operator confirms the running Gazebo world and the known initial simulation pose, the existing `web/tests/nav2-saved-map.browser.cjs` can exercise map load, keepouts, a **simulation** goal, result propagation and a React screenshot. It explicitly refuses to run without `NAV2_SIMULATION_TEST=1` and requires the managed bridge to report `environment=simulation`. The Gazebo launch spawns the AMR at `(0, 0, 0)`; verify that pose before using it. This script uses simulation planning points only and does **not** test cancel or a Nav2 action failure:

```bash
cd "$WRMS_ROOT/web"
npx playwright install chromium
export NAV2_SIMULATION_TEST=1
export NAV2_INITIAL_POSE='{"x":0,"y":0,"yaw":0}'
export NAV2_TEST_MAP_PREFIX="$WRMS_SIM_DIR/warehouse"
export NAV2_TEST_ARTIFACT_DIR="$WRMS_SIM_DIR/artifacts"
export TEST_BACKEND_URL=http://127.0.0.1:8000/api
export TEST_FRONTEND_URL=http://127.0.0.1:5173
node tests/nav2-saved-map.browser.cjs 2>&1 | tee "$WRMS_SIM_DIR/nav2-browser.log"
```

Pass requires the script's terminal `SUCCEEDED` assertion, a matching `map_id`/`map_hash`, `map_verified`, `localization_valid`, `nav2_active`, `keepout_verified`, observed path/pose, and a rendered React screenshot. Preserve `artifacts/3c-navigation-observed.json`, `artifacts/3c-result.json` and screenshots. Goal **acceptance alone is not success**.

For cancellation, while the isolated managed session is `READY`, choose a distinct safe planning point in the **same** simulation map and start it from the existing Saved Map UI. Observe `NAVIGATING` in `/api/ros/navigation/status`, click the existing cancel control, and record the Nav2 action result, backend status and React status. Pass only if the action result is `CANCELLED` and no task is falsely completed. If the goal reaches a terminal state before cancellation, record **NOT RUN** and choose a longer safe simulation route; do not claim a cancel pass. For a failure check, use an operator-selected blocked/unreachable point in this isolated simulation and require `REJECTED` or `FAILED` to propagate without a task success. A preflight 409 is a separate backend rejection check, not evidence of Nav2 action failure. Do not fabricate a location or use the physical map to force failure.

### Phase 4C.1 evidence status

| Live check | Status | Evidence |
| --- | --- | --- |
| `/scan`, `/odom`, TF chain, `/amcl_pose` | NOT RUN | Ubuntu ROS2 unavailable |
| Map Server/AMCL/Nav2 lifecycle | NOT RUN | Ubuntu ROS2 unavailable |
| Saved Map identity and localization | NOT RUN | No Gazebo world or bridge launched |
| Goal acceptance, result and React propagation | NOT RUN | No simulation goal sent |
| Cancel and Nav2 failure result | NOT RUN | No simulation goal sent |

No live logs were produced in this session. No integration bug was confirmed by live evidence, so no source file was changed. CV remains PENDING; AGV auto dispatch remains OFF.
