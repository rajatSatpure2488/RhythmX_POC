import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import Sidebar from '../components/Layout/Sidebar'
import Topbar from '../components/Layout/Topbar'
import AuthGate from '../components/Sidebar/AuthGate'
import AuthStage from '../components/Sidebar/AuthStage'
import Ingestion from './Ingestion'
import ReviewDataset from './ReviewDataset'
import Mapping from './Mapping'
import Validation from './Validation'
import EHRPush from './EHRPush'

const STAGE_ORDER = ['auth', 'ingestion', 'review', 'mapping', 'validation', 'push']
const STAGE_TITLES = {
  auth:       'EHR Authentication',
  ingestion:  'Data Ingestion',
  review:     'Review Dataset',
  mapping:    'Field Mapping',
  validation: 'Dry-Run Validation',
  push:       'EHR Push',
}

const PIPELINE_KEY = 'medisync_pipeline'

// Pipeline progress is NOT persisted across reloads / logins, because the
// dataset (DatasetContext) is in-memory only. Showing completed-stage check
// marks without underlying data is misleading. Always boot fresh.
function loadPipeline() {
  try { sessionStorage.removeItem(PIPELINE_KEY) } catch { /* ignore */ }
  return { activeStage: 'auth', completedStages: [] }
}

function savePipeline(_activeStage, _completedStages) {
  // No-op: pipeline state is ephemeral. See loadPipeline() for rationale.
}

export default function Dashboard() {
  const { auth } = useAuth()

  const [activeStage, setActiveStageRaw]         = useState(() => loadPipeline().activeStage)
  const [completedStages, setCompletedStagesRaw] = useState(() => loadPipeline().completedStages)

  // Wrap setters to persist every change to sessionStorage
  const setActiveStage = (stage) => {
    setActiveStageRaw(stage)
    setCompletedStagesRaw(prev => {
      savePipeline(stage, prev)
      return prev
    })
  }

  const setCompletedStages = (updater) => {
    setCompletedStagesRaw(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      savePipeline(activeStage, next)
      return next
    })
  }

  // ── Guards ─────────────────────────────────────────────────
  if (!auth.connected && auth.status !== 'connecting') return <AuthGate />

  if (auth.status === 'connecting') {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', background: 'var(--app-bg)',
      }}>
        <div className="auth-gate__spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
        <p style={{ marginTop: 16, color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          Completing authentication…
        </p>
      </div>
    )
  }

  // ── Stage advance helper ────────────────────────────────────
  const advanceStage = (currentId) => {
    setCompletedStages(prev => {
      const next = prev.includes(currentId) ? prev : [...prev, currentId]
      const idx = STAGE_ORDER.indexOf(currentId)
      if (idx >= 0 && idx < STAGE_ORDER.length - 1) {
        const nextStage = STAGE_ORDER[idx + 1]
        setActiveStageRaw(nextStage)
        savePipeline(nextStage, next)
      }
      return next
    })
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeStage={activeStage}
        onNavigate={setActiveStage}
        completedStages={completedStages}
      />

      <div className="main-area">
        <Topbar title={STAGE_TITLES[activeStage] ?? 'MediSync'} />

        <main className="main-content">
          {activeStage === 'auth'       && <AuthStage     onComplete={() => advanceStage('auth')} />}
          {activeStage === 'ingestion'  && <Ingestion     onComplete={() => advanceStage('ingestion')} />}
          {activeStage === 'review'     && <ReviewDataset  onComplete={() => advanceStage('review')} />}
          {activeStage === 'mapping'    && <Mapping        onComplete={() => advanceStage('mapping')} />}
          {activeStage === 'validation' && <Validation     onComplete={() => advanceStage('validation')} />}
          {activeStage === 'push'       && <EHRPush />}
        </main>
      </div>
    </div>
  )
}
