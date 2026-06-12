import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getAuthStatus, initiateOAuthFlow, setManualTokenAPI, exchangeCode, loginWithPasswordAPI } from '../services/ehrService'

const AuthContext = createContext(null)

// Module-level guard (survives StrictMode double-mount / remounts) so a single-use
// DrChrono authorization code is never exchanged twice — the 2nd exchange would fail
// with invalid_grant even though the 1st succeeded.
const _processedCodes = new Set()

/**
 * Auth persistence strategy:
 *  - sessionStorage only — cleared automatically when the browser tab/window closes
 *    or the dev server restarts (new tab).
 *  - This ensures the login page ALWAYS appears on a fresh start.
 *  - OAuth callback codes are still handled (they come back via URL params in the
 *    same tab, so sessionStorage survives the redirect).
 */
const SESSION_KEY = 'medisync_auth_session'

const INITIAL = {
  connected: false, accessToken: null, refreshToken: null,
  doctorId: null, doctorName: null, targetSystem: 'DrChrono EHR',
  expiresIn: null, lastHandshake: null, status: 'idle', error: null, devMode: false,
}

function saveSession(auth) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({
      connected:    auth.connected,
      doctorId:     auth.doctorId,
      doctorName:   auth.doctorName,
      targetSystem: auth.targetSystem,
      devMode:      auth.devMode ?? false,
      status:       auth.status,
    }))
  } catch { /* quota exceeded */ }
}

function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const saved = JSON.parse(raw)
    // Only restore within the same tab session (OAuth redirect keeps session alive)
    if (saved.connected || saved.devMode) return saved
  } catch { /* corrupted */ }
  return null
}

/** Also clear any old localStorage key from the previous implementation */
function clearLegacyStorage() {
  try { localStorage.removeItem('medisync_auth') } catch { /* ignore */ }
}

export function AuthProvider({ children }) {
  const [auth, setAuthState] = useState(() => {
    clearLegacyStorage()         // remove stale localStorage on every boot
    const saved = loadSession()  // only restore if same-tab OAuth redirect

    // If we're landing on an OAuth callback URL (?code=...), start in
    // 'connecting' state so Dashboard renders the spinner immediately
    // instead of briefly showing AuthGate before the useEffect kicks in.
    let override = {}
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      if (params.get('code')) override = { status: 'connecting' }
    }

    return { ...INITIAL, ...(saved || {}), ...override }
  })

  const setAuth = useCallback((updater) => {
    setAuthState(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      saveSession(next)
      return next
    })
  }, [])

  // ── Poll /auth/status every 60 s (skip in dev mode) ──────────
  const syncStatus = useCallback(async () => {
    if (auth.devMode) return
    try {
      const data = await getAuthStatus()
      setAuth(prev => ({
        ...prev,
        connected:     data.connected,
        doctorId:      data.doctor_id,
        doctorName:    data.doctor_name,
        targetSystem:  data.target_system || 'DrChrono EHR',
        expiresIn:     data.expires_in,
        lastHandshake: data.last_handshake,
        status:        data.connected ? 'connected' : 'idle',
        error:         null,
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

  // ── OAuth Callback handler (handles redirect back from DrChrono) ──
  useEffect(() => {
    const params     = new URLSearchParams(window.location.search)
    const code       = params.get('code')
    const oauthError = params.get('error')

    if (oauthError) {
      setAuth(prev => ({ ...prev, status: 'error', error: `DrChrono auth error: ${oauthError}` }))
      window.history.replaceState({}, '', window.location.pathname)
      return
    }

    if (code && !_processedCodes.has(code)) {
      _processedCodes.add(code)                       // exchange this code at most once
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
        .catch(err => {
          // A failed exchange (e.g. invalid_grant from a duplicate/expired code) might
          // still mean we're connected — the backend may already hold a valid token.
          // Confirm via /auth/status before surfacing an error.
          getAuthStatus()
            .then(s => {
              if (s && s.connected) {
                setAuth(prev => ({
                  ...prev, connected: true,
                  doctorId: s.doctor_id, doctorName: s.doctor_name,
                  expiresIn: s.expires_in, status: 'connected', error: null,
                }))
              } else {
                setAuth(prev => ({ ...prev, status: 'error', error: err.message || 'Token exchange failed' }))
              }
            })
            .catch(() => setAuth(prev => ({ ...prev, status: 'error', error: err.message || 'Token exchange failed' })))
        })
    }
  }, []) // eslint-disable-line

  // ── Actions ───────────────────────────────────────────────────
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

  const loginWithPassword = async (username, password) => {
    setAuth(prev => ({ ...prev, status: 'connecting', error: null }))
    try {
      const data = await loginWithPasswordAPI(username, password)
      setAuth(prev => ({
        ...prev, connected: true,
        doctorId: data.doctor_id, doctorName: data.doctor_name,
        expiresIn: data.expires_in, status: 'connected', error: null,
      }))
    } catch (err) {
      setAuth(prev => ({ ...prev, status: 'error', error: err.message }))
      throw err
    }
  }

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
    sessionStorage.removeItem(SESSION_KEY)
    sessionStorage.removeItem('medisync_pipeline')  // reset pipeline to Step 1
    try { localStorage.removeItem('medisync_auth') } catch { /* ignore */ }
    setAuthState({ ...INITIAL })
  }

  return (
    <AuthContext.Provider value={{ auth, initiateOAuth, setManualToken, loginWithPassword, enterDevMode, logout, syncStatus }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
