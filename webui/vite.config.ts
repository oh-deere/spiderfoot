import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/webui/',  // production URL prefix for hashed assets
  server: {
    port: 5173,
    proxy: {
      // Every path except /static/webui/* proxies to CherryPy during dev.
      // Vite handles static assets; everything else (API, legacy pages) goes through.
      '^/(?!static/webui/|@vite|src|node_modules).*': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
