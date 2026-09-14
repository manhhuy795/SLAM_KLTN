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

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None) is not None:
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
                "verification_status": "AUTO_VERIFIED",
            },
        )
        self.assertEqual(status, 201)

        for next_status in ("TRANSPORTING", "ARRIVED_AT_DELIVERY"):
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
                "verification_status": "MANUAL_CONFIRMED",
                "confirmed_by": operator_id,
            },
        )
        self.assertEqual(status, 201)

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
