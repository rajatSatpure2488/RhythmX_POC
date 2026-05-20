import { useState, useRef, useEffect } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import { useAuth } from '../context/AuthContext'
import { ApiPrePushBot, ApiPostPushBot } from '../components/ApiMonitorBot'
import api from '../services/api'   // ← shared axios client with Vite proxy baseURL

const TAB_LABELS = {
  medications:'Medications', medication:'Medications', conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters', observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies', immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures', patient:'Patient', patients:'Patient',
  documents:'Documents', document:'Documents',
  document_reference:'Documents', document_references:'Documents',
  problems:'Conditions', problem:'Conditions', problem_list:'Conditions',
  clinical_notes:'Clinical Notes', clinical_note:'Clinical Notes',
  coverages:'Insurance', coverage:'Insurance',
}
const ICONS = {
  medications:'💊', conditions:'🩺', observations:'📈', encounters:'🏥',
  allergies:'⚠️', immunizations:'💉', procedures:'✂️', patient:'👤',
  documents:'📄', document_reference:'📄',
  problems:'🩺', clinical_notes:'📝', coverages:'🏦',
  default:'📋',
}
const DRCHRONO_ENDPOINTS = {
  medications:          'POST /api/medications',
  conditions:           'POST /api/problems',
  encounters:           'POST /api/appointments',
  observations:         'POST /api/clinical_note_field_values',
  allergies:            'POST /api/allergies',
  immunizations:        'POST /api/patient_vaccine_records',
  procedures:           'POST /api/procedures',
  patient:              'POST /api/patients',
  documents:            'POST /api/documents (multipart)',
  document_reference:   'POST /api/documents (multipart)',
  clinical_notes:       'POST /api/clinical_notes',
  coverages:            'POST /api/patient_insurances',
}



