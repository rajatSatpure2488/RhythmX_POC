import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend target — defaults to localhost for host-based dev,
// overridden to http://backend:8000 in docker-compose so the
// frontend container reaches the backend service on the docker network.
const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8501,
    strictPort: true,          // Error if 8501 is taken — don't silently increment
    proxy: {
      '/auth':       { target: BACKEND, changeOrigin: true },
      '/upload':     { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 },
      '/mapping':    { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      '/dryrun':     { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      '/push':       { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 },
      '/ai':         { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      '/drchrono':   { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      '/fhir-proxy': { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      '/mapper':     { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
      // FHIR Pipeline Lab (independent — remove to disconnect)
      '/pipeline':   { target: BACKEND, changeOrigin: true, timeout: 60000,  proxyTimeout: 60000  },
    },
  },
})
