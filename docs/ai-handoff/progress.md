# Progress and next action

| Phase | Status |
|---|---|
| Phase 1 — architecture audit | **COMPLETED** |
| Phase 1.5 — persistent context | **DOCUMENTATION HANDOFF** |
| Phase 2 — frontend modularization | **IMPLEMENTED; MOCKED BROWSER QA PASSED; FALLBACK FIXED** |
| Phase 3 — backend modularization | **3A/3B COMPLETE; 3C/3D MOCK BACKEND IMPLEMENTED; PHYSICAL INTEGRATION BLOCKED** |
| Phase 4 — integration and review | **NOT STARTED** |

## Repository state at handoff

- Branch: `ai/team-pilot`; HEAD: `a1b4f67957491c6c281d6540ea508d8f37d9f3fd`.
- Before this handoff: `git status --short --branch` reported `?? .codex/` and `?? AGENTS.md`; branch was ahead of its configured upstream by one commit. No tracked or staged changes were reported.
- Relevant tracked source files have no current tracked or staged diff, and the worktree status matches the Phase 1 snapshot. The Phase 1 HEAD SHA was not recorded, so an intervening commit cannot be independently ruled out from that snapshot alone. The untracked instructions/configuration were left untouched. This handoff adds only `docs/ai-handoff/*.md`.

## Completed analysis

- Mapped frontend features, shared API/realtime clients, AMR and AGV UI, map rendering/editing, backend routes/services/models, task dispatch, and existing tests.
- Recorded proposed file moves, import impacts, target boundaries, compatibility requirements, batch gates, and rollback approach in this directory.

## Open risks and required checks

- Fallback AGV coordinate defect was confirmed during Phase 2 and fixed in the focused follow-up below. The schematic has no map identity; LINE robots are withheld from map markers and shown as `POSITION_UNKNOWN / UNCALIBRATED`.
- Task start currently requires ROS/Nav2 for any assigned robot. Resolve in Phase 3 with robot-specific dispatch and regression tests.
- Frontend `LINE-01` hardcoding needs a compatibility-safe robot-code input. AGV ACK must never imply mission completion.
- Required in Phase 2: `npm.cmd run build`, existing frontend `node --test` service tests, focused coordinate-frame check, and manual inspection of live/saved/fallback views without movement commands.
- Required in Phase 3/4: existing backend tests, new ownership/lifecycle/ACK checks, route and WS compatibility, import-boundary review, and independent reviewer pass.

## Next action

Phase 3C and Phase 4 remain unapproved. Review the 3B results below and `phase3a-dispatch-design.md` before further backend work. Real robot integration remains unverified.

## Phase 2 batch log

### Batch 2A — completed

- Moved `web/src/UI/{Header,Sidebar}.jsx` to `web/src/shared/ui/`; `{DashboardSidePanel,ActiveTasks}.jsx` to `web/src/features/dashboard/`; `{RobotStatus,Robots}.jsx` to `web/src/features/robots/shared/`; `Tasks.jsx`, `Alerts.jsx`, and `History.jsx` to their `features/{missions,alerts,history}/` directories. Updated `web/src/App.jsx` and moved-file relative imports. `DashboardSidePanel` temporarily imports the old AMR `UI/NavigationPanel` until 2B.
- Frontend agent reported `npm.cmd run build` passed, `node --test --test-isolation=none` passed 14/14 service tests, and `git diff --check` passed. Plain `node --test` hit sandbox spawn `EPERM`; the isolation-free rerun completed. Manager confirmed the build import paths in the diff and a clean `git diff --check`.
- No known Batch 2A regression. Visual QA was not performed. The fallback AGV frame defect remains unresolved and outside this batch.

### Batch 2B — completed

