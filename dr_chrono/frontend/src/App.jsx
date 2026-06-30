import React, { useEffect, useRef, useState } from 'react'
import {
  clearUploadSession,
  getUploadStatus,
  loadFiles,
  loadSingleFile,
  pushUploadedFiles
} from './services/ehrApi'

const allowedExtensions = new Set(['csv', 'json', 'zip'])

function fileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function extensionOf(fileName) {
  return fileName.split('.').pop().toLowerCase()
}

function ResultList({ title, items, emptyText }) {
  return (
    <section className="panel">
      <div className="panel__header">
        <h2>{title}</h2>
      </div>
      {!items?.length ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <div className="result-list">
          {items.map((item, index) => (
            <div className="result-row" key={`${item.filename || item.category_name || index}-${index}`}>
              <span className={item.success === false || item.recognized === false ? 'dot dot--error' : 'dot'} />
              <div>
                <strong>{item.filename || item.category_name || item.detected_as || `Result ${index + 1}`}</strong>
                <p>
                  {item.error ||
                    item.failure_reason ||
                    item.method ||
                    item.category_api ||
                    'Processed successfully'}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default function App() {
  const inputRef = useRef(null)
  const [files, setFiles] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [statusError, setStatusError] = useState('')
  const [uploadSummary, setUploadSummary] = useState(null)
  const [status, setStatus] = useState(null)
  const [pushResults, setPushResults] = useState([])

  async function refreshStatus() {
    try {
      const nextStatus = await getUploadStatus()
      setStatus(nextStatus)
      setStatusError('')
      return nextStatus
    } catch (err) {
      setStatus(null)
      setStatusError(err.message || 'Backend is not reachable yet.')
      throw err
    }
  }

  useEffect(() => {
    refreshStatus().catch(() => {
      // First paint should still show the uploader when backend is offline.
    })
  }, [])

  function addFiles(fileList) {
    const incoming = Array.from(fileList || [])
    const supported = incoming.filter((file) => allowedExtensions.has(extensionOf(file.name)))
    const existingNames = new Set(files.map((file) => `${file.name}-${file.size}`))
    const unique = supported.filter((file) => !existingNames.has(`${file.name}-${file.size}`))
    setFiles((current) => [...current, ...unique])

    if (incoming.length !== supported.length) {
      setError('Only CSV, JSON, and ZIP files are supported.')
    } else {
      setError('')
    }
  }

  function removeFile(index) {
    setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  async function runAction(label, action) {
    setBusy(label)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Request failed.')
    } finally {
      setBusy('')
    }
  }

  function handleLoadAll() {
    if (!files.length) return
    runAction('load', async () => {
      const result = await loadFiles(files)
      setUploadSummary(result)
      setPushResults([])
      await refreshStatus()
    })
  }

  function handleMergeOne(file) {
    runAction(`merge-${file.name}`, async () => {
      const result = await loadSingleFile(file)
      setUploadSummary(result)
      await refreshStatus()
    })
  }

  function handlePush() {
    if (!files.length) return
    runAction('push', async () => {
      const result = await pushUploadedFiles(files)
      setPushResults(Array.isArray(result) ? result : [result])
    })
  }

  function handleClear() {
    runAction('clear', async () => {
      await clearUploadSession()
      setUploadSummary(null)
      setStatus(null)
      setPushResults([])
      await refreshStatus()
    })
  }

  const detectionDetails = uploadSummary?.detection_summary?.details || []
  const resources = uploadSummary?.resources || {}

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">DrChrono EHR Connector</p>
          <h1>Upload clinical files, review detected resources, then push to EHR.</h1>
          <p className="hero__copy">
            This screen is intentionally focused on the standalone DrChrono flow:
            CSV, JSON, and ZIP files go through the upload service, then the same
            files can be sent to the dynamic EHR API handler.
          </p>
        </div>
        <div className="status-card">
          <span>Session</span>
          <strong>{statusError ? 'Backend Offline' : status?.loaded ? 'Loaded' : 'Empty'}</strong>
          <p>
            {statusError ||
              `${status?.total_records || 0} records across ${status?.resource_count || 0} resource groups`}
          </p>
        </div>
      </section>

      <section
        className={`drop-panel${dragging ? ' drop-panel--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          addFiles(event.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.json,.zip"
          onChange={(event) => addFiles(event.target.files)}
        />
        <span className="drop-panel__badge">CSV / JSON / ZIP</span>
        <h2>Drop files here or browse from your machine</h2>
        <p>Filename decides resource type, for example `patient.csv`, `medications.csv`, or `careplan.json`.</p>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="workspace">
        <div className="panel">
          <div className="panel__header">
            <h2>Selected Files</h2>
            <span>{files.length} ready</span>
          </div>
          {!files.length ? (
            <p className="muted">No files selected yet.</p>
          ) : (
            <div className="file-list">
              {files.map((file, index) => (
                <div className="file-card" key={`${file.name}-${file.size}`}>
                  <div>
                    <strong>{file.name}</strong>
                    <p>{extensionOf(file.name).toUpperCase()} file · {fileSize(file.size)}</p>
                  </div>
                  <div className="file-card__actions">
                    <button type="button" onClick={() => handleMergeOne(file)} disabled={Boolean(busy)}>
                      Merge
                    </button>
                    <button type="button" className="ghost" onClick={() => removeFile(index)} disabled={Boolean(busy)}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="action-row">
            <button type="button" className="primary" onClick={handleLoadAll} disabled={!files.length || Boolean(busy)}>
              {busy === 'load' ? 'Loading...' : 'Load Batch'}
            </button>
            <button type="button" className="accent" onClick={handlePush} disabled={!files.length || Boolean(busy)}>
              {busy === 'push' ? 'Pushing...' : 'Push To EHR'}
            </button>
            <button type="button" className="ghost" onClick={handleClear} disabled={Boolean(busy)}>
              Clear Session
            </button>
          </div>
        </div>

        <section className="panel">
          <div className="panel__header">
            <h2>Detected Resources</h2>
            <button type="button" className="ghost" onClick={refreshStatus}>Refresh</button>
          </div>
          {!Object.keys(resources).length ? (
            <p className="muted">Load files to see detected resources here.</p>
          ) : (
            <div className="resource-grid">
              {Object.entries(resources).map(([resourceType, records]) => (
                <div className="resource-pill" key={resourceType}>
                  <span>{resourceType}</span>
                  <strong>{records.length}</strong>
                </div>
              ))}
            </div>
          )}
        </section>
      </section>

      <section className="workspace workspace--bottom">
        <ResultList
          title="Upload Detection"
          items={detectionDetails}
          emptyText="No detection details yet."
        />
        <ResultList
          title="EHR Push Results"
          items={pushResults}
          emptyText="No EHR push has been run yet."
        />
      </section>
    </main>
  )
}
