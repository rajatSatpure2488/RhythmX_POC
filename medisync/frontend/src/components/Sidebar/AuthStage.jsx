/**
 * AuthStage — embeds the full AuthGate login UI inside the pipeline
 * content area when the user navigates to "EHR Authentication" in the sidebar.
 * Shown whether already connected (status summary) or not (login form).
 */
import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../context/AuthContext'
import AuthGate from './AuthGate'

/**
 * TokenBox — fetches the live DrChrono access token from GET /auth/token and lets
 * the user copy it (raw or as "Bearer <token>") for use in Postman / external tools.
 * The token is masked by default and revealed on hover.
 */
function TokenBox() {
  const [token, setToken]   = useState(null)
  const [meta, setMeta]     = useState({})
  const [error, setError]   = useState(null)
  const [copied, setCopied] = useState('')
  const [reveal, setReveal] = useState(false)

  const load = useCallback(() => {
    setError(null); setToken(null)
    fetch('/auth/token')
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || `HTTP ${r.status}`)))
      .then(d => { setToken(d.access_token); setMeta({ doctorId: d.doctor_id, expiresIn: d.expires_in_seconds }) })
      .catch(e => setError(typeof e === 'string' ? e : 'Could not load token'))
  }, [])

  useEffect(() => { load() }, [load])

  const copy = (text, label) => {
    navigator.clipboard.writeText(text)
      .then(() => { setCopied(label); setTimeout(() => setCopied(''), 1600) })
      .catch(() => setError('Clipboard blocked — select the token and copy manually.'))
  }

  const labelStyle = { fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }
  const btnStyle = { fontSize: '0.74rem', fontWeight: 600, padding: '5px 10px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--card-bg)', cursor: 'pointer', color: 'var(--text-primary)' }

  return (
    <div style={{ background: 'var(--app-bg)', borderRadius: 8, padding: '16px', marginBottom: 24, textAlign: 'left' }}>
      <div style={{ ...labelStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>DrChrono Access Token — for Postman</span>
        <button onClick={load} title="Refresh token" style={{ ...btnStyle, padding: '2px 8px', fontSize: '0.68rem' }}>↻</button>
      </div>

      {error && (
        <div style={{ fontSize: '0.78rem', color: 'var(--danger)' }}>
          {error} {error.includes('No active') || error.includes('401')
            ? '— connect to DrChrono first.' : ''}
        </div>
      )}

      {!error && !token && <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Loading token…</div>}

      {token && (
        <>
          <code
            onMouseEnter={() => setReveal(true)}
            onMouseLeave={() => setReveal(false)}
            onClick={() => copy(token, 'token')}
            title="Hover to reveal · click to copy the access token"
            style={{
              display: 'block', wordBreak: 'break-all', fontFamily: 'monospace',
              fontSize: '0.74rem', background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '8px 10px', marginBottom: 10, cursor: 'pointer',
              color: 'var(--text-primary)', lineHeight: 1.5,
            }}
          >
            {reveal ? token : `${token.slice(0, 10)}${'•'.repeat(24)}${token.slice(-6)}`}
          </code>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={() => copy(token, 'token')} title="Copy the raw access token" style={btnStyle}>
              {copied === 'token' ? '✓ Copied' : '📋 Copy Access Token'}
            </button>
            <button onClick={() => copy(`Bearer ${token}`, 'bearer')} title="Copy 'Bearer <token>' for the Authorization header in Postman" style={btnStyle}>
              {copied === 'bearer' ? '✓ Copied' : '📋 Copy Bearer Token'}
            </button>
          </div>

          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 8 }}>
            In Postman → Authorization → Type <strong>Bearer Token</strong>, paste the access token.
            {meta.expiresIn != null && ` Expires in ~${Math.max(0, Math.round(meta.expiresIn / 60))} min.`}
          </div>
        </>
      )}
    </div>
  )
}

export default function AuthStage({ onComplete }) {
  const { auth, logout } = useAuth()

  // Already connected — show a status card + option to reconnect
  if (auth.connected || auth.devMode) {
    return (
      <div style={{
        maxWidth: 560, margin: '48px auto', padding: '0 16px',
      }}>
        <div style={{
          background: 'var(--card-bg)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: '36px 40px',
          boxShadow: 'var(--shadow-md)', textAlign: 'center',
        }}>
          {/* Status badge */}
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            background: auth.devMode ? '#FEF3C7' : '#DCFCE7',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px',
          }}>
            {auth.devMode ? (
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#D97706" strokeWidth="2">
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
            ) : (
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            )}
          </div>

          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>
            {auth.devMode ? 'Developer Mode Active' : 'EHR Connected'}
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 24, lineHeight: 1.6 }}>
            {auth.devMode
              ? 'You are running in Developer Mode. No DrChrono connection is required. All pipeline stages are fully accessible.'
              : `Connected to DrChrono as Dr. ${auth.doctorName || auth.doctorId || '—'}. The pipeline is ready to push data.`
            }
          </p>

          {/* Details grid */}
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px',
            background: 'var(--app-bg)', borderRadius: 8, padding: '16px', marginBottom: 24,
            textAlign: 'left',
          }}>
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 3 }}>Mode</div>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {auth.devMode ? '⚡ Developer' : '🔒 Production'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 3 }}>EHR Provider</div>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>DrChrono</div>
            </div>
            {!auth.devMode && auth.doctorId && (
              <div style={{ gridColumn: '1/-1' }}>
                <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 3 }}>Doctor ID</div>
                <div style={{ fontSize: '0.82rem', fontFamily: 'monospace', color: 'var(--text-primary)' }}>{auth.doctorId}</div>
              </div>
            )}
          </div>

          {/* Access token copy panel — only in real DrChrono mode */}
          {!auth.devMode && <TokenBox />}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              className="btn btn--primary"
              onClick={() => onComplete?.()}
            >
              Continue to Ingestion →
            </button>
            <button
              className="btn btn--ghost"
              onClick={logout}
              style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}
            >
              {auth.devMode ? 'Exit Dev Mode' : 'Disconnect'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Not connected — render the full login form inline
  return (
    <div style={{ position: 'relative', overflow: 'hidden' }}>
      <AuthGate />
    </div>
  )
}
