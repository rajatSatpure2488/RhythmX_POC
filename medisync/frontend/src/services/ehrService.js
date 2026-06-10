import api from './api'

// ── Auth ──────────────────────────────────────────────────
export const initiateOAuthFlow = () =>
  api.get('/auth/oauth/initiate').then(r => r.data)

export const exchangeCode = (code) =>
  api.post('/auth/oauth/exchange', { code }).then(r => r.data)

export const getAuthStatus = () =>
  api.get('/auth/status').then(r => r.data)

export const setManualTokenAPI = (access_token, doctor_id) =>
  api.post('/auth/manual', { access_token, doctor_id }).then(r => r.data)

export const loginWithPasswordAPI = (username, password) =>
  api.post('/auth/login', { username, password }).then(r => r.data)

export const refreshTokenAPI = () =>
  api.post('/auth/refresh').then(r => r.data)

// ── Upload ────────────────────────────────────────────────
export const uploadAndProcess = (formData) =>
  api.post('/upload/load', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)

// ── Mapping ───────────────────────────────────────────────
export const runMapping = () =>
  api.post('/mapping/run').then(r => r.data)

export const getMappingResults = () =>
  api.get('/mapping/results').then(r => r.data)

// ── Dry Run ───────────────────────────────────────────────
export const runDryRun = (selectedResources) =>
  api.post('/dryrun/run', { resources: selectedResources }).then(r => r.data)

// ── Push ──────────────────────────────────────────────────
export const pushToEHR = (selectedResources) =>
  api.post('/push/run', { resources: selectedResources }).then(r => r.data)