- Moved `web/src/UI/{NavigationPanel,SavedMapNavigation}.jsx` and `web/src/services/{rosStatus,rosStatus.test}.js` to `web/src/features/robots/amr/`. Moved `web/src/UI/AgvTelemetryPanel.jsx` and `web/src/services/{agv,agvAlignment,agvAlignment.test}.js` to `web/src/features/robots/agv/`. Updated imports in `web/src/{App.jsx,UI/WarehouseMap.jsx,features/dashboard/DashboardSidePanel.jsx}`.
- AGV client, panel, and aligned pose accept a robot code with `LINE-01` as the existing default. The alignment calculations and command vocabulary were not changed; one identity assertion was added.
- Frontend agent reported `node --test --test-isolation=none` passed 15/15, `npm.cmd run build` passed, and `git diff --check` passed. Manager checked relevant imports and the AGV identity changes; no stale imports were found. No known Batch 2B regression. Visual QA was not performed.

### Fallback coordinate verification — confirmed before Batch 2C

- `web/backend/app/api/routes/agv.py:82-85` writes AGV-local `x/y/yaw` into generic `RobotStatus`. `web/src/UI/WarehouseMap.jsx:246-247,435-436,741-742` filters status by presence and draws those raw `x/y` with schematic scaling in the fallback branch. That branch does not call `agvToSharedMap`.
- Saved-map AGV rendering does call `agvToSharedMap` at `WarehouseMap.jsx:260-261`; `agvAlignment.test.js` checks rejection of missing alignment, wrong map hash, and invalid anchors. The existing tests do not cover the fallback branch. **Defect and impact:** a LINE robot with local telemetry can be shown at a misleading warehouse-map position in fallback mode. No coordinate semantics have been changed; this remains unresolved for separate approval.

### Batch 2C, step 1 — completed

- Moved `web/src/UI/{WarehouseMap,MapEditor,MapProducts,SavedMapControls}.jsx` to `web/src/features/map/` and `UI/SlamMap.jsx` to `features/map/layers/SlamMap.jsx` temporarily. Moved `web/src/services/{slamMap,slamMap.test}.js` to `features/map/transforms/` and `{savedMap,savedMap.test,planning,planning.test}.js` to `features/map/`. Updated affected imports in `App.jsx`, map components, AMR `NavigationPanel.jsx`, and AGV `agvAlignment.js`.
- Frontend agent reported `node --test --test-isolation=none` passed 15/15, `npm.cmd run build` passed, and `git diff --check` passed. Manager confirmed no stale old imports in the affected feature tree and that fallback `RobotMarker` still reads raw `status.x/y`.
- No known step 1 regression. Presentation extraction and visual QA remain outstanding. The fallback coordinate defect remains unresolved.

### Batch 2C, step 2 — completed

- Extracted `features/map/layers/{FallbackWarehouseMap,RestrictedZones,LocationsLayer,fallbackCoordinates,BaseOccupancyMap,AmrMapLayer,AgvMapLayer}` from `WarehouseMap.jsx`, `MapEditor.jsx`, and the temporary `layers/SlamMap.jsx` wrapper. Added `fallbackCoordinates.test.js` and `AmrMapLayer.test.js`. The fallback component retains raw `RobotStatus.x/y` scaling with an explicit comment; no coordinate formula or frame guard was changed.
- Frontend agent reported 17/17 Node tests, `npm.cmd run build`, and `git diff --check` passed. Manager independently reran the same checks: 17/17 tests, successful Vite production build, and clean diff check. No known Batch 2C regression from these checks.
- A local preview server started, but Windows Computer Use stopped the browser check because it could not determine the current browser URL confidently enough to enforce policy. Browser visual QA and live/saved/fallback interaction checks remain unverified. The preview server was stopped.

### Independent review and fix

- Reviewer inspected the working tree, including new untracked frontend files. One medium finding: `layers/AgvMapLayer.jsx` always labeled an aligned pose `LINE-01` even when the AGV adapter supplied another `robot_code`. The frontend agent fixed visible and accessible labels to use the pose code with the existing default. Geometry remained unchanged; manager independently reran 17/17 tests, a successful build, and a clean diff check after the fix. A targeted source search found no stale old service/UI imports.
- Reviewer found no additional broken imports, REST/WS changes, AMR/AGV internal cross-imports, coordinate calculation changes, map editing changes, or scope violations. Reviewer also confirmed the fallback defect remains and the new fallback test covers scaling, not frame correctness.

