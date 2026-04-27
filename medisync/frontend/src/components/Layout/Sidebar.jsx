import { useAuth } from '../../context/AuthContext'
import { useDataset } from '../../context/DatasetContext'
import { useApiRate } from '../../context/ApiRateContext'
import { STAGES } from './navItems'

export default function Sidebar({ activeStage, onNavigate, completedStages = [] }) {
  const { auth, logout } = useAuth()
  const { dataset }      = useDataset()
  const { rate, limit, pct, color } = useApiRate()

  const getStepState = (stage) => {
    if (completedStages.includes(stage.id)) return 'done'
    if (stage.id === activeStage) return 'active'
    if (auth.devMode) return 'accessible'
    if (stage.step === 1) return 'accessible'
    const prevStage = STAGES[stage.step - 2]
    if (completedStages.includes(prevStage?.id) || stage.step <= 2) return 'accessible'
    return 'locked'
  }

  // Dataset status derived values
  const resourceCount  = dataset.resourceCount || 0
  const uploadStatus   = dataset.uploadStatus   // idle | loaded | error
  const apiRateUsed    = rate || 0
  const apiRateLimit   = limit || 500
  const apiRatePct     = pct || 0
  const apiRateColor   = color || '#16a34a'

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar__logo">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
        MediSync
      </div>

      {/* EHR Status Badge */}
      {auth.devMode ? (
        <div className="sidebar__ehr-badge devmode">
          <span style={{ fontSize: '0.85rem' }}>⚡</span>
          Developer Mode — No EHR
        </div>
      ) : (
        <div className={`sidebar__ehr-badge ${auth.connected ? 'connected' : 'disconnected'}`}>
          <span className="sidebar__ehr-dot" />
          {auth.connected
            ? `Connected · Dr. ${auth.doctorName || auth.doctorId || '—'}`
            : 'Not connected to DrChrono'}
        </div>
      )}

      {/* Stage Stepper */}
      <div className="sidebar__stepper-label">PIPELINE STAGES</div>
      <nav className="sidebar__stepper">
        {STAGES.map((stage) => {
          const state    = getStepState(stage)
          const isLocked = state === 'locked'
          return (
            <div
              key={stage.id}
              id={`stage-${stage.id}`}
              className={`stage-step stage-step--${state}`}
              onClick={() => !isLocked && onNavigate(stage.id)}
              title={isLocked ? 'Complete previous stage first' : stage.label}
            >
              <div className="stage-step__num">
                {state === 'done' ? (
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                ) : stage.step}
              </div>
              {stage.step < STAGES.length && <div className="stage-step__line" />}
              <div className="stage-step__content">
                <span className="stage-step__icon">{stage.icon}</span>
                <span className="stage-step__label">{stage.label}</span>
                {isLocked && (
                  <svg className="stage-step__lock" width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="3" y="11" width="18" height="11" rx="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                )}
              </div>
            </div>
          )
        })}
      </nav>

      {/* ── System Status ──────────────────────────────────── */}
      <div className="sidebar__system-status">
        <div className="sidebar__system-label">SYSTEM STATUS</div>

        {/* Dataset Status */}
        <div
          className="sidebar__status-item"
          onClick={() => onNavigate('review')}
          title="Click to review dataset"
          style={{ cursor: 'pointer' }}
        >
          <div className="sidebar__status-item__header">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
              <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            <span>Dataset Status</span>
            <span className={`sidebar__status-dot sidebar__status-dot--${uploadStatus === 'loaded' ? 'green' : uploadStatus === 'error' ? 'red' : 'gray'}`} />
          </div>
          <div className="sidebar__status-item__value">
            {uploadStatus === 'loaded'
              ? `${resourceCount} resource type${resourceCount !== 1 ? 's' : ''} loaded`
              : uploadStatus === 'error'
              ? 'Load error'
              : 'No dataset loaded'}
          </div>
        </div>

        {/* API Rate Monitor */}
        <div className="sidebar__status-item">
          <div className="sidebar__status-item__header">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            <span>API Rate Monitor</span>
            <span style={{ marginLeft: 'auto', fontSize: '0.65rem', fontWeight: 700, color: apiRateColor }}>
              {apiRatePct}%
            </span>
          </div>
          <div className="sidebar__rate-bar">
            <div
              className="sidebar__rate-fill"
              style={{ width: `${apiRatePct}%`, background: apiRateColor }}
            />
          </div>
          <div className="sidebar__rate-label">
            {apiRateUsed} / {apiRateLimit} req/min
          </div>
        </div>
      </div>

      {/* Bottom */}
      <div className="sidebar__bottom">
        <div className="sidebar__version">v1.0 · Stage Pipeline</div>
        {(auth.connected || auth.devMode) && (
          <button className="sidebar__logout" onClick={logout}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            {auth.devMode ? 'Exit Dev Mode' : 'Disconnect'}
          </button>
        )}
      </div>
    </aside>
  )
}
