/**
 * ApiRateContext — live API-rate monitor.
 *
 * The real rate-limited calls are the DrChrono pushes that happen on the BACKEND, so
 * this polls GET /logs/api (derived from the loguru log buffer in core/logger.py) for
 * the true calls/min, and also tracks any client-side calls via recordCall() for
 * instant feedback. The displayed rate is the larger of the two.
 *
 * Usage:
 *   const { rate, limit, pct, color, recordCall } = useApiRate()
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'

const ApiRateContext = createContext(null)

const BACKEND_BASE  = 'http://localhost:8000'
const DEFAULT_LIMIT = 29          // DrChrono per-minute push throttle
const WINDOW_MS     = 60_000      // 1 minute sliding window
const TICK_MS       = 1_000       // recompute client window every second
const POLL_MS       = 3_000       // poll backend monitor every 3 s

export function ApiRateProvider({ children }) {
  const callsRef = useRef([])                       // client-side call timestamps (ms)
  const [clientRate, setClientRate] = useState(0)
  const [backend, setBackend] = useState({ used: 0, limit: DEFAULT_LIMIT })

  // Prune the client-side window and recompute every second.
  useEffect(() => {
    const id = setInterval(() => {
      const cutoff = Date.now() - WINDOW_MS
      callsRef.current = callsRef.current.filter(t => t > cutoff)
      setClientRate(callsRef.current.length)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [])

  // Poll the backend API monitor for real DrChrono push activity.
  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await fetch(`${BACKEND_BASE}/logs/api?window_seconds=60&rate_limit=${DEFAULT_LIMIT}`)
        if (!r.ok) return
        const data = await r.json()
        if (alive) setBackend({ used: data.used ?? 0, limit: data.rate_limit ?? DEFAULT_LIMIT })
      } catch {
        // backend unreachable — keep the last known value
      }
    }
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // Call this every time the frontend itself fires an API request.
  const recordCall = useCallback((n = 1) => {
    const now = Date.now()
    for (let i = 0; i < n; i++) callsRef.current.push(now + i)
  }, [])

  const limit     = backend.limit || DEFAULT_LIMIT
  const rate      = Math.max(clientRate, backend.used)
  const pct       = Math.min(100, Math.round((rate / limit) * 100))
  const color     = pct > 80 ? '#dc2626' : pct > 60 ? '#d97706' : '#16a34a'
  const remaining = Math.max(0, limit - rate)

  return (
    <ApiRateContext.Provider value={{ rate, limit, pct, color, remaining, recordCall }}>
      {children}
    </ApiRateContext.Provider>
  )
}

export const useApiRate = () => useContext(ApiRateContext)
