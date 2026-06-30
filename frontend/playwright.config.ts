import { defineConfig } from '@playwright/test';

// E2E runs against the PRODUCTION same-origin server: a single uvicorn process
// serves both the built SPA (frontend/dist) and the JSON API on :8000. This is
// required because the Vite dev proxy does NOT forward `/auth`, so the login
// flow (and therefore every authenticated page) only works same-origin on 8000.
//
// Start the server before running these tests (from the repo root):
//   SHIFT_FRONTEND_DIST="$PWD/frontend/dist" SHIFT_ADMIN_ID=admin \
//   SHIFT_ADMIN_PW=admin12345 uvicorn webapp.api.main:app \
//   --host 127.0.0.1 --port 8000
// then build the SPA (`npm run build`) and seed/freeze a June-2026 roster.
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: BASE_URL },
});
