import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        // Set BACKEND_URL env var to point at a remote backend (staging, Railway, Render, etc.)
        // Falls back to local FastAPI dev server when unset.
        target: process.env.BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})

