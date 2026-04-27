import { useAuth } from '../../context/AuthContext'
import { useState, useEffect } from 'react'

function formatExpiry(seconds) {
  if (!seconds || seconds <= 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function formatHandshake(ts) {
  if (!ts) return '—'
  return ts
}

export default function EHRPanel() {
  const { auth } = useAuth()
  const [countdown, setCountdown] = useState(auth.expiresIn)

  useEffect(() => {
    setCountdown(auth.expiresIn)
  }, [auth.expiresIn])

  // Tick down every minute
  useEffect(() => {
    if (!countdown) return
    const id = setInterval(() => setCountdown(prev => (prev > 60 ? prev - 60 : 0)), 60000)
    return () => clearInterval(id)
  }, [countdown])

  return (
    <aside className="right-panel">
      {/* EHR Authentication card */}
      <div className="panel-card">
        <div className="panel-card__header">
          <span className="panel-card__title">EHR Authentication</span>
          {/* grid icon */}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9CA3AF" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
          </svg>
        </div>

        {/* Connection badge */}
        <div className={`badge ${auth.connected ? 'badge--connected' : 'badge--disconnected'}`}>
          <span className="badge__dot" />
          {auth.connected ? 'CONNECTED' : 'DISCONNECTED'}
        </div>

        {/* Stat rows */}
        <div className="stat-row">
          <span className="stat-row__label">Target System</span>
          <span className="stat-row__value">{auth.targetSystem}</span>
        </div>
        <div className="stat-row">
          <span className="stat-row__label">Last Handshake</span>
          <span className="stat-row__value">{formatHandshake(auth.lastHandshake)}</span>
        </div>
        <div className="stat-row">
          <span className="stat-row__label">Token Expiry</span>
          <span className="stat-row__value" style={{ color: countdown && countdown < 1800 ? '#DC2626' : undefined }}>
            {formatExpiry(countdown)}
          </span>
        </div>

        <a className="panel-link" href="#" onClick={e => e.preventDefault()}>
          Manage Connection Config →
        </a>
      </div>

      {/* Ingestion guidelines */}
      <div className="info-box">
        <div className="info-box__title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm1 14h-2v-6h2zm0-8h-2V6h2z"/>
          </svg>
          Ingestion Guidelines
        </div>
        <p className="info-box__text">
          Ensure all unstructured notes are de-identified if not using the secure HIPAA-compliant tunnel.
          The ingestion pipeline will automatically map standard FHIR resources.
        </p>
      </div>
    </aside>
  )
}