### Phase 2 browser visual QA — completed with deterministic mocks

- Added `web/playwright.config.js`, `web/tests/visual.spec.js`, `test:visual` in `web/package.json`, and ignored generated `web/test-results/` and `web/tests/screenshots/` in `.gitignore`. The existing Playwright dependency and user screenshot `web/wrms-test.png` were preserved.
- Playwright Chromium: **13/13 passed**, zero failed at 1920×1080, 1366×768, 768×1024, and 390×844. Tests cover dashboard, shared robot and AGV panels, AMR SLAM/Nav2 status, all sidebar destinations, task/history pages, map editor entry, light theme, major-panel overlap, page-level horizontal overflow, and browser console/page errors (none observed). All non-GET API requests are blocked; no mutation or robot command was attempted.
- Map modes actually tested: **fallback** (mock ROS map and selected map `null`; schematic, robot labels, restricted zone); **live** (mock occupancy grid and AMR pose/path canvas pixel); **saved** (mock selected map, planning editor, and calibrated AGV SVG marker). Saved↔live controls were exercised. Screenshots: 20 PNGs under `web/tests/screenshots/`, including all three map modes at every viewport and task/robot/map/history pages at desktop and mobile.
- Screenshot inspection found no missing major panel or unexpected overlap after allowing the mobile sidebar closing transition to finish. The narrow robot-detail tab row scrolls horizontally by design. No new visual defect was confirmed in the mocked states.
- Existing frontend Node tests: **17/17 passed** with `node --test --test-isolation=none`; `npm.cmd run build` passed; `git diff --check` passed. The first sandboxed Playwright attempt failed with worker spawn `EPERM`; the approved local rerun and final rerun passed.
- Unverified: real backend data, live WebSocket updates, map upload and save, robot commands, and physical map alignment. The confirmed fallback AGV-local-coordinate defect remains unchanged and requires separate approval to fix.

### Focused fallback AGV coordinate fix — completed after Phase 2 QA

- Root cause: `web/backend/app/api/routes/agv.py` stores AGV-local odometry in generic `RobotStatus.x/y`, while `features/map/layers/FallbackWarehouseMap.jsx` scaled those values directly into its fixed 12 m × 8 m schematic. The fallback has no map ID/hash to validate the saved-map A/B/D alignment against.
- Changed only `features/map/layers/{FallbackWarehouseMap.jsx,fallbackCoordinates.js,fallbackCoordinates.test.js}` and the relevant `web/tests/visual.spec.js` assertion. LINE markers are absent from fallback SVG; each LINE robot is listed as `POSITION_UNKNOWN / UNCALIBRATED`. AMR markers, saved-map alignment math, map controls, navigation, and motor logic were unchanged.
- Validation: frontend Node tests **18/18 passed**, Vite production build passed, `git diff --check` passed. Playwright fallback, live, and saved map cases **12/12 passed** across all four viewports. The first sandboxed Playwright attempt failed with worker spawn `EPERM`; the approved local rerun passed. The 390 px fallback screenshot shows the unknown-position note without an AGV marker.
- Remaining limits: tests use deterministic mock REST/WS data; real robot localization, map upload/save, and physical alignment were not exercised. Phase 3 was not started.

### Phase 3A backend dispatch design — completed, read-only

- Design and exact implementation gates: `docs/ai-handoff/phase3a-dispatch-design.md`. A focused backend agent traced `Task.robot_id` ownership, unconditional AMR Nav2 dispatch, AGV mailbox/ACK behavior, and process-local concurrency limits. No backend source or model was changed; no backend tests were run in this design phase.
- 3B proposal: guard task dispatch by DB robot type/capability before any Nav2 goal or state mutation, including post-pickup delivery dispatch; preserve AMR behavior and REST/WS contracts. 3C proposal: AGV station adapter only after verified mapping, completion evidence, and durable task-command correlation. AGV auto-task dispatch remains disabled meanwhile.
- Current blocker: `RobotCommand` only persists PAUSE/RESUME/CANCEL/SAFE_STOP, while M1–M4 commands are process-local and unlinked to Task. Existing process-local locks cannot prevent cross-worker duplicate dispatch. A future schema change, if necessary for durable correlation, needs separate approval under the model-preservation constraint.

