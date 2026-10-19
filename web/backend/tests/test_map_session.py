import json
import unittest
from uuid import uuid4
from unittest.mock import patch

import test_saved_maps as maps_test
from app.services.map_session import MapSession


class SessionUnitTest(unittest.TestCase):
    def test_stale_bridge_and_pending_are_never_ready(self):
        session=MapSession()
        session.update(dict(enabled=True,ready=True,keepout_verified=True,state="READY",session_id="a"))
        self.assertTrue(session.guard()["ready"])
        session.received-=5
        self.assertFalse(session.status()["keepout_verified"])
        with self.assertRaises(ValueError):session.guard()
        session.pending=dict(id="operation")
        session.started=0
        self.assertEqual(session.status()["state"],"FAILED")
        self.assertFalse(session.status()["keepout_verified"])

    def test_only_matching_result_clears_pending(self):
        session=MapSession();session.pending=dict(id="new")
        session.update(dict(enabled=True,ready=True,state="READY",request_id="old"))
        self.assertIsNotNone(session.pending)
        session.update(dict(enabled=True,ready=False,state="FAILED",request_id="new"))
        self.assertIsNone(session.pending)


class MapSessionHttpTest(unittest.TestCase):
    setUpClass=classmethod(maps_test.SavedMapsHttpTest.setUpClass.__func__)
    start_server=classmethod(maps_test.SavedMapsHttpTest.start_server.__func__)
    tearDownClass=classmethod(maps_test.SavedMapsHttpTest.tearDownClass.__func__)
    request=classmethod(maps_test.SavedMapsHttpTest.request.__func__)
    upload=maps_test.SavedMapsHttpTest.upload

    def post(self,path,data):
        return self.request(path,"POST",json.dumps(data).encode())

    def test_map_apply_versioned_point_and_cancel(self):
        code,m=self.upload(yaml_data=maps_test.metadata(origin=[0,0,0]))
        self.assertEqual(code,201)
        self.assertEqual(self.post("/ros/map-session/apply",dict(map_id=m["id"]))[0],409)
        report=dict(enabled=True,ready=False,state="WAITING",session_id="test")
        self.assertEqual(self.post("/ros/map-session/status",report)[0],200)
        self.assertEqual(self.post("/ros/navigation/goal",dict(x=0,y=0))[0],409)
        code,pending=self.post("/ros/map-session/apply",dict(map_id=m["id"]))
        self.assertEqual(code,200,pending)
        code,command=self.request("/ros/map-session/command")
        self.assertEqual(command["map_hash"],m["map_hash"])
        self.assertIsNone(self.request("/ros/map-session/command")[1])
        report.update(ready=True,state="READY",request_id=command["id"],map_id=m["id"],map_hash=m["map_hash"],planning_revision=0)
        self.post("/ros/map-session/status",report)
        point=dict(id=str(uuid4()),name="HOME",type="HOME",x=.3,y=.2,yaw=0)
        code,layer=self.request("/maps/"+m["id"]+"/planning","PUT",json.dumps(dict(revision=0,objects=[point])).encode())
        self.assertEqual(code,200,layer)
        report["planning_revision"]=layer["revision"];self.post("/ros/map-session/status",report)
        data=dict(x=999,y=999,map_id=m["id"],planning_point_id=point["id"],planning_revision=layer["revision"])
        code,status=self.post("/ros/navigation/goal",data)
        self.assertEqual(code,200,status)
        self.assertEqual(status["goal"]["x"],point["x"])
        self.assertEqual(status["goal"]["map_context"]["session_id"],"test")
        self.assertEqual(self.post("/ros/map-session/apply",dict(map_id=m["id"]))[0],409)
        self.assertEqual(self.post("/ros/navigation/cancel",{})[1]["state"],"CANCELLED")
        data["planning_revision"]=0
        self.assertEqual(self.post("/ros/navigation/goal",data)[0],409)
        data["planning_revision"]=1;data["planning_point_id"]=str(uuid4())
        self.assertEqual(self.post("/ros/navigation/goal",data)[0],422)
        code,rotated=self.upload()
        self.assertEqual(code,201)
        self.assertEqual(self.post("/ros/map-session/apply",dict(map_id=rotated["id"]))[0],422)
