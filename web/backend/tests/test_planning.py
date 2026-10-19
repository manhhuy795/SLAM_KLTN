import hashlib
import json
import math
from pathlib import Path
import sqlite3
import unittest
from uuid import uuid4

from app.schemas.planning import PlanningObject
from pydantic import ValidationError
import test_saved_maps as maps_test
from test_saved_maps import metadata

BACKEND=Path(__file__).resolve().parents[1]


class PlanningHttpTest(unittest.TestCase):
    setUpClass=classmethod(maps_test.SavedMapsHttpTest.setUpClass.__func__)
    start_server=classmethod(maps_test.SavedMapsHttpTest.start_server.__func__)
    tearDownClass=classmethod(maps_test.SavedMapsHttpTest.tearDownClass.__func__)
    request=classmethod(maps_test.SavedMapsHttpTest.request.__func__)
    upload=maps_test.SavedMapsHttpTest.upload

    def create_map(self):
        code, result=self.upload(image_data=(BACKEND/"tests/fixtures/maps/import_demo.pgm").read_bytes(),
                                 yaml_data=metadata(resolution=.1,origin=[-1.2,-.8,.35]))
        self.assertEqual(code,201,result)
        return result["id"]

    def obj(self, kind="HOME", column=12, row=10):
        x,y=column*.1,row*.1
        return dict(id=str(uuid4()),type=kind,name="Test "+kind,
                    x=-1.2+math.cos(.35)*x-math.sin(.35)*y,
                    y=-.8+math.sin(.35)*x+math.cos(.35)*y,yaw=.35,
                    width=.2 if kind=="RACK" else None,height=.3 if kind=="RACK" else None,
                    vertices=[dict(x=-.1,y=-.1),dict(x=.1,y=-.1),dict(x=0,y=.1)] if kind=="NO_GO" else [])

    def save(self, map_id, revision, objects):
        return self.request(f"/maps/{map_id}/planning","PUT",
                            json.dumps(dict(revision=revision,objects=objects)).encode())

    def test_crud_restart_isolation_cascade_and_grid_immutable(self):
        from websockets.sync.client import connect
        a,b=self.create_map(),self.create_map()
        folder=Path(self.env["WRMS_MAPS_DIR"])/a
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        self.assertEqual(self.request(f"/maps/{a}/planning")[1]["objects"],[])
        objects=[self.obj(kind) for kind in ["RACK","RACK","HOME","PICKUP","DELIVERY","CHARGING","NO_GO"]]
        with connect(f"ws://127.0.0.1:{self.port}/ws") as ws:
            code,saved=self.save(a,0,objects)
            self.assertEqual(code,200,saved)
            event=json.loads(ws.recv(timeout=5))
            self.assertEqual(event["type"],"PLANNING_UPDATED")
            self.assertEqual(event["data"]["map_id"],a)
        self.assertEqual(saved["revision"],1)
        self.assertTrue(all(o["map_id"]==a and o["created_at"] and o["updated_at"] for o in saved["objects"]))
        self.assertEqual(self.request(f"/maps/{b}/planning")[1]["objects"],[])
        self.process.terminate();self.process.wait(timeout=5);type(self).start_server()
        reopened=self.request(f"/maps/{a}/planning")[1]
        self.assertEqual(reopened["objects"],saved["objects"])
        objects[0]["name"]="Renamed rack"
        objects[0]["x"]+=.02
        code,changed=self.save(a,1,objects[:-1])
        self.assertEqual(code,200,changed)
        self.assertEqual(len(changed["objects"]),6)
        self.assertEqual(changed["objects"][0]["created_at"],saved["objects"][0]["created_at"])
        self.assertNotEqual(changed["objects"][0]["updated_at"],saved["objects"][0]["updated_at"])
        self.assertEqual(changed["objects"][1]["updated_at"],saved["objects"][1]["updated_at"])
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()})
        self.assertEqual(self.request(f"/maps/{a}/planning?revision=2","DELETE")[0],200)
        self.assertEqual(self.request(f"/maps/{a}/planning")[1]["objects"],[])
        self.assertEqual(self.save(b,0,[self.obj()])[0],200)
        self.assertEqual(self.request(f"/maps/{b}","DELETE")[0],204)
        db=sqlite3.connect(Path(self.folder.name)/"test.db")
        self.assertEqual(db.execute("select count(*) from planning_layers where map_id=?",(b,)).fetchone()[0],0)
        db.close()

    def test_stale_save_is_rejected_and_invalid_geometry_is_atomic(self):
        map_id=self.create_map()
        item=self.obj()
        self.assertEqual(self.save(map_id,0,[item])[0],200)
        self.assertEqual(self.save(map_id,0,[])[0],409)
        invalid=[{**item,"x":1000},{**self.obj("RACK",1,1),"width":2},
                 {**item,"name":"  "},{**item,"yaw":float("inf")},
                 {**self.obj("RACK"),"height":0},
                 {**self.obj("NO_GO"),"vertices":[dict(x=0,y=0),dict(x=1,y=1),dict(x=0,y=1),dict(x=1,y=0)]}]
        for bad in invalid:
            with self.subTest(bad=bad):
                self.assertEqual(self.save(map_id,1,[bad])[0],422)
        self.assertEqual(self.save(map_id,1,[item,item])[0],422)
        self.assertEqual(self.request(f"/maps/{map_id}/planning")[1]["revision"],1)
        self.assertEqual(self.request(f"/maps/{uuid4()}/planning")[0],404)

    def test_occupied_unknown_warnings_and_concurrent_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        map_id=self.create_map()
        grid=self.request(f"/maps/{map_id}")[1]
        items=[]
        for value in [100,-1]:
            index=grid["data"].index(value)
            items.append(self.obj(column=index%32+.5,row=index//32+.5))
        code,saved=self.save(map_id,0,items)
        self.assertEqual(code,200,saved)
        self.assertEqual(len(saved["warnings"]),2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:self.save(map_id,1,items)[0],range(2)))
        self.assertEqual(sorted(results),[200,409])


class PolygonValidationTest(unittest.TestCase):
    def test_reject_self_crossing_even_nonzero_area_and_duplicate_vertices(self):
        base=dict(id=uuid4(),type="NO_GO",name="Zone",x=0,y=0)
        for points in [[(0,0),(3,2),(0,2),(2,0)],[(0,0),(1,0),(0,1),(0,0)]]:
            with self.assertRaises(ValidationError):
                PlanningObject(**base,vertices=[dict(x=x,y=y) for x,y in points])
