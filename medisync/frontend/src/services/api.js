import axios from 'axios'

const api = axios.create({
  baseURL: '/',          // Vite proxy handles routing to :8000
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Response interceptor — normalise errors
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred'
    return Promise.reject(new Error(message))
  }
)

export default api
