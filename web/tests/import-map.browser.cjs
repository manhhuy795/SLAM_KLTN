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
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'import-map-browser-'));
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
  const errors = [];
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
  await page.goto(frontend,{waitUntil:"domcontentloaded"});
  await page.getByRole('button', {name:'Bản đồ & Sản phẩm', exact:true}).click();
  await page.getByRole('heading', {name:'Bản đồ kho và quản lý sản phẩm', exact:true}).waitFor();
  assert.equal(await page.getByRole('button', {name:'Live Map (ROS 2)', exact:true}).getAttribute('aria-pressed'), 'true');
  await page.getByRole('button', { name: 'Saved Map (server)', exact: true }).click();
  await page.getByText('Chưa chọn bản đồ đã lưu.', { exact: false }).waitFor();
  assert.equal((await fetch(api + '/ros/state').then(r => r.json())).bridge_online, false);

  async function upload(name, yaml, image) {
    await page.waitForFunction(() => window.mapTestSocket?.readyState === WebSocket.OPEN);
    await page.getByLabel('Tên bản đồ', { exact: true }).fill(name);
    await page.getByLabel('ROS YAML', { exact: true }).setInputFiles(yaml);
    await page.getByLabel('Ảnh bản đồ', { exact: true }).setInputFiles(image);
    await page.getByRole('button', { name: 'Upload Map', exact: true }).click();
    await page.getByRole('button', { name: 'Upload Map', exact: true }).waitFor();
  }
  await upload('Browser PGM TEST', path.join(fixtures, 'import_demo.yaml'), path.join(fixtures, 'import_demo.pgm'));
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 32);
  await page.getByText('origin [-1.2, -0.8, 0.35]', { exact: false }).waitFor();
  const pixels = await page.locator('canvas').evaluate(canvas => {
    const context = canvas.getContext('2d');
    return [[0, 0], [30, 1], [1, 22], [6, 4]].map(([x, y]) =>
      Array.from(context.getImageData(x, y, 1, 1).data));
  });
  assert.deepEqual(pixels, [[220,226,232,255], [8,11,15,255], [39,55,67,255], [220,226,232,255]]);
  assert.equal(await page.locator('canvas').evaluate(c => getComputedStyle(c).objectFit), 'contain');
  await until(() => frames.includes('SAVED_MAPS_UPDATED'), 'saved map websocket event');
  await page.locator('.map-panel').screenshot({ path: path.join(temporary, 'saved-pgm.png') });
  const saved = await fetch(api + '/maps/selected').then(r => r.json());

  const live = { width: 4, height: 3, resolution: .2, origin: {x:0,y:0,yaw:0},
    frame_id: 'map', map_hash: 'SYNTHETIC_LIVE_TEST_ONLY', data: Array(12).fill(0) };
  assert.equal((await fetch(api + '/ros/map', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(live)})).status, 200);
  await until(() => frames.includes('SLAM_MAP_UPDATED'), 'live map websocket event');
  assert.equal(await page.locator('canvas').evaluate(c => c.width), 32);
  await page.getByRole('button', {name:'Live Map (ROS 2)', exact:true}).click();
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 4);
  await page.getByRole('button', {name:'Saved Map (server)', exact:true}).click();
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 32);

  await stop();
  await start();
  assert.deepEqual(await fetch(api + '/maps/selected').then(r => r.json()), saved);
  await page.reload({waitUntil:"domcontentloaded"});
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 32);
  assert.equal(await page.getByRole('button', {name:'Saved Map (server)', exact:true}).getAttribute('aria-pressed'), 'true');
  await page.getByRole('button', {name:'Bản đồ & Sản phẩm', exact:true}).click();
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 32);
  assert.equal(await page.getByRole('button', {name:'Saved Map (server)', exact:true}).getAttribute('aria-pressed'), 'true');
  assert.equal((await fetch(api + '/ros/state').then(r => r.json())).bridge_online, false);

  fs.writeFileSync(path.join(temporary, 'sample.yaml'),
    'image: sample.png\nresolution: 0.25\norigin: [-2, 3, 1.2]\nnegate: 0\nfree_thresh: 0.196\noccupied_thresh: 0.65\n');
  const created = spawnSync(python, ['-c',
    'from PIL import Image; import sys; im=Image.new("L",(3,2)); im.putdata([0,255,205,255,0,128]); im.save(sys.argv[1])',
    path.join(temporary, 'sample.png')], { encoding:'utf8' });
  assert.equal(created.status, 0, created.stderr);
  await upload('Browser PNG TEST', path.join(temporary, 'sample.yaml'), path.join(temporary, 'sample.png'));
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 3);
  const pngPixels = await page.locator('canvas').evaluate(c => Array.from(c.getContext('2d').getImageData(0,0,3,2).data));
  assert.deepEqual(pngPixels, [220,226,232,255,39,55,67,255,8,11,15,255,39,55,67,255,220,226,232,255,8,11,15,255]);
  await page.locator('.map-panel').screenshot({path:path.join(temporary,'saved-png.png')});
  await page.getByLabel('Bản đồ đã lưu', {exact:true}).selectOption(saved.id);
  await page.waitForFunction(() => document.querySelector('canvas')?.width === 32);

  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Xóa bản đồ',exact:true}).click();
  await page.getByText('Chưa chọn bản đồ đã lưu.',{exact:false}).waitFor();
  assert.equal((await fetch(api + '/maps/' + saved.id)).status,404);
  assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync(path.join(temporary,'result.json'),JSON.stringify({
    passed:true,checks:['warehouse map page','PGM UI upload','PNG UI upload','canvas pixel orientation','origin/resolution',
      'aspect ratio','Live/Saved switching','live WS isolation','restart persistence without ROS',
      'saved map WS','select','delete','no browser exceptions'],screenshots:['saved-pgm.png','saved-png.png']
  },null,2));
  console.log('PASS: import map browser checks. Evidence: ' + temporary);
  await stop();
  fs.closeSync(log);
})().catch(error => {console.error(error);process.exitCode=1;}).finally(async () => {
  if(browser) await browser.close();
  if(server && server.exitCode==null) server.kill('SIGTERM');
});
