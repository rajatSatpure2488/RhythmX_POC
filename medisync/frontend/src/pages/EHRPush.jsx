import { useState, useRef, useEffect } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import { useAuth } from '../context/AuthContext'
import { ApiPrePushBot, ApiPostPushBot } from '../components/ApiMonitorBot'
import api from '../services/api'

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
  observations:         'POST /api/patient_lab_results',
  observation_notes:    'POST /api/patient_lab_results',
  allergies:            'POST /api/allergies',
  immunizations:        'POST /api/patient_vaccine_records',
  procedures:           'POST /api/procedures',
  patient:              'POST /api/patients',
  documents:            'POST /api/documents (multipart)',
  document_reference:   'POST /api/documents (multipart)',
  clinical_notes:       'PATCH /api/appointments (vitals) + POST /api/clinical_note_field_values',
  coverages:            'POST /api/insurances',
}

// Parse DrChrono's "field: message | field2: message2" error string into
// structured rows so the UI can show exactly WHICH field failed and WHY,
// instead of a generic guessed hint.
function parseFieldErrors(detail) {
  if (!detail) return []
  return String(detail)
    .split(' | ')
    .map(seg => {
      const i = seg.indexOf(':')
      if (i > 0 && i < 40) {
        return { field: seg.slice(0, i).trim(), message: seg.slice(i + 1).trim() }
      }
      return { field: null, message: seg.trim() }
    })
    .filter(e => e.message)
}

