# Phase 3C revised AGV contracts and safety gate

Status: **historical 3C.1R design snapshot; see `phase3c-backend-implementation.md` for current mock-only work.** The latest station names are HOME, PICKUP, and RACK_A–D. M1–M4 remain manual test commands, not a final station topology. No physical graph or automatic hardware dispatch is installed.

## Verified and unverified

- Verified in source: FastAPI AGV telemetry/manual command endpoint uses HTTP and `robot_code`; the current firmware sends encoder/local pose, IMU-derived yaw, line data, `state`, and `ack_id`. Its M1–M4 legs are test behavior. A manual `STOP` string exists, but a task-correlated CANCEL, stopped acknowledgement, and restart-safe stop protocol are **unverified**. Phase 3B keeps LINE tasks out of AMR Nav2.
- Clarified requirement, not hardware-verified: physical destinations HOME, PICKUP, RACK_A–D; one product per mission; classification at PICKUP by MobileNetV3-Small into cylinder, rectangular_box, triangular_prism; cargo removal at the rack; next PICKUP or HOME after delivery. No class-to-rack assignment, physical graph, station markers, or validated camera view was supplied.
- Targeted inspection of `web/backend/app` and `scripts` found no camera, MobileNet, or cargo-presence integration. Camera placement and model reliability remain unverified; classification is never proof of removal.

## 3C.1R station graph

`web/backend/app/services/agv_station_graph.py` exports `validate_station_graph` and `plan_station_route`; both are pure data operations. Input is a supplied graph with `map_id`, `robot_id`, required station nodes, optional junction nodes, directed edges, and `junction_transitions`. Every edge names source, destination, `FORWARD` direction, finite positive cost, abstract `STRAIGHT|LEFT|RIGHT` action, and optional verification marker. A junction transition explicitly permits an incoming source → junction → outgoing destination with the matching action. Dijkstra uses incoming-node state, so an undeclared turn is not routed. Unknown nodes, missing edges, invalid actions/transitions, unreachable destinations, and supplied map/robot mismatches fail closed.

The graph has **no default edges**. Test fixtures contain synthetic edges only. `FORWARD` and turn tokens are planning labels, not firmware commands. The supplied IDs have not been checked against an active database map or robot; that belongs at a future integration boundary. A physical survey must verify edges, junction transitions, markers, and route costs for each map and robot before a route can be dispatched.

## Proposed HTTP command and evidence contract (not implemented)

- Durable command: `command_id`, `task_id`, `robot_id`, `mission_stage`, `source_station`, `target_station`, `route_id`, ordered `route_steps`, monotonic `command_sequence`, `issued_at`, and status `REQUESTED|ACCEPTED|ACKNOWLEDGED|EXECUTING|ARRIVED|STOPPED|FAILED|CANCELLED|UNKNOWN`.
- Telemetry/event: `command_id`, `robot_id`, current/expected station, execution state, encoder and IMU samples, junction event with marker identity, arrival evidence, stopped evidence, and timestamp. Verify device identity, command sequence, target, marker and stopped state together before ARRIVED. ACK is receipt only. Reject duplicate, stale, wrong-robot, wrong-stage, and out-of-order events.
- Persistence design: a dedicated AGV command-intent record linked to Task and Robot, with immutable target/route identity, unique command ID and robot sequence, timestamps, evidence/error fields, and a database-enforced one-active-mission-per-robot claim. Reconcile uncertain commands after restart; never blindly resend. `RobotCommand` currently constrains command values to PAUSE/RESUME/CANCEL/SAFE_STOP and cannot simply carry route steps. Schema, indexes, transactional claim, and reversible migration need review before implementation; no migration was made.
- Firmware work required: parse ordered route steps and command IDs; persist or reconcile the last accepted sequence; report current station and junction/marker identity; correlate ACK, arrival and STOP/CANCEL to command ID; emit verified stopped state; reject duplicate/stale commands across reconnects. Preserve motor, line-following, encoder, IMU and manual test behavior. Physical station detection may need markers or sensors; encoder distance alone is insufficient. Nothing was flashed or driven.

## Mission, cancellation, and camera boundaries

Future AGV adapter: validate DB Task owner/type and active map/graph, then claim a durable command before sending. Shared Task states remain WAITING → MOVING_TO_PICKUP → ARRIVED_AT_PICKUP → PICKUP_CONFIRMED → TRANSPORTING → ARRIVED_AT_DELIVERY → DELIVERY_CONFIRMED → COMPLETED. At PICKUP, classification and operator proof must be separate from motion evidence. At a rack, verified arrival and stop precede cargo-presence assessment. Return to PICKUP for a valid pending mission or HOME otherwise, each via its own correlated command and verified arrival; a queue entry alone says nothing about physical cargo. AMR stays on its existing Nav2 path.

Cancellation must block later stages immediately, request a device-correlated stop when supported, and remain UNKNOWN until stopped evidence arrives. Disconnect, timeout, stale ACK, restart, or camera uncertainty cannot complete a task or authorize retry without reconciliation. The current manual STOP command is not sufficient proof of cancellation.

Future camera interface: a cargo-area observation tied to robot, task, delivery command, station, timestamp, and image/evidence reference returns `PRESENT|ABSENT|UNCERTAIN` plus confidence and provenance. `PRESENT` waits; `UNCERTAIN` requires manual review; `ABSENT` may support proof only after physical camera placement and model validation, verified rack arrival/stop, and a separate default-off automatic proof gate. MobileNet shape class never establishes absence. No camera interface or mock tests were added because camera placement/capability is not verified.

Keep automatic dispatch and camera proof behind **separate default-off gates** when those code paths are implemented; do not reuse `WRMS_AGV_ENABLE_COMMANDS`, which controls manual AGV commands. No automatic path or gate was added in this batch. Existing REST, WebSocket, AMR, and AGV manual contracts are unchanged. Rollback of this batch is removal of the standalone planner and tests only; no schema or runtime state changed.

## Validation and next gate

Focused graph, AGV runtime and Phase 3B guard tests: **24/24 passed**. Full backend suite: **58/58 passed**. Independent reviewer found and then verified repair of a junction-sequence gap. No hardware tests were run. Batches 3C.2–3C.5 are blocked pending a physically verified graph and station/marker evidence, command-correlated arrival and stop, reviewed durable command schema/concurrency protocol, and camera placement/cargo-presence validation. Do not enable automation based on mock tests.
