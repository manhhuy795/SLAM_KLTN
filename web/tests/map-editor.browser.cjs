// Run on Ubuntu with PLAYWRIGHT_MODULE pointing to an installed Playwright module.
// Requests are redirected to a temporary backend: no synthetic live map reaches the real database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const web = path.resolve(__dirname, '..');
const backend = path.join(web, 'backend');
const python = path.join(backend, '.venv/bin/python');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'map-editor-browser-'));
const fixtures = path.join(backend, 'tests/fixtures/maps');
const frontend = process.env.TEST_FRONTEND_URL || 'http://127.0.0.1:5173';
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
let server;
let browser;
async function until(check, description) {
  for (let i = 0; i < 100; i++) {
    try { if (await check()) return; } catch {}
    await delay(100);
  }
  throw new Error('Timed out: ' + description);
}

(async () => {
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  const api = 'http://127.0.0.1:' + port + '/api';
  const env = { ...process.env, WRMS_DATABASE_URL: 'sqlite:///' + temporary + '/maps.db',
    WRMS_MAPS_DIR: temporary + '/maps' };
  for (const script of ['init_db.py', 'seed.py']) {
    const result = spawnSync(python, [script], { cwd: backend, env, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
  const log = fs.openSync(path.join(temporary, 'backend.log'), 'a');
  async function start() {
    server = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
      '--port', String(port)], { cwd: backend, env, stdio: ['ignore', log, log] });
    await until(async () => (await fetch(api + '/health')).ok, 'backend ready');
  }
  async function stop() {
    if (server && server.exitCode == null) {
      const exit = new Promise(resolve => server.once('exit', resolve));
      server.kill('SIGTERM');
      await exit;
    }
  }
  await start();
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  page.setDefaultTimeout(15000);
  const errors = [];
  const serverErrors = [];
  page.on("response", r=>{if(r.status()>=500)serverErrors.push(r.status()+" "+r.url());});
  const frames = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('websocket', socket => socket.on('framereceived', event => {
    try { frames.push(JSON.parse(String(event.payload)).type); } catch {}
  }));
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    return route.continue({ url: api + url.pathname.slice(4) + url.search });
  });
  await page.addInitScript(({ port }) => {
    const OriginalSocket = window.WebSocket;
    window.WebSocket = class extends OriginalSocket {
      constructor(address, ...args) {
        super(String(address).replace(':8000/', ':' + port + '/'), ...args);
        window.mapTestSocket = this;
      }
    };
  }, { port });

  async function uploadMap(name) {
    const form=new FormData();
    form.set('name',name);
    form.set('yaml_file',new Blob([fs.readFileSync(path.join(fixtures,'import_demo.yaml'))]),'import_demo.yaml');
    form.set('image_file',new Blob([fs.readFileSync(path.join(fixtures,'import_demo.pgm'))]),'import_demo.pgm');
    const response=await fetch(api+'/maps',{method:'POST',body:form});
    assert.equal(response.status,201);
    return response.json();
  }
  const first=await uploadMap('EDITOR SYNTHETIC A'),second=await uploadMap('EDITOR SYNTHETIC B');
  const originalGrid=await fetch(api+'/maps/'+first.id).then(r=>r.json());
  const planning=()=>fetch(api+'/maps/'+first.id+'/planning').then(r=>r.json());
  async function warehouse() {
    await page.getByRole('button',{name:'Bản đồ & Sản phẩm',exact:true}).click();
    await page.getByRole('button',{name:'Saved Map (server)',exact:true}).click();
  }
  await page.goto(frontend,{waitUntil:"domcontentloaded"});
  await warehouse();
  await page.getByLabel('Bản đồ đã lưu',{exact:true}).selectOption(first.id);
  await page.getByRole('button',{name:'Chỉnh sửa bản đồ',exact:true}).click();
  const button=name=>page.getByRole('button',{name,exact:true});
  const field=name=>page.getByLabel(name,{exact:true});
  const world=(x,y)=>({x:-1.2+Math.cos(.35)*x*.1-Math.sin(.35)*(24-y)*.1,
    y:-.8+Math.sin(.35)*x*.1+Math.cos(.35)*(24-y)*.1});
  const close=(a,b)=>assert.ok(Math.abs(a-b)<.015,a+' != '+b);
  async function screen(x,y) {
    await page.locator('.planning-viewport').scrollIntoViewIfNeeded();
    const r=await page.locator('.planning-scene').boundingBox();
    return {x:r.x+x/32*r.width,y:r.y+y/24*r.height};
  }
  async function clickPixel(x,y) {const p=await screen(x,y);await page.mouse.click(p.x,p.y);}
  async function add(tool,x,y,name) {
    await button(tool).click();await clickPixel(x,y);
    await field('Tên đối tượng').fill(name);
    const p=world(x,y);
    close(Number(await field('X (m)').inputValue()),p.x);
    close(Number(await field('Y (m)').inputValue()),p.y);
  }
  await add('Add Rack',8,8,'RACK-A');
  await field('Rộng (m)').fill('0.4');
  await field('Dài (m)').fill('0.3');
  await add('Add Rack',20,8,'RACK-B');
  await add('Add Home',8,17,'HOME-A');
  await add('Add Pickup',14,17,'PICKUP-A');
  await add('Add Delivery',20,17,'DELIVERY-A');
  await add('Add Charging',26,17,'CHARGING-A');
  await button('Draw No-Go Zone').click();
  for(const [x,y] of [[20,12],[26,12],[26,15],[20,15]])await clickPixel(x,y);
  await button('Hoàn tất vùng cấm').click();
  await field('Tên đối tượng').fill('ZONE-A');
  const beforeVertex=await field('Đỉnh 1 X').inputValue();
  const handle=page.locator('[data-vertex="0"]');
  const h=await handle.boundingBox();
  await page.mouse.move(h.x+h.width/2,h.y+h.height/2);await page.mouse.down();
  await page.mouse.move(h.x+h.width/2-8,h.y+h.height/2+4,{steps:5});await page.mouse.up();
  assert.notEqual(await field('Đỉnh 1 X').inputValue(),beforeVertex);

  const rack=page.locator('g[aria-label="RACK: RACK-A"] polygon');
  const r=await rack.boundingBox(),target=await screen(10,9);
  await page.mouse.move(r.x+r.width/2,r.y+r.height/2);await page.mouse.down();
  await page.mouse.move(target.x,target.y,{steps:8});await page.mouse.up();
  close(Number(await field('X (m)').inputValue()),world(10,9).x);
  await field('Yaw (rad)').fill('0.8');
  const position=[await field('X (m)').inputValue(),await field('Y (m)').inputValue()];
  await button('Phóng to').click();
  await button('Pan').click();
  const vp=await page.locator('.planning-viewport').boundingBox();
  await page.mouse.move(vp.x+30,vp.y+30);await page.mouse.down();
  await page.mouse.move(vp.x+70,vp.y+55,{steps:5});await page.mouse.up();
  assert.deepEqual([await field('X (m)').inputValue(),await field('Y (m)').inputValue()],position);
  await button('Fit map').click();
  await field('X (m)').fill('10000');
  assert.equal(await button('Save').isDisabled(),true);
  await field('X (m)').fill(position[0]);

  page.once('dialog',dialog=>dialog.dismiss());
  await button('Nhiệm vụ').click();
  assert.equal(await button('Save').count(),1);
  assert.equal(await button('Live Map (ROS 2)').isDisabled(),true);
  await button('Save').click();
  await button('Chỉnh sửa bản đồ').waitFor();
  const saved=await planning();
  assert.equal(saved.objects.length,7);
  assert.ok(saved.objects.every(o=>o.map_id===first.id&&o.created_at&&o.updated_at));
  await until(()=>frames.includes('PLANNING_UPDATED'),'planning websocket');
  await page.locator('.planning-editor').screenshot({path:path.join(temporary,'saved-editor.png')});

  await page.reload({waitUntil:"domcontentloaded"});await warehouse();
  await until(async()=>await page.locator('.planning-object').count()===7,'refresh objects');
  assert.deepEqual((await planning()).objects,saved.objects);
  await stop();await start();
  await page.reload({waitUntil:"domcontentloaded"});await warehouse();
  await until(async()=>await page.locator('.planning-object').count()===7,'restart objects');
  assert.deepEqual((await planning()).objects,saved.objects);
  await page.route('**/api/maps/'+second.id+'/select',async route=>{
    await delay(300);await route.fallback();
  });
  await field('Bản đồ đã lưu').selectOption(second.id);
  assert.equal(await button('Chỉnh sửa bản đồ').isDisabled(),true);
  await button('Chỉnh sửa bản đồ').click();
  assert.equal(await page.locator('.planning-object').count(),0);
  await add('Add Home',12,12,'HOME-B');await button('Save').click();
  await button('Chỉnh sửa bản đồ').waitFor();
  await field('Bản đồ đã lưu').selectOption(first.id);
  await until(async()=>await page.locator('.planning-object').count()===7,'map isolation');

  await button('Chỉnh sửa bản đồ').click();
  await field('Đối tượng quy hoạch').selectOption({label:'RACK · RACK-A'});
  await button('Delete').click();
  page.once('dialog',dialog=>dialog.accept());
  await button('Cancel').click();
  await button('Chỉnh sửa bản đồ').waitFor();
  assert.equal(await page.locator('.planning-object').count(),7);
  await button('Chỉnh sửa bản đồ').click();
  await field('Đối tượng quy hoạch').selectOption({label:'RACK · RACK-A'});
  await field('Tên đối tượng').fill('LOCAL DRAFT');
  const current=await planning();
  const payload=current.objects.map(({map_id,created_at,updated_at,...o})=>o);
  const remote=await fetch(api+'/maps/'+first.id+'/planning',{method:'PUT',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.revision,objects:payload})});
  assert.equal(remote.status,200);
  await button('Save').click();
  await page.getByRole('alert').filter({hasText:'changed elsewhere'}).waitFor();
  assert.equal(await field('Tên đối tượng').inputValue(),'LOCAL DRAFT');
  page.once('dialog',dialog=>dialog.accept());await button('Cancel').click();
  await button('Chỉnh sửa bản đồ').waitFor();

  await button('Chỉnh sửa bản đồ').click();
  await field('Đối tượng quy hoạch').selectOption({label:'CHARGING · CHARGING-A'});
  await button('Delete').click();await button('Save').click();
  await button('Chỉnh sửa bản đồ').waitFor();
  assert.equal((await planning()).objects.length,6);
  assert.deepEqual(await fetch(api+'/maps/'+first.id).then(r=>r.json()),{...originalGrid,is_selected:true});
  await button('Live Map (ROS 2)').click();
  assert.equal(await button('Chỉnh sửa bản đồ').count(),0);
  const live={width:2,height:2,resolution:.1,origin:{x:0,y:0,yaw:0},frame_id:'map',map_hash:'EDITOR-LIVE-TEST',data:[0,100,-1,0]};
  assert.equal((await fetch(api+'/ros/map',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(live)})).status,200);
  await page.waitForFunction(()=>document.querySelector('canvas')?.width===2);
  for(const name of ['Nhiệm vụ','Tổng quan','Bản đồ & Sản phẩm'])await button(name).click();
  await button('Saved Map (server)').click();
  await until(async()=>await page.locator('.planning-object').count()===6,'return from old pages');
  assert.deepEqual(errors,[]);
  assert.deepEqual(serverErrors,[]);
  fs.writeFileSync(path.join(temporary,'result.json'),JSON.stringify({passed:true,
    checks:['all object types','drag rack','polygon vertex resize','numeric resize and yaw',
      'coordinates with rotated origin','zoom/pan invariant','boundary block','dirty navigation guard',
      'save/refresh/restart','map isolation','cancel rollback','delete save','revision conflict',
      'planning WS','grid unchanged','Live read-only','Task/Dashboard navigation','no JS errors']},null,2));
  console.log('PASS Map Editor browser tests. Evidence: '+temporary);
  await stop();fs.closeSync(log);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  if(server&&server.exitCode==null)server.kill('SIGTERM');
});
