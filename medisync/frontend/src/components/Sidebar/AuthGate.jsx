import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'

export default function AuthGate() {
  const { auth, initiateOAuth, setManualToken, enterDevMode } = useAuth()
  const [showManual, setShowManual] = useState(false)
  const [token, setToken]     = useState('')
  const [docId, setDocId]     = useState('')
  const [error, setError]     = useState(null)
  const [loading, setLoading] = useState(false)

  const handleManual = async (e) => {
    e.preventDefault()
    if (!token.trim() || !docId.trim()) {
      setError('Both fields are required.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await setManualToken(token.trim(), docId.trim())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-gate">
      {/* Background decorative blobs */}
      <div className="auth-gate__blob auth-gate__blob--1" />
      <div className="auth-gate__blob auth-gate__blob--2" />

      <div className="auth-gate__card">
        {/* Logo */}
        <div className="auth-gate__logo">MediSync</div>
        <div className="auth-gate__tagline">Clinical Notes Integration Platform</div>

        {/* Lock icon */}
        <div className="auth-gate__icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="#1565C0" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </div>

        <h1 className="auth-gate__title">Authentication Required</h1>
        <p className="auth-gate__desc">
          Connect your DrChrono EHR account to access the clinical
          data integration pipeline.
        </p>

        {/* Error from OAuth return */}
        {auth.error && (
          <div className="auth-gate__error">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/>
            </svg>
            {auth.error}
          </div>
        )}

        {/* Primary OAuth button */}
        {!showManual && (
          <>
            <button
              id="btn-oauth-connect"
              className="auth-gate__oauth-btn"
              onClick={initiateOAuth}
              disabled={auth.status === 'connecting'}
            >
              {auth.status === 'connecting' ? (
                <>
                  <span className="auth-gate__spinner" />
                  Redirecting to DrChrono…
                </>
              ) : (
                <>
                  {/* DrChrono-style icon */}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
                  </svg>
                  Connect with DrChrono
                </>
              )}
            </button>

            <div className="auth-gate__redirect-note">
              You'll be redirected to
              <span className="auth-gate__redirect-url"> app.drchrono.com </span>
              to log in and authorise access.
            </div>

            <div className="section-sep" style={{ margin: '20px 0' }}>or</div>

            <button
              id="btn-show-manual"
              className="auth-gate__manual-link"
              onClick={() => setShowManual(true)}
            >
              Use a manual access token instead →
            </button>

            {/* ══════ Developer Mode ══════ */}
            <div className="auth-gate__dev-section">
              <div className="auth-gate__dev-divider">
                <span>DEVELOPER</span>
              </div>
              <button
                id="btn-dev-mode"
                className="auth-gate__dev-btn"
                onClick={enterDevMode}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="16 18 22 12 16 6"/>
                  <polyline points="8 6 2 12 8 18"/>
                </svg>
                Enter Developer Mode
              </button>
              <p className="auth-gate__dev-note">
                Skip authentication and explore the full pipeline with simulated data.
                No DrChrono connection required.
              </p>
            </div>
          </>
        )}

        {/* Manual token fallback */}
        {showManual && (
          <form onSubmit={handleManual} className="auth-gate__manual-form">
            <div className="form-group">
              <label className="form-label" htmlFor="gate-token">Access Token</label>
              <input
                id="gate-token"
                className="form-input"
                type="password"
                placeholder="Paste DrChrono access token"
                value={token}
                onChange={e => setToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="gate-docid">Doctor ID</label>
              <input
                id="gate-docid"
                className="form-input"
                type="text"
                placeholder="e.g. 123456"
                value={docId}
                onChange={e => setDocId(e.target.value)}
              />
            </div>
            {error && (
              <p style={{ color: 'var(--danger)', fontSize: '0.75rem', marginBottom: 10 }}>{error}</p>
            )}
            <button
              id="btn-manual-connect"
              type="submit"
              className="auth-gate__oauth-btn"
              disabled={loading}
            >
              {loading ? 'Connecting…' : 'Connect'}
            </button>
            <button
              type="button"
              className="auth-gate__manual-link"
              style={{ marginTop: 10 }}
              onClick={() => setShowManual(false)}
            >
              ← Back to OAuth
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
