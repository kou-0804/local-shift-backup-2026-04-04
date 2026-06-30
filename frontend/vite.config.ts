import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies API calls to the FastAPI backend on :8000 so the SPA can
// use same-origin relative paths in both dev and prod.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/rosters': { target: 'http://localhost:8000', changeOrigin: true },
      '/jobs': { target: 'http://localhost:8000', changeOrigin: true },
      // Master-management API (P3). Without these, GET /master-sets and /masters/*
      // fall through to the SPA index.html and the master UI can never load data.
      '/masters': { target: 'http://localhost:8000', changeOrigin: true },
      '/master-sets': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
