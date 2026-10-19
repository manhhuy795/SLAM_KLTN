import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
import yaml

from app.services.saved_maps import parse_map, MAX_CELLS, MAX_YAML_BYTES

BACKEND_DIR = Path(__file__).resolve().parents[1]
PGM = b"P2\n# Deliberately asymmetric TEST map, not LiDAR data\n3 2\n255\n0 255 205\n255 0 128\n"


def metadata(**overrides):
    result = dict(image="sample.pgm", resolution=0.25, origin=[-1.5, 2, 0.7],
                  negate=0, free_thresh=0.196, occupied_thresh=0.65)
    result.update(overrides)
    return yaml.safe_dump(result).encode()


def png(mode, size, pixels):
    image = Image.new(mode, size)
    image.putdata(pixels)
    target = io.BytesIO()
    image.save(target, format="PNG")
    return target.getvalue()


def multipart(yaml_data=None, image_data=PGM, image_name="sample.pgm", name="Synthetic test map"):
    boundary = uuid4().hex
    parts = []
    for field, filename, content_type, data in (
        ("name", None, None, name.encode()),
        ("yaml_file", "sample.yaml", "application/yaml", metadata() if yaml_data is None else yaml_data),
        ("image_file", image_name, "application/octet-stream", image_data),
    ):
        header = f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"'
        if filename:
            header += f'; filename="{filename}"\r\nContent-Type: {content_type}'
        parts.append(header.encode() + b"\r\n\r\n" + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class MapConversionTest(unittest.TestCase):
    def test_pgm_orientation_metadata_and_unknown(self):
        _, grid = parse_map(metadata(), PGM, "sample.yaml", "sample.pgm")
        self.assertEqual(grid["data"], [0, 100, -1, 100, 0, -1])
        self.assertEqual((grid["width"], grid["height"]), (3, 2))
        self.assertEqual(grid["origin"], dict(x=-1.5, y=2, yaw=0.7))
        self.assertEqual(grid["resolution"], 0.25)

    def test_binary_pgm_does_not_strip_pixel_whitespace(self):
        data = b"P5\n3 1\n255\n" + bytes([10, 255, 128])
        _, grid = parse_map(metadata(), data, "sample.yaml", "sample.pgm")
        self.assertEqual(grid["data"], [100, 0, -1])

    def test_png_transparency_negate_and_scale(self):
        image = png("RGBA", (3, 1), [(0, 0, 0, 128), (255, 255, 255, 255), (128, 128, 128, 255)])
        _, grid = parse_map(metadata(image="sample.png", mode="scale", free_thresh=.2,
                                     occupied_thresh=.8), image, "a.yaml", "sample.png")
        self.assertEqual(grid["data"], [-1, 0, 50])
        _, grid = parse_map(metadata(negate=1), PGM, "a.yaml", "sample.pgm")
        self.assertEqual(grid["data"], [100, 0, -1, 0, 100, 100])

    def test_raw_and_missing_mode(self):
        data = b"P5\n4 1\n255\n" + bytes([0, 100, 101, 255])
        _, grid = parse_map(metadata(mode="raw", negate=1), data, "a.yaml", "sample.pgm")
        self.assertEqual(grid["data"], [0, 100, -1, -1])

    def test_reject_bad_yaml_dimensions_and_files(self):
        bad_yaml = [
            b"!!python/object/apply:os.system [echo unsafe]",
            b"image: &a [*a]", b"[]", b"{",
            metadata(resolution=0), metadata(origin=[0, 1]),
            metadata(origin=[0, 0, float("nan")]), metadata(mode="invalid"),
            metadata(free_thresh=.8, occupied_thresh=.7),
            metadata(image="another.pgm"), metadata(negate=2),
        ]
        for data in bad_yaml:
            with self.subTest(data=data), self.assertRaises(HTTPException):
                parse_map(data, PGM, "a.yaml", "sample.pgm")
        for content, filename in ((b"not an image", "sample.pgm"), (PGM, "sample.png")):
            with self.assertRaises(HTTPException):
                parse_map(metadata(image=filename), content, "a.yaml", filename)
        with self.assertRaises(HTTPException) as error:
            parse_map(b"x" * (MAX_YAML_BYTES + 1), PGM, "a.yaml", "sample.pgm")
        self.assertEqual(error.exception.status_code, 413)
        with self.assertRaises(HTTPException) as error:
            parse_map(metadata(), f"P5\n{MAX_CELLS + 1} 1\n255\n".encode(), "a.yaml", "sample.pgm")
        self.assertEqual(error.exception.status_code, 413)

    def test_yaml_path_is_only_used_to_match_uploaded_basename(self):
        _, grid = parse_map(metadata(image="../../not-read/sample.pgm"), PGM, "a.yaml", "sample.pgm")
        self.assertEqual(grid["data"][0], 0)


class SavedMapsHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.env = os.environ.copy()
        cls.env["WRMS_DATABASE_URL"] = "sqlite:///" + cls.folder.name + "/test.db"
        cls.env["WRMS_MAPS_DIR"] = cls.folder.name + "/maps"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.url = f"http://127.0.0.1:{cls.port}/api"
        cls.log = open(Path(cls.folder.name) / "server.log", "w+")
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "error"],
            cwd=BACKEND_DIR, env=cls.env, stdout=cls.log, stderr=cls.log)
        for _ in range(100):
            try:
                if cls.request("/health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.log.seek(0)
        raise RuntimeError(cls.log.read())

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.log.close()
        cls.folder.cleanup()

    @classmethod
    def request(cls, path, method="GET", data=None, content_type="application/json"):
        request = Request(cls.url + path, data=data, method=method,
                          headers={"Content-Type": content_type})
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    def upload(self, **kwargs):
        body, content_type = multipart(**kwargs)
        return self.request("/maps", "POST", body, content_type)

    def test_upload_select_restart_live_isolation_delete_and_websocket(self):
        from websockets.sync.client import connect
        with connect(f"ws://127.0.0.1:{self.port}/ws") as ws:
            code, created = self.upload()
            self.assertEqual(code, 201, created)
            event = json.loads(ws.recv(timeout=5))
            self.assertEqual(event["type"], "SAVED_MAPS_UPDATED")
            map_id = created["id"]
            code, selected = self.request(f"/maps/{map_id}/select", "POST")
            self.assertEqual(code, 200, selected)
            self.assertEqual(selected["data"], [0, 100, -1, 100, 0, -1])
        stored = Path(self.env["WRMS_MAPS_DIR"]) / map_id
        self.assertTrue((stored / "map.yaml").is_file())
        self.assertTrue((stored / "map.pgm").is_file())
        self.process.terminate()
        self.process.wait(timeout=5)
        type(self).start_server()
        code, reopened = self.request("/maps/selected")
        self.assertEqual(code, 200)
        self.assertEqual(reopened, selected)
        self.assertFalse(self.request("/ros/state")[1]["bridge_online"])
        self.assertEqual(len(self.request("/maps")[1]), 1)

        # This synthetic live payload exercises isolation; it is not a ROS sensor run.
        live = dict(width=1, height=1, resolution=1, origin=dict(x=0, y=0, yaw=0),
                    frame_id="map", map_hash="synthetic-live", data=[100])
        self.assertEqual(self.request("/ros/map", "POST", json.dumps(live).encode())[0], 200)
        self.assertEqual(self.request("/maps/selected")[1]["map_hash"], selected["map_hash"])
        self.assertEqual(self.request("/ros/map")[1]["map_hash"], "synthetic-live")

        code, other = self.upload(name="Second synthetic map", image_name="sample.png",
                                  image_data=png("L", (2, 1), [0, 255]),
                                  yaml_data=metadata(image="sample.png"))
        self.assertEqual(code, 201, other)
        self.assertEqual(self.request(f"/maps/{other['id']}/select", "POST")[0], 200)
        items = self.request("/maps")[1]
        self.assertEqual(sum(item["is_selected"] for item in items), 1)
        self.assertEqual(self.request(f"/maps/{uuid4().hex}/select", "POST")[0], 404)
        self.assertEqual(self.request("/maps/selected")[1]["id"], other["id"])
        for item in items:
            self.assertEqual(self.request(f"/maps/{item['id']}", "DELETE")[0], 204)
            self.assertFalse((Path(self.env["WRMS_MAPS_DIR"]) / item["id"]).exists())
        self.assertIsNone(self.request("/maps/selected")[1])
        self.assertEqual(self.request(f"/maps/{map_id}")[0], 404)

    def test_invalid_upload_and_request_limit_leave_no_files(self):
        before = self.request("/maps")[1]
        self.assertEqual(self.upload(image_data=b"broken")[0], 422)
        self.assertEqual(self.upload(name="   ")[0], 422)
        self.assertEqual(self.upload(yaml_data=metadata(resolution=-1))[0], 422)
        self.assertEqual(self.upload(image_data=b"x" * (21 * 1024 * 1024))[0], 413)
        self.assertEqual(self.request("/maps/not-a-uuid")[0], 422)
        self.assertEqual(self.request("/maps")[1], before)
        folders = list(Path(self.env["WRMS_MAPS_DIR"]).glob("*"))
        self.assertEqual(len(folders), len(before))


if __name__ == "__main__":
    unittest.main()
