import axios from 'axios'

const api = axios.create({
  baseURL: '/',          // Vite proxy handles routing to :8000
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Response interceptor — normalise errors while preserving HTTP status
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred'

    // Preserve the real HTTP status so catch blocks can show the right code
    const enriched = new Error(message)
    enriched.httpStatus   = err.response?.status ?? 0
    enriched.responseData = err.response?.data
    return Promise.reject(enriched)
  }
)

export default api
