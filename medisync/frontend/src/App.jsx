import { AuthProvider }    from './context/AuthContext'
import { DatasetProvider } from './context/DatasetContext'
import { ApiRateProvider } from './context/ApiRateContext'
import Dashboard from './pages/Dashboard'

export default function App() {
  return (
    <AuthProvider>
      <ApiRateProvider>
        <DatasetProvider>
          <Dashboard />
        </DatasetProvider>
      </ApiRateProvider>
    </AuthProvider>
  )
}
