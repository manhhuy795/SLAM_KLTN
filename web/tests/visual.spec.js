import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const screenshotDir = join(import.meta.dirname, 'screenshots');
const sizes = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];
const map = {
  id: 'qa-map', name: 'QA warehouse', map_hash: 'qa-hash', frame_id: 'map',
  width: 40, height: 30, resolution: 0.1,
  origin: { x: 0, y: 0, yaw: 0 }, data: Array(1200).fill(0),
};
const robots = [
  { id: 1, robot_code: 'AMR-01', robot_type: 'AMR', model: 'QA AMR', is_active: true,
    status: { online: true, state: 'IDLE', battery_percent: 82, x: 2, y: 1.5, yaw: 0, localization_quality: 'GOOD' } },
  { id: 2, robot_code: 'LINE-01', robot_type: 'LINE', model: 'QA AGV', is_active: true,
    status: { online: true, state: 'IDLE', battery_percent: 70, x: 0.5, y: 0.7, yaw: 0, line_segment_id: 1 } },
];

async function mockBackend(page, mode) {
  const errors = [];
  const blocked = [];
  const unknown = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.routeWebSocket('**/ws', socket => { socket.onMessage(() => {}); });
  await page.addInitScript(() => {
    localStorage.setItem('wrms-agv-align-qa-hash', JSON.stringify({
      map_id: 'qa-map', map_hash: 'qa-hash',
      a: { x: 0.2, y: 2.5 }, b: { x: 0.2, y: 0.99 }, d: { x: 1.74, y: 2.5 },
    }));
  });
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice(4);
    if (request.method() !== 'GET') {
      blocked.push(`${request.method()} ${path}`);
      await route.fulfill({ status: 403, json: { detail: 'Visual QA blocks all mutations' } });
      return;
    }
    const responses = {
      '/robots': robots,
      '/tasks': [],
      '/alerts': [],
      '/operators': [{ id: 1, name: 'QA Operator' }],
      '/locations': [],
      '/products': [],
      '/history': [],
      '/ros/state': { bridge_online: true, slam_online: true, nav2_online: true,
        map_status: 'RECEIVED', lidar_online: true, localization_available: true,
        tf_available: true, heartbeat_timeout_sec: 60 },
      '/ros/map': mode === 'fallback' ? null : map,
      '/ros/pose': { robot_id: 1, frame_id: 'map', timestamp: Date.now() / 1000,
        x: 2, y: 1.5, yaw: 0 },
      '/ros/navigation/status': { state: 'IDLE', goal: null, distance_remaining: null },
      '/ros/navigation/path': { frame_id: 'map', poses: [{ x: 0.5, y: 0.5 }, { x: 2, y: 1.5 }] },
      '/ros/map-session': { enabled: false, state: 'OFFLINE', map_id: null, map_hash: null },
      '/maps': [map],
      '/maps/selected': mode === 'saved' ? map : null,
      '/maps/qa-map/planning': { map_id: 'qa-map', revision: 1, objects: [] },
      '/agv/LINE-01/state': { robot_code: 'LINE-01', connected: true, commands_enabled: false,
        telemetry: { x: 0.5, y: 0.7, yaw: 0, state: 'IDLE', line_mask: 5,
          ticks_l: 10, ticks_r: 11, speed: 0, dist: 0.2, pwm_l: 0, pwm_r: 0, line_err: 0 },
        trail: [[0, 0], [0.5, 0.7]], last_ack_id: 1, command_status: 'NONE' },
      '/agv/LINE-01/mission-config': { robot_code: 'LINE-01', robot_id: 2,
        selected_map: { id: 'qa-map', name: 'QA warehouse' }, station_location_ids: {},
        graph: null, policy: null, revision: null, simulation_status: 'BLOCKED',
        hardware_status: 'BLOCKED', hardware_blockers: ['Physical station evidence unverified'],
        errors: ['HOME: select an existing active location', 'PICKUP: select an existing active location'],
        checklist: [
          { id: 'robot', ok: true, detail: 'OK' },
          { id: 'backend', ok: true, detail: 'OK' },
          { id: 'telemetry', ok: true, detail: 'OK' },
          { id: 'map', ok: true, detail: 'OK' },
          { id: 'HOME', ok: false, detail: 'Configure HOME' },
          { id: 'PICKUP', ok: false, detail: 'Configure PICKUP' },
          { id: 'racks', ok: false, detail: 'Configure racks' },
          { id: 'graph', ok: false, detail: 'Provide routes' },
          { id: 'class_mapping', ok: false, detail: 'Map classes' },
          { id: 'vision', ok: false, detail: 'Validate capture' },
          { id: 'dispatch', ok: false, detail: 'Disabled' },
        ] },
      '/agv/LINE-01/mission-preview': { validation: { simulation_status: 'BLOCKED',
        errors: ['HOME: select an existing active location'] }, sequence: [], target_rack: null },
    };
    if (!(path in responses)) {
      unknown.push(path);
      await route.fulfill({ status: 501, json: { detail: `No QA fixture for ${path}` } });
      return;
    }
    await route.fulfill({ json: responses[path] });
  });
  return { errors, blocked, unknown };
}

