/**
 * AuthStage — embeds the full AuthGate login UI inside the pipeline
 * content area when the user navigates to "EHR Authentication" in the sidebar.
 * Shown whether already connected (status summary) or not (login form).
 */
import { useAuth } from '../../context/AuthContext'
import AuthGate from './AuthGate'

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