function LogEntry({ entry }) {
  const [open, setOpen] = useState(false)
  const fieldErrors = !entry.success && !entry.already_exists ? parseFieldErrors(entry.detail) : []
  // Short, scannable summary for the one-line row: the failed field name(s).
  const failSummary = fieldErrors.length
    ? fieldErrors.map(e => e.field).filter(Boolean).join(', ') || entry.error
    : entry.error
  const statusColor = entry.already_exists ? '#d97706'
    : entry.success ? '#16a34a' : '#dc2626'
  const statusLabel = entry.already_exists
    ? `⟳ ${entry.httpStatus} Already Exists`
    : entry.success ? `✓ ${entry.httpStatus} Created` : `✗ ${entry.httpStatus} ${failSummary}`
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
          <div>
            <strong>HTTP Status:</strong> <span className="err-tag err-tag--null">{entry.httpStatus}</span>
            {' '}
            <span
              className={`err-tag ${entry.retryable ? 'err-tag--term' : 'err-tag--null'}`}
              title={entry.retryable
                ? 'Transient failure — retrying may succeed.'
                : 'Deterministic validation failure — retrying the same data will fail again.'}
            >
              {entry.retryable ? '↺ Retryable' : '⛔ Validation — won’t retry'}
            </span>
          </div>

          {/* Real DrChrono per-field errors — what actually failed and why */}
          {fieldErrors.length > 0 ? (
            <div style={{ marginTop: 8 }}>
              <strong>DrChrono rejected these fields:</strong>
              <ul className="push-log-field-errors" style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                {fieldErrors.map((fe, i) => (
                  <li key={i} style={{ marginBottom: 2 }}>
                    {fe.field && (
                      <code className="err-tag err-tag--date" style={{ marginRight: 6 }}>{fe.field}</code>
                    )}
                    <span>{fe.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div style={{ marginTop: 6 }}><strong>Detail:</strong> {entry.detail}</div>
          )}

          <div style={{ marginTop: 8 }}>
            <strong>Suggested Fix:</strong>
            <div className="push-log-debug-hint">
              {fieldErrors.some(fe => fe.field === 'scheduled_time' && /century|2000/i.test(fe.message)) && (
                '📅 This appointment is dated before the year 2000. DrChrono only accepts ' +
                'appointment dates in 2000–2099. Either exclude pre-2000 visits or shift the date ' +
                'into the supported range before pushing.'
              )}
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
  const { auth } = useAuth()

  const availableKeys = Object.entries(resources || {})
    .filter(([, v]) => Array.isArray(v) && v.length > 0)
    .map(([k]) => k)

  const [selected, setSelected] = useState(() => {
    const vd = validationResults?.details || {}
    return availableKeys.reduce((acc, k) => {
      acc[k] = vd[k] ? vd[k].rate >= 80 : true
      return acc
    }, {})
  })

  const [pushing, setPushing]   = useState(false)
  const [done, setDone]         = useState(false)
  // Detailed failed-records (file/row/patient context) from the backend LoggingService.
  const [failedRecords, setFailedRecords] = useState([])
  const [runId, setRunId]       = useState(null)
  const logRef = useRef(null)
  const { recordCall }          = useApiRate()

  // Backend base for the Excel download link (mirrors the fetch base below).
  const apiBase = (() => {
    const rb = (api.defaults && api.defaults.baseURL) || ''
    return rb === '/' ? '' : rb.replace(/\/$/, '')
  })()

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
    setFailedRecords([]); setRunId(null)
    let passed = 0, failed = 0

    const selectedKeys = availableKeys.filter(k => selected[k])

    try {
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

      const doctorId = auth.doctorId ? parseInt(auth.doctorId, 10) : undefined

      // api.defaults.baseURL is '/' so the Vite proxy can route to :8000.
      // Concatenating '/' + '/push/...' would yield '//push/...', a protocol-
      // relative URL the browser resolves to host "push" → "Failed to fetch".
      // Normalise to a clean relative path (or absolute base if overridden).
      const rawBase = (api.defaults && api.defaults.baseURL) || ''
      const baseURL = rawBase === '/' ? '' : rawBase.replace(/\/$/, '')
      const resp = await fetch(`${baseURL}/push/run-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resources: selectedKeys,
          dry_run: false,
          ...(doctorId && { doctor_id: doctorId }),
        }),
      })

      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        const err = new Error(text || `HTTP ${resp.status}`)
        err.response = { status: resp.status }
        throw err
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let alreadyExists = 0
      let lastSummary = null

      while (true) {
        const { value, done: streamDone } = await reader.read()
        if (streamDone) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue
          let evt
          try { evt = JSON.parse(line) } catch { continue }

          if (evt.type === 'record') {
            const ts = new Date().toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', second:'2-digit' })
            const endpoint = DRCHRONO_ENDPOINTS[evt.resource] || `POST /api/${evt.resource}`
            const httpStatus = evt.status_code || (evt.success ? 201 : 400)
            addPushLogEntry({
              ts,
              resource:       evt.resource,
              recordId:       evt.record_id,
              endpoint,
              httpStatus,
              success:        evt.success,
              already_exists: evt.already_exists,
              error:          evt.success ? null : (evt.error || 'DrChrono Error'),
              detail:         evt.already_exists
                                ? 'Already exists in DrChrono — no duplicate created.'
                                : (evt.error || null),
              retryable:      evt.success ? false : !!evt.retryable,
              latency:        evt.latency_ms || 0,
            })
            recordCall()
            if (evt.already_exists) alreadyExists++
            if (evt.success) passed++; else failed++
          } else if (evt.type === 'summary') {
            lastSummary = evt
          }
        }
      }

      // Flush any trailing buffered line (rare)
      if (buffer.trim()) {
        try {
          const evt = JSON.parse(buffer)
          if (evt.type === 'summary') lastSummary = evt
        } catch { /* ignore */ }
      }

      setPushSummary({
        total:          lastSummary?.total ?? (passed + failed),
        successful:     lastSummary?.successful ?? passed,
        failed:         lastSummary?.failed ?? failed,
        already_exists: lastSummary?.already_exists ?? alreadyExists,
      })
      // Detailed failed records (file/row/patient) from the backend LoggingService.
      setFailedRecords(lastSummary?.failed_records || [])
      setRunId(lastSummary?.run_id || null)

    } catch (err) {
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
  const failedEntries = pushLog.filter(e => !e.success)
  const retryableFailCount   = failedEntries.filter(e => e.retryable).length
  const validationFailCount  = failedEntries.length - retryableFailCount

  return (
    <div className="push-select-page">

      {/* ── Header ─────────────────────────────────────── */}
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

      {/* ── Two-column body ─────────────────────────────── */}
      <div className="push-two-col">

        {/* LEFT — Resource selection + AI bots */}
        <div className="push-left-col">
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

          {/* AI Post-Push Failure Analysis */}
          <ApiPostPushBot pushLog={pushLog} pushSummary={pushSummary} />
        </div>

        {/* RIGHT — Sticky Push Log panel */}
        <div className="push-right-col">
          <div className="push-log-panel">
            {/* Panel header */}
            <div className="push-log-panel__header">
              <span className="push-log-title">
                {pushing
                  ? <><span className="btn-spinner" style={{ width: 10, height: 10, borderWidth: 2 }} /> Live Push Log</>
                  : '📋 Push Log'}
              </span>
              {pushSummary && (
                <div className="push-log-summary" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 12px', marginTop: 6 }}>
                  <span style={{ color: '#16a34a', fontWeight: 600 }}>✓ {pushSummary.successful} passed</span>
                  {pushSummary.already_exists > 0 && (
                    <span style={{ color: '#d97706', fontWeight: 600 }}>⟳ {pushSummary.already_exists} existed</span>
                  )}
                  <span style={{ color: '#dc2626', fontWeight: 600 }}>✗ {pushSummary.failed} failed</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', alignSelf: 'center' }}>
                    of {pushSummary.total} total
                  </span>
                </div>
              )}
              {!pushSummary && !pushing && (
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Push results will appear here
                </span>
              )}
            </div>

            {/* Progress bar */}
            {pushing && (
              <div className="push-log-progress">
                <div className="push-log-progress__fill" style={{ width: `${Math.round((pushLog.length / Math.max(totalSel, 1)) * 100)}%` }} />
              </div>
            )}

            {/* Empty state */}
            {pushLog.length === 0 && !pushing && (
              <div className="push-log-empty">
                <div style={{ fontSize: '2rem', marginBottom: 8 }}>📡</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.6 }}>
                  No push activity yet.<br />
                  Select resources and click <strong>Push Selected Data</strong>.
                </div>
              </div>
            )}

            {/* Log entries — scrollable */}
            {pushLog.length > 0 && (
              <div className="push-log-body" ref={logRef}>
                {pushLog.map((entry, i) => <LogEntry key={i} entry={entry} />)}
              </div>
            )}

            {/* Failed records debug table */}
            {done && failedEntries.length > 0 && (
              <div className="push-log-fail-table">
                <div className="vld-debug-table-header">
                  <span className="vld-debug-table-title">
                    ⚠ {failedEntries.length} Failed
                    {validationFailCount > 0 && ` · ${validationFailCount} validation`}
                    {retryableFailCount > 0 && ` · ${retryableFailCount} retryable`}
                    {' '}— click a row above for details
                  </span>
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={handlePush}
                    disabled={retryableFailCount === 0}
                    title={retryableFailCount === 0
                      ? 'All failures are validation errors — fix the source data and re-push.'
                      : 'Retry the push.'}
                  >↺ Retry</button>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table className="vld-debug-table">
                    <thead>
                      <tr>
                        <th>RECORD ID</th>
                        <th>RESOURCE</th>
                        <th>HTTP</th>
                        <th>TYPE</th>
                        <th>ERROR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {failedEntries.map((e, i) => {
                        const fes = parseFieldErrors(e.detail)
                        const msg = fes.length
                          ? fes.map(fe => fe.field ? `${fe.field}: ${fe.message}` : fe.message).join(' · ')
                          : (e.detail || e.error)
                        return (
                          <tr key={i}>
                            <td className="vld-record-id">{e.recordId}</td>
                            <td>{TAB_LABELS[e.resource] || e.resource}</td>
                            <td><span className="err-tag err-tag--null">{e.httpStatus}</span></td>
                            <td>
                              <span className={`err-tag ${e.retryable ? 'err-tag--term' : 'err-tag--null'}`}>
                                {e.retryable ? '↺ Retryable' : '⛔ Validation'}
                              </span>
                            </td>
                            <td className="vld-debug-detail" style={{ maxWidth: 240, wordBreak: 'break-word' }}>
                              {msg}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Failed Records — detailed (file/row/patient context from the backend
                LoggingService); includes the Excel export. */}
            {done && failedRecords.length > 0 && (
              <div className="push-log-fail-table" style={{ marginTop: 12 }}>
                <div className="vld-debug-table-header">
                  <span className="vld-debug-table-title">
                    📄 Failed Records — {failedRecords.length} record{failedRecords.length !== 1 ? 's' : ''}
                    {runId && (
                      <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · run {runId}</span>
                    )}
                  </span>
                  <a
                    className="btn btn--ghost btn--sm"
                    href={`${apiBase}/push/failed-records.xlsx`}
                    download="failed_records.xlsx"
                    title="Download all failed records as Excel"
                  >⬇ Download Excel</a>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table className="vld-debug-table">
                    <thead>
                      <tr>
                        <th>FILE</th>
                        <th>ROW</th>
                        <th>PATIENT</th>
                        <th>RESOURCE</th>
                        <th>ENDPOINT</th>
                        <th>HTTP</th>
                        <th>ERROR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {failedRecords.map((f, i) => (
                        <tr key={i}>
                          <td>{f.file_name || '—'}</td>
                          <td className="vld-record-id">{f.row}</td>
                          <td>{f.source_patient_id || '—'}</td>
                          <td>{TAB_LABELS[f.resource_type] || f.resource_type}</td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.72rem' }}>{f.endpoint}</td>
                          <td><span className="err-tag err-tag--null">{f.status_code}</span></td>
                          <td className="vld-debug-detail" style={{ maxWidth: 280, wordBreak: 'break-word' }}>
                            {f.error_reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Bottom bar ─────────────────────────────────── */}
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