async function checkPage(page, network) {
  const layout = await page.evaluate(() => {
    const overflows = ['html', 'body', '.app-body', 'main'].flatMap(selector =>
      [...document.querySelectorAll(selector)]
        .filter(element => element.getBoundingClientRect().width > 0 && element.scrollWidth > element.clientWidth + 1)
        .map(element => `${selector}: ${element.scrollWidth} > ${element.clientWidth}`));
    const main = document.querySelector('.dashboard-main-column')?.getBoundingClientRect();
    const side = document.querySelector('.dashboard-side-column')?.getBoundingClientRect();
    const overlap = main && side
      ? Math.max(0, Math.min(main.right, side.right) - Math.max(main.left, side.left))
        * Math.max(0, Math.min(main.bottom, side.bottom) - Math.max(main.top, side.top))
      : 0;
    return { overflows, overlap };
  });
  expect(layout.overflows).toEqual([]);
  expect(layout.overlap).toBe(0);
  expect(await page.locator('body').evaluate(element =>
    getComputedStyle(element).backgroundColor)).toBe('rgb(248, 250, 252)');
  expect(network.blocked).toEqual([]);
  expect(network.unknown).toEqual([]);
  expect(network.errors).toEqual([]);
}

async function screenshot(page, name) {
  await mkdir(screenshotDir, { recursive: true });
  await page.screenshot({ path: join(screenshotDir, `${name}.png`), fullPage: true });
}

