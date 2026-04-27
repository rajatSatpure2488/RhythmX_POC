import { useState, useRef, useCallback } from 'react'
import { useDataset } from '../context/DatasetContext'
import axios from 'axios'

// Direct to backend — bypasses Vite proxy for large files
const BACKEND = 'http://localhost:8000'

const FILE_ICONS = {
  zip: '🗜️', csv: '📊', json: '📋', hl7: '🏥', txt: '📄', default: '📁',
}

function getExt(name) { return (name || '').split('.').pop().toLowerCase() }
function getIcon(name) { return FILE_ICONS[getExt(name)] ?? FILE_ICONS.default }
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function Ingestion({ onComplete }) {
  const { setLoaded }             = useDataset()
  const [files, setFiles]         = useState([])
  const [dragging, setDragging]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [progress, setProgress]   = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)
  const inputRef                  = useRef()
  const folderRef                 = useRef()

  // ── File management ───────────────────────────────────────
  const addFiles = useCallback((incoming) => {
    const allowed = ['zip', 'csv', 'json', 'hl7', 'txt']
    const arr = Array.from(incoming).filter(f => allowed.includes(getExt(f.name)))
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...arr.filter(f => !names.has(f.name))]
    })
    setError(null)
    setResult(null)
  }, [])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }, [addFiles])

  const removeFile = (name) => setFiles(prev => prev.filter(f => f.name !== name))

  // ── Sequential file-by-file upload ───────────────────────
  // Sends each file separately to /upload/load-single so no
  // single request body ever exceeds what the proxy can handle.
  const handleProcess = async () => {
    if (!files.length) { setError('Please add at least one file.'); return }
    setLoading(true); setError(null); setResult(null); setProgress(0)

    try {
      // Reset backend session
      await axios.post(`${BACKEND}/upload/clear`)

      let lastResponse = null

      for (let i = 0; i < files.length; i++) {
        const f    = files[i]
        const pct  = Math.round(((i) / files.length) * 90)
        setProgress(pct)
        setStatusMsg(`Uploading ${i + 1}/${files.length}: ${f.name}`)

        const form = new FormData()
        form.append('file', f)

        const res = await axios.post(`${BACKEND}/upload/load-single`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000,
        })
        lastResponse = res.data
      }

      setProgress(100)
      setStatusMsg('Parsing complete!')
      setResult(lastResponse)
      setLoaded(lastResponse?.patient_info ?? null, lastResponse?.resources ?? {})
      setTimeout(() => onComplete?.(lastResponse), 900)

    } catch (err) {
      const isOffline = !err.response && (
        err.code === 'ERR_NETWORK' ||
        err.code === 'ECONNREFUSED' ||
        err.message?.toLowerCase().includes('network')
      )
      setError(isOffline
        ? '⚠️ Backend is offline. Start the FastAPI server:\n  uvicorn app.main:app --reload --port 8000'
        : err.response?.data?.detail || err.message || 'Upload failed'
      )
      setProgress(0)
      setStatusMsg('')
    } finally {
      setLoading(false)
    }
  }

  const grouped = files.reduce((acc, f) => {
    const ext = getExt(f.name)
    ;(acc[ext] = acc[ext] || []).push(f)
    return acc
  }, {})

  return (
    <div className="ingestion-page">
      {/* Header */}
      <div className="stage-header">
        <div className="stage-header__badge">Stage 2</div>
        <h1 className="stage-header__title">Data Ingestion</h1>
        <p className="stage-header__desc">
          Upload patient datasets in any supported format. Mix ZIP archives, CSV files,
          and FHIR JSON in a single batch — each file is processed individually for reliability.
        </p>
      </div>

      {/* Format chips */}
      <div className="format-chips">
        {[
          { ext: 'ZIP',  desc: 'Zipped dataset folder' },
          { ext: 'CSV',  desc: 'Tabular resource files' },
          { ext: 'JSON', desc: 'FHIR JSON bundles'      },
          { ext: 'HL7',  desc: 'HL7 v2/v3 messages'    },
        ].map(f => (
          <div key={f.ext} className="format-chip">
            <span className="format-chip__ext">{f.ext}</span>
            <span className="format-chip__desc">{f.desc}</span>
          </div>
        ))}
      </div>

      {/* Drop Zone */}
      <div
        className={`drop-zone${dragging ? ' drop-zone--active' : ''}${files.length ? ' drop-zone--has-files' : ''}`}
        onDrop={onDrop}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onClick={() => !files.length && inputRef.current?.click()}
      >
        {/* Hidden file input */}
        <input
          ref={inputRef} type="file" multiple
          accept=".zip,.csv,.json,.hl7,.txt"
          style={{ display: 'none' }}
          onChange={e => addFiles(e.target.files)}
        />
        {/* Hidden folder input */}
        <input
          ref={folderRef} type="file"
          style={{ display: 'none' }}
          webkitdirectory="true" directory="true" multiple
          onChange={e => addFiles(e.target.files)}
        />

        {!files.length ? (
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
              <span>or choose an option below</span>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
              <button className="btn btn--secondary btn--sm"
                onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>
                📄 Browse Files
              </button>
              <button className="btn btn--secondary btn--sm"
                onClick={e => { e.stopPropagation(); folderRef.current?.click() }}>
                📁 Upload Folder
              </button>
            </div>
            <div className="drop-zone__hint">ZIP · CSV · JSON · HL7 — mix formats freely</div>
          </div>
        ) : (
          <div className="drop-zone__files">
            <div className="drop-zone__files-header">
              <span>{files.length} file{files.length !== 1 ? 's' : ''} ready</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn--sm btn--ghost"
                  onClick={e => { e.stopPropagation(); folderRef.current?.click() }}>
                  📁 Add Folder
                </button>
                <button className="btn btn--sm btn--ghost"
                  onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>
                  + Add Files
                </button>
              </div>
            </div>
            {Object.entries(grouped).map(([ext, group]) => (
              <div key={ext} className="file-group">
                <div className="file-group__label">{ext.toUpperCase()} ({group.length})</div>
                {group.map(f => (
                  <div key={f.name} className="file-item">
                    <span className="file-item__icon">{getIcon(f.name)}</span>
                    <span className="file-item__name">{f.name}</span>
                    <span className="file-item__size">{formatSize(f.size)}</span>
                    <button className="file-item__remove"
                      onClick={e => { e.stopPropagation(); removeFile(f.name) }}>×</button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="alert alert--error" style={{ whiteSpace: 'pre-line' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
            <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/>
          </svg>
          {error}
        </div>
      )}

      {/* Progress */}
      {loading && (
        <div className="upload-progress">
          <div className="upload-progress__bar">
            <div className="upload-progress__fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="upload-progress__label">{statusMsg || `Processing… ${progress}%`}</span>
        </div>
      )}

      {/* Success */}
      {result && !loading && (
        <div className="alert alert--success">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ flexShrink: 0 }}>
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Dataset ingested — {result.total_records ?? 0} records across {result.resource_count ?? 0} resource types. Advancing to Review…
        </div>
      )}

      {/* Actions */}
      <div className="stage-actions">
        <button className="btn btn--ghost"
          onClick={() => { setFiles([]); setError(null); setResult(null); setProgress(0) }}
          disabled={loading || !files.length}>
          Clear All
        </button>
        <button id="btn-process-upload" className="btn btn--primary"
          onClick={handleProcess} disabled={loading || !files.length}>
          {loading
            ? <><span className="btn-spinner" /> Processing {statusMsg ? '…' : ''}</>
            : <>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 11 12 14 22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
                Process Dataset
              </>
          }
        </button>
      </div>
    </div>
  )
}
