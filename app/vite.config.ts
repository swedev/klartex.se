import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev we proxy /api → api.klartex.se so the browser never sees a
// cross-origin request and we don't need to relax Caddy's strict CORS
// (`Access-Control-Allow-Origin: https://app.klartex.se`). The /api
// prefix is stripped so frontend code calls endpoints by their real
// names (`/render`, `/page-templates`, …).
//
// In prod the app runs on app.klartex.se, hits api.klartex.se directly,
// and Caddy's strict CORS allows the origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'https://api.klartex.se',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
