const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'
const SHARED_NODE_MODULES = process.env.SHARED_NODE_MODULES

export default {
  base: './',
  resolve: {
    alias: SHARED_NODE_MODULES
      ? {
          react: `${SHARED_NODE_MODULES}/react`,
          'react-dom': `${SHARED_NODE_MODULES}/react-dom`,
          'react/jsx-runtime': `${SHARED_NODE_MODULES}/react/jsx-runtime.js`
        }
      : {}
  },
  server: {
    port: 8502,
    strictPort: true,
    proxy: {
      '/load': { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 },
      '/load-single': { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 },
      '/status': { target: BACKEND, changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
      '/clear': { target: BACKEND, changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
      '/call-uploaded-file': { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 },
      '/call-uploaded-files': { target: BACKEND, changeOrigin: true, timeout: 120000, proxyTimeout: 120000 }
    }
  }
}
