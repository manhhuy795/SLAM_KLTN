import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND_DIR = Path(__file__).resolve().parents[1]


class WrmsSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "smoke.db"
        cls.env = os.environ.copy()
        cls.env["WRMS_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        cls.env["PYTHONPATH"] = str(BACKEND_DIR)
        cls.env["PYTHONIOENCODING"] = "utf-8"
        cls.env["WRMS_CORS_ORIGINS"] = " http://192.168.56.10:5173, http://127.0.0.1:15173 "

        for script in ("init_db.py", "seed.py"):
            subprocess.run(
                [sys.executable, script],
                cwd=BACKEND_DIR,
                env=cls.env,
                check=True,
                stdout=subprocess.DEVNULL,
            )

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]

        cls.base_url = f"http://127.0.0.1:{cls.port}/api"
        cls.ws_url = f"ws://127.0.0.1:{cls.port}/ws"
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--log-level",
                "error",
            ],
            cwd=BACKEND_DIR,
            env=cls.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                status, _ = cls.request("/health")
                if status == 200:
                    return
            except Exception:
                time.sleep(0.1)

        cls.server.terminate()
        raise RuntimeError("Backend did not start")

    def test_configured_browser_origins(self):
        for origin in ["http://192.168.56.10:5173", "http://127.0.0.1:15173",
                       "http://localhost:5173"]:
            request = Request(self.base_url + "/health", method="OPTIONS",
                              headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
        request = Request(self.base_url + "/health", method="OPTIONS",
                          headers={"Origin": "https://not-allowed.example",
                                   "Access-Control-Request-Method": "GET"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 400)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None) is not None:
            if os.name == "nt":
                # The Windows venv launcher has a child holding SQLite open.
                subprocess.run(
                    ["taskkill", "/PID", str(cls.server.pid), "/T", "/F"],
                    check=True, stdout=subprocess.DEVNULL,
                )
            else:
                cls.server.terminate()
            cls.server.wait(timeout=5)
        cls.temp_dir.cleanup()

    @classmethod
    def request(cls, path, method="GET", body=None):
        payload = None
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{cls.base_url}{path}",
            data=payload,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except HTTPError as error:
            raw = error.read()
            return error.code, json.loads(raw) if raw else None

    def test_smoke_end_to_end(self):
        status, locations = self.request("/locations")
        self.assertEqual(status, 200)
        rack = next(item for item in locations if item["location_type"] == "RACK")
        delivery = next(
            item for item in locations if item["location_type"] == "DELIVERY"
        )

        status, location = self.request(
            "/locations",
            "POST",
            {
                "code": "SMOKE-RACK",
                "name": "Smoke rack",
                "location_type": "RACK",
                "x": 10,
                "y": 10,
                "yaw": 0,
            },
        )
        self.assertEqual(status, 201)
        status, updated_location = self.request(
            f"/locations/{location['id']}",
            "PATCH",
            {"name": "Smoke rack updated"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_location["name"], "Smoke rack updated")
        status, _ = self.request(
            f"/locations/{location['id']}",
            "DELETE",
        )
        self.assertEqual(status, 204)

        status, deleted_product = self.request(
            "/products",
            "POST",
            {
                "product_code": "SMOKE-DELETE",
                "name": "Delete me",
                "default_rack_id": rack["id"],
            },
        )
        self.assertEqual(status, 201)
        status, _ = self.request(
            f"/products/{deleted_product['id']}",
            "PATCH",
            {"name": "Updated product", "default_rack_id": rack["id"]},
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            f"/products/{deleted_product['id']}",
            "GET",
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            f"/products/{deleted_product['id']}",
            "DELETE",
        )
        self.assertEqual(status, 204)

        status, product = self.request(
            "/products",
            "POST",
            {
                "product_code": "SMOKE-TASK",
                "name": "Smoke task product",
                "default_rack_id": rack["id"],
            },
        )
        self.assertEqual(status, 201)
        status, product = self.request(
            f"/products/{product['id']}",
            "PATCH",
            {"default_rack_id": rack["id"]},
        )
        self.assertEqual(status, 200)

        status, robots = self.request("/robots")
        self.assertEqual(status, 200)
        robot = robots[0]
        status, _ = self.request(
            f"/robots/{robot['id']}/status",
            "PATCH",
            {"battery_percent": -1},
        )
        self.assertEqual(status, 422)
        status, _ = self.request(
            f"/robots/{robot['id']}/status",
            "PATCH",
            {"line_segment_id": 999999},
        )
        self.assertEqual(status, 404)
        status, robot = self.request(
            f"/robots/{robot['id']}/status",
            "PATCH",
            {"online": True, "state": "IDLE", "battery_percent": 80},
        )
        self.assertEqual(status, 200)
        self.assertTrue(robot["status"]["online"])

        status, operators = self.request("/operators")
        self.assertEqual(status, 200)
        operator_id = operators[0]["id"]

        status, task = self.request(
            "/tasks",
            "POST",
            {
                "product_id": product["id"],
                "dropoff_location_id": delivery["id"],
                "robot_id": robot["id"],
            },
        )
        self.assertEqual(status, 201)
        task_code = task["task_code"]

        status, _ = self.request(
            f"/tasks/{task['id']}/status",
            "PATCH",
            {"status": "ARRIVED_AT_PICKUP"},
        )
        self.assertEqual(status, 400)

        for next_status in ("MOVING_TO_PICKUP", "ARRIVED_AT_PICKUP"):
            status, task = self.request(
                f"/tasks/{task['id']}/status",
                "PATCH",
                {"status": next_status},
            )
            self.assertEqual(status, 200)

        status, _ = self.request(
            f"/tasks/{task['id']}/proofs",
            "POST",
            {
                "proof_type": "PICKUP",
                "image_path": "/proofs/smoke-pickup.jpg",
                "verification_status": "PENDING",
            },
        )
        self.assertEqual(status, 201)

        for next_status in (
            "PICKUP_CONFIRMED",
            "TRANSPORTING",
            "ARRIVED_AT_DELIVERY",
        ):
            status, task = self.request(
                f"/tasks/{task['id']}/status",
                "PATCH",
                {"status": next_status},
            )
            self.assertEqual(status, 200)

        status, _ = self.request(
            f"/tasks/{task['id']}/proofs",
            "POST",
            {
                "proof_type": "DELIVERY",
                "image_path": "/proofs/smoke-delivery.jpg",
                "verification_status": "PENDING",
            },
        )
        self.assertEqual(status, 201)

        status, task = self.request(
            f"/tasks/{task['id']}/status",
            "PATCH",
            {"status": "DELIVERY_CONFIRMED"},
        )
        self.assertEqual(status, 200)

        status, task = self.request(
            f"/tasks/{task['id']}/status",
            "PATCH",
            {"status": "COMPLETED"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["progress"], 100)

        status, proofs = self.request(f"/tasks/{task['id']}/proofs")
        self.assertEqual(status, 200)
        self.assertEqual(len(proofs), 2)

        status, _ = self.request(
            "/alerts",
            "POST",
            {
                "robot_id": robot["id"],
                "alert_type": "SMOKE",
                "severity": "WARNING",
                "message": "Smoke warning",
                "group_key": "SMOKE-WARNING",
            },
        )
        self.assertEqual(status, 201)
        status, alert = self.request(
            "/alerts",
            "POST",
            {
                "robot_id": robot["id"],
                "alert_type": "SMOKE",
                "severity": "WARNING",
                "message": "Smoke warning repeated",
                "group_key": "SMOKE-WARNING",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(alert["occurrence_count"], 2)
        status, alert = self.request(
            f"/alerts/{alert['id']}/acknowledge",
            "PATCH",
            {"operator_id": operator_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(alert["status"], "ACKNOWLEDGED")
        status, alert = self.request(
            f"/alerts/{alert['id']}/resolve",
            "PATCH",
            {"operator_id": operator_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(alert["status"], "RESOLVED")

        query = urlencode({
            "robot_id": robot["id"],
            "task_id": task["id"],
            "event_type": "TASK_COMPLETED",
            "created_from": "2000-01-01T00:00:00",
            "created_to": "2100-01-01T00:00:00",
        })
        status, history = self.request(f"/history?{query}")
        self.assertEqual(status, 200)
        self.assertTrue(history)
        self.assertTrue(all(item["task_code"] == task_code for item in history))
        self.assertTrue(all(item["robot_code"] == robot["robot_code"] for item in history))

        status, _ = self.request(
            f"/history?created_from=2100-01-01T00:00:00&created_to=2000-01-01T00:00:00"
        )
        self.assertEqual(status, 400)

        self.assert_websocket_event(robot["id"], robot["robot_code"])

    def test_ros_bridge_snapshots(self):
        status, ros_map = self.request(
            "/ros/map",
            "POST",
            {
                "width": 2,
                "height": 2,
                "resolution": 0.05,
                "origin": {"x": -1, "y": -1, "yaw": 0},
                "frame_id": "map",
                "timestamp": 1,
                "map_hash": "smoke-map",
                "data": [-1, 0, 100, 0],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(ros_map["width"], 2)

        status, pose = self.request(
            "/ros/pose",
            "POST",
            {
                "robot_id": 1,
                "frame_id": "map",
                "timestamp": 1,
                "x": 0.2,
                "y": 0.3,
                "yaw": 0.4,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(pose["frame_id"], "map")

        status, ros_status = self.request(
            "/ros/state",
            "POST",
            {
                "bridge_online": True,
                "slam_online": True,
                "map_status": "RECEIVED",
                "lidar_online": True,
                "localization_available": True,
                "tf_available": True,
                "scan_rate_hz": 10,
                "last_scan_age_ms": 25,
                "timestamp": 1,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(ros_status["tf_available"])

        status, current_map = self.request("/ros/map")
        self.assertEqual(status, 200)
        self.assertEqual(current_map["map_hash"], "smoke-map")
        status, current_pose = self.request("/ros/pose")
        self.assertEqual(status, 200)
        self.assertEqual(current_pose["robot_id"], 1)
        status, current_state = self.request("/ros/state")
        self.assertEqual(status, 200)
        self.assertTrue(current_state["bridge_online"])

    def test_lidar_diagnostics_http_and_existing_websocket(self):
        from websockets.sync.client import connect

        payload = dict(
            bridge_online=True, slam_online=False, map_status="WAITING",
            lidar_online=True, localization_available=False, tf_available=False,
            lidar_status="ONLINE", scan_rate_hz=6.0, last_scan_age_ms=25,
            scan_frame_id="laser_link", scan_points_valid=190, scan_points_total=383,
            nearest_obstacle_m=0.3, scan_gap_ms=167, scan_max_gap_ms=640,
            scan_stale_sec=0.5, scan_offline_sec=3, bridge_queue_age_ms=1,
        )
        with connect(self.ws_url) as websocket:
            for status, age in (("ONLINE", 25), ("STALE", 650), ("OFFLINE", 3100), ("ONLINE", 10)):
                payload.update(lidar_status=status, last_scan_age_ms=age,
                               lidar_online=status == "ONLINE")
                code, response = self.request("/ros/state", "POST", payload)
                self.assertEqual(code, 200)
                self.assertEqual(response["lidar_status"], status)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    event = json.loads(websocket.recv(timeout=5))
                    if event["type"] == "SLAM_STATUS_UPDATED":
                        break
                else:
                    self.fail("Missing existing SLAM_STATUS_UPDATED event")
                self.assertEqual(event["data"]["lidar_status"], status)
                self.assertEqual(event["data"]["scan_points_valid"], 190)
                self.assertEqual(event["data"]["nearest_obstacle_m"], 0.3)
                self.assertNotIn("ranges", event["data"])
                code, current = self.request("/ros/state")
                self.assertEqual(code, 200)
                self.assertEqual(current["lidar_status"], status)
                self.assertEqual(current["scan_frame_id"], "laser_link")

    def test_navigation_http_and_websocket_contract(self):
        # These are bridge payloads, not a claim of physical Nav2 execution.
        from websockets.sync.client import connect

        code, locations = self.request("/locations")
        self.assertEqual(code, 200)
        rack_test = next(item for item in locations if item["code"] == "RACK-TEST")

        with connect(self.ws_url) as websocket:
            code, goal = self.request("/ros/navigation/goal", "POST", {
                # Coordinates are resolved again by the backend from location_id.
                "x": 99.0, "y": 99.0, "yaw": 1.0,
                "location_id": rack_test["id"],
            })
            self.assertEqual(code, 200)
            self.assertEqual(goal["state"], "SENDING")
            self.assertEqual(goal["goal"]["x"], 0.5)
            self.assertEqual(goal["goal"]["y"], 0.0)
            self.assertEqual(goal["goal"]["yaw"], 0.0)
            self.assertEqual(goal["goal"]["location"]["code"], "RACK-TEST")
            code, command = self.request("/ros/navigation/command")
            self.assertEqual(command["id"], goal["command_id"])
            self.assertEqual(command["location"]["id"], rack_test["id"])
            self.assertEqual(self.request("/ros/navigation/command"), (200, None))
            endpoint = f"/ros/navigation/command/{command['id']}/status"
            for distance in (0.5, 0.2):
                code, status = self.request(endpoint, "POST", {
                    "command_id": command["id"], "state": "NAVIGATING",
                    "distance_remaining": distance,
                })
                self.assertEqual(code, 200)
                self.assertEqual(status["distance_remaining"], distance)
            path = {"frame_id": "map", "poses": [
                {"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
            ]}
            self.assertEqual(self.request("/ros/navigation/path", "POST", {
                "command_id": command["id"], **path,
            }), (200, path))
            self.assertEqual(self.request("/ros/navigation/path"), (200, path))
            self.assertEqual(self.request(endpoint, "POST", {
                "command_id": command["id"], "state": "SUCCEEDED",
                "distance_remaining": 0.0,
            })[0], 200)
            self.assertEqual(self.request("/ros/navigation/status")[1]["state"], "SUCCEEDED")
            self.assertEqual(self.request("/ros/navigation/path"), (200, None))

            states, distances, paths = [], [], []
            while not states or states[-1] != "SUCCEEDED":
                message = json.loads(websocket.recv(timeout=5))
                if message["type"] == "NAVIGATION_STATUS_UPDATED":
                    states.append(message["data"]["state"])
                    distances.append(message["data"]["distance_remaining"])
                if message["type"] == "NAVIGATION_PATH_UPDATED":
                    paths.append(message["data"])
            self.assertEqual(states, ["SENDING", "NAVIGATING", "NAVIGATING", "SUCCEEDED"])
            self.assertEqual(distances, [None, 0.5, 0.2, 0.0])
            self.assertIn(path, paths)

        code, inactive = self.request("/locations", "POST", {
            "code": "INACTIVE-NAV", "name": "Inactive navigation target",
            "location_type": "RACK", "x": 0.2, "y": 0.0, "yaw": 0.0,
            "is_active": False,
        })
        self.assertEqual(code, 201)
        code, error = self.request("/ros/navigation/goal", "POST", {
            "x": inactive["x"], "y": inactive["y"], "yaw": inactive["yaw"],
            "location_id": inactive["id"],
        })
        self.assertEqual(code, 409)
        self.assertEqual(error["detail"], "Location is inactive")

        self.request("/ros/navigation/goal", "POST", {"x": 1.0, "y": 0.0})
        self.assertEqual(self.request("/ros/navigation/cancel", "POST")[1]["state"], "CANCELLED")
        self.assertEqual(self.request("/ros/navigation/command"), (200, None))

    def test_ros_websocket_events(self):
        try:
            import websockets
        except ImportError:
            self.skipTest("websockets is not installed")

        received = []
        ready = threading.Event()
        failure = []
        expected = {
            "SLAM_MAP_UPDATED",
            "ROBOT_POSE_UPDATED",
            "SLAM_STATUS_UPDATED",
        }

        async def listen():
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    ready.set()
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        timeout = max(0.1, deadline - time.time())
                        message = json.loads(
                            await asyncio.wait_for(
                                websocket.recv(),
                                timeout=timeout,
                            )
                        )
                        received.append(message)
                        if {item.get("type") for item in received} >= expected:
                            return
            except Exception as error:
                failure.append(error)
                ready.set()

        import asyncio

        thread = threading.Thread(
            target=lambda: asyncio.run(listen()),
            daemon=True,
        )
        thread.start()
        self.assertTrue(ready.wait(timeout=5))

        self.request(
            "/ros/map",
            "POST",
            {
                "width": 1,
                "height": 1,
                "resolution": 0.05,
                "origin": {"x": 0, "y": 0, "yaw": 0},
                "frame_id": "map",
                "timestamp": 2,
                "map_hash": "ws-map",
                "data": [0],
            },
        )
        self.request(
            "/ros/pose",
            "POST",
            {
                "robot_id": 1,
                "frame_id": "map",
                "timestamp": 2,
                "x": 0,
                "y": 0,
                "yaw": 0,
            },
        )
        self.request(
            "/ros/state",
            "POST",
            {
                "bridge_online": True,
                "slam_online": True,
                "map_status": "RECEIVED",
                "lidar_online": True,
                "localization_available": True,
                "tf_available": True,
                "timestamp": 2,
            },
        )

        thread.join(timeout=6)
        self.assertFalse(failure, failure)
        self.assertTrue(expected <= {item.get("type") for item in received})

    def test_task_executor_contract(self):
        from websockets.sync.client import connect

        code, locations = self.request("/locations")
        self.assertEqual(code, 200)
        pickup = next(item for item in locations if item["code"] == "RACK-TEST")
        delivery = next(
            item for item in locations if item["location_type"] == "DELIVERY"
        )
        code, product = self.request("/products", "POST", {
            "product_code": "EXECUTOR-PRODUCT",
            "name": "Task executor product",
            "default_rack_id": pickup["id"],
        })
        self.assertEqual(code, 201)
        robot = self.request("/robots")[1][0]

        def set_ros_online(online=True):
            self.request("/ros/state", "POST", {
                "bridge_online": online,
                "nav2_online": online,
                "slam_online": online,
                "map_status": "RECEIVED" if online else "WAITING",
                "lidar_online": online,
                "localization_available": online,
                "tf_available": online,
                "timestamp": time.time(),
            })
            if online:
                self.request("/ros/pose", "POST", {
                    "robot_id": robot["id"],
                    "frame_id": "map",
                    "timestamp": time.time(),
                    "x": 0.0, "y": 0.0, "yaw": 0.0,
                })

        def create_executor_task(robot_id=robot["id"]):
            code, task = self.request("/tasks", "POST", {
                "product_id": product["id"],
                "dropoff_location_id": delivery["id"],
                "robot_id": robot_id,
            })
            self.assertEqual(code, 201)
            return task

        def start(task):
            return self.request(f"/tasks/{task['id']}/start", "PATCH")

        def get_task(task):
            return self.request(f"/tasks/{task['id']}")[1]

        def claim_goal(task, location, stage):
            command = self.request("/ros/navigation/command")[1]
            self.assertEqual(command["task"]["id"], task["id"])
            self.assertEqual(command["task"]["stage"], stage)
            self.assertEqual(command["location"]["id"], location["id"])
            return command

        def post_nav(command, state, **extra):
            return self.request(
                f"/ros/navigation/command/{command['id']}/status",
                "POST",
                {"command_id": command["id"], "state": state, **extra},
            )

        def confirm(task, proof_type):
            code, _ = self.request(
                f"/tasks/{task['id']}/proofs",
                "POST",
                {
                    "proof_type": proof_type,
                    "image_path": f"/proofs/{task['task_code']}-{proof_type}.jpg",
                    "verification_status": "AUTO_VERIFIED",
                },
            )
            self.assertEqual(code, 201)
            return get_task(task)

        def arrive_at_pickup(task):
            self.assertEqual(start(task)[0], 200)
            goal = claim_goal(task, pickup, "PICKUP")
            self.assertEqual(post_nav(
                goal, "NAVIGATING", distance_remaining=0.5,
            )[0], 200)
            self.assertEqual(post_nav(
                goal, "SUCCEEDED", distance_remaining=0.0,
            )[0], 200)
            self.assertEqual(get_task(task)["status"], "ARRIVED_AT_PICKUP")
            return goal

        def start_delivery(task):
            task = confirm(task, "PICKUP")
            self.assertEqual(task["status"], "TRANSPORTING")
            return task, claim_goal(task, delivery, "DELIVERY")

        set_ros_online()
        task = create_executor_task()
        blocked_task = create_executor_task()

        with connect(self.ws_url) as websocket:
            code, task = start(task)
            self.assertEqual(code, 200)
            self.assertEqual(task["status"], "MOVING_TO_PICKUP")
            nav = self.request("/ros/navigation/status")[1]
            self.assertEqual(nav["state"], "SENDING")
            self.assertEqual(nav["goal"]["task"]["id"], task["id"])
            self.assertEqual(nav["goal"]["x"], pickup["x"])

            code, error = start(blocked_task)
            self.assertEqual(code, 409)
            self.assertEqual(error["detail"], "Robot already has an active task")

            command = claim_goal(task, pickup, "PICKUP")
            self.assertEqual(post_nav(
                command, "NAVIGATING", distance_remaining=0.5,
            )[0], 200)
            self.assertEqual(post_nav(
                command, "SUCCEEDED", distance_remaining=0.0,
            )[0], 200)
            task = get_task(task)
            self.assertEqual(task["status"], "ARRIVED_AT_PICKUP")

            task = confirm(task, "PICKUP")
            self.assertEqual(task["status"], "TRANSPORTING")
            delivery_command = claim_goal(task, delivery, "DELIVERY")

            # The terminal callback from the previous pickup goal is stale now.
            self.assertEqual(post_nav(command, "FAILED")[0], 404)
            self.assertEqual(get_task(task)["status"], "TRANSPORTING")

            self.assertEqual(post_nav(
                delivery_command, "NAVIGATING", distance_remaining=0.7,
            )[0], 200)
            self.assertEqual(post_nav(
                delivery_command, "SUCCEEDED", distance_remaining=0.0,
            )[0], 200)
            task = get_task(task)
            self.assertEqual(task["status"], "ARRIVED_AT_DELIVERY")
            task = confirm(task, "DELIVERY")
            self.assertEqual(task["status"], "COMPLETED")
            self.assertEqual(task["progress"], 100)
            self.assertIsNotNone(task["completed_at"])
            self.assertEqual(
                self.request("/ros/navigation/status")[1]["state"],
                "SUCCEEDED",
            )
            self.assertEqual(
                self.request("/ros/navigation/command"),
                (200, None),
            )

            task_states = []
            nav_states = []
            deadline = time.time() + 5
            while time.time() < deadline:
                message = json.loads(websocket.recv(timeout=5))
                if message["type"] == "TASK_UPDATED":
                    task_states.append(message["data"]["status"])
                elif message["type"] == "NAVIGATION_STATUS_UPDATED":
                    nav_states.append(message["data"]["state"])
                if (
                    "COMPLETED" in task_states
                    and nav_states.count("SUCCEEDED") >= 2
                ):
                    break
            for expected in (
                "MOVING_TO_PICKUP",
                "ARRIVED_AT_PICKUP",
                "PICKUP_CONFIRMED",
                "TRANSPORTING",
                "ARRIVED_AT_DELIVERY",
                "DELIVERY_CONFIRMED",
                "COMPLETED",
            ):
                self.assertIn(expected, task_states)
            self.assertIn("SENDING", nav_states)
            self.assertIn("NAVIGATING", nav_states)
            self.assertIn("SUCCEEDED", nav_states)

        # Completion releases the robot; a rejected pickup goal fails the next task.
        code, blocked_task = start(blocked_task)
        self.assertEqual(code, 200)
        rejected_command = claim_goal(blocked_task, pickup, "PICKUP")
        post_nav(
            rejected_command,
            "REJECTED",
            error_code=42,
            error_message="Planner rejected pickup goal",
        )
        blocked_task = self.request(f"/tasks/{blocked_task['id']}")[1]
        self.assertEqual(blocked_task["status"], "FAILED")
        self.assertEqual(blocked_task["fail_reason"], "Planner rejected pickup goal")

        pickup_failure_task = create_executor_task()
        self.assertEqual(start(pickup_failure_task)[0], 200)
        failed_pickup = claim_goal(pickup_failure_task, pickup, "PICKUP")
        post_nav(
            failed_pickup,
            "FAILED",
            error_code=16,
            error_message="Controller failed pickup goal",
        )
        pickup_failure_task = get_task(pickup_failure_task)
        self.assertEqual(pickup_failure_task["status"], "FAILED")
        self.assertEqual(
            pickup_failure_task["fail_reason"],
            "Controller failed pickup goal",
        )

        # Verified proofs are rejected outside their exact lifecycle state.
        delivery_failure_task = create_executor_task()
        for proof_type in ("PICKUP", "DELIVERY"):
            code, _ = self.request(
                f"/tasks/{delivery_failure_task['id']}/proofs",
                "POST",
                {
                    "proof_type": proof_type,
                    "image_path": "/proofs/invalid.jpg",
                    "verification_status": "AUTO_VERIFIED",
                },
            )
            self.assertEqual(code, 409)
        self.assertEqual(
            self.request(f"/tasks/{delivery_failure_task['id']}/proofs")[1],
            [],
        )

        # A delivery navigation failure records its reason on the task.
        arrive_at_pickup(delivery_failure_task)
        code, _ = self.request(
            f"/tasks/{delivery_failure_task['id']}/proofs",
            "POST",
            {
                "proof_type": "DELIVERY",
                "image_path": "/proofs/too-early.jpg",
                "verification_status": "AUTO_VERIFIED",
            },
        )
        self.assertEqual(code, 409)
        delivery_failure_task, failed_delivery = start_delivery(
            delivery_failure_task,
        )
        post_nav(
            failed_delivery,
            "FAILED",
            error_code=17,
            error_message="Controller failed delivery goal",
        )
        delivery_failure_task = get_task(delivery_failure_task)
        self.assertEqual(delivery_failure_task["status"], "FAILED")
        self.assertEqual(
            delivery_failure_task["fail_reason"],
            "Controller failed delivery goal",
        )

        # Cancelling a moving task creates a Nav2 cancel command immediately.
        cancel_task = create_executor_task()
        self.assertEqual(start(cancel_task)[0], 200)
        cancel_goal = claim_goal(cancel_task, pickup, "PICKUP")
        post_nav(cancel_goal, "NAVIGATING", distance_remaining=0.4)
        with connect(self.ws_url) as websocket:
            code, cancel_task = self.request(
                f"/tasks/{cancel_task['id']}/cancel", "PATCH"
            )
            robot_cancel_command = None
            deadline = time.time() + 5
            while time.time() < deadline:
                message = json.loads(websocket.recv(timeout=5))
                if (
                    message["type"] == "COMMAND_CREATED"
                    and message["data"]["task_id"] == cancel_task["id"]
                    and message["data"]["command"] == "CANCEL"
                ):
                    robot_cancel_command = message["data"]
                    break
        self.assertEqual(code, 200)
        self.assertEqual(cancel_task["status"], "CANCELLED")
        self.assertIsNotNone(robot_cancel_command)
        cancel_command = self.request("/ros/navigation/command")[1]
        self.assertEqual(cancel_command["command"], "CANCEL")
        self.assertEqual(
            cancel_command["navigation_command_id"], cancel_goal["id"]
        )
        post_nav(cancel_goal, "CANCELLED", distance_remaining=0.4)
        self.assertEqual(self.request(
            f"/robots/{robot['id']}/commands/"
            f"{robot_cancel_command['id']}/ack",
            "PATCH",
            {"status": "ACKNOWLEDGED"},
        )[0], 200)
        cancel_task = get_task(cancel_task)
        self.assertFalse(cancel_task["cancel_requested"])

        # Pickup pause/resume returns to pickup, then cancel works after arrival.
        paused_task = create_executor_task()
        self.assertEqual(start(paused_task)[0], 200)
        paused_goal = claim_goal(paused_task, pickup, "PICKUP")
        post_nav(paused_goal, "NAVIGATING", distance_remaining=0.3)
        code, paused_task = self.request(
            f"/tasks/{paused_task['id']}/pause", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertTrue(paused_task["is_paused"])
        self.assertEqual(
            self.request("/ros/navigation/command")[1]["command"], "CANCEL"
        )
        post_nav(paused_goal, "CANCELLED", distance_remaining=0.3)
        paused_task = get_task(paused_task)
        self.assertEqual(paused_task["status"], "MOVING_TO_PICKUP")
        self.assertTrue(paused_task["is_paused"])
        code, paused_task = self.request(
            f"/tasks/{paused_task['id']}/resume", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertFalse(paused_task["is_paused"])
        resumed_goal = claim_goal(paused_task, pickup, "PICKUP")
        post_nav(resumed_goal, "SUCCEEDED", distance_remaining=0.0)
        self.assertEqual(
            get_task(paused_task)["status"],
            "ARRIVED_AT_PICKUP",
        )
        code, paused_task = self.request(
            f"/tasks/{paused_task['id']}/cancel", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertEqual(paused_task["status"], "CANCELLED")

        # Delivery pause resumes the delivery location; cancellation ignores late callbacks.
        delivery_pause_task = create_executor_task()
        arrive_at_pickup(delivery_pause_task)
        delivery_pause_task, first_delivery_goal = start_delivery(
            delivery_pause_task,
        )
        post_nav(first_delivery_goal, "NAVIGATING", distance_remaining=0.6)
        code, delivery_pause_task = self.request(
            f"/tasks/{delivery_pause_task['id']}/pause", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertTrue(delivery_pause_task["is_paused"])
        self.assertEqual(
            self.request("/ros/navigation/command")[1]["command"], "CANCEL"
        )
        post_nav(first_delivery_goal, "CANCELLED", distance_remaining=0.6)
        code, delivery_pause_task = self.request(
            f"/tasks/{delivery_pause_task['id']}/resume", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertFalse(delivery_pause_task["is_paused"])
        resumed_delivery_goal = claim_goal(
            delivery_pause_task, delivery, "DELIVERY",
        )
        post_nav(resumed_delivery_goal, "NAVIGATING", distance_remaining=0.5)
        code, delivery_pause_task = self.request(
            f"/tasks/{delivery_pause_task['id']}/cancel", "PATCH"
        )
        self.assertEqual(code, 200)
        self.assertEqual(delivery_pause_task["status"], "CANCELLED")
        self.assertEqual(
            self.request("/ros/navigation/command")[1]["command"], "CANCEL"
        )
        post_nav(resumed_delivery_goal, "CANCELLED", distance_remaining=0.5)
        post_nav(resumed_delivery_goal, "FAILED", error_message="late callback")
        self.assertEqual(get_task(delivery_pause_task)["status"], "CANCELLED")

        # No goal is created while the bridge/Nav2 state is offline.
        offline_task = create_executor_task()
        set_ros_online(False)
        code, error = start(offline_task)
        self.assertEqual(code, 409)
        self.assertEqual(error["detail"], "ROS bridge is offline")
        self.assertEqual(
            get_task(offline_task)["status"],
            "WAITING",
        )

    def assert_websocket_event(self, robot_id, robot_code):
        try:
            import websockets
        except ImportError:
            self.skipTest("websockets is not installed")

        received = []
        ready = threading.Event()
        failure = []

        async def listen():
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    ready.set()
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        timeout = max(0.1, deadline - time.time())
                        message = json.loads(
                            await asyncio.wait_for(
                                websocket.recv(),
                                timeout=timeout,
                            )
                        )
                        received.append(message)
                        if {
                            item.get("type") for item in received
                        } >= {
                            "EVENT_CREATED",
                            "ROBOT_STATUS_UPDATED",
                        }:
                            return
            except Exception as error:
                failure.append(error)
                ready.set()

        import asyncio

        thread = threading.Thread(
            target=lambda: asyncio.run(listen()),
            daemon=True,
        )
        thread.start()
        self.assertTrue(ready.wait(timeout=5))
        status, _ = self.request(
            f"/robots/{robot_id}/status",
            "PATCH",
            {"state": "ERROR"},
        )
        self.assertEqual(status, 200)
        thread.join(timeout=6)
        self.assertFalse(failure, failure)

        status_message = next(
            item for item in received
            if item.get("type") == "ROBOT_STATUS_UPDATED"
        )
        self.assertEqual(status_message["data"]["robot_code"], robot_code)

        event_message = next(
            item for item in received
            if item.get("type") == "EVENT_CREATED"
        )
        self.assertEqual(event_message["data"]["robot_code"], robot_code)


if __name__ == "__main__":
    unittest.main()
