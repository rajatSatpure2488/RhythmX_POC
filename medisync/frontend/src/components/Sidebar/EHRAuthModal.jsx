import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'

export default function EHRAuthModal({ onClose }) {
  const { auth, initiateOAuth, setManualToken } = useAuth()
  const [tab, setTab] = useState('oauth')       // oauth | manual
  const [token, setToken]   = useState('')
  const [docId, setDocId]   = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)

  const handleOAuth = async () => {
    setError(null)
    await initiateOAuth()
  }

  const handleManual = async (e) => {
    e.preventDefault()
    if (!token.trim() || !docId.trim()) {
      setError('Both Access Token and Doctor ID are required.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await setManualToken(token.trim(), docId.trim())
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal__header">
          <span className="modal__title" id="modal-title">EHR Authentication</span>
          <button className="modal__close" id="btn-close-auth-modal" onClick={onClose}>✕</button>
        </div>

        <div className="modal__body">
          {/* Current status */}
          {auth.connected && (
            <div className={`badge badge--connected`} style={{ marginBottom: 16 }}>
              <span className="badge__dot" /> Connected as {auth.doctorName}
            </div>
          )}

          {/* Tabs */}
          <div className="tab-group">
            <div id="tab-oauth"  className={`tab${tab === 'oauth'  ? ' active' : ''}`} onClick={() => setTab('oauth')}>
              OAuth 2.0
            </div>
            <div id="tab-manual" className={`tab${tab === 'manual' ? ' active' : ''}`} onClick={() => setTab('manual')}>
              Manual Token
            </div>
          </div>

          {/* OAuth tab */}
          {tab === 'oauth' && (
            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: 16, lineHeight: 1.6 }}>
                Redirects to DrChrono login in a new window. After granting permission,
                your token will be stored securely for this session.
              </p>
              <button
                id="btn-drchrono-oauth"
                className="btn btn--primary"
                style={{ marginTop: 0 }}
                onClick={handleOAuth}
                disabled={auth.status === 'connecting'}
              >
                {auth.status === 'connecting' ? 'Connecting…' : 'Link via DrChrono OAuth →'}
              </button>
            </div>
          )}

          {/* Manual token tab */}
          {tab === 'manual' && (
            <form onSubmit={handleManual}>
              <div className="form-group">
                <label className="form-label" htmlFor="input-access-token">Access Token</label>
                <input
                  id="input-access-token"
                  className="form-input"
                  type="password"
                  placeholder="Paste your DrChrono access token"
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="input-doctor-id">Doctor ID</label>
                <input
                  id="input-doctor-id"
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
                id="btn-connect-manual"
                type="submit"
                className="btn btn--primary"
                style={{ marginTop: 4 }}
                disabled={loading}
              >
                {loading ? 'Connecting…' : 'Connect'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
