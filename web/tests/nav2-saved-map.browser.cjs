// Ubuntu integration test: explicit simulation opt-in; persists a labeled test map for inspection.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),assert=require('node:assert/strict'),{randomUUID}=require('node:crypto');
assert.equal(process.env.NAV2_SIMULATION_TEST,'1','Explicitly opt into Gazebo motion');
assert.ok(process.env.NAV2_INITIAL_POSE,'Supply the known simulation initial pose as JSON');
assert.ok(process.env.NAV2_TEST_MAP_PREFIX,'Supply the generated warehouse.sdf map prefix');
const dir=process.env.NAV2_TEST_ARTIFACT_DIR||fs.mkdtempSync(require('os').tmpdir()+'/nav2-browser-');
fs.mkdirSync(dir,{recursive:true});
const base=process.env.TEST_BACKEND_URL||'http://127.0.0.1:8000/api';
const mapPrefix=process.env.NAV2_TEST_MAP_PREFIX;
async function api(path,method='GET',data){const r=await fetch(base+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const v=await r.json();assert.ok(r.ok,JSON.stringify(v));return v;}
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(test,seconds=65){let s;for(let i=0;i<seconds*2;i++){s=await api('/ros/map-session');if(test(s))return s;if(s.state==='FAILED')throw Error(JSON.stringify(s));await delay(500);}throw Error('Timeout '+JSON.stringify(s));}
(async()=>{
 const bridge=await api('/ros/map-session');
 assert.ok(bridge.enabled&&bridge.environment==='simulation','Managed simulation bridge required');
 const b=await chromium.launch({headless:true});
 try{
  const p=await b.newPage({viewport:{width:1600,height:1600}});p.setDefaultTimeout(20000);
  await p.goto(process.env.TEST_FRONTEND_URL||'http://127.0.0.1:5173',{waitUntil:'domcontentloaded'});
  const button=name=>p.getByRole('button',{name,exact:true});
  await button('Bản đồ & Sản phẩm').click();await button('Saved Map (server)').click();
  let map;
  if(fs.existsSync(dir+'/geometry-map.json'))map=JSON.parse(fs.readFileSync(dir+'/geometry-map.json'));
  else{
   await p.getByLabel('Tên bản đồ',{exact:true}).fill('SIMULATION ONLY - warehouse.sdf geometry');
   await p.getByLabel('ROS YAML',{exact:true}).setInputFiles(mapPrefix+'.yaml');
   await p.getByLabel('Ảnh bản đồ',{exact:true}).setInputFiles(mapPrefix+'.pgm');
   const [response]=await Promise.all([p.waitForResponse(r=>r.url().endsWith('/api/maps')&&r.request().method()==='POST'),button('Upload Map').click()]);
   assert.equal(response.status(),201);map=await response.json();fs.writeFileSync(dir+'/geometry-map.json',JSON.stringify(map));
  }
  await p.getByLabel('Bản đồ đã lưu',{exact:true}).selectOption(map.id);
  let layer=await api('/maps/'+map.id+'/planning');
  if(!layer.objects.length){
   layer=await api('/maps/'+map.id+'/planning','PUT',{revision:0,objects:[
    {id:randomUUID(),name:'SIM Destination',type:'DELIVERY',x:2,y:0,yaw:0},
    {id:randomUUID(),name:'SIM Keepout',type:'NO_GO',x:1,y:.2,yaw:0,vertices:[{x:-.2,y:-.35},{x:.2,y:-.35},{x:.2,y:.35},{x:-.2,y:.35}]}
   ]});
  }
  const pose=JSON.parse(process.env.NAV2_INITIAL_POSE);
  const destination=layer.objects.find(o=>o.type==='DELIVERY');
  destination.x=pose.x>1.5?0:2;
  layer=await api('/maps/'+map.id+'/planning','PUT',{revision:layer.revision,
    objects:layer.objects.map(({map_id,created_at,updated_at,...o})=>o)});
  await p.getByLabel('Tôi đã đối chiếu bản đồ này với môi trường Gazebo đang chạy.').check();
  await p.getByLabel('Đặt initial pose đã biết trong simulation (m, rad)').check();
  for(const k of ['x','y','yaw'])await p.getByLabel('Initial '+k,{exact:true}).fill(String(pose[k]));
  const [loadResponse]=await Promise.all([p.waitForResponse(r=>r.url().endsWith('/map-session/apply')&&r.request().method()==='POST'),button('Nạp bản đồ vào Nav2').click()]);
  const loadRequest=await loadResponse.json();assert.ok(loadResponse.ok(),JSON.stringify(loadRequest));
  await until(s=>s.request_id===loadRequest.request_id&&s.map_id===map.id&&s.map_verified&&s.nav2_active&&s.localization_valid);
  console.log('Map/localization confirmed');
  const [applyResponse]=await Promise.all([p.waitForResponse(r=>r.url().endsWith('/map-session/apply')&&r.request().method()==='POST'),button('Áp dụng vùng cấm').click()]);
  const applyRequest=await applyResponse.json();assert.ok(applyResponse.ok(),JSON.stringify(applyRequest));
  const session=await until(s=>s.request_id===applyRequest.request_id&&s.ready&&s.keepout_verified&&s.planning_revision===layer.revision);
  assert.ok(session.keepout_cells.global>0&&session.keepout_cells.local>0);
  console.log('Both costmaps confirmed',session);
  fs.writeFileSync(dir+'/3c-mask-result.json',JSON.stringify(session,null,2));
  await p.locator('.saved-map-navigation').screenshot({path:dir+'/3c-mask-web.png'});
  const target=layer.objects.find(o=>o.type==='DELIVERY');
  await p.getByLabel('Điểm quy hoạch',{exact:true}).selectOption(target.id);
  await Promise.all([p.waitForResponse(r=>r.url().endsWith('/navigation/goal')&&r.request().method()==='POST'),button('Đi tới điểm').click()]);
  let status,paths=[],poses=[],states=[];
  for(let i=0;i<360;i++){
   status=await api('/ros/navigation/status');states.push(status.state);
   const path=await api('/ros/navigation/path');if(path?.poses?.length){paths.push(path);if(paths.length===2)await p.locator('.map-panel').screenshot({path:dir+'/3c-path-web.png'});}
   poses.push(await api('/ros/pose'));
   if(['SUCCEEDED','FAILED','REJECTED','CANCELLED'].includes(status.state))break;
   await delay(500);
  }
  fs.writeFileSync(dir+'/3c-navigation-observed.json',JSON.stringify({status,paths,poses,states}));
  assert.equal(status.state,'SUCCEEDED',JSON.stringify(status));assert.ok(paths.length);
  for(const path of paths)for(const pt of path.poses)assert.ok(!(pt.x>=.8&&pt.x<=1.2&&pt.y>=-.15&&pt.y<=.55),'Path crosses NO-GO');
  assert.ok(paths.some(path=>path.poses.some(pt=>pt.x>.7&&pt.x<1.4&&(pt.y<-.4||pt.y>.8))));
  await p.locator('.map-panel').screenshot({path:dir+'/3c-web.png'});
  fs.writeFileSync(dir+'/3c-result.json',JSON.stringify({passed:true,session,status,states:[...new Set(states)],paths:paths.length,final:poses.at(-1)},null,2));
  console.log('PASS 3C: route avoids keepout and robot reached destination');
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
