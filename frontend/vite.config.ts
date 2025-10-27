import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',  // Ensure correct base path for production
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,  // Disable sourcemaps for production
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})