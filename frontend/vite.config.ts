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
      '/dashboard': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '/coach': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '/config': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '/preferences': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '/health': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
      '/oauth': { target: 'https://uprxy587ri.execute-api.us-east-1.amazonaws.com/prod', changeOrigin: true, secure: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
