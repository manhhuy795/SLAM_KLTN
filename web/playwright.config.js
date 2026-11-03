import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: 'visual.spec.js',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173/', browserName: 'chromium' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173/',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
