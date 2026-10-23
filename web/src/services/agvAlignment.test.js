import test from 'node:test';
import assert from 'node:assert/strict';
import { agvToSharedMap } from './agvAlignment.js';

const map={id:'map1',map_hash:'same',frame_id:'map',width:476,height:336,resolution:.005,origin:{x:0,y:0,yaw:0}};
const alignment={map_hash:'same',map_id:'map1',a:{x:.2,y:1.6},d:{x:1.74,y:1.6},b:{x:.2,y:.09}};
test('AGV origin maps to calibrated A on shared map',()=>{
 const pose=agvToSharedMap(map,alignment,{x:0,y:0,yaw:90});
 assert.ok(pose);
 assert.ok(Math.abs(pose.x-.2)<1e-8);
 assert.ok(Math.abs(pose.y-1.6)<1e-8);
 assert.ok(Math.abs(pose.yaw+Math.PI/2)<1e-8);
});
test('AGV B maps to physical B anchor',()=>{
 const pose=agvToSharedMap(map,alignment,{x:0,y:1.51,yaw:90});
 assert.ok(pose);
 assert.ok(Math.abs(pose.y-.09)<1e-8);
});
test('do not overlay uncalibrated or wrong-map robot',()=>{
 assert.equal(agvToSharedMap(map,null,{x:0,y:0,yaw:0}),null);
 assert.equal(agvToSharedMap({...map,map_hash:'other'},alignment,{x:0,y:0,yaw:0}),null);
 assert.equal(agvToSharedMap(map,{...alignment,d:{x:9,y:9}},{x:0,y:0,yaw:0}),null);
});
