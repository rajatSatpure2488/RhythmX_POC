import { useRef, useState } from 'react'
import { useDataset } from '../../context/DatasetContext'
import { uploadAndProcess } from '../../services/ehrService'

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function FileUploader() {
  const { dataset, stageFiles, removeFile } = useDataset()
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const zipRef    = useRef()
  const folderRef = useRef()
  const filesRef  = useRef()

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const items = e.dataTransfer.files
    if (items.length) stageFiles(items)
  }

  const handleLoad = async () => {
    if (!dataset.stagedFiles.length) return
    setLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      dataset.stagedFiles.forEach(f => fd.append('files', f))
      await uploadAndProcess(fd)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h1 className="card__title">Upload Dataset</h1>
      <p className="card__subtitle">
        Securely transfer patient records and clinical notes for ingestion.
      </p>

      <div className="divider" />

      {/* Drop zone */}
      <div
        id="dropzone"
        className={`dropzone${dragOver ? ' dragover' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => filesRef.current.click()}
      >
        <div className="dropzone__icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1565C0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
            <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
          </svg>
        </div>
        <div className="dropzone__title">Drop your ZIP file, folder, or files here</div>
        <div className="dropzone__hint">
          Supports standard HL7, FHIR JSON, and unstructured clinical notes (PDF, TXT). Max 5GB per batch.
        </div>
      </div>

      {/* Hidden file inputs */}
      <input ref={zipRef}    type="file" accept=".zip" style={{ display: 'none' }}
        onChange={e => stageFiles(e.target.files)} />
      <input ref={folderRef} type="file" style={{ display: 'none' }} webkitdirectory=""
        onChange={e => stageFiles(e.target.files)} />
      <input ref={filesRef}  type="file" multiple style={{ display: 'none' }}
        onChange={e => stageFiles(e.target.files)} />

      {/* Upload buttons */}
      <div className="upload-buttons">
        <button id="btn-upload-zip"    className="btn" onClick={() => zipRef.current.click()}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          Upload ZIP
        </button>
        <button id="btn-upload-folder" className="btn" onClick={() => folderRef.current.click()}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          Upload Folder
        </button>
        <button id="btn-upload-files"  className="btn" onClick={() => filesRef.current.click()}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
          Upload Files
        </button>
      </div>

      {/* Staged files */}
      {dataset.stagedFiles.length > 0 && (
        <div className="staged-files">
          <div className="staged-files__label">
            Staged Files ({dataset.stagedFiles.length})
          </div>
          {dataset.stagedFiles.map((file, i) => (
            <div key={i} className="staged-file-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1565C0" strokeWidth="2">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                <polyline points="13 2 13 9 20 9"/>
              </svg>
              <span className="staged-file-item__name">{file.name}</span>
              <span className="staged-file-item__size">{formatBytes(file.size)}</span>
              <button className="btn btn--danger" id={`remove-file-${i}`} onClick={() => removeFile(i)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                  <path d="M10 11v6"/><path d="M14 11v6"/>
                  <path d="M9 6V4h6v2"/>
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {error && (
        <p style={{ color: 'var(--danger)', fontSize: '0.78rem', marginTop: '12px' }}>{error}</p>
      )}

      {/* CTA */}
      <button
        id="btn-load-dataset"
        className="btn btn--primary"
        disabled={dataset.stagedFiles.length === 0 || loading}
        onClick={handleLoad}
      >
        {loading ? (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'spin 1s linear infinite' }}>
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            Processing…
          </>
        ) : (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            LOAD &amp; PROCESS DATASET
          </>
        )}
      </button>
    </div>
  )
}