### Phase 3B robot-type dispatch guards — completed

- Changed `web/backend/app/services/task_executor.py` and `web/backend/tests/test_smoke.py`; added `web/backend/tests/test_robot_dispatch.py`. A central DB lookup of `Task.robot_id` now requires an existing, active `AMR` before AMR navigation operations or callback-driven task mutations. Start, resume, pickup-proof delivery dispatch, pause, cancel, and completion reach this guard. No API route, model, AGV manual endpoint, frontend, ROS, or firmware file changed.
- LINE task start returns the existing HTTP 409 error shape before goal creation or task mutation; focused tests also cover LINE resume/proof-stage rejection, missing/inactive ownership, no goal/cancel/commit side effects, valid AMR start/cancel/complete, and wrong-robot/stale callback handling. AMR lifecycle and existing REST/WS behavior remain covered by the full suite.
- Backend agent ran focused tests **5/5 passed** and full Python 3.11 backend suite **47/47 passed**; `git diff --check` passed. Initial local runs hit environment-only Python/dependency/codepage/sandbox process-cleanup failures; final UTF-8 Python 3.11 runs passed. No physical hardware was used.
- Sequential reviewer found no new guard bypass or regression. Residual pre-existing compatibility paths: manual Task status PATCH can advance LINE without dispatch evidence, and generic RobotCommand ACK can affect pause/cancel flags. LINE Task cancel now returns 409 even when WAITING; a shared cancellation policy needs separate design. Process-local locks still do not prevent cross-worker duplicate dispatch.
- Phase 3C prerequisites remain: verified Task-location→AGV station mapping, durable task/robot/stage/command correlation across restarts, explicit arrival/stopped evidence, and separate approval. AGV automatic task dispatch remains disabled.

### Phase 3C AGV mission integration — stopped at Batch 3C.1

- Focused protocol audit confirmed that M1–M4 are fixed A→B→C→D→A legs, while the active map has no validated physical station binding. AGV telemetry lacks station/leg/task completion identity; `AT_STATION` and ACK cannot prove a particular task destination was reached. See `phase3c-agv-mission-gate.md` for source references, adapter contract, persistence and state requirements, and rollback.
- No backend source, database, route, firmware, ROS, or frontend file changed. Automatic AGV task dispatch remains disabled; the existing manual command flag is separate. Batches 3C.2–3C.5 were not started because their station and evidence prerequisites are unverified.
- Backend agent ran mocked `tests.test_agv_runtime` and `tests.test_robot_dispatch`: **13/13 passed**. Full backend regression was not run because no implementation batch passed the gate. Next action: verify the physical station/route and correlated arrival/stopped protocol, then review durable persistence and a default-off dispatch gate before resuming 3C.1.
- Independent reviewer confirmed the high-severity blocker and found no safe current-contract path to AGV automatic dispatch. Hardware behavior remains unverified.

### Revised Phase 3C Batch 3C.1R — data-only route planning completed

- Added `web/backend/app/services/agv_station_graph.py` and `web/backend/tests/test_agv_station_graph.py`; updated `phase3c-agv-mission-gate.md` and added `phase3c-revised-contracts.md`. Six required stations and optional junctions are validated against supplied map/robot IDs. Explicit directed edges and permitted junction transitions feed Dijkstra. No physical topology or firmware mapping is bundled, and no TaskExecutor, API, schema, firmware, ROS, or frontend file changed.
- Focused graph/AGV runtime/Phase 3B guard tests **24/24 passed**. Full backend suite **58/58 passed** on Python 3.11; `git diff --check` clean. Reviewer found an initial junction-turn sequence gap; repaired it with explicit transitions and incoming-edge search state, then reviewer confirmed no remaining concrete data-planner defect.
- Current gate: physical graph, markers, station/command-correlated arrival and stopped evidence, durable command persistence, and camera placement/cargo-presence capability remain unverified. Batches 3C.2–3C.5 are not started; automatic dispatch and automatic camera proof remain absent/disabled. Next action is physical and protocol verification, then reviewed schema/adapter work. No hardware was operated.

