/**
 * ApiRateContext — Tracks real API calls in a 60-second sliding window.
 *
 * Usage:
 *   const { rate, limit, recordCall } = useApiRate()
 *   recordCall()  ← call this whenever you make an API request
 *
 * The sidebar reads `rate` and `limit` to render the live monitor bar.
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'

const ApiRateContext = createContext(null)

const LIMIT       = 500          // DrChrono default: 500 req/min
const WINDOW_MS   = 60_000       // 1 minute sliding window
const TICK_MS     = 1_000        // update every second

export function ApiRateProvider({ children }) {
  // Each entry = timestamp (ms) of one API call
  const callsRef  = useRef([])
  const [rate, setRate] = useState(0)   // calls in last 60 s

  // Prune old entries and recompute rate every second
  useEffect(() => {
    const id = setInterval(() => {
      const now     = Date.now()
      const cutoff  = now - WINDOW_MS
      callsRef.current = callsRef.current.filter(t => t > cutoff)
      setRate(callsRef.current.length)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [])

  // Call this every time an API request fires
  const recordCall = useCallback((n = 1) => {
    const now = Date.now()
    for (let i = 0; i < n; i++) callsRef.current.push(now + i)
  }, [])

  const pct        = Math.min(100, Math.round((rate / LIMIT) * 100))
  const color      = pct > 80 ? '#dc2626' : pct > 60 ? '#d97706' : '#16a34a'
  const remaining  = Math.max(0, LIMIT - rate)

  return (
    <ApiRateContext.Provider value={{ rate, limit: LIMIT, pct, color, remaining, recordCall }}>
      {children}
    </ApiRateContext.Provider>
  )
}

export const useApiRate = () => useContext(ApiRateContext)
