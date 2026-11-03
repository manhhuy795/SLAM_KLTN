# Incremental migration plan

Phase 2 was approved and implemented on the current branch. All paths are under `web/src/`. This table records the implemented destinations and the remaining fallback-coordinate decision. Preserve component props, REST/WS contracts, class names, light theme, and map editing behavior.

## Exact Phase 2 path mapping

| Old path | Proposed new path / extraction |
|---|---|
| `App.jsx` | Remains; update feature imports only. |
| `UI/Header.jsx`, `UI/Sidebar.jsx` | `shared/ui/{Header,Sidebar}.jsx` |
| `UI/DashboardSidePanel.jsx`, `UI/ActiveTasks.jsx` | `features/dashboard/{DashboardSidePanel,ActiveTasks}.jsx` |
| `UI/RobotStatus.jsx`, `UI/Robots.jsx` | `features/robots/shared/{RobotStatus,Robots}.jsx` |
| `UI/NavigationPanel.jsx`, `UI/SavedMapNavigation.jsx` | `features/robots/amr/{NavigationPanel,SavedMapNavigation}.jsx` |
| `UI/AgvTelemetryPanel.jsx` | `features/robots/agv/AgvTelemetryPanel.jsx` |
| `UI/WarehouseMap.jsx` | `features/map/WarehouseMap.jsx`; extract `layers/FallbackWarehouseMap.jsx`, `RestrictedZones.jsx`, `LocationsLayer.jsx`, and robot visualization layers. The fallback name identifies the isolated raw-status path pending coordinate approval. |
| `UI/SlamMap.jsx` | `features/map/layers/SlamMap.jsx` wrapper, `BaseOccupancyMap.jsx` canvas, and `AmrMapLayer.js` for pose, goal, and path drawing. |
| `UI/MapEditor.jsx`, `UI/MapProducts.jsx`, `UI/SavedMapControls.jsx` | `features/map/{MapEditor,MapProducts,SavedMapControls}.jsx`; extract `layers/AgvMapLayer.jsx` from editor overlay. `SavedMapControls` already serves as map controls, so no wrapper is needed. |
| `UI/Tasks.jsx`, `UI/Alerts.jsx`, `UI/History.jsx` | `features/{missions/Tasks,alerts/Alerts,history/History}.jsx` |
| `services/agv.js`, `services/agvAlignment.js` and `agvAlignment.test.js` | `features/robots/agv/` with same filenames. Robot code is an optional input with current `LINE-01` default. |
| `services/rosStatus.js` and `rosStatus.test.js` | `features/robots/amr/` with same filenames. |
| `services/slamMap.js` and `slamMap.test.js` | `features/map/transforms/` with same filenames; keep conversion functions unchanged. |
| `services/{savedMap,planning}.js` and their matching `*.test.js` | `features/map/` with same filenames initially. |
| `services/{api,realtime,safeStop,safeStop.test}.js`; `styles/{dashboard,responsive}.css`; `main.jsx` | Remain shared and in place. Review imports/selectors; edit only if required. |

## Batches and gates

1. Move shell, dashboard, missions, alerts, history, and robot pages; update `App.jsx` imports. Build and run existing service tests. Avoid simultaneous edits to `App.jsx`.
2. Move shared map services and their tests, keeping exports and coordinate functions unchanged. Run `slamMap`, `savedMap`, and `planning` tests.
3. Move AMR and AGV UI/services into their boundaries. Parameterize AGV code at the UI/API boundary with compatibility default. Run `rosStatus` and `agvAlignment` tests; verify no AMR/AGV internal cross-imports.
4. Before extracting fallback markers, write a focused check for local AGV coordinates versus shared-map placement. Keep the finding unresolved until behavior is verified. Then split base map, restricted zones, locations, and robot layers; test live, saved, and fallback views. Preserve map identity, ROS frame checks, and editing prompts.
5. Run `npm.cmd run build` and all existing `node --test` frontend service tests; inspect the final diff and light theme. No live robot commands.

The `layers/` and `transforms/` subdirectories refine the Phase 1 path proposal to match the approved Phase 2 target tree. They contain actual rendering and coordinate files, not placeholders.
`App.jsx` remains the app entry/shell at its current path; creating an otherwise empty `app/` directory would add no boundary.

## Compatibility and rollback

- Keep `App` page keys, `WarehouseMap` callers (`App` and `MapProducts`), component props, API endpoints, WebSocket event names, localStorage alignment key, map metadata, and planning revision behavior.
- Retain each batch as a small reviewable diff. If a batch fails, reverse only that batch's path moves/import updates; do not reset the branch or discard user files. Source control operations require preserving the current untracked `AGENTS.md` and `.codex/`.

## Later phase boundaries

- Phase 3, after approval: shared task lifecycle and robot-specific dispatch in FastAPI; keep routes/schema/database stable. Add ownership, AMR/AGV lifecycle, ACK, and contract regression tests. Do not modify firmware or ROS packages.
- Phase 4: production build, frontend and backend tests, import-boundary checks, AMR/AGV integration-path review, diff inspection, independent reviewer analysis, and an honest report of any unavailable checks. Do not deploy or operate hardware.