### Phase 3C.2–3C.5 offline backend work — mock implementation, open gates

- Added `app/models/{agv_mission,agv_cargo_evidence}.py`, `app/services/{agv_mission_store,agv_mission_adapter,agv_cargo_verifier}.py`, and `tests/test_agv_mission_store.py`; updated the graph and test to HOME/PICKUP/RACK_A–D; changed `app/api/routes/{tasks,commands,agv}.py`, `app/main.py`, and `init_db.py`. `phase3c-backend-implementation.md` records schema, state transitions, flags, REST/WS impact, rollback and hardware gates. Earlier 3B edits and user files were preserved.
- Three additive tables persist mission ownership, command intents and camera captures. File-backed SQLite tests cover one active mission per robot, concurrent claim, duplicate command, stale/wrong-robot callback and explicit offline restart quarantine. The adapter uses an injected mock graph/transport and never enters Nav2; the production singleton has no provider/transport. Device-token-protected mission callbacks require the separate default-off AGV dispatch gate. Camera auto-confirmation has its own default-off gate and no production analyzer.
- Mock lifecycle covers pickup, delivery, manual proofs, verified arrival, return HOME or PICKUP, cancellation and uncertain states. Reviewer findings led to two focused repair passes for duplicate send claims, source checks, return cancellation/handoff, post-commit failure semantics and callback publication. Final review found that midroute stop was wrongly coupled to target arrival; manager separated stopped evidence and added a regression test. Reviewer confirmed this fix. Stopped/marker evidence remains mock-only.
- Focused AGV graph/store/runtime/3B tests **53/53 passed** before the last fix; focused mission-store tests **29/29 passed** after. Full Python 3.11 backend suite **87/87 passed** after the fix; `git diff --check` clean. No robot, camera, firmware or ROS2 operation occurred.
- **At the Phase 3C checkpoint, V1 was incomplete:** existing Task creation required DELIVERY dropoff and derived pickup from the product rack, so classify-at-PICKUP → assign RACK_A–D lacked a public API and policy. Phase 3D adds a separate compatible LINE path below. Online multiworker restart reconciliation still has no safe lease/coordinator: offline recovery requires all workers stopped. Physical graph, authenticated station/stop evidence, device-side deduplication, camera placement and cargo-presence model remain unverified. Keep automatic dispatch/proof off. Phase 4 not started.

### Phase 3D vision-to-mission — offline mock workflow completed

- Added `app/models/agv_vision.py`, `app/services/agv_vision.py`, `tests/test_agv_vision.py`, and test-only `requirements-test.txt`; updated `app/api/routes/tasks.py`, `app/schemas/task.py`, `app/services/agv_mission_adapter.py`, `app/main.py`, and `init_db.py`. Three additive policy/job/capture tables preserve the existing Task columns. See `phase3d-vision-workflow.md` for exact API, policy, sentinel, rollback and remaining safety gates.
- New `POST /api/tasks/agv` creates a LINE task with durable unassigned rack state. TaskOut emits null dropoff fields until a reviewed capture assigns RACK_A–D; existing `POST /api/tasks` and AMR values remain unchanged. PICKUP capture requires verified arrival; explicit per-map class-to-rack policy has no defaults. Operator review assigns the rack on the same Task; only the subsequent operator PICKUP proof invokes the existing AGV adapter for one durable DELIVERY stage. Shape classification is separate from cargo-removal proof.
- Reviewer found a NaN confidence bypass and missing HTTP response-model coverage. Both were fixed and confirmed on re-review. `httpx` was installed locally for TestClient and added only to test requirements; production requirements did not change. Focused Phase 3D tests **8/8 passed** and full Python 3.11 backend tests **95/95 passed** with UTF-8 console encoding; `git diff --check` clean. No webcam, firmware, ROS2 or robot command was used.
- **Hardware remains blocked:** the production classifier is unconfigured, physical capture provenance/model reliability and station/stop evidence are unverified, no real graph/transport is installed, and online multiworker recovery still needs a coordinator. Keep AGV automatic dispatch and camera auto-proof off. Phase 4 was not started.

