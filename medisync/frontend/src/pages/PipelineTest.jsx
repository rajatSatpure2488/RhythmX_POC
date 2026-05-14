/**
 * PipelineTest.jsx — Self-contained test UI for the FHIR Pipeline module.
 *
 * INDEPENDENT from main Dashboard. To remove:
 *   1. Delete this file + PipelineTest.css
 *   2. Remove the import/toggle from App.jsx
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../services/api'
import './PipelineTest.css'

const SAMPLE_DATA = {
  patient_csv: {
    label: 'Patient (CSV)', resource_type: 'patient', source_format: 'csv',
    record: { first_name: 'John', last_name: 'Doe', dob: '1990-01-15', gender: 'Male', phone: '555-0100', email: 'john@example.com', address: '123 Main St', city: 'Boston', state: 'MA', zip: '02101' }
  },
  patient_fhir: {
    label: 'Patient (FHIR)', resource_type: 'patient', source_format: 'fhir',
    record: { resourceType: 'Patient', name: [{ use: 'official', family: 'Smith', given: ['Jane'] }], birthDate: '1985-06-20', gender: 'female', telecom: [{ system: 'phone', value: '555-0200' }, { system: 'email', value: 'jane@example.com' }], address: [{ use: 'home', line: ['456 Oak Ave'], city: 'New York', state: 'NY', postalCode: '10001' }] }
  },
  medication_fhir: {
    label: 'Medication (FHIR)', resource_type: 'medication', source_format: 'fhir',
    record: { resourceType: 'MedicationRequest', medicationCodeableConcept: { coding: [{ system: 'http://www.nlm.nih.gov/research/umls/rxnorm', code: '197361', display: 'Amlodipine 5 MG' }], text: 'Amlodipine 5mg' }, status: 'active', authoredOn: '2024-03-15', dosageInstruction: [{ text: 'Take 1 tablet daily', route: { coding: [{ display: 'Oral' }] } }] }
  },
  condition_csv: {
    label: 'Condition (CSV)', resource_type: 'condition', source_format: 'csv',
    record: { icd_code: 'I10', description: 'Essential Hypertension', onset_date: '2023-01-10', status: 'active' }
  },
  allergy_fhir: {
    label: 'Allergy (FHIR)', resource_type: 'allergy', source_format: 'fhir',
    record: { resourceType: 'AllergyIntolerance', code: { coding: [{ system: 'http://snomed.info/sct', code: '387207008', display: 'Ibuprofen' }] }, clinicalStatus: { coding: [{ code: 'active' }] }, reaction: [{ manifestation: [{ coding: [{ display: 'Hives' }] }], severity: 'moderate' }] }
  },
  immunization_csv: {
    label: 'Immunization (CSV)', resource_type: 'immunization', source_format: 'csv',
    record: { vaccine: 'COVID-19 mRNA Vaccine', cvx_code: '208', date: '2024-01-15', status: 'completed' }
  },
}

/* ── Helpers ──────────────────────────────────────────────── */
function JsonBlock({ data, label, collapsed = false }) {
  const [open, setOpen] = useState(!collapsed)
  if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) return null
  return (
    <div className="pp-json-block">
      <button className="pp-json-toggle" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} {label}
      </button>
      {open && <pre className="pp-json">{JSON.stringify(data, null, 2)}</pre>}
    </div>
  )
}

function Badge({ ok, label }) {
  return <span className={`pp-badge ${ok ? 'pp-badge-ok' : 'pp-badge-err'}`}>{label}</span>
}

