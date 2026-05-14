import { useState } from 'react'
import { AuthProvider }    from './context/AuthContext'
import { DatasetProvider } from './context/DatasetContext'
import { ApiRateProvider } from './context/ApiRateContext'
import Dashboard from './pages/Dashboard'
import PipelineTest from './pages/PipelineTest'

export default function App() {
  const [view, setView] = useState('dashboard') // dashboard | pipeline

  return (
    <AuthProvider>
      <ApiRateProvider>
        <DatasetProvider>
          {/* View toggle — remove this block + PipelineTest import to clean up */}
          <div style={{
            position: 'fixed', top: 12, right: 16, zIndex: 9999,
            display: 'flex', gap: 4, background: '#0f172a',
            padding: 4, borderRadius: 10, border: '1px solid #1e293b',
          }}>
            <button onClick={() => setView('dashboard')} style={{
              padding: '6px 14px', borderRadius: 8, border: 'none', fontSize: '0.78rem',
              fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s',
              background: view === 'dashboard' ? 'linear-gradient(135deg,#4f46e5,#7c3aed)' : 'transparent',
              color: view === 'dashboard' ? '#fff' : '#94a3b8',
            }}>Dashboard</button>
            <button onClick={() => setView('pipeline')} style={{
              padding: '6px 14px', borderRadius: 8, border: 'none', fontSize: '0.78rem',
              fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s',
              background: view === 'pipeline' ? 'linear-gradient(135deg,#4f46e5,#7c3aed)' : 'transparent',
              color: view === 'pipeline' ? '#fff' : '#94a3b8',
            }}>🔬 Pipeline Lab</button>
          </div>

          {view === 'dashboard' ? <Dashboard /> : <PipelineTest />}
        </DatasetProvider>
      </ApiRateProvider>
    </AuthProvider>
  )
}
