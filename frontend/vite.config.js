import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'node:path'

const localApiProxy = {
  target: 'http://127.0.0.1:5000',
  changeOrigin: true,
}

// https://vite.dev/config/
export default defineConfig({
  logLevel: 'info',
  appType: 'spa',
  server: {
    proxy: {
      '/api': localApiProxy,
    },
  },
  preview: {
    proxy: {
      '/api': localApiProxy,
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
