import assert from 'node:assert/strict';
import {test} from 'node:test';
import {worldToCanvas} from './slamMap.js';
import {canvasToWorld,clientToWorld,footprint,localToWorld,worldToLocal,
  polygonValid,objectIssues,objectPayload} from './planning.js';

const map={width:120,height:80,resolution:.05,origin:{x:-2,y:3,yaw:.73},data:Array(9600).fill(0)};
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);

test('rotated translated origin: canvas/world roundtrip, Y flip and zoom/pan invariance',()=>{
  for(const pixel of [{x:0,y:80},{x:57.25,y:21.7},{x:120,y:0}]) {
    const world=canvasToWorld(map,pixel.x,pixel.y);
    const rendered=worldToCanvas(map,world.x,world.y,120,80);
    close(rendered.x,pixel.x);close(rendered.y,pixel.y);
    for(const zoom of [.5,1,4,12]) {
      const rect={left:-81,top:117,width:600*zoom,height:400*zoom};
      const moved=clientToWorld(map,rect,rect.left+pixel.x/120*rect.width,rect.top+pixel.y/80*rect.height);
      close(moved.x,world.x);close(moved.y,world.y);
    }
  }
  assert.deepEqual(canvasToWorld(map,0,80),{x:-2,y:3});
});

test('rotated rack footprint, local polygon and boundary checks',()=>{
  const center=canvasToWorld(map,60,40);
  const rack={id:'id',type:'RACK',name:'Rack',...center,yaw:.73,width:1,height:2,vertices:[]};
  assert.equal(footprint(rack).length,4);
  assert.deepEqual(objectIssues(map,rack),{errors:[],warnings:[]});
  const p={x:.2,y:-.3},roundtrip=worldToLocal(rack,localToWorld(rack,p));
  close(p.x,roundtrip.x);close(p.y,roundtrip.y);
  assert.ok(objectIssues(map,{...rack,width:20}).errors.length);
  assert.ok(objectIssues(map,{...rack,x:NaN}).errors.length);
  assert.ok(objectIssues(map,{...rack,width:0}).errors.length);
});

test('point occupancy warnings never imply reachability',()=>{
  const point={type:'HOME',name:'Home',...canvasToWorld(map,20.5,69.5),yaw:0,vertices:[]};
  const data=[...map.data];data[10*120+20]=-1;
  assert.match(objectIssues({...map,data},point).warnings[0],/chưa biết/);
  data[10*120+20]=100;
  assert.match(objectIssues({...map,data},point).warnings[0],/chiếm dụng/);
  assert.ok(objectIssues(map,{...point,...canvasToWorld(map,-1,20)}).errors.length);
});

test('polygon validity and save payload excludes server fields',()=>{
  assert.ok(polygonValid([{x:0,y:0},{x:2,y:0},{x:1,y:2}]));
  assert.equal(polygonValid([{x:0,y:0},{x:3,y:2},{x:0,y:2},{x:2,y:0}]),false);
  assert.equal(polygonValid([{x:0,y:0},{x:1,y:0},{x:2,y:0}]),false);
  assert.equal('map_id' in objectPayload({id:'a',map_id:'b',created_at:'now'}),false);
});
