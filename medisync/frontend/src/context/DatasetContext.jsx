import { createContext, useContext, useState } from 'react'

const DatasetContext = createContext(null)

const INITIAL = {
  stagedFiles:       [],
  uploadStatus:      'idle',      // idle | uploading | loaded | error
  patientInfo:       null,        // { name, dob, id, gender }
  resources:         {},          // { medications:[...], conditions:[...], ... }
  resourceCount:     0,
  notes:             {},          // { resourceKey: [ {id, text, ts} ] }
  mappingResults:    null,        // { total_mapped, results: { key: { mapped, success, sample, fields:[...] } } }
  validationResults: null,        // { total, passed, failed, details: { key: { count, passed, failed, rate, errors, records } } }
  pushLog:           [],          // [ { ts, resource, recordId, endpoint, status, latency, error, detail } ]
  pushSummary:       null,        // { total, successful, failed }
  error:             null,
}

export function DatasetProvider({ children }) {
  const [dataset, setDataset] = useState(INITIAL)

  // ── Upload / Load ──────────────────────────────────────────
  const setLoaded = (patientInfo, resources) =>
    setDataset(prev => ({
      ...prev,
      uploadStatus:   'loaded',
      patientInfo,
      resources,
      resourceCount:  Object.values(resources).filter(v => v?.length > 0).length,
      error:          null,
      // Reset downstream state when a new dataset is loaded
      mappingResults:    null,
      validationResults: null,
      pushLog:           [],
      pushSummary:       null,
    }))

  const setError = (error) =>
    setDataset(prev => ({ ...prev, error, uploadStatus: 'error' }))

  const clearAll = () => setDataset(INITIAL)

  // ── Notes ─────────────────────────────────────────────────
  const addNote = (resourceKey, text) =>
    setDataset(prev => {
      const existing = prev.notes[resourceKey] || []
      return {
        ...prev,
        notes: {
          ...prev.notes,
          [resourceKey]: [
            ...existing,
            { id: Date.now(), text, ts: new Date().toLocaleTimeString() },
          ],
        },
      }
    })

  // ── Mapping ───────────────────────────────────────────────
  const setMappingResults = (results) =>
    setDataset(prev => ({ ...prev, mappingResults: results }))

  // ── Validation ────────────────────────────────────────────
  const setValidationResults = (results) =>
    setDataset(prev => ({ ...prev, validationResults: results }))

  // ── Push Log ─────────────────────────────────────────────
  const addPushLogEntry = (entry) =>
    setDataset(prev => ({ ...prev, pushLog: [...prev.pushLog, entry] }))

  const setPushSummary = (summary) =>
    setDataset(prev => ({ ...prev, pushSummary: summary }))

  const clearPushLog = () =>
    setDataset(prev => ({ ...prev, pushLog: [], pushSummary: null }))

  return (
    <DatasetContext.Provider value={{
      dataset,
      setLoaded, setError, clearAll,
      addNote,
      setMappingResults,
      setValidationResults,
      addPushLogEntry, setPushSummary, clearPushLog,
    }}>
      {children}
    </DatasetContext.Provider>
  )
}

export const useDataset = () => useContext(DatasetContext)
