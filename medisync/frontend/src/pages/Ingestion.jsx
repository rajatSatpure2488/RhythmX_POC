/**
 * Ingestion.jsx — Stage 2
 *
 * State persistence: all scan results are saved to DatasetContext.ingestionState
 * so navigating away and back restores the full view (detected resources,
 * per-file statuses, failed files, error messages).
 *
 * Failed file reporting: any file that errors during upload OR that the backend
 * returns 0 records for is listed in a "Failed / Unrecognized Files" panel.
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useDataset } from '../context/DatasetContext'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const TAB_LABELS = {
  patient:'Patient', patients:'Patient',
  medications:'Medications', medication:'Medications',
  conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters',
  observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies',
  immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures',
  coverages:'Coverages', coverage:'Coverages',
  diagnostic_reports:'Diagnostic Reports', clinical_notes:'Clinical Notes',
  devices:'Devices', goals:'Goals', vitals:'Vitals',
  claims:'Claims', care_plans:'Care Plans', family_history:'Family History',
  appointments:'Appointments', documents:'Documents', labs:'Labs',
  observation_notes:'Observation Notes',
}

const FILE_ICONS = { zip:'🗜️', csv:'📊', json:'📋', hl7:'🏥', txt:'📄', default:'📁' }
const ALLOWED    = new Set(['zip', 'csv', 'json', 'hl7', 'txt'])

function getExt(name)  { return (name || '').split('.').pop().toLowerCase() }
function getIcon(name) { return FILE_ICONS[getExt(name)] ?? FILE_ICONS.default }
function formatSize(b) {
  if (b < 1024)         return `${b} B`
  if (b < 1024 * 1024) return `${(b/1024).toFixed(1)} KB`
  return `${(b/1024/1024).toFixed(1)} MB`
}

function Chip({ status }) {
  const map = {
    pending:   { label:'Pending',   cls:'chip--gray'  },
    uploading: { label:'Uploading', cls:'chip--blue'  },
    done:      { label:'✓ Done',    cls:'chip--green' },
    error:     { label:'✗ Error',   cls:'chip--red'   },
    empty:     { label:'⚠ Empty',   cls:'chip--red'   },
  }
  const { label, cls } = map[status] || map.pending
  return <span className={`file-status-chip ${cls}`}>{label}</span>
}

function ResourceBadge({ label, count }) {
  return (
    <div className="resource-detect-badge">
      <span className="resource-detect-dot" />
      <span className="resource-detect-name">{label}</span>
      <span className="resource-detect-count">{count.toLocaleString()}</span>
    </div>
  )
}

// Method labels for display
const METHOD_LABELS = {
  filename_alias: '✓ Matched by filename',
  column_hint:    '✓ Matched by column names',
  stem_fallback:  '⚠ Stored under filename stem (may not map to DrChrono)',
  unrecognized:   '✗ Could not determine resource type',
  error:          '✗ File parse error',
  empty:          '✗ File has no data rows',
  unsupported:    '✗ Unsupported file format',
  fhir_bundle:    '✓ FHIR Bundle',
  json_array:     '✓ JSON array of records',
  json_single:    '✓ Single FHIR resource',
}

function DetectionSummaryPanel({ unrecognized, recognized, total, totalRecognized, allFiles }) {
  const [expanded, setExpanded] = useState({})
  const unrecog = unrecognized || []
  
  // Group recognized files by their detected category for transparency
  const mapping = (allFiles || []).reduce((acc, f) => {
    if (!f.recognized || !f.detected_as) return acc
    const cat = f.detected_as
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(f.filename)
    return acc
  }, {})

  const mappingKeys = Object.keys(mapping).sort()

  if (unrecog.length === 0 && total === 0 && mappingKeys.length === 0) return null

  return (
    <div className="ingest-summary-panel">
      {/* Summary header */}
      <div className="ingest-summary-header">
        <div className="ingest-summary-stat ingest-summary-stat--green">
          <span className="ingest-summary-stat__num">{totalRecognized}</span>
          <span className="ingest-summary-stat__label">Files Recognized</span>
        </div>
        <div className="ingest-summary-divider" />
        <div className="ingest-summary-stat">
          <span className="ingest-summary-stat__num">{total}</span>
          <span className="ingest-summary-stat__label">Total Files</span>
        </div>
        <div className="ingest-summary-divider" />
        <div className={`ingest-summary-stat ${unrecog.length > 0 ? 'ingest-summary-stat--red' : 'ingest-summary-stat--green'}`}>
          <span className="ingest-summary-stat__num">{unrecog.length}</span>
          <span className="ingest-summary-stat__label">Not Recognized</span>
        </div>
      </div>

      {/* ── Recognized Mapping Section (Transparency) ────────── */}
      {mappingKeys.length > 0 && (
        <div className="ingest-mapping-section">
          <div className="ingest-mapping-title">
            📂 Recognized Category Mapping
          </div>
          <div className="ingest-mapping-grid">
            {mappingKeys.map(cat => (
              <div key={cat} className="ingest-mapping-card">
                <div className="ingest-mapping-card__type">
                  {TAB_LABELS[cat] || cat}
                  {mapping[cat].length > 1 && (
                    <span className="ingest-mapping-merged-badge">Merged ({mapping[cat].length} files)</span>
                  )}
                </div>
                <div className="ingest-mapping-card__files">
                  {mapping[cat].map(fname => (
                    <div key={fname} className="ingest-mapping-file">
                      <span className="ingest-mapping-file__icon">📄</span>
                      <span className="ingest-mapping-file__name">{fname}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Unrecognized / Unsupported Files (Action Required) ── */}
      {unrecog.length > 0 && (
        <div className="ingest-unrecog-section">
          <div className="ingest-unrecog-title ingest-unrecog-title--red">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/>
            </svg>
            Action Required: {unrecog.length} file{unrecog.length !== 1 ? 's' : ''} not recognized
          </div>
          <div className="ingest-unrecog-list">
            {unrecog.map((f, i) => (
              <div key={i} className="ingest-unrecog-card ingest-unrecog-card--failed">
                <div className="ingest-unrecog-card__header"
                  onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}>
                  <span className="ingest-unrecog-card__name">📄 {f.filename}</span>
                  <span className="ingest-unrecog-card__method ingest-unrecog-card__method--red">
                    {METHOD_LABELS[f.method] || f.method || 'Unrecognized'}
                  </span>
                  <span className="ingest-unrecog-card__toggle">{expanded[i] ? '▴ Hide' : '▾ Show Details'}</span>
                </div>

                {/* Always show issue, collapse only the fix guide if desired, but let's keep it expanded for importance */}
                <div className="ingest-unrecog-card__body">
                  <div className="ingest-diag-row ingest-diag-row--warn">
                    <span className="ingest-diag-label">Failure Reason:</span>
                    <span className="ingest-diag-val">{f.failure_reason || 'System could not determine how to parse this file.'}</span>
                  </div>

                  {f.columns_found?.length > 0 && expanded[i] && (
                    <div className="ingest-diag-row">
                      <span className="ingest-diag-label">Columns Found:</span>
                      <div className="ingest-diag-val">
                        {f.columns_found.map(c => (
                          <code key={c} className="ingest-col-chip">{c}</code>
                        ))}
                      </div>
                    </div>
                  )}

                  {f.fix_hint && (
                    <div className="ingest-fix-box">
                      <div className="ingest-fix-box__title">💡 Troubleshooting & Fix Guide</div>
                      <pre className="ingest-fix-box__text">{f.fix_hint}</pre>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="ingest-unrecog-footer">
            Note: Only recognized files will be advanced to the Mapping & Review stages.
          </div>
        </div>
      )}

      {unrecog.length === 0 && total > 0 && (
        <div style={{ padding:'16px', fontSize:'0.82rem', color:'#166534', background:'#F0FDF4', borderTop:'1px solid #DCFCE7' }}>
          ✅ <strong>Success:</strong> All {total} files were successfully recognized and mapped to categories.
        </div>
      )}
    </div>
  )
}

export default function Ingestion({ onComplete }) {
  const { dataset, setIngestionState, clearIngestionState, setLoaded } = useDataset()
  const iState = dataset.ingestionState   // persisted state from context

  // Local: actual File objects (not serialisable, re-selected each session)
  const [localFiles, setLocalFiles] = useState([])  // [{ file, status, resourcesFound, error }]
  const [dragging, setDragging]     = useState(false)

  const inputRef  = useRef()
  const folderRef = useRef()

  // Convenience shortcuts from persisted state
  const phase             = iState.phase
  const detectedResources = iState.detectedResources
  const failedFiles       = iState.failedFiles
  const totalRecords      = iState.totalRecords
  const overallPct        = iState.overallPct
  const statusMsg         = iState.statusMsg
  const errorMsg          = iState.errorMsg
  const detectionSummary  = iState.detectionSummary || {}

  const loading = phase === 'scanning'
  const isDone  = phase === 'done'

  // Merge localFiles statuses with persisted iState.files metadata for display
  const displayFiles = iState.files.length > 0
    ? iState.files.map(meta => {
        const live = localFiles.find(e => e.file.name === meta.name)
        return {
          name:           meta.name,
          size:           meta.size,
          ext:            meta.ext,
          status:         live ? live.status : meta.status,
          resourcesFound: meta.resourcesFound,
          error:          meta.error,
        }
      })
    : localFiles.map(e => ({
        name:  e.file.name, size: e.file.size,
        ext:   getExt(e.file.name), status: e.status,
        resourcesFound: e.resourcesFound, error: e.error,
      }))

  const grouped = displayFiles.reduce((acc, f) => {
    ;(acc[f.ext] = acc[f.ext] || []).push(f)
    return acc
  }, {})

  // ── Add files ─────────────────────────────────────────────
  const addFiles = useCallback((incoming) => {
    const arr = Array.from(incoming).filter(f => ALLOWED.has(getExt(f.name)))
    setLocalFiles(prev => {
      const names = new Set(prev.map(e => e.file.name))
      return [...prev, ...arr.filter(f => !names.has(f.name)).map(f => ({
        file: f, status: 'pending', resourcesFound: 0, error: null,
      }))]
    })
    // If previously done, allow re-scan but keep detected panel until new scan starts
    if (phase === 'done' || phase === 'error') {
      setIngestionState({ phase: 'idle', errorMsg: null })
    }
  }, [phase, setIngestionState])

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files)
  }, [addFiles])

  const removeFile = name => {
    setLocalFiles(prev => prev.filter(e => e.file.name !== name))
    setIngestionState(prev => ({
      ...prev,
      files: prev.files.filter(m => m.name !== name),
    }))
  }

  const updateLocalStatus = (name, patch) =>
    setLocalFiles(prev => prev.map(e => e.file.name === name ? { ...e, ...patch } : e))

  // ── Main scan ─────────────────────────────────────────────
  const handleProcess = async () => {
    if (!localFiles.length) {
      setIngestionState({ errorMsg: 'Please add at least one file.' })
      return
    }

    // Reset persisted state for new scan
    setIngestionState({
      phase: 'scanning', errorMsg: null,
      detectedResources: {}, failedFiles: [],
      totalRecords: 0, overallPct: 0, statusMsg: '',
      files: localFiles.map(e => ({
        name: e.file.name, size: e.file.size,
        ext: getExt(e.file.name), status: 'pending',
        resourcesFound: 0, error: null,
      })),
    })

    try {
      await axios.post(`${BACKEND}/upload/clear`)

      let lastResponse    = null
      const failedList    = []
      let cumulativeRsrc  = {}

      for (let i = 0; i < localFiles.length; i++) {
        const entry = localFiles[i]
        const f     = entry.file
        const pct   = Math.round((i / localFiles.length) * 95)

        setIngestionState(prev => ({
          ...prev,
          overallPct: pct,
          statusMsg: `Scanning ${i + 1}/${localFiles.length}: ${f.name}`,
          files: prev.files.map(m =>
            m.name === f.name ? { ...m, status: 'uploading' } : m
          ),
        }))
        updateLocalStatus(f.name, { status: 'uploading' })

        const form = new FormData()
        form.append('file', f)

        try {
          const res = await axios.post(`${BACKEND}/upload/load-single`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 180000,
          })
          lastResponse = res.data

          const rsrc      = res.data.resources || {}
          const newFound  = Object.values(rsrc).reduce((s, v) => s + (v?.length || 0), 0)

          // Extract per-file detection metadata
          const fileDet = res.data.file_detection || {}
          const detSum  = res.data.detection_summary || {}

          // Merge into cumulative
          for (const [k, v] of Object.entries(rsrc)) {
            if (v?.length > 0) cumulativeRsrc[k] = (cumulativeRsrc[k] || 0) + v.length
          }

          // Track unrecognized files from backend metadata
          const fileRecognized = Array.isArray(fileDet)
            ? fileDet.every(d => d.recognized)
            : fileDet.recognized !== false

          const fileFailedMeta = Array.isArray(fileDet)
            ? fileDet.filter(d => !d.recognized)
            : (!fileDet.recognized && fileDet.filename ? [fileDet] : [])

          if (fileFailedMeta.length > 0) {
            failedList.push(...fileFailedMeta)
          } else if (newFound === 0) {
            // Fallback if backend didn't return detection metadata
            failedList.push({
              filename: f.name, recognized: false, method: 'unrecognized',
              columns_found: [], record_count: 0,
              failure_reason: 'No recognizable records found.',
              fix_hint: 'Rename file to match a resource type (e.g. medications.csv).',
            })
          }

          setIngestionState(prev => ({
            ...prev,
            files: prev.files.map(m =>
              m.name === f.name ? { ...m, status: fileRecognized && newFound > 0 ? 'done' : 'empty', resourcesFound: newFound } : m
            ),
            detectedResources: { ...cumulativeRsrc },
            totalRecords: res.data.total_records || 0,
            failedFiles: [...failedList],
            detectionSummary: {
              total:        detSum.total_files || 0,
              recognized:   detSum.recognized_files || 0,
              unrecognized: detSum.unrecognized_files || 0,
              unrecognizedDetails: detSum.unrecognized_details || failedList,
            },
          }))
          updateLocalStatus(f.name, { status: fileRecognized && newFound > 0 ? 'done' : 'empty', resourcesFound: newFound })

        } catch (fileErr) {
          const reason = fileErr.response?.data?.detail || fileErr.message || 'Upload failed'
          failedList.push({ name: f.name, reason })
          setIngestionState(prev => ({
            ...prev,
            files: prev.files.map(m =>
              m.name === f.name ? { ...m, status: 'error', error: reason } : m
            ),
            failedFiles: [...failedList],
          }))
          updateLocalStatus(f.name, { status: 'error', error: reason })
        }
      }

      setIngestionState(prev => ({ ...prev, overallPct: 100 }))

      if (!lastResponse || Object.keys(cumulativeRsrc).length === 0) {
        setIngestionState(prev => ({
          ...prev, phase: 'error',
          errorMsg: 'No recognizable data found in any uploaded file.',
          statusMsg: '',
        }))
        return
      }

      const finalResources = lastResponse.resources || {}
      const detectedCount  = Object.keys(cumulativeRsrc).length

      setIngestionState(prev => ({
        ...prev,
        phase: 'done',
        statusMsg: `✓ ${detectedCount} resource type${detectedCount !== 1 ? 's' : ''} detected — ${(lastResponse.total_records || 0).toLocaleString()} records`,
        detectedResources: cumulativeRsrc,
        totalRecords: lastResponse.total_records || 0,
        failedFiles: failedList,
      }))

      setLoaded(lastResponse.patient_info ?? null, finalResources)
      setTimeout(() => onComplete?.(lastResponse), 1800)

    } catch (err) {
      const isOffline = !err.response && (
        err.code === 'ERR_NETWORK' || err.code === 'ECONNREFUSED' ||
        err.message?.toLowerCase().includes('network')
      )
      setIngestionState(prev => ({
        ...prev, phase: 'error',
        errorMsg: isOffline
          ? '⚠️ Backend offline.\nStart with:\n  uvicorn app.main:app --reload --port 8000'
          : err.response?.data?.detail || err.message || 'Upload failed',
        statusMsg: '', overallPct: 0,
      }))
    }
  }

  const handleClear = () => {
    setLocalFiles([])
    clearIngestionState()
  }

  const detectedKeys = Object.entries(detectedResources).filter(([, n]) => n > 0)

  return (
    <div className="ingestion-page">
      {/* Header */}
      <div className="stage-header">
        <div className="stage-header__badge">Stage 2</div>
        <h1 className="stage-header__title">Data Ingestion</h1>
        <p className="stage-header__desc">
          Upload a patient dataset — <strong>ZIP folder</strong>, individual <strong>CSV</strong> or
          <strong> FHIR JSON</strong> files, or select an entire folder.
          The pipeline scans every file, detects all resource types, and reports any files it couldn't parse.
        </p>
      </div>

      {/* Format chips */}
      <div className="format-chips">
        {[
          { ext:'ZIP',    desc:'Zipped folder — all inner CSV/JSON are scanned' },
          { ext:'CSV',    desc:'Tabular file — filename or columns identify type'  },
          { ext:'JSON',   desc:'FHIR Bundle or resource array'                    },
          { ext:'FOLDER', desc:'Upload entire folder — every file inside scanned' },
        ].map(f => (
          <div key={f.ext} className="format-chip">
            <span className="format-chip__ext">{f.ext}</span>
            <span className="format-chip__desc">{f.desc}</span>
          </div>
        ))}
      </div>

      {/* Drop Zone — show compact if already done */}
      {!isDone ? (
        <div
          className={`drop-zone${dragging ? ' drop-zone--active' : ''}${displayFiles.length ? ' drop-zone--has-files' : ''}`}
          onDrop={onDrop}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onClick={() => !displayFiles.length && inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" multiple accept=".zip,.csv,.json,.hl7,.txt"
            style={{ display:'none' }} onChange={e => addFiles(e.target.files)} />
          <input ref={folderRef} type="file" multiple webkitdirectory="true" directory="true"
            style={{ display:'none' }} onChange={e => addFiles(e.target.files)} />

          {!displayFiles.length ? (
            <div className="drop-zone__empty">
              <div className="drop-zone__icon">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
                  <polyline points="16 16 12 12 8 16"/>
                  <line x1="12" y1="12" x2="12" y2="21"/>
                  <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
                </svg>
              </div>
              <div className="drop-zone__text">
                <strong>Drop files or folders here</strong>
                <span>ZIP · CSV · FHIR JSON — or select an entire folder</span>
              </div>
              <div style={{ display:'flex', gap:10, flexWrap:'wrap', justifyContent:'center', marginTop:4 }}>
                <button className="btn btn--secondary btn--sm"
                  onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>📄 Browse Files</button>
                <button className="btn btn--secondary btn--sm"
                  onClick={e => { e.stopPropagation(); folderRef.current?.click() }}>📁 Upload Folder</button>
              </div>
              <div className="drop-zone__hint">Every CSV/JSON inside a ZIP or folder is scanned automatically</div>
            </div>
          ) : (
            <div className="drop-zone__files">
              <div className="drop-zone__files-header">
                <span>{displayFiles.length} file{displayFiles.length !== 1 ? 's' : ''} queued</span>
                <div style={{ display:'flex', gap:8 }}>
                  <button className="btn btn--sm btn--ghost"
                    onClick={e => { e.stopPropagation(); folderRef.current?.click() }}>📁 Add Folder</button>
                  <button className="btn btn--sm btn--ghost"
                    onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>+ Add Files</button>
                </div>
              </div>
              {Object.entries(grouped).map(([ext, group]) => (
                <div key={ext} className="file-group">
                  <div className="file-group__label">{ext.toUpperCase()} ({group.length})</div>
                  {group.map(f => (
                    <div key={f.name} className="file-item">
                      <span className="file-item__icon">{getIcon(f.name)}</span>
                      <span className="file-item__name" title={f.name}>{f.name}</span>
                      <span className="file-item__size">{formatSize(f.size)}</span>
                      {f.resourcesFound > 0 && (
                        <span style={{ fontSize:'0.7rem', color:'#16a34a', fontWeight:600, flexShrink:0 }}>
                          {f.resourcesFound.toLocaleString()} rec
                        </span>
                      )}
                      <Chip status={f.status} />
                      {!loading && (
                        <button className="file-item__remove"
                          onClick={e => { e.stopPropagation(); removeFile(f.name) }}>×</button>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* Compact restore view when coming back to this stage */
        <div className="ingest-done-bar">
          <div className="ingest-done-bar__left">
            <span className="ingest-done-bar__icon">✅</span>
            <div>
              <div className="ingest-done-bar__title">Dataset Loaded — {detectedKeys.length} resource types</div>
              <div className="ingest-done-bar__sub">{totalRecords.toLocaleString()} total records · {iState.files.length} files processed</div>
            </div>
          </div>
          <div style={{ display:'flex', gap:8 }}>
            <button className="btn btn--sm btn--ghost" onClick={handleClear}>🔄 Load New Dataset</button>
            <button className="btn btn--sm btn--primary" onClick={() => onComplete?.()}>Continue →</button>
          </div>
        </div>
      )}

      {/* Error banner */}
      {errorMsg && (
        <div className="alert alert--error" style={{ whiteSpace:'pre-line', marginTop:12 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink:0 }}>
            <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/>
          </svg>
          {errorMsg}
        </div>
      )}

      {/* Progress bar */}
      {loading && (
        <div className="upload-progress" style={{ marginTop:12 }}>
          <div className="upload-progress__bar">
            <div className="upload-progress__fill" style={{ width:`${overallPct}%` }} />
          </div>
          <span className="upload-progress__label">{statusMsg || `Scanning… ${overallPct}%`}</span>
        </div>
      )}

      {/* ── Detected Resources Panel ────────────────────────── */}
      {detectedKeys.length > 0 && (
        <div className="resource-detect-panel" style={{ marginTop:16 }}>
          <div className="resource-detect-panel__header">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
              <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            {isDone
              ? `✅ ${detectedKeys.length} Resource Types Detected — ${totalRecords.toLocaleString()} Total Records`
              : `🔍 Detecting… ${detectedKeys.length} type${detectedKeys.length !== 1 ? 's' : ''} found`}
          </div>
          <div className="resource-detect-grid">
            {detectedKeys.map(([key, count]) => (
              <ResourceBadge key={key} label={TAB_LABELS[key] || key} count={count} />
            ))}
          </div>
        </div>
      )}

      {/* ── Ingestion Summary + Mappings + Unrecognized ───── */}
      {(detectedKeys.length > 0 || detectionSummary.total > 0) && (
        <DetectionSummaryPanel
          unrecognized={detectionSummary.unrecognizedDetails || failedFiles}
          total={detectionSummary.total || iState.files.length}
          totalRecognized={detectionSummary.recognized || (iState.files.length - failedFiles.length)}
          allFiles={detectionSummary.recognizedDetails}
        />
      )}

      {/* Success banner */}
      {isDone && !loading && (
        <div className="alert alert--success" style={{ marginTop:12 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ flexShrink:0 }}>
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          {detectedKeys.length} resource type{detectedKeys.length !== 1 ? 's' : ''} loaded
          {failedFiles.length > 0 ? ` · ${failedFiles.length} file${failedFiles.length !== 1 ? 's' : ''} skipped` : ''} — advancing to Review…
        </div>
      )}

      {/* Actions */}
      {!isDone && (
        <div className="stage-actions">
          <button className="btn btn--ghost"
            onClick={handleClear}
            disabled={loading || (!displayFiles.length && !detectedKeys.length)}>
            Clear All
          </button>
          <button id="btn-process-upload" className="btn btn--primary"
            onClick={handleProcess}
            disabled={loading || !localFiles.length}>
            {loading
              ? <><span className="btn-spinner"/> Scanning {localFiles.length} file{localFiles.length !== 1 ? 's' : ''}…</>
              : <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="9 11 12 14 22 4"/>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                  </svg>
                  Scan &amp; Process Dataset
                </>}
          </button>
        </div>
      )}
    </div>
  )
}
