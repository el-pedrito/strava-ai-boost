/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    global: 'globalThis',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '^/dashboard/': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '^/coach/': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '^/config/': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '^/preferences': {
        target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod',
        changeOrigin: true,
        secure: true,
        // Skip SPA navigation reloads: only proxy fetch/XHR requests (which include Authorization or accept JSON).
        bypass: (req) => {
          const accept = req.headers['accept'] ?? '';
          if (typeof accept === 'string' && accept.includes('text/html')) {
            return req.url ?? null;
          }
          return null;
        },
      },
      '^/health/': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '^/oauth/': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // Split only the heavy isolated libs that don't depend on React internals.
        // Keep React, React DOM, React Router, lucide, framer-motion in the main
        // bundle to avoid execution-order bugs across cross-chunk imports.
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('recharts') || id.includes('d3-')) return 'recharts';
            if (id.includes('amazon-cognito')) return 'cognito';
          }
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