/* ══════════════════════════════════════════════════════════ */
export default function PipelineTest() {
  const [status, setStatus] = useState(null)
  const [activeTab, setActiveTab] = useState('upload')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Config IDs (persistent across all tabs)
  const [doctorId, setDoctorId] = useState('')
  const [patientId, setPatientId] = useState('')
  const [officeId, setOfficeId] = useState('')

  // Upload state
  const fileInputRef = useRef(null)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [dragOver, setDragOver] = useState(false)

  // Mapper test state
  const [selectedSample, setSelectedSample] = useState('patient_csv')
  const [customJson, setCustomJson] = useState('')
  const [mapperResult, setMapperResult] = useState(null)

  // Pipeline state
  const [mapResult, setMapResult] = useState(null)
  const [validateResult, setValidateResult] = useState(null)

  // Push state
  const [pushResult, setPushResult] = useState(null)

  // Load status on mount
  const refreshStatus = useCallback(() => {
    api.get('/pipeline/status').then(r => setStatus(r.data)).catch(() => {})
  }, [])
  useEffect(() => { refreshStatus() }, [refreshStatus])

  /* ── Upload ───────────────────────────────────────────── */
  const handleUpload = useCallback(async (files) => {
    if (!files || files.length === 0) return
    setLoading(true); setError('')
    try {
      const formData = new FormData()
      for (const f of files) formData.append('files', f)
      const res = await api.post('/upload/load', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadResult(res.data)
      setUploadedFiles(prev => [
        ...prev,
        ...Array.from(files).map(f => ({ name: f.name, size: f.size }))
      ])
      refreshStatus()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [refreshStatus])

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragOver(false)
    handleUpload(e.dataTransfer.files)
  }, [handleUpload])

  const handleClear = useCallback(async () => {
    await api.post('/upload/clear').catch(() => {})
    setUploadResult(null); setUploadedFiles([])
    setMapResult(null); setValidateResult(null); setPushResult(null)
    refreshStatus()
  }, [refreshStatus])

  /* ── Mapper Test ──────────────────────────────────────── */
  const runMapperTest = useCallback(async () => {
    setLoading(true); setError(''); setMapperResult(null)
    try {
      let payload
      if (customJson.trim()) {
        const parsed = JSON.parse(customJson)
        payload = { resource_type: selectedSample.split('_')[0], record: parsed, source_format: 'auto' }
      } else {
        const sample = SAMPLE_DATA[selectedSample]
        payload = { resource_type: sample.resource_type, record: sample.record, source_format: sample.source_format }
      }
      const res = await api.post('/pipeline/test-mapper', payload)
      setMapperResult(res.data)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [selectedSample, customJson])

  /* ── Pipeline ─────────────────────────────────────────── */
  const runMap = useCallback(async () => {
    setLoading(true); setError(''); setMapResult(null)
    try {
      const res = await api.post('/pipeline/map', { resources: [] })
      setMapResult(res.data)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [])

  const runValidate = useCallback(async () => {
    setLoading(true); setError(''); setValidateResult(null)
    try {
      const res = await api.post('/pipeline/validate', {
        resources: [],
        doctor_id: doctorId ? parseInt(doctorId) : null,
        patient_id: patientId ? parseInt(patientId) : null,
        office_id: officeId ? parseInt(officeId) : null,
      })
      setValidateResult(res.data)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [doctorId, patientId, officeId])

  /* ── Push ──────────────────────────────────────────────── */
  const runPush = useCallback(async (dryRun) => {
    setLoading(true); setError(''); setPushResult(null)
    try {
      const res = await api.post('/pipeline/push', {
        resources: [],
        doctor_id: doctorId ? parseInt(doctorId) : null,
        patient_id: patientId ? parseInt(patientId) : null,
        office_id: officeId ? parseInt(officeId) : null,
        dry_run: dryRun,
      })
      setPushResult(res.data)
      // Auto-capture patient ID from push result
      if (res.data.patient_id && !patientId) {
        setPatientId(String(res.data.patient_id))
      }
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [doctorId, patientId, officeId])

  /* ── Computed ──────────────────────────────────────────── */
  const loadedCount = status
    ? Object.values(status.loaded_resources || {}).reduce((a, b) => a + b, 0)
    : 0

  return (
    <div className="pp-container">
      {/* ── Header ──────────────────────────────────────── */}
      <div className="pp-header">
        <div className="pp-header-left">
          <h1 className="pp-title">🔬 FHIR Pipeline Lab</h1>
          <p className="pp-subtitle">Independent test environment — safe to delete</p>
        </div>
        {status && (
          <div className="pp-header-badges">
            <Badge ok={true} label={`v${status.version}`} />
            <Badge ok={true} label={`${status.available_mappers?.length || 0} mappers`} />
            <Badge ok={loadedCount > 0} label={`${loadedCount} records loaded`} />
          </div>
        )}
      </div>

      {/* ── Config Bar (always visible) ─────────────────── */}
      <div className="pp-config-bar">
        <div className="pp-config-title">⚙️ DrChrono Config</div>
        <div className="pp-config-fields">
          <div className="pp-config-field">
            <label>Doctor ID <span className="pp-required">*</span></label>
            <input type="number" value={doctorId} onChange={e => setDoctorId(e.target.value)}
                   placeholder="e.g. 394073" />
          </div>
          <div className="pp-config-field">
            <label>Patient ID</label>
            <input type="number" value={patientId} onChange={e => setPatientId(e.target.value)}
                   placeholder="Auto on push" />
          </div>
          <div className="pp-config-field">
            <label>Office ID</label>
            <input type="number" value={officeId} onChange={e => setOfficeId(e.target.value)}
                   placeholder="For appts" />
          </div>
        </div>
        {!doctorId && <div className="pp-config-hint">💡 Enter your DrChrono Doctor ID to enable validation & push</div>}
      </div>

      {/* ── Tabs ────────────────────────────────────────── */}
      <div className="pp-tabs">
        {[
          { key: 'upload',   label: '📂 Upload Data' },
          { key: 'mapper',   label: '🧪 Mapper Test' },
          { key: 'pipeline', label: '⚙️ Full Pipeline' },
          { key: 'push',     label: '🚀 Push to DrChrono' },
        ].map(tab => (
          <button key={tab.key}
                  className={`pp-tab ${activeTab === tab.key ? 'pp-tab-active' : ''}`}
                  onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>

      {error && <div className="pp-error">❌ {error}</div>}

      {/* ══ UPLOAD TAB ═══════════════════════════════════ */}
      {activeTab === 'upload' && (
        <div className="pp-section">
          <h2>Upload Clinical Data</h2>
          <p className="pp-hint">
            Drag & drop CSV, JSON (FHIR Bundle), or ZIP files. The system auto-detects resource types.
          </p>

          {/* Drop zone */}
          <div className={`pp-dropzone ${dragOver ? 'pp-dropzone-active' : ''}`}
               onDragOver={e => { e.preventDefault(); setDragOver(true) }}
               onDragLeave={() => setDragOver(false)}
               onDrop={handleDrop}
               onClick={() => fileInputRef.current?.click()}>
            <input ref={fileInputRef} type="file" multiple accept=".csv,.json,.zip"
                   style={{ display: 'none' }}
                   onChange={e => handleUpload(e.target.files)} />
            <div className="pp-dropzone-icon">📂</div>
            <div className="pp-dropzone-text">
              {loading ? '⏳ Uploading...' : 'Drop files here or click to browse'}
            </div>
            <div className="pp-dropzone-hint">Supports: CSV, JSON (FHIR), ZIP</div>
          </div>

          {/* Uploaded files */}
          {uploadedFiles.length > 0 && (
            <div className="pp-uploaded-files">
              <div className="pp-uploaded-header">
                <h3>📁 Uploaded Files ({uploadedFiles.length})</h3>
                <button className="pp-btn pp-btn-small pp-btn-danger" onClick={handleClear}>Clear All</button>
              </div>
              {uploadedFiles.map((f, i) => (
                <div key={i} className="pp-file-row">
                  <span className="pp-file-icon">📄</span>
                  <span className="pp-file-name">{f.name}</span>
                  <span className="pp-file-size">{(f.size / 1024).toFixed(1)} KB</span>
                </div>
              ))}
            </div>
          )}

          {/* Upload results */}
          {uploadResult && (
            <div className="pp-result-card">
              <h3>Detection Results — {uploadResult.total_records} records found</h3>
              <div className="pp-resource-grid">
                {Object.entries(uploadResult.resources || {}).map(([key, records]) => (
                  <div key={key} className="pp-resource-card">
                    <div className="pp-resource-name">{key}</div>
                    <div className="pp-resource-stats">
                      <Badge ok={true} label={`${records.length} records`} />
                    </div>
                    <JsonBlock data={records[0]} label="Sample record" collapsed />
                  </div>
                ))}
              </div>
              {uploadResult.detection_summary && (
                <div style={{ marginTop: 12, fontSize: '0.82rem', color: '#94a3b8' }}>
                  ✅ {uploadResult.detection_summary.recognized_files} recognized
                  {uploadResult.detection_summary.unrecognized_files > 0 &&
                    <> · ⚠️ {uploadResult.detection_summary.unrecognized_files} unrecognized</>}
                </div>
              )}
              <div className="pp-next-step">
                ✨ Data loaded! Go to <button className="pp-link-btn" onClick={() => setActiveTab('pipeline')}>⚙️ Full Pipeline</button> to map & validate.
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══ MAPPER TEST TAB ══════════════════════════════ */}
      {activeTab === 'mapper' && (
        <div className="pp-section">
          <h2>Test Individual Mappers</h2>
          <p className="pp-hint">Select a sample or paste custom JSON to test how data gets mapped to DrChrono format.</p>
          <div className="pp-row">
            <div className="pp-col">
              <label className="pp-label">Sample Data</label>
              <div className="pp-sample-grid">
                {Object.entries(SAMPLE_DATA).map(([key, val]) => (
                  <button key={key}
                          className={`pp-sample-btn ${selectedSample === key ? 'pp-sample-active' : ''}`}
                          onClick={() => { setSelectedSample(key); setCustomJson('') }}>
                    {val.label}
                  </button>
                ))}
              </div>
              <label className="pp-label" style={{marginTop: 16}}>Or paste custom JSON:</label>
              <textarea className="pp-textarea" rows={6} value={customJson}
                        onChange={e => setCustomJson(e.target.value)}
                        placeholder='{"resourceType": "Patient", "name": [...]}' />
              <button className="pp-btn pp-btn-primary" onClick={runMapperTest} disabled={loading}>
                {loading ? '⏳ Mapping...' : '▶ Run Mapper'}
              </button>
            </div>
            <div className="pp-col">
              {mapperResult ? (
                <>
                  <div className="pp-result-header">
                    <Badge ok={mapperResult.is_valid} label={mapperResult.is_valid ? '✅ DATA VALID' : '❌ DATA ERRORS'} />
                    <span className="pp-format-tag">Format: {mapperResult.detected_format}</span>
                  </div>
                  <JsonBlock data={mapperResult.mapping?.payload} label="Mapped Payload (DrChrono format)" />
                  <JsonBlock data={mapperResult.post_processed} label="Post-Processed" collapsed />

                  {/* Data errors (must fix) */}
                  {mapperResult.validation_errors?.length > 0 && (
                    <div className="pp-errors-list">
                      <h4>❌ Data Errors (must fix in your files):</h4>
                      {mapperResult.validation_errors.map((e, i) => (
                        <div key={i} className="pp-error-item">{e}</div>
                      ))}
                    </div>
                  )}

                  {/* System info (auto-injected at push) */}
                  {mapperResult.system_info?.length > 0 && (
                    <div className="pp-system-info">
                      <h4>ℹ️ System IDs (auto-injected at push time):</h4>
                      {mapperResult.system_info.map((e, i) => (
                        <div key={i} className="pp-info-item">{e}</div>
                      ))}
                    </div>
                  )}

                  {/* Recommendations */}
                  {mapperResult.recommendations?.length > 0 && (
                    <div className="pp-recommendations">
                      <h4>💡 Recommended fields (optional):</h4>
                      {mapperResult.recommendations.map((e, i) => (
                        <div key={i} className="pp-rec-item">{e}</div>
                      ))}
                    </div>
                  )}

                  <JsonBlock data={SAMPLE_DATA[selectedSample]?.record} label="Original Input" collapsed />
                </>
              ) : (
                <div className="pp-empty">Select a sample and click "Run Mapper" to see results</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══ PIPELINE TAB ═════════════════════════════════ */}
      {activeTab === 'pipeline' && (
        <div className="pp-section">
          <h2>Full Pipeline: Map → Validate</h2>
          <p className="pp-hint">
            {loadedCount > 0
              ? <>✅ <strong>{loadedCount} records</strong> loaded from {Object.keys(status?.loaded_resources || {}).length} resource types. Ready to map!</>
              : <>⚠️ No data loaded. Go to <button className="pp-link-btn" onClick={() => setActiveTab('upload')}>📂 Upload</button> tab first.</>
            }
          </p>

          <div className="pp-btn-row">
            <button className="pp-btn pp-btn-primary" onClick={runMap} disabled={loading || loadedCount === 0}>
              {loading ? '⏳' : '1️⃣'} Map Resources
            </button>
            <button className="pp-btn pp-btn-secondary" onClick={runValidate} disabled={loading || !mapResult}>
              {loading ? '⏳' : '2️⃣'} Validate
            </button>
          </div>

          {mapResult && (
            <div className="pp-result-card">
              <h3>Mapping Results — {mapResult.total_mapped} records mapped</h3>
              <div className="pp-resource-grid">
                {Object.entries(mapResult.results || {}).map(([key, val]) => (
                  <div key={key} className="pp-resource-card">
                    <div className="pp-resource-name">{key}</div>
                    <div className="pp-resource-stats">
                      <Badge ok={val.failed === 0} label={`${val.success}/${val.total}`} />
                      <span className="pp-format-tag">{val.source_format}</span>
                    </div>
                    {val.errors?.length > 0 && (
                      <div className="pp-mini-errors">{val.errors.map((e,i) => <div key={i}>{e}</div>)}</div>
                    )}
                    <JsonBlock data={val.sample} label="Sample payload" collapsed />
                  </div>
                ))}
              </div>
            </div>
          )}

          {validateResult && (
            <div className="pp-result-card">
              <h3>Validation — {validateResult.overall_rate}% pass rate</h3>
              <div className="pp-stat-bar">
                <div className="pp-stat-fill" style={{width: `${validateResult.overall_rate}%`}} />
              </div>
              <div className="pp-stat-nums">
                <span className="pp-stat-ok">✓ {validateResult.passed} passed</span>
                <span className="pp-stat-fail">✗ {validateResult.failed} failed</span>
              </div>
              {Object.entries(validateResult.details || {}).map(([key, val]) => (
                <div key={key} className="pp-validate-row">
                  <span className="pp-resource-name">{key}</span>
                  <Badge ok={val.pass_rate === 100} label={`${val.pass_rate}%`} />
                  {val.unique_errors?.length > 0 && (
                    <div className="pp-mini-errors">{val.unique_errors.map((e,i) => <div key={i}>{e}</div>)}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══ PUSH TAB ═════════════════════════════════════ */}
      {activeTab === 'push' && (
        <div className="pp-section">
          <h2>Push to DrChrono</h2>
          <p className="pp-hint">Orchestrated push: Patient first → children with injected IDs → retry on failure.</p>

          {!doctorId && (
            <div className="pp-warning">⚠️ Doctor ID is required for push. Enter it in the config bar above.</div>
          )}

          <div className="pp-btn-row">
            <button className="pp-btn pp-btn-secondary" onClick={() => runPush(true)} disabled={loading || loadedCount === 0}>
              {loading ? '⏳' : '🧪'} Dry Run (validate only)
            </button>
            <button className="pp-btn pp-btn-danger" onClick={() => runPush(false)} disabled={loading || !doctorId || loadedCount === 0}>
              {loading ? '⏳' : '🚀'} Live Push
            </button>
          </div>

          {pushResult && (
            <div className="pp-result-card">
              <h3>
                {pushResult.dry_run ? '🧪 Dry Run' : '🚀 Push'} Results
                — {pushResult.successful}/{pushResult.total} succeeded
              </h3>
              {pushResult.patient_id && (
                <div className="pp-patient-id">Patient ID: <strong>{pushResult.patient_id}</strong></div>
              )}
              {Object.entries(pushResult.results || {}).map(([key, records]) => (
                <div key={key} className="pp-push-group">
                  <h4>{key} ({records.length} records)</h4>
                  {records.map((r, i) => (
                    <div key={i} className={`pp-push-row ${r.success ? 'pp-push-ok' : 'pp-push-fail'}`}>
                      <Badge ok={r.success} label={r.success ? 'OK' : 'FAIL'} />
                      {r.drchrono_id && <span>ID: {r.drchrono_id}</span>}
                      {r.retries_used > 0 && <span className="pp-retry-tag">{r.retries_used} retries</span>}
                      {r.error && <span className="pp-push-error">{r.error}</span>}
                      {r.phase && <span className="pp-format-tag">{r.phase}</span>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="pp-footer">
        <span>🔬 FHIR Pipeline Lab — Independent module</span>
        <span>To remove: delete <code>fhir_pipeline/</code> + <code>PipelineTest.jsx</code></span>
      </div>
    </div>
  )
}
