# Phase 3A — backend dispatch design

Status: **design complete; no backend implementation approved**. Source paths are under `web/backend/app/`. This design preserves current database models, REST paths/payloads, WebSocket event names, and AMR navigation behavior.

## A. Current flow and ownership

1. `models/task.py` stores nullable `Task.robot_id` as the owning robot FK. `models/robot.py` stores unique `robot_code` and constrained `robot_type` (`AMR` or `LINE`). `api/routes/tasks.py:207-347` checks that an assigned robot exists and is active, but does not validate navigation capability.
2. `PATCH /tasks/{id}/start` calls `TaskExecutor.start_pickup` for either type (`tasks.py:352-375`). Pickup proof calls `start_delivery` (`tasks.py:897-908`); pause/resume/cancel also call `TaskExecutor` (`tasks.py:411,494,577`). `services/task_executor.py:207-243` requires ROS bridge, Nav2, localization/TF, and a ROS pose whose `robot_id` equals the task owner for stage starts, but it has no type check. Thus LINE tasks can be assigned but cannot safely execute through this path. The executor's pause, cancel, and completion paths also consult Nav2 state; they must not route a LINE task to Nav2.
3. AMR dispatch builds a ROS `map` frame goal with task/robot metadata (`task_executor.py:257-277`, `services/navigation.py:31-66`). The Nav2 callback checks task ID, stage, robot ID, and location before arrival/failure (`task_executor.py:153-205`). Pickup and delivery proofs gate progression/completion.
4. `api/routes/agv.py` resolves `/{robot_code}` to a `LINE` robot, authenticates device telemetry, and updates generic status with **AGV-local** x/y/yaw. `services/agv_runtime.py` has a per-code in-memory command mailbox, 2.5 s online window, 15 s pending ACK window, and no Task link. M1–M4/manual commands are not derived from Task locations. ACK clears the pending mailbox command; it does not prove arrival.
5. Generic `models/robot_command.py` persists only PAUSE/RESUME/CANCEL/SAFE_STOP with PENDING/ACKNOWLEDGED/FAILED. `api/routes/commands.py` checks robot/task ownership, but its ACK path can change pause/cancel flags. It cannot persist an AGV M1–M4 task-stage command under the current constraint.

## B. Minimal adapter boundary

Use an adapter selected **only** from the DB-loaded `Robot.robot_type` after checking `Task.robot_id == Robot.id`. Keep shared lifecycle and response broadcasting in `TaskExecutor`/routes. The smallest contract needed once both robots can dispatch is:

```text
validate_stage(robot, task, stage, destination) -> validated robot-specific target or error
dispatch_stage(robot, task, stage, target) -> correlation receipt or error
request_cancel(robot, task, active_receipt) -> stop/cancel request receipt or error
```

The target and receipt are robot-specific; no common low-level goal shape. AMR targets remain ROS map-frame goals. AGV targets must be verified station/route identifiers, never raw ROS x/y or local odometry. A dispatch receipt means **accepted for delivery**, not movement or completion. Keep callback/telemetry correlation in robot-specific handlers, not a generic ACK-to-task transition. Do not add a protocol class before both implementations actually need it; Phase 3B can start with the safety guard.

## C–E. Execution and states

| Layer | AMR | AGV |
|---|---|---|
| Capability check | Active AMR owner; destination valid in ROS map; bridge/Nav2/localization/TF and matching robot pose available. | Active LINE owner; verified Task location→station/route mapping, device online, commands enabled, route supported, durable correlation and completion evidence available. Otherwise reject before task mutation. |
| Request/accept | Task start validates and queues a Nav2 goal, preserving current response/WS behavior. | Future task start records a unique task/robot/stage command intent, then queues a station command; disabled until prerequisites below are met. |
| Acknowledged/executing | Nav2 accepts goal, then reports navigation state. | Firmware ACK proves receipt only; correlated telemetry must establish movement. |
| Navigation completed | Matching Nav2 SUCCEEDED callback marks arrival. | Matching station-arrival evidence, not `ack_id`, marks arrival. Exact predicate must be verified against the device protocol. |
| Mission completed | Delivery proof confirmation progresses to `COMPLETED` as today. | Delivery proof confirmation progresses to `COMPLETED` only after verified arrival. |

