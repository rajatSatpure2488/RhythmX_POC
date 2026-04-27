import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8501,
    strictPort: true,          // Error if 8501 is taken — don't silently increment
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 120000,       // 2 min for large file/folder uploads
        proxyTimeout: 120000,
      },
      '/mapping': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 60000,
        proxyTimeout: 60000,
      },
      '/dryrun': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 60000,
        proxyTimeout: 60000,
      },
      '/push': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
})
