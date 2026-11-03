# Phase 3C AGV mission integration: station gate

Status: **historical 3C.1 safety audit**. Revised Batch 3C.1R adds a data-only planner; see `phase3c-revised-contracts.md`. No automatic AGV mission dispatch is implemented. This is a source and protocol audit, not a hardware validation. The existing AMR TaskExecutor and AGV manual endpoints remain unchanged.

## Verified contracts and missing mapping

| Source | Verified behavior | Consequence |
|---|---|---|
| `firmware/esp32_s3/agv_line_controller/agv_line_controller.ino` (`startMission`, M1–M4 handling) | M1–M4 select fixed legs A→B, B→C, C→D, D→A. A leg can be started without a verified physical starting station. | A WRMS destination named HOME, PICKUP, or DELIVERY cannot safely be converted to an M command by name or map coordinates. |
| Same firmware (telemetry, `AT_STATION`) | Telemetry has AGV-local pose, state, and `ack_id`; `AT_STATION` follows a leg-distance stop. It has no station, leg, task, or command-completion identity. | ACK proves receipt only. `AT_STATION` alone cannot prove arrival at the requested task station, or correlate it to a particular command after restart/retry. |
| `web/backend/app/models/{location,planning_layer}.py` | Locations have type and map coordinates; planning objects belong to a saved map. Neither defines a verified physical A/B/C/D binding for the active map and robot. | No validated Task location→AGV station/route lookup exists. AGV-local odometry cannot substitute for a ROS map pose. |
| `web/backend/app/services/agv_runtime.py` | Command IDs and pending/ACK status live in a per-process mailbox; ACK clears the pending command. | Task/robot/stage/command ownership and restart recovery are not durable; cross-worker starts cannot be made safe with this mailbox alone. |
| `web/backend/app/models/robot_command.py` | Persisted commands are constrained to PAUSE, RESUME, CANCEL, SAFE_STOP. | M1–M4 cannot be persisted there without a designed schema change. |
| `web/backend/app/api/routes/agv.py` | Manual `mission` command accepts M1–M4 behind `WRMS_AGV_ENABLE_COMMANDS=1`; telemetry and manual endpoints do not link commands to a Task. | Manual control contract is preserved. This flag is **not** an automatic task-dispatch flag. |

## Adapter and state contract for a future implementation

No adapter was added. The minimal boundary remains `validate_stage(owner, task, stage, destination)`, `dispatch_stage(...) -> durable receipt`, and `request_cancel(...) -> stop receipt`. Select by DB-loaded `Task.robot_id` and `Robot.robot_type`; preserve the AMR Nav2 path. An AGV target must be a verified physical station/route on a selected map, never raw map coordinates or local odometry.

Persist a unique command ID with robot ID, task ID, stage, target station/route, issue and ACK timestamps, status, completion evidence, and error details. Claim one active mission per robot transactionally before dispatch. Reconcile uncertain commands after restart without blind resend. These are requirements, **not implemented behavior**; the current schema needs a reviewed, backward-compatible persistence design and rollback before a migration.

Keep command requested, server accepted, device ACK, executing, arrival verified, operator proof, and stage completed separate. Only command-correlated arrival evidence may advance the matching task/stage; pickup and delivery still require operator proof. A stop request or ACK alone cannot establish stopped state. Timeout, disconnect, duplicate callbacks, stale IDs, and cancellation must leave uncertain motion unresolved and block further stages until reconciliation.

## Gate, validation, and rollback

Before resuming 3C.1, obtain and verify per-robot, per-active-map physical station identities for at least HOME/PICKUP/DELIVERY where present, supported directed routes from the robot's verified current station, and an arrival/stopped signal that identifies the command and station. Verify these against the actual firmware/protocol and on safe bench hardware before enabling automation. Then design durable command persistence, concurrency and restart reconciliation, and a separate `false`-by-default automatic dispatch flag. The existing `WRMS_AGV_ENABLE_COMMANDS` controls manual commands only.

No production source, database schema, API, WebSocket event, firmware, or ROS package was changed in this batch. Focused mocked backend tests `tests.test_agv_runtime` and `tests.test_robot_dispatch` passed **13/13**. Later 3C batches and the full backend suite were not run because this first safety gate failed. Rollback is unnecessary for source and schema; keep automatic dispatch disabled and the Phase 3B AMR guard in place.

Independent reviewer confirmed the high-severity gate from the firmware telemetry and command handling, map models, and mailbox. No source regression was introduced or reviewed because there was no production edit; physical behavior was not tested.
