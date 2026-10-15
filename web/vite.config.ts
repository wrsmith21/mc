import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { '/api': { target: process.env.API_TARGET ?? 'http://127.0.0.1:8001', changeOrigin: true } },
  },
})
