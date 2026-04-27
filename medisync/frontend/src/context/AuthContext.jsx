import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getAuthStatus, initiateOAuthFlow, setManualTokenAPI, exchangeCode } from '../services/ehrService'

const AuthContext = createContext(null)

const STORAGE_KEY = 'medisync_auth'

const INITIAL = {
  connected: false, accessToken: null, refreshToken: null,
  doctorId: null, doctorName: null, targetSystem: 'DrChrono EHR',
  expiresIn: null, lastHandshake: null, status: 'idle', error: null, devMode: false,
}

/** Persist only safe fields — never store raw tokens in localStorage in production */
function saveToStorage(auth) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      connected:    auth.connected,
      doctorId:     auth.doctorId,
      doctorName:   auth.doctorName,
      targetSystem: auth.targetSystem,
      devMode:      auth.devMode ?? false,
      status:       auth.connected || auth.devMode ? auth.status : 'idle',
    }))
  } catch { /* quota exceeded — ignore */ }
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const saved = JSON.parse(raw)
    // Only restore if still connected or in dev mode
    if (saved.connected || saved.devMode) return saved
  } catch { /* corrupted */ }
  return null
}

export function AuthProvider({ children }) {
  const [auth, setAuthState] = useState(() => {
    const saved = loadFromStorage()
    return saved ? { ...INITIAL, ...saved } : INITIAL
  })

  // Wrap setState to always persist
  const setAuth = useCallback((updater) => {
    setAuthState(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      saveToStorage(next)
      return next
    })
  }, [])

  // Poll /auth/status every 60s (skip in dev mode)
  const syncStatus = useCallback(async () => {
    if (auth.devMode) return
    try {
      const data = await getAuthStatus()
      setAuth(prev => ({
        ...prev,
        connected:    data.connected,
        doctorId:     data.doctor_id,
        doctorName:   data.doctor_name,
        targetSystem: data.target_system || 'DrChrono EHR',
        expiresIn:    data.expires_in,
        lastHandshake:data.last_handshake,
        status:       data.connected ? 'connected' : 'idle',
        error:        null,
      }))
    } catch {
      // Backend unreachable — keep existing state silently
    }
  }, [auth.devMode, setAuth])

  useEffect(() => {
    if (!auth.devMode) {
      syncStatus()
      const id = setInterval(syncStatus, 60000)
      return () => clearInterval(id)
    }
  }, [syncStatus, auth.devMode])

  // OAuth Callback handler
  useEffect(() => {
    const params     = new URLSearchParams(window.location.search)
    const code       = params.get('code')
    const oauthError = params.get('error')

    if (oauthError) {
      setAuth(prev => ({ ...prev, status: 'error', error: `DrChrono auth error: ${oauthError}` }))
      window.history.replaceState({}, '', window.location.pathname)
      return
    }

    if (code) {
      window.history.replaceState({}, '', window.location.pathname)
      setAuth(prev => ({ ...prev, status: 'connecting' }))
      exchangeCode(code)
        .then(data => setAuth(prev => ({
          ...prev, connected: true,
          doctorId: data.doctor_id, doctorName: data.doctor_name,
          targetSystem: data.target_system || 'DrChrono EHR',
          expiresIn: data.expires_in, lastHandshake: data.last_handshake,
          status: 'connected', error: null,
        })))
        .catch(err => setAuth(prev => ({ ...prev, status: 'error', error: err.message || 'Token exchange failed' })))
    }
  }, []) // eslint-disable-line

  const initiateOAuth = async () => {
    setAuth(prev => ({ ...prev, status: 'connecting', error: null }))
    try {
      const { auth_url } = await initiateOAuthFlow()
      window.location.href = auth_url
    } catch (err) {
      setAuth(prev => ({ ...prev, status: 'error', error: err.message }))
    }
  }

  const setManualToken = async (accessToken, doctorId) => {
    setAuth(prev => ({ ...prev, status: 'connecting', error: null }))
    try {
      const data = await setManualTokenAPI(accessToken, doctorId)
      setAuth(prev => ({
        ...prev, connected: true, accessToken,
        doctorId: data.doctor_id, doctorName: data.doctor_name,
        status: 'connected', error: null,
      }))
    } catch (err) {
      setAuth(prev => ({ ...prev, status: 'error', error: err.message }))
    }
  }

  // ── Developer Mode — bypass OAuth for testing ──────────────
  const enterDevMode = () => {
    setAuth({
      connected: true, accessToken: 'DEV_MODE_TOKEN', refreshToken: null,
      doctorId: 'DEV-001', doctorName: 'Dev Doctor',
      targetSystem: 'DrChrono EHR (Dev Mode)',
      expiresIn: 99999, lastHandshake: new Date().toISOString(),
      status: 'connected', error: null, devMode: true,
    })
  }

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY)
    setAuthState({ ...INITIAL })
  }

  return (
    <AuthContext.Provider value={{ auth, initiateOAuth, setManualToken, enterDevMode, logout, syncStatus }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
