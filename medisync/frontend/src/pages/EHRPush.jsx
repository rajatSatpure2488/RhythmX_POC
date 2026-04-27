import { useState, useRef, useEffect } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications', conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters', observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies', immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures', patient:'Patient', patients:'Patient',
}
const ICONS = {
  medications:'💊', conditions:'🩺', observations:'📈', encounters:'🏥',
  allergies:'⚠️', immunizations:'💉', procedures:'✂️', patient:'👤', default:'📋',
}
const DRCHRONO_ENDPOINTS = {
  medications:  'POST /api/medications',
  conditions:   'POST /api/conditions',
  encounters:   'POST /api/appointments',
  observations: 'POST /api/clinical_note_field_values',
  allergies:    'POST /api/allergies',
  immunizations:'POST /api/immunizations',
  procedures:   'POST /api/procedures',
  patient:      'POST /api/patients',
}

// Simulate per-record push result
function simulatePush(resource, record, idx) {
  const rand = Math.random()
  // ~12% failure rate
  if (rand < 0.04) return {
    success: false, httpStatus: 422,
    error: 'Null value', detail: `Required field missing in record ${idx + 1}`,
    endpoint: DRCHRONO_ENDPOINTS[resource] || 'POST /api/unknown',
  }
  if (rand < 0.08) return {
    success: false, httpStatus: 400,
    error: 'Invalid date format', detail: `Date field not in ISO-8601 format in record ${idx + 1}`,
    endpoint: DRCHRONO_ENDPOINTS[resource] || 'POST /api/unknown',
  }
  if (rand < 0.12) return {
    success: false, httpStatus: 409,
    error: 'Duplicate record', detail: `Record with same identifier already exists in DrChrono`,
    endpoint: DRCHRONO_ENDPOINTS[resource] || 'POST /api/unknown',
  }
  return {
    success: true, httpStatus: 201,
    error: null, detail: null,
    endpoint: DRCHRONO_ENDPOINTS[resource] || 'POST /api/unknown',
  }
}

function LogEntry({ entry }) {
  const [open, setOpen] = useState(false)
  const statusColor = entry.success ? '#16a34a' : '#dc2626'
  return (
    <div className={`push-log-entry ${entry.success ? '' : 'push-log-entry--fail'}`}>
      <div className="push-log-entry__main" onClick={() => !entry.success && setOpen(o => !o)} style={{ cursor: entry.success ? 'default' : 'pointer' }}>
        <span className="push-log-entry__ts">{entry.ts}</span>
        <span className="push-log-entry__resource">{TAB_LABELS[entry.resource] || entry.resource}</span>
        <code className="push-log-entry__endpoint">{entry.endpoint}</code>
        <span className="push-log-entry__status" style={{ color: statusColor }}>
          {entry.success ? `✓ ${entry.httpStatus} Created` : `✗ ${entry.httpStatus} ${entry.error}`}
        </span>
        <span className="push-log-entry__latency">{entry.latency}ms</span>
        {!entry.success && <span className="push-log-entry__expand">{open ? '▴' : '▾'} Debug</span>}
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
              {entry.httpStatus === 422 && 'Check for null required fields in your source data and re-upload after filling them.'}
              {entry.httpStatus === 400 && "Ensure date fields follow ISO-8601 format: YYYY-MM-DD. Use a data transformation before upload."}
              {entry.httpStatus === 409 && 'This record already exists in DrChrono. Use PATCH /api/... instead to update existing records.'}
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

    for (const key of availableKeys.filter(k => selected[k])) {
      const recs = resources[key] || []
      for (let i = 0; i < recs.length; i++) {
        await new Promise(r => setTimeout(r, 40 + Math.random() * 60))
        recordCall()   // register in live API rate monitor
        const result  = simulatePush(key, recs[i], i)
        const recordId = recs[i]?.id || recs[i]?.patient_id || `${key.toUpperCase()}-${i + 1}`
        const entry = {
          ts:       new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          resource: key,
          recordId,
          endpoint: result.endpoint,
          httpStatus: result.httpStatus,
          success:  result.success,
          error:    result.error,
          detail:   result.detail,
          latency:  Math.floor(80 + Math.random() * 320),
        }
        addPushLogEntry(entry)
        if (result.success) passed++; else failed++
      }
    }

    setPushSummary({ total: totalSel, successful: passed, failed })
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