Shared `Task.status` remains WAITING → MOVING_TO_PICKUP → ARRIVED_AT_PICKUP → PICKUP_CONFIRMED → TRANSPORTING → ARRIVED_AT_DELIVERY → DELIVERY_CONFIRMED → COMPLETED, plus FAILED/CANCELLED. Keep AMR Nav2 states (IDLE/SENDING/NAVIGATING/SUCCEEDED/FAILED/REJECTED/CANCELLED), AGV mailbox states (NONE/PENDING/ACKNOWLEDGED/TIMEOUT), and AGV telemetry state separate from Task status. Requested, server-accepted, device-acknowledged, executing, arrived, and mission-completed are distinct facts. Existing manual Task status PATCH remains a compatibility path; it is not dispatch evidence.

## Policies and safety gates

- **Wrong robot:** resolve the owner by `Task.robot_id`; validate active DB robot and type; scope every AGV code/command and callback to the same robot ID, task ID, stage, and command correlation. Reject stale/mismatched callbacks. UI labels never select dispatch.
- **Duplicate start:** make a conditional DB claim of the expected Task state and check one active mission per robot in the same transaction. Existing process-local locks/query guards (`task_executor.py:26-30,246-255`) are insufficient across workers. Do not promise exactly-once physical dispatch without a durable command intent and reconciliation; a single-worker deployment is only a temporary operational constraint.
- **Timeout/disconnect:** preserve AMR handling. For AGV, current 15 s ACK timeout or 2.5 s telemetry offline means execution is **uncertain**, not safely failed or complete. Hold the prior shared Task state, record the uncertainty, and block another stage until robot state is reconciled.
- **Cancel/retry/recovery:** a cancel request blocks new dispatch. AGV stop request/ACK is not proof of stop; require correlated stopped/cancelled evidence before terminal CANCELLED. Preserve existing AMR cancel semantics. Never blindly repeat motion after timeout, disconnect, or restart. Recover from durable task/command state plus device telemetry; if evidence is missing, require operator reconciliation before retry. Use measured route-specific deadlines only after the station protocol is verified.

## F–I. Implementation gates, files, tests, rollback

| Increment | Source scope | Gate and tests |
|---|---|---|
| **3B: safe AMR dispatch boundary** | `services/task_executor.py`; `api/routes/tasks.py` only if error mapping needs adjustment. No model/route shape changes. Introduce an AMR adapter module only if moving existing Nav2 calls actually simplifies the boundary. | Reject LINE/unsupported capabilities with existing 409 response **before** stage start/resume or other Nav2 mutation, including delivery proof dispatch; define shared cancel of an unstarted LINE task separately. Audit pause/cancel/completion and generic `RobotCommand` creation so a LINE task cannot issue an AMR navigation operation. Preserve AMR timing, events, and responses. Extend `tests/test_navigation.py`, `test_smoke.py`; add focused `test_robot_dispatch.py` for wrong type, owner/pose mismatch, stale callback, and duplicate start. |
| **3C: AGV mission dispatch, separately approved** | `services/agv_runtime.py`, `api/routes/agv.py`, shared dispatch boundary, robot-specific adapter/handler, and focused tests. `RobotCommand` currently cannot represent M1–M4; do not overload its constrained command field. | First verify location→station/route mapping, arrival/stopped evidence, and a durable task/robot/stage/command correlation mechanism that survives restart and prevents duplicate execution. If that needs a schema change, seek a separate design approval; the current model-preservation rule takes precedence. Test offline, timeout, ACK≠arrival, cancel/stop, recovery, ownership, and concurrent starts in `test_agv_runtime.py` and dispatch tests. Keep AGV task dispatch disabled by default until all gates pass. |

Rollback: leave existing AGV telemetry/manual-command APIs intact and keep AGV mission dispatch off. Revert a failed 3B adapter/routing batch selectively while preserving the working tree and existing AMR route contract; no database migration is planned for 3B. A future 3C release needs a separate AGV dispatch gate so it can be disabled without affecting AMR. Do not modify firmware, ROS packages, navigation algorithms, or physical hardware.

**Open design blocker:** Task destinations are ROS map locations; no verified station mapping, durable M1–M4 Task correlation, or AGV arrival predicate exists today. AGV automatic Task dispatch cannot be safely implemented under the current evidence and model constraints.