async function openNav(page, index) {
  const menu = page.getByRole('button', { name: 'Mở menu' });
  const mobile = await menu.isVisible();
  if (mobile) await menu.click();
  await page.locator('.sidebar-link').nth(index).click();
  if (mobile) await expect.poll(() => page.locator('.sidebar').evaluate(element =>
    element.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
}

for (const size of sizes) {
  const label = `${size.width}x${size.height}`;
  test.describe(label, () => {
    test.use({ viewport: size });

    test('dashboard, robot panels, and fallback map', async ({ page }) => {
      const network = await mockBackend(page, 'fallback');
      await page.goto('/');
      await expect(page.locator('.dashboard-grid')).toBeVisible();
      await expect(page.locator('.robot-card--green')).toContainText('LINE-01');
      await expect(page.locator('.robot-card--orange')).toContainText('2.0, 1.5 m');
      await expect(page.locator('.robot-card--green')).toContainText('N/A');
      await expect(page.locator('.robot-card')).toHaveCount(2);
      await expect(page.locator('.robot-card').getByRole('button', { name: 'Xem chi tiết robot' })).toHaveCount(2);
      await expect(page.getByRole('img', { name: /Sơ đồ thử nghiệm AGV/ })).toHaveCount(0);
      await expect(page.locator('.agv-camera-preview')).toHaveCount(0);
      await expect(page.getByLabel('SLAM status')).toBeVisible();
      await expect(page.locator('.warehouse-map-schematic svg')).toBeVisible();
      await expect(page.locator('.warehouse-map-schematic [fill="url(#hazard-pattern)"]')).toBeVisible();
      await expect(page.locator('.warehouse-map-schematic').getByText('AMR-01')).toBeVisible();
      await expect(page.locator('.warehouse-map-schematic svg').getByText('LINE-01')).toHaveCount(0);
      await expect(page.locator('.warehouse-map-schematic').getByText('LINE-01: POSITION_UNKNOWN / UNCALIBRATED')).toBeVisible();
      await screenshot(page, `${label}-fallback-dashboard`);
      await checkPage(page, network);
    });

    test('live map and AMR path', async ({ page }) => {
      const network = await mockBackend(page, 'live');
      await page.goto('/');
      await expect(page.getByRole('button', { name: 'Live Map (ROS 2)' })).toHaveAttribute('aria-pressed', 'true');
      const canvas = page.getByRole('img', { name: 'SLAM occupancy grid and robot pose' });
      await expect(canvas).toBeVisible();
      await expect.poll(() => canvas.evaluate(element => element.width)).toBe(map.width);
      expect(await canvas.evaluate(element => {
        const pixels = element.getContext('2d').getImageData(0, 0, element.width, element.height).data;
        for (let index = 0; index < pixels.length; index += 4) {
          if (pixels[index] === 255 && pixels[index + 1] === 115 && pixels[index + 2] === 0) return true;
        }
        return false;
      })).toBe(true);
      await screenshot(page, `${label}-live-map`);
      await checkPage(page, network);
    });

    test('saved map, AGV overlay, and map editor', async ({ page }) => {
      const network = await mockBackend(page, 'saved');
      await page.goto('/');
      await expect(page.getByRole('button', { name: 'Saved Map (server)' })).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('.planning-editor')).toBeVisible();
      await expect(page.getByLabel('AGV LINE-01')).toBeVisible();
      await expect(page.getByRole('img', { name: 'SLAM occupancy grid and robot pose' })).toBeVisible();
      await page.getByRole('button', { name: 'Live Map (ROS 2)' }).click();
      await expect(page.locator('.planning-editor')).toHaveCount(0);
      await page.getByRole('button', { name: 'Saved Map (server)' }).click();
      await expect(page.locator('.planning-editor')).toBeVisible();
      await page.getByRole('button', { name: 'Chỉnh sửa bản đồ' }).click();
      await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
      await expect(page.getByLabel('Khung quy hoạch bản đồ')).toBeVisible();
      await screenshot(page, `${label}-saved-map-editor`);
      await checkPage(page, network);
    });
  });
}

test('sidebar reaches every page at desktop and mobile', async ({ browser }) => {
  for (const size of [sizes[1], sizes[3]]) {
    const page = await browser.newPage({ viewport: size });
    const network = await mockBackend(page, 'fallback');
    await page.goto('/');
    await openNav(page, 1);
    await expect(page.locator('.page-content h1')).toBeVisible();
    await screenshot(page, `${size.width}x${size.height}-tasks`);
    await checkPage(page, network);
    await openNav(page, 2);
    await expect(page.getByRole('heading', { name: 'Quản lý robot' })).toBeVisible();
    await screenshot(page, `${size.width}x${size.height}-robots`);
    await checkPage(page, network);
    await openNav(page, 3);
    await expect(page.locator('.map-products-page')).toBeVisible();
    await screenshot(page, `${size.width}x${size.height}-map-page`);
    await checkPage(page, network);
    await openNav(page, 4);
    await expect(page.getByRole('heading', { name: 'Quản lý cảnh báo' })).toBeVisible();
    await checkPage(page, network);
    await openNav(page, 5);
    await expect(page.getByRole('heading', { name: 'Lịch sử vận hành' })).toBeVisible();
    await screenshot(page, `${size.width}x${size.height}-history`);
    await checkPage(page, network);
    await page.close();
  }
});

test('LINE camera preview stops when leaving its existing Robot tab', async ({ page }) => {
  const network = await mockBackend(page, 'fallback');
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: async () => {
        const canvas = document.createElement('canvas');
        const stream = canvas.captureStream(1);
        window.qaCameraTrack = stream.getVideoTracks()[0];
        return stream;
      },
      enumerateDevices: async () => [{ kind: 'videoinput', deviceId: 'qa-camera', label: 'QA camera' }],
    } });
  });
  await page.goto('/');
  await page.locator('.robot-card--green').getByRole('button', { name: 'Xem chi tiết robot' }).click();
  await page.getByRole('button', { name: 'Camera', exact: true }).click();
  await expect(page.locator('.robot-detail-page .agv-camera-preview')).toBeVisible();
  await page.getByRole('button', { name: 'Mở camera USB' }).click();
  await expect(page.locator('.robot-detail-page video')).toBeVisible();
  await page.getByRole('button', { name: 'Telemetry', exact: true }).click();
  expect(await page.evaluate(() => window.qaCameraTrack.readyState)).toBe('ended');
  await checkPage(page, network);
});

