import { useAuth } from '../../context/AuthContext'

export default function Topbar({ title }) {
  const { auth } = useAuth()
  const initials = auth.doctorName
    ? auth.doctorName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'DR'

  return (
    <header className="topbar">
      {/* Stage title */}
      <div className="topbar__title">
        {title || 'MediSync'}
      </div>

      <div className="topbar__right">
        {auth.devMode ? (
          <div className="topbar__devmode">
            ⚡ DEV MODE
          </div>
        ) : auth.connected ? (
          <div className="topbar__connected">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            DrChrono Connected
          </div>
        ) : null}

        <div className="topbar__user">
          <div className="avatar avatar--lg" style={{ background: '#1565C0', color: '#fff' }}>
            {initials}
          </div>
          <span>{auth.doctorName || 'Dr. —'}</span>
        </div>
      </div>
    </header>
  )
}