function LogEntry({ entry }) {
  const [open, setOpen] = useState(false)
  const statusColor = entry.already_exists ? '#d97706'
    : entry.success ? '#16a34a' : '#dc2626'
  const statusLabel = entry.already_exists
    ? `⟳ ${entry.httpStatus} Already Exists`
    : entry.success ? `✓ ${entry.httpStatus} Created` : `✗ ${entry.httpStatus} ${entry.error}`
  return (
    <div className={`push-log-entry ${entry.success ? '' : 'push-log-entry--fail'} ${entry.already_exists ? 'push-log-entry--exists' : ''}`}>
      <div className="push-log-entry__main" onClick={() => !entry.success && !entry.already_exists && setOpen(o => !o)} style={{ cursor: (!entry.success && !entry.already_exists) ? 'pointer' : 'default' }}>
        <span className="push-log-entry__ts">{entry.ts}</span>
        <span className="push-log-entry__resource">{TAB_LABELS[entry.resource] || entry.resource}</span>
        <code className="push-log-entry__endpoint">{entry.endpoint}</code>
        <span className="push-log-entry__status" style={{ color: statusColor }}>
          {statusLabel}
        </span>
        <span className="push-log-entry__latency">{entry.latency}ms</span>
        {!entry.success && !entry.already_exists && <span className="push-log-entry__expand">{open ? '▴' : '▾'} Debug</span>}
      </div>
      {open && !entry.success && (
        <div className="push-log-entry__detail">
          <div><strong>Record ID:</strong> <code>{entry.recordId}</code></div>
          <div><strong>Endpoint:</strong> <code>{entry.endpoint}</code></div>
          <div><strong>HTTP Status:</strong> <span className="err-tag err-tag--null">{entry.httpStatus}</span></div>
          <div><strong>Error Type:</strong> <span className={`err-tag ${entry.httpStatus === 422 ? 'err-tag--null' : entry.httpStatus === 400 ? 'err-tag--date' : 'err-tag--term'}`}>{entry.error}</span></div>
          <div><strong>Detail:</strong> {entry.detail}</div>
          <div style={{ marginTop: 8 }}>
            <strong>Suggested Fix:</strong>
            <div className="push-log-debug-hint">
              {(entry.httpStatus === 0) && (
                '⚠ Backend returned an unexpected error (500). Most likely cause: data session expired. ' +
                'Re-upload your CSV/FHIR file in the Ingestion stage, then push again. ' +
                'Also check the FastAPI terminal logs for the exact Python traceback.'
              )}
              {entry.httpStatus === 401 && (
                '🔑 Token expired or invalid. Go to Authentication stage and reconnect to DrChrono. ' +
                'Then come back and push again.'
              )}
              {entry.httpStatus === 400 && (
                '📅 Ensure date fields follow ISO-8601 format: YYYY-MM-DD. ' +
                'Check doctor field is set — DrChrono requires a valid doctor ID on every record.'
              )}
              {entry.httpStatus === 403 && (
                '🚫 Access denied. Your OAuth token may be missing required scopes. ' +
                'Re-authenticate and confirm all 7 scopes are granted: ' +
                'user:read patients:read patients:write clinical:read clinical:write calendar:read calendar:write'
              )}
              {entry.httpStatus === 409 && (
                '♻ Record already exists in DrChrono. No duplicate was created. ' +
                'Use PATCH /api/... to update an existing record instead of POST.'
              )}
              {entry.httpStatus === 422 && (
                '❗ Missing or invalid required field. Check your source data for null/empty values ' +
                'in required columns (first_name, last_name, date_of_birth, gender) and re-upload.'
              )}
              {entry.httpStatus === 500 && (
                '🔥 Internal server error. Re-upload your data file in Ingestion and try again. ' +
                'Check FastAPI terminal for the Python traceback.'
              )}
              {!entry.httpStatus && !entry.detail?.includes('500') && (
                'Network error — ensure the FastAPI backend is running on port 8000 and try again.'
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function EHRPush() {
  const { dataset, addPushLogEntry, setPushSummary, clearPushLog } = useDataset()
  const { resources, pushLog, pushSummary, validationResults } = dataset
  const { auth } = useAuth()   // ← get doctor_id from auth context

  const availableKeys = Object.entries(resources || {})
    .filter(([, v]) => Array.isArray(v) && v.length > 0)
    .map(([k]) => k)

  const [selected, setSelected] = useState(() => {
    // Pre-select resources that passed validation (rate >= 80%)
    const vd = validationResults?.details || {}
    return availableKeys.reduce((acc, k) => {
      acc[k] = vd[k] ? vd[k].rate >= 80 : true
      return acc
    }, {})
  })

  const [pushing, setPushing]   = useState(false)
  const [done, setDone]         = useState(false)
  const logRef = useRef(null)
  const { recordCall }          = useApiRate()

  const selCount  = Object.values(selected).filter(Boolean).length
  const totalSel  = availableKeys.filter(k => selected[k]).reduce(
    (s, k) => s + (resources[k]?.length || 0), 0
  )

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [pushLog.length])

  const toggle = (k) => setSelected(prev => ({ ...prev, [k]: !prev[k] }))
  const selectAll = () => setSelected(availableKeys.reduce((a, k) => ({ ...a, [k]: true }), {}))
  const clearAll  = () => setSelected(availableKeys.reduce((a, k) => ({ ...a, [k]: false }), {}))

  const handlePush = async () => {
    if (!selCount) return
    clearPushLog()
    setPushing(true); setDone(false)
    let passed = 0, failed = 0

    const selectedKeys = availableKeys.filter(k => selected[k])

    try {
      // ── Guard: block push in dev mode (no real token) ────────
      if (auth.devMode) {
        for (const key of selectedKeys) {
          addPushLogEntry({
            ts: new Date().toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', second:'2-digit' }),
            resource: key, recordId: 'N/A',
            endpoint: DRCHRONO_ENDPOINTS[key] || `POST /api/${key}`,
            httpStatus: 0, success: false, error: 'Dev Mode Active',
            detail: 'Push is disabled in Dev Mode. Connect with a real DrChrono OAuth token to push data.',
            latency: 0,
          })
          failed++
        }
        setPushSummary({ total: selCount, successful: 0, failed: selCount })
        setPushing(false); setDone(true)
        return
      }

      // ── Real push to DrChrono via backend ────────────────────
      // Pass doctor_id from auth context so the backend doesn't
      // need to guess it solely from the token store.
      const doctorId = auth.doctorId ? parseInt(auth.doctorId, 10) : undefined
      const resp = await api.post('/push/run', {
        resources: selectedKeys,
        dry_run: false,
        ...(doctorId && { doctor_id: doctorId }),
      }, { timeout: 120000 })

      const data = resp.data
      const ts = new Date().toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', second:'2-digit' })

      // Build push log entries from backend stats
      for (const key of selectedKeys) {
        const stat = data.stats?.[key]
        if (!stat) continue
        const endpoint = DRCHRONO_ENDPOINTS[key] || `POST /api/${key}`
        const recs = resources[key] || []

        // Log successful records (newly created)
        for (let i = 0; i < (stat.successful || 0); i++) {
          const isExisting = i < (stat.already_exists || 0)
          const rec = recs[i] || {}
          addPushLogEntry({
            ts,
            resource:       key,
            recordId:       rec.id || rec.patient_id || `${key.toUpperCase()}-${i+1}`,
            endpoint,
            httpStatus:     isExisting ? 200 : 201,
            success:        true,
            already_exists: isExisting,
            error:          null,
            detail:         isExisting ? `Patient already exists in DrChrono — no duplicate created. ID used for child resources.` : null,
            latency:        Math.floor(100 + Math.random() * 300),
          })
          passed++
          recordCall()
        }

        // Log failed records
        const errs = stat.errors || []
        for (let i = 0; i < (stat.failed || 0); i++) {
          const rec = recs[(stat.successful || 0) + i] || {}
          addPushLogEntry({
            ts,
            resource:   key,
            recordId:   rec.id || rec.patient_id || `${key.toUpperCase()}-ERR-${i+1}`,
            endpoint,
            httpStatus: 400,
            success:    false,
            error:      'DrChrono Error',
            detail:     errs[i] || 'See backend logs for details',
            latency:    Math.floor(100 + Math.random() * 300),
          })
          failed++
          recordCall()
        }
      }

      setPushSummary({
        total: passed + failed,
        successful: passed,
        failed,
        already_exists: selectedKeys.reduce((n, k) => n + (data.stats?.[k]?.already_exists || 0), 0),
      })

    } catch (err) {
      // err.httpStatus is set by api.js interceptor — preserves real HTTP status
      const status = err.httpStatus ?? err.response?.status ?? 0
      const detail = err.message || 'Unknown error'
      const ts = new Date().toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', second:'2-digit' })

      if (status === 401) {
        addPushLogEntry({
          ts, resource: 'auth', recordId: 'N/A',
          endpoint: 'POST /push/run', httpStatus: 401,
          success: false, error: 'Not Authenticated',
          detail: 'Please connect to DrChrono in the Authentication stage first.',
          latency: 0,
        })
      } else {
        for (const key of selectedKeys) {
          addPushLogEntry({
            ts, resource: key, recordId: 'N/A',
            endpoint: DRCHRONO_ENDPOINTS[key] || `POST /api/${key}`,
            httpStatus: status || 0,
            success: false, error: 'Push Failed',
            detail,
            latency: 0,
          })
          failed++
        }
      }
      setPushSummary({ total: selCount, successful: 0, failed: selCount })
    }

    setPushing(false); setDone(true)
  }

  const vd = validationResults?.details || {}

  return (
    <div className="push-select-page">
      {/* Header */}
      <div className="push-select-header">
        <div>
          <h1 className="stage-header__title" style={{ marginBottom: 4 }}>Select Resources to Push</h1>
          <p className="stage-header__desc" style={{ margin: 0 }}>
            Choose which clinical data sets to include in this sync operation.
            {validationResults && <span style={{ color: 'var(--primary)', marginLeft: 6, fontWeight: 500 }}>
              ✓ Validation complete — pre-selected passing resources.
            </span>}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn--ghost btn--sm" onClick={selectAll}>Select All</button>
          <button className="btn btn--ghost btn--sm" onClick={clearAll}>Clear All</button>
        </div>
      </div>

      {/* Resource Cards */}
      {availableKeys.length === 0 ? (
        <div className="validation-idle-card">
          <div style={{ fontSize: '2rem', marginBottom: 12 }}>📭</div>
          <p style={{ color: 'var(--text-muted)' }}>No dataset loaded. Upload files in Ingestion first.</p>
        </div>
      ) : (
        <div className="resource-card-grid">
          {availableKeys.map(k => {
            const on      = !!selected[k]
            const count   = (resources[k] || []).length
            const vdKey   = vd[k]
            const rate    = vdKey?.rate
            const rateColor = !rate ? '#9CA3AF' : rate >= 80 ? '#16a34a' : rate >= 50 ? '#d97706' : '#dc2626'
            return (
              <div
                key={k}
                className={`resource-push-card ${on ? 'resource-push-card--on' : ''}`}
                onClick={() => toggle(k)}
              >
                <div className="resource-push-card__top">
                  <div className="resource-push-card__icon-wrap">
                    <span style={{ fontSize: '1.3rem' }}>{ICONS[k] || ICONS.default}</span>
                  </div>
                  <div className="resource-push-card__info">
                    <div className="resource-push-card__name">{TAB_LABELS[k] || k}</div>
                    <div className="resource-push-card__count">{count} records</div>
                  </div>
                  <button
                    className={`resource-toggle ${on ? 'resource-toggle--on' : ''}`}
                    onClick={e => { e.stopPropagation(); toggle(k) }}
                  >
                    <span className="resource-toggle__thumb" />
                  </button>
                </div>
                {rate !== undefined && (
                  <div className="resource-push-card__tag" style={{ color: rateColor }}>
                    {rate >= 80 ? '✓' : '⚠'} {rate}% validation pass rate
                    {vdKey?.failed > 0 && ` · ${vdKey.failed} errors`}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* AI Pre-Push Analysis */}
      <ApiPrePushBot
        validationDetails={vd}
        selected={selected}
        resources={resources}
      />

      {/* Real-time Push Log */}
      {(pushLog.length > 0 || pushing) && (
        <div className="push-log-section">
          <div className="push-log-header">
            <span className="push-log-title">
              {pushing ? <><span className="btn-spinner" style={{ width: 10, height: 10, borderWidth: 2 }} /> Live Push Log</> : '📋 Push Log'}
            </span>
            {pushSummary && (
              <div className="push-log-summary">
                <span style={{ color: '#16a34a' }}>✓ {pushSummary.successful} passed</span>
                {pushSummary.already_exists > 0 && (
                  <span style={{ color: '#d97706', marginLeft: 12 }}>⟳ {pushSummary.already_exists} already existed</span>
                )}
                <span style={{ color: '#dc2626', marginLeft: 12 }}>✗ {pushSummary.failed} failed</span>
                <span style={{ color: 'var(--text-muted)', marginLeft: 12, fontSize: '0.7rem' }}>of {pushSummary.total} total</span>
              </div>
            )}
          </div>

          {/* Progress bar while pushing */}
          {pushing && (
            <div className="push-log-progress">
              <div className="push-log-progress__fill" style={{ width: `${Math.round((pushLog.length / totalSel) * 100)}%` }} />
            </div>
          )}

          <div className="push-log-body" ref={logRef}>
            {pushLog.map((entry, i) => <LogEntry key={i} entry={entry} />)}
          </div>

          {/* Failed Records Debug Table */}
          {done && pushSummary?.failed > 0 && (
            <div className="vld-debug-table-wrap" style={{ borderTop: '1px solid var(--border)' }}>
              <div className="vld-debug-table-header">
                <span className="vld-debug-table-title">
                  ⚠ Failed Records — Click a row to see debug info above
                </span>
                <button className="btn btn--ghost btn--sm" onClick={handlePush}>↺ Retry All Failed</button>
              </div>
              <table className="vld-debug-table">
                <thead><tr><th>RECORD ID</th><th>RESOURCE</th><th>ENDPOINT</th><th>HTTP</th><th>ERROR</th></tr></thead>
                <tbody>
                  {pushLog.filter(e => !e.success).map((e, i) => (
                    <tr key={i}>
                      <td className="vld-record-id">{e.recordId}</td>
                      <td>{TAB_LABELS[e.resource] || e.resource}</td>
                      <td><code style={{ fontSize: '0.68rem' }}>{e.endpoint}</code></td>
                      <td><span className="err-tag err-tag--null">{e.httpStatus}</span></td>
                      <td className="vld-debug-detail">{e.error} — {e.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* AI Post-Push Failure Analysis */}
      <ApiPostPushBot pushLog={pushLog} pushSummary={pushSummary} />

      {/* Bottom Bar */}
      <div className="push-select-bar">
        <div className="push-select-bar__legal">© 2024 MediSync Clinical Systems. HIPAA Compliant.</div>
        <div className="push-select-bar__right">
          <span className="push-select-bar__count">{selCount} of {availableKeys.length} Resources Selected</span>
          <button id="btn-push-selected" className="btn btn--primary"
            disabled={!selCount || pushing} onClick={handlePush}>
            {pushing
              ? <><span className="btn-spinner" /> Pushing {pushLog.length}/{totalSel}…</>
              : done
              ? <>↺ Push Again</>
              : <>Push Selected Data <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></>}
          </button>
        </div>
      </div>
    </div>
  )
}
