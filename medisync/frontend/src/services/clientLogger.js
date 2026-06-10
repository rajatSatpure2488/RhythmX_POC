/**
 * clientLogger.js — ships browser-side events to the backend log file.
 *
 * Why: backend already writes to medisync/logs/medisync.log via core/logger.py.
 * This module mirrors important frontend events into the same file so a single
 * `tail -f` shows the whole system.
 *
 * What gets shipped (by default):
 *   - Uncaught JS errors (window.onerror)
 *   - Unhandled promise rejections
 *   - Any explicit clog.info / clog.warn / clog.error calls
 *
 * What is NOT shipped:
 *   - Every console.log (would be noisy + circular if we logged from interceptors)
 *
 * Reliability: a small in-memory queue is flushed via /logs/client/batch every
 * 1.5s and on page-hide. If the backend is unreachable, the queue keeps growing
 * to a cap so we don't leak memory.
 */
const BACKEND_BASE = 'http://localhost:8000'
const FLUSH_MS     = 1500
const MAX_QUEUE    = 200

const queue = []

function enqueue(entry) {
  queue.push({
    ...entry,
    url: typeof window !== 'undefined' ? window.location.href : undefined,
  })
  if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE)
}

async function flush() {
  if (!queue.length) return
  const batch = queue.splice(0, queue.length)
  try {
    await fetch(`${BACKEND_BASE}/logs/client/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries: batch }),
      keepalive: true,  // lets the request complete on page unload
    })
  } catch {
    // backend unreachable — drop this batch silently so we don't spin
  }
}

let timer = null
function scheduleFlush() {
  if (timer) return
  timer = setTimeout(() => { timer = null; flush() }, FLUSH_MS)
}

export const clog = {
  debug: (message, meta) => { enqueue({ level: 'debug', message, meta }); scheduleFlush() },
  info:  (message, meta) => { enqueue({ level: 'info',  message, meta }); scheduleFlush() },
  warn:  (message, meta) => { enqueue({ level: 'warn',  message, meta }); scheduleFlush() },
  error: (message, meta) => { enqueue({ level: 'error', message, meta }); scheduleFlush() },
}

export function installClientLogger() {
  if (typeof window === 'undefined') return

  window.addEventListener('error', (e) => {
    enqueue({
      level: 'error',
      message: e.message || 'window.onerror',
      source: e.filename ? `${e.filename}:${e.lineno}:${e.colno}` : undefined,
      stack: e.error?.stack,
    })
    scheduleFlush()
  })

  window.addEventListener('unhandledrejection', (e) => {
    const reason = e.reason
    enqueue({
      level: 'error',
      message: `Unhandled promise rejection: ${reason?.message || String(reason)}`,
      stack: reason?.stack,
    })
    scheduleFlush()
  })

  // Best-effort flush when the tab is hidden / unloaded.
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush()
  })
  window.addEventListener('pagehide', flush)

  clog.info('Frontend logger installed', { ua: navigator.userAgent })
}
