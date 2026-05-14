import { createContext, useContext, useState } from 'react'

const DatasetContext = createContext(null)

/**
 * ingestionState persists the full Ingestion stage result so navigating
 * back to Stage 2 restores everything (file list, scan results, detected
 * resources, per-file statuses, failed files).
 *
 * Shape:
 * {
 *   phase:             'idle' | 'scanning' | 'done' | 'error'
 *   files:             [{ name, size, ext, status, resourcesFound, error }]
 *   detectedResources: { key: count }
 *   failedFiles:       [{ name, reason }]
 *   totalRecords:      number
 *   overallPct:        number
 *   statusMsg:         string
 *   errorMsg:          string | null
 * }
 */

const INITIAL_INGESTION = {
  phase:             'idle',
  files:             [],
  detectedResources: {},
  failedFiles:       [],
  totalRecords:      0,
  overallPct:        0,
  statusMsg:         '',
  errorMsg:          null,
}

const INITIAL = {
  ingestionState:    INITIAL_INGESTION,
  uploadStatus:      'idle',      // idle | uploading | loaded | error
  patientInfo:       null,        // { name, dob, id, gender }
  resources:         {},          // { medications:[...], conditions:[...], ... }
  resourceCount:     0,
  notes:             {},          // { resourceKey: [ {id, text, ts} ] }
  mappingResults:    null,
  validationResults: null,
  pushLog:           [],
  pushSummary:       null,
  error:             null,
}

export function DatasetProvider({ children }) {
  const [dataset, setDataset] = useState(INITIAL)

  // ── Ingestion state (persists across navigation) ───────────
  const setIngestionState = (patch) =>
    setDataset(prev => ({
      ...prev,
      ingestionState: {
        ...prev.ingestionState,
        ...(typeof patch === 'function' ? patch(prev.ingestionState) : patch),
      },
    }))

  const clearIngestionState = () =>
    setDataset(prev => ({ ...prev, ingestionState: INITIAL_INGESTION }))

  // ── Upload / Load ──────────────────────────────────────────
  const setLoaded = (patientInfo, resources) =>
    setDataset(prev => ({
      ...prev,
      uploadStatus:  'loaded',
      patientInfo,
      resources,
      resourceCount: Object.values(resources).filter(v => v?.length > 0).length,
      error:         null,
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
      setIngestionState, clearIngestionState,
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
