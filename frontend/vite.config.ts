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
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('recharts') || id.includes('d3-')) return 'recharts';
            if (id.includes('react-i18next') || id.includes('i18next')) return 'i18n';
            if (id.includes('amazon-cognito')) return 'cognito';
            if (id.includes('@radix-ui')) return 'radix';
            if (id.includes('framer-motion') || id.includes('motion-dom') || id.includes('motion-utils')) return 'motion';
            if (id.includes('lucide-react')) return 'icons';
            if (id.includes('react-router')) return 'router';
            if (id.includes('/react-dom/') || id.includes('/react/') || id.includes('scheduler')) return 'react';
            return 'vendor';
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