### Post-Phase-3 database repair and web smoke — completed

- Actual database: `web/backend/data/wrms.db` (default `WRMS_DATABASE_URL`; no override set). It held only eight saved-map/AGV tables because FastAPI lifespan creates those tables individually, while the core schema is created by `init_db.py`. Backed up first via SQLite backup API to `web/backend/data/wrms.db.backup-20261103-184436` (integrity `ok`); no backup was overwritten.
- Ran the existing `init_db.py` against that database, adding the 12 missing core tables without dropping or replacing any table. Invoked existing `seed_robots` and `seed_robot_status` only; `AMR-01` is `AMR`, `LINE-01` is `LINE`, with one row each. All eight preexisting tables retained their original row counts (zero). `PRAGMA foreign_key_check` returned no violations and `integrity_check` returned `ok`.
- Actual FastAPI `TestClient` startup and read-only GET smoke returned HTTP 200 for `/api/health`, `/api/robots` (2 robots), `/api/agv/LINE-01/state`, and `/api/tasks` (0 tasks). Registered routes include `POST /api/tasks/agv`, `POST /api/tasks/{task_id}/vision/captures`, and `POST /api/tasks/{task_id}/vision/review`. Focused `tests.test_agv_vision` + `tests.test_smoke`: **16/16 passed**. `git diff --check` clean. No application source changed; full backend regression was not repeated. Automatic AGV dispatch and camera proof remained off, and no physical command was issued.

### Phase 4A runtime integration readiness — checked; product-free task blocked

- `tasks.product_id` and `tasks.dropoff_location_id` are both `NOT NULL`. Phase 3D's `POST /api/tasks/agv` still requires `product_id`; a product-free request returns HTTP 422. The unassigned dropoff is stored as the PICKUP location until classification, then exposed as `null` by the response. Existing seeded products are required for the mock workflow. Making `product_id` truly optional needs a coordinated schema and API change; SQLite cannot relax this constraint with an additive `ALTER TABLE`. No table rebuild or placeholder product was applied to the live database.
- The live database has zero products, locations, selected maps, and tasks. The same-task classify/review/assign/delivery flow passed in two existing deterministic mock tests, but cannot be exercised against this live database until valid warehouse configuration exists. No real command was sent.
- Actual local Uvicorn startup and Vite `http://127.0.0.1:5173/` returned HTTP 200. Browser-origin GETs to `/api/health`, `/api/robots` (2), `/api/tasks` (0), and `/api/agv/LINE-01/state` all returned HTTP 200 with `Access-Control-Allow-Origin: http://127.0.0.1:5173`. `api.js` defaults to the page hostname on backend port 8000; Vite has no proxy and needs none for this local setup. The temporary Uvicorn process was stopped.
- Phase 4B blockers: decide and implement a data-preserving migration plus backward-compatible product-free task contract if product-free creation is required; configure real pickup/racks, selected map, products or revised inventory policy, class-to-rack policy, physical route graph, verified station/stop evidence, device deduplication and camera provenance. Hardware dispatch and camera auto-confirmation stay off. No frontend or backend source changed in 4A; no full backend suite or frontend build was required.

### Phase 4A.1 product-free LINE task — completed offline

