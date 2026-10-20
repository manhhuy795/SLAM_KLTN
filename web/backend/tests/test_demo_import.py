import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1]


class DemoImportTest(unittest.TestCase):
    def test_fresh_import_repeat_and_preserve_edited_planning(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "demo.db"
            maps = Path(folder) / "maps"
            env = {**os.environ, "WRMS_DATABASE_URL": "sqlite:///" + str(database),
                   "WRMS_MAPS_DIR": str(maps)}
            def run(dataset="final", ok=True):
                result = subprocess.run(
                    [sys.executable, "import_demo.py", "--dataset", dataset],
                    cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
            run()
            run("simulation")
            db = sqlite3.connect(database)
            selected = db.execute("select id from saved_maps where is_selected=1").fetchone()[0]
            layer = db.execute("select revision,objects from planning_layers where map_id=?", (selected,)).fetchone()
            objects = json.loads(layer[1])
            self.assertEqual(len(objects), 14)
            expected = {"HOME": (.30, .84), "PICKUP": (1.19, .84),
                        "A1": (.75, 1.45), "A2": (1.05, 1.45), "B1": (1.33, 1.45),
                        "B2": (1.63, 1.45), "C1": (.75, .23), "C2": (1.05, .23),
                        "D1": (1.33, .23), "D2": (1.63, .23)}
            self.assertEqual({o["name"]: (o["x"], o["y"]) for o in objects if o["type"] != "RACK"}, expected)
            self.assertEqual(sum(o["type"] == "RACK" for o in objects), 4)
            self.assertFalse(any(o["type"] in {"DELIVERY", "CHARGING", "NO_GO"} for o in objects))
            files = {str(p): p.read_bytes() for p in maps.rglob("*") if p.is_file()}
            run()
            run("simulation")
            self.assertEqual(db.execute("select count(*) from saved_maps").fetchone()[0], 2)
            self.assertEqual(db.execute("select revision,objects from planning_layers where map_id=?", (selected,)).fetchone(), layer)
            self.assertEqual({str(p): p.read_bytes() for p in maps.rglob("*") if p.is_file()}, files)
            objects[0]["name"] = "USER EDIT - KEEP"
            db.execute("update planning_layers set objects=? where map_id=?", (json.dumps(objects), selected))
            db.commit()
            run(ok=False)
            self.assertEqual(json.loads(db.execute("select objects from planning_layers where map_id=?", (selected,)).fetchone()[0]), objects)
            db.close()


if __name__ == "__main__":
    unittest.main()