test('stale LINE telemetry is not shown as a live measurement', async ({ page }) => {
  const network = await mockBackend(page, 'fallback');
  await page.route('**/api/agv/LINE-01/state', route => route.fulfill({ json: {
    robot_code: 'LINE-01', connected: false, last_seen_age_ms: 8000,
    commands_enabled: false, telemetry: { x: 999, y: 999, line_mask: 31 },
  } }));
  await page.goto('/');
  await page.locator('.robot-card--green').getByRole('button', { name: 'Xem chi tiết robot' }).click();
  await page.getByRole('button', { name: 'Telemetry', exact: true }).click();
  const telemetry = page.getByLabel('AGV telemetry');
  await expect(telemetry).toContainText('OFFLINE');
  await expect(telemetry).not.toContainText('999');
  await checkPage(page, network);
});

test('LINE details separate real telemetry from unavailable sensors and test tools', async ({ page }) => {
  const network = await mockBackend(page, 'fallback');
  await page.goto('/?page=robots&robot=LINE-01');
  await page.getByRole('button', { name: 'Telemetry', exact: true }).click();
  const telemetry = page.getByLabel('AGV telemetry');
  await expect(telemetry).toContainText('Encoder trái');
  await expect(telemetry).toContainText('10 ticks');
  await expect(telemetry).toContainText('RPM trái / phải');
  await expect(telemetry).toContainText('firmware chưa gửi RPM');
  await expect(telemetry).toContainText('Odometry là tọa độ local');
  await page.getByRole('button', { name: 'Chẩn đoán' }).click();
  await expect(page.getByRole('img', { name: /Sơ đồ thử nghiệm AGV/ })).toBeVisible();
  await expect(page.locator('.agv-telemetry-json')).toContainText('"ticks_l": 10');
  await expect(page.getByRole('button', { name: 'M1', exact: true })).toBeDisabled();
  await checkPage(page, network);
});

test('LINE mission configuration stays in Robot Management and preview is read-only', async ({ page }) => {
  const network = await mockBackend(page, 'fallback');
  await page.goto('/?page=robots&robot=LINE-01');
  const config = page.getByLabel('AGV mission configuration');
  await expect(config).toBeVisible();
  await expect(config).toContainText('MISSION CONFIGURATION');
  await expect(config).toContainText('HOME: select an existing active location');
  await expect(config).toContainText('BLOCKED');
  await config.getByLabel('Cargo class').selectOption('cylinder');
  await config.getByRole('button', { name: 'Xem tuyến, không tạo task' }).click();
  await expect(config).toContainText('HOME → PICKUP → CLASSIFY');
  await expect(page.locator('.dashboard-grid')).toHaveCount(0);
  await checkPage(page, network);
});

test('dashboard robot links, history and invalid direct link', async ({ page }) => {
  const network = await mockBackend(page, 'fallback');
  await page.goto('/');
  await page.locator('.robot-card--green').getByRole('button', { name: 'Xem chi tiết robot' }).click();
  await expect(page).toHaveURL(/page=robots&robot=LINE-01/);
  await expect(page.locator('.sidebar-link--active')).toContainText('Robot');
  await expect(page.locator('.robot-detail-page h2')).toHaveText('LINE-01');
  await page.goBack();
  await expect(page.locator('.dashboard-grid')).toBeVisible();
  await page.locator('.robot-card--orange').getByRole('button', { name: 'Xem chi tiết robot' }).click();
  await expect(page.locator('.robot-detail-page h2')).toHaveText('AMR-01');
  await page.goBack();
  await page.goForward();
  await expect(page.locator('.robot-detail-page h2')).toHaveText('AMR-01');
  await page.goto('/?page=robots&robot=LINE-01');
  await expect(page.locator('.robot-detail-page h2')).toHaveText('LINE-01');
  await page.goto('/?page=robots&robot=NO-SUCH-ROBOT');
  await expect(page.locator('.page-shell')).toContainText('không tồn tại');
  await checkPage(page, network);
});