- `Task.product_id` and `Task.dropoff_location_id` are nullable for pending LINE tasks. `POST /api/tasks/agv` accepts omitted `product_id` and stores both fields as SQL `NULL`; its list/detail responses expose null product and destination fields. The existing `POST /api/tasks` request schema still requires product and dropoff IDs, preserving AMR creation validation. The PICKUP-as-dropoff workaround was removed. AGV destination validation and operator review now use an explicit null destination; delivery stays blocked until the vision job has a reviewed rack assignment and verified pickup proof.
- `init_db.py` now performs an idempotent SQLite migration before `create_all`: it copies the existing `tasks` schema with only the two `NOT NULL` constraints relaxed, preserving rows, checks, FKs, explicit indexes and triggers within a transaction. It writes a unique SQLite backup first. Applied to `web/backend/data/wrms.db`; backup: `web/backend/data/wrms.db.backup-20261103-193141-629992` (integrity `ok`). Live tasks remained at 0 rows, task indexes remained present, both columns are nullable, `PRAGMA foreign_key_check` returned no violations, and `integrity_check` returned `ok`. Rollback: stop the backend and restore this backup after preserving any subsequent writes separately; restoring it directly would discard those writes.
- Focused file-backed SQLite migration and AGV API/workflow tests **9/9 passed**. The same-task mock flow creates with null product/dropoff, verifies pickup, classifies, reviews, assigns RACK_A, and dispatches delivery once; AMR request validation remains strict. Full backend regression **96/96 passed**. `git diff --check` clean. No physical commands, frontend, firmware or ROS2 changes. AGV automatic hardware dispatch and camera auto-confirmation remain disabled.
- Remaining Phase 4B blockers: live warehouse still lacks pickup/rack locations, selected map and class-to-rack policy; physical route graph, station/stop evidence, device command deduplication and camera provenance remain unverified. Product-free LINE tasks intentionally have null product fields after classification until a separate product identity/inventory policy is defined.

### Phase 4B.1/4B.2 Dashboard UI clarification — frontend integration completed, hardware unverified

- The existing Dashboard LINE robot card now contains the existing AGV telemetry content in a collapsible details section; the former standalone Dashboard placement was removed. Existing command controls, robot selection, navigation, Missions, Tasks, AMR and Nav2 components remain in place. The LINE card uses the AGV state endpoint's live connection flag and does not show cached battery, voltage, location, or stale telemetry as verified measurements.
- A user-started browser-local USB camera preview is available in the Dashboard LINE details and the existing Robot camera tab. It supports camera selection and releases the stream on stop or navigation. It does not capture evidence or enable automatic camera proof. A USB camera attached to a different backend host is not reachable through this browser-only preview; actual webcam placement and video quality remain unverified.
- Changed frontend files: `src/App.jsx`, `src/features/robots/shared/RobotStatus.jsx`, `src/features/robots/shared/Robots.jsx`, `src/features/robots/agv/AgvTelemetryPanel.jsx`, new `src/features/robots/agv/UsbCameraPreview.jsx`, `src/styles/dashboard.css`, and `tests/visual.spec.js`. Node frontend tests **18/18 passed**, Playwright Chromium visual tests **15/15 passed** across the existing four viewports, production build passed, and `git diff --check` passed. Camera playback and cleanup were tested with a browser mock; no real webcam, ESP32, or robot command was used.

### Dashboard cleanup and Robot Management details — frontend implemented

- Dashboard cards now show compact mission/destination/verified-position/task/ETA information and link to the existing Robot Management page. URL query parameters select a robot and support direct links and browser Back/Forward; invalid robot codes show not-found. LINE hardware content moved to the existing Overview, Telemetry, Camera, and Diagnostics tabs; AMR navigation/sensor tabs remain. One AGV state poll/subscription belongs to the active Robot page. Camera mounts only on its tab. Missing RPM, voltage, battery and raw IMU display `N/A`; AGV odometry remains explicitly local. Dashboard AMR position requires a fresh `map`-frame pose and good localization; LINE has no verified warehouse pose.
- Hardware/protocol facts and Windows startup instructions are in `agv-hardware-integration.md`. Visual tests cover Dashboard links, sidebar selection, Back/Forward, direct/invalid URLs, stale LINE telemetry and camera cleanup. Actual ESP32 and USB webcam behavior remains unverified; no hardware commands or backend changes were made.
- Validation: frontend Node tests **18/18 passed**, Chromium visual tests **17/17 passed** across the existing four viewports, production build passed, and `git diff --check` passed. No backend, firmware, ROS2, database or physical hardware operation was performed.
