import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // The dev server proxies API calls to the FastAPI backend on :8000.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
  },
  use: { baseURL: 'http://localhost:5173' },
});
