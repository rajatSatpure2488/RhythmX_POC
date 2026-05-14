/**
 * ApiMonitorBot.jsx
 * Embedded AI monitor for the EHR Push page.
 * Analyzes API push failures in real-time, predicts which APIs will fail,
 * and provides root-cause analysis + monitoring recommendations.
 * Completely optional — users can dismiss and still push.
 */
import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const HTTP_COLORS = {
  400: '#d97706', 401: '#dc2626', 403: '#dc2626',
  404: '#7c3aed', 409: '#2563eb', 422: '#dc2626',
  429: '#d97706', 201: '#16a34a',
}

const HTTP_ICONS = {
  400: '📋', 401: '🔑', 403: '🚫', 404: '🔍',
  409: '♻️', 422: '⚠️', 429: '⏱', 201: '✅',
}

// ── Risk badge for pre-push analysis ─────────────────────────────────────────
function RiskBadge({ risk }) {
  const map = {
    high:   { cls: 'ai-risk--high',   icon: '🔴', label: 'High Risk'   },
    medium: { cls: 'ai-risk--medium', icon: '🟡', label: 'Medium Risk' },
    low:    { cls: 'ai-risk--low',    icon: '🟢', label: 'Low Risk'    },
  }
  const m = map[risk] || map.low
  return <span className={`ai-risk-badge ${m.cls}`}>{m.icon} {m.label}</span>
}

// ── Pre-push prediction panel ─────────────────────────────────────────────────
function PrePushAnalysis({ validationDetails, selected, resources }) {
  const [open, setOpen]       = useState(false)
  const [dismissed, dismiss]  = useState(false)

  if (dismissed) return null

  // Predict failure risk per resource
  const predictions = Object.entries(validationDetails || {})
    .filter(([k]) => selected[k] && (resources[k]?.length || 0) > 0)
    .map(([k, d]) => {
      const rate = d.rate || 100
      const risk = rate < 60 ? 'high' : rate < 85 ? 'medium' : 'low'
      const failCount = d.failed || 0
      const reasons = []
      if (d.errorsByType?.null_value > 0)
        reasons.push(`${d.errorsByType.null_value} null fields → HTTP 422`)
      if (d.errorsByType?.date_format > 0)
        reasons.push(`${d.errorsByType.date_format} bad dates → HTTP 400`)
      if (d.errorsByType?.terminology > 0)
        reasons.push(`${d.errorsByType.terminology} term issues → possible 400`)
      return { key: k, risk, rate, failCount, reasons }
    })
    .sort((a, b) => (a.risk === 'high' ? -1 : b.risk === 'high' ? 1 : 0))

  const highRisk = predictions.filter(p => p.risk === 'high').length
  const medRisk  = predictions.filter(p => p.risk === 'medium').length

  return (
    <div className="ai-monitor-card">
      <div className="ai-monitor-card__header" onClick={() => setOpen(o => !o)}>
        <div className="ai-monitor-card__title">
          <span>🤖</span>
          <div>
            <div className="ai-monitor-card__name">AI Pre-Push Analysis</div>
            <div className="ai-monitor-card__sub">
              {highRisk > 0
                ? `⚠️ ${highRisk} resource(s) at high risk of API failure`
                : medRisk > 0
                ? `${medRisk} resource(s) may have partial failures`
                : '✅ All selected resources look ready to push'}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="ai-icon-btn" onClick={e => { e.stopPropagation(); dismiss(true) }}>✕</button>
          <span className="ai-icon-btn">{open ? '▴' : '▾'}</span>
        </div>
      </div>

      {open && (
        <div className="ai-monitor-card__body">
          {predictions.length === 0 ? (
            <p className="ai-text">No validation data available. Run validation first for predictions.</p>
          ) : (
            <>
              <p className="ai-text" style={{ marginBottom: 12 }}>
                Based on your validation results, here is the predicted API outcome per resource:
              </p>
              <div className="ai-predict-list">
                {predictions.map(p => (
                  <div key={p.key} className="ai-predict-row">
                    <div className="ai-predict-row__left">
                      <RiskBadge risk={p.risk} />
                      <span className="ai-predict-row__name">{p.key}</span>
                      <span className="ai-predict-row__rate" style={{
                        color: p.rate >= 85 ? '#16a34a' : p.rate >= 60 ? '#d97706' : '#dc2626',
                      }}>{p.rate}% valid</span>
                    </div>
                    {p.reasons.length > 0 && (
                      <div className="ai-predict-row__reasons">
                        {p.reasons.map((r, i) => <span key={i} className="ai-predict-reason">→ {r}</span>)}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {highRisk > 0 && (
                <div className="ai-monitor-tip ai-monitor-tip--warn">
                  💡 <strong>Recommendation:</strong> Fix validation errors before pushing high-risk resources.
                  Go back to Stage 5 → click AI Fix Assistant on the failing resources.
                </div>
              )}
              {highRisk === 0 && (
                <div className="ai-monitor-tip ai-monitor-tip--ok">
                  ✅ <strong>Looks good!</strong> Proceed with push — low risk of API failures.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Post-push failure analysis panel ──────────────────────────────────────────
function PostPushAnalysis({ pushLog, pushSummary }) {
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [open, setOpen]           = useState(false)
  const [dismissed, dismiss]      = useState(false)
  const [accepted, setAccepted]   = useState(new Set())
  const [denied, setDenied]       = useState(new Set())
  const prevSummaryRef = useRef(null)

  const failures = pushLog.filter(e => !e.success)

  // Auto-analyze when new failures appear after push completes
  useEffect(() => {
    const summaryKey = `${pushSummary?.total}-${pushSummary?.failed}`
    if (pushSummary && pushSummary.failed > 0 && summaryKey !== prevSummaryRef.current) {
      prevSummaryRef.current = summaryKey
      setResult(null); setAccepted(new Set()); setDenied(new Set())
      setDismissed_inner(false)
      handleAnalyze(failures)
    }
  }, [pushSummary])

  const [dismissed_inner, setDismissed_inner] = useState(false)

  const handleAnalyze = async (fails) => {
    if (!fails?.length) return
    setLoading(true); setOpen(true)

    const payload = fails.slice(0, 30).map(f => ({
      record_id: String(f.recordId),
      resource: f.resource,
      endpoint: f.endpoint,
      http_status: f.httpStatus,
      error: f.error,
      detail: f.detail,
    }))

    try {
      const resp = await axios.post(`${BACKEND}/ai/explain/api`, {
        failures: payload,
        context: 'DrChrono EHR push stage',
      }, { timeout: 12000 })
      setResult(resp.data)
    } catch {
      // Offline fallback
      const byStatus = {}
      fails.forEach(f => { byStatus[f.httpStatus] = (byStatus[f.httpStatus] || 0) + 1 })
      const groups = Object.entries(byStatus).map(([s, c]) => `HTTP ${s}: ${c} record(s)`)
      setResult({
        summary: `${fails.length} API call(s) failed. Breakdown: ${groups.join(', ')}.`,
        root_cause: 'Backend AI unavailable — showing offline analysis.',
        impact: 'Failed records were NOT saved to DrChrono. Retry after fixing the root cause.',
        suggestions: Object.keys(byStatus).map(status => ({
          field: `HTTP ${status}`,
          action: 'fix',
          reason: {
            '400': 'Invalid data format. Check date fields (YYYY-MM-DD) and enum values.',
            '401': 'Token expired. Re-authenticate via OAuth at /auth/login.',
            '409': 'Duplicate records. Use PATCH instead of POST for existing records.',
            '422': 'Missing required fields. Run validation and fix null values first.',
            '429': 'Rate limited. Add 60ms delay between requests, max 29/min.',
          }[status] || 'Check DrChrono API documentation for this status code.',
        })),
        can_proceed: Object.keys(byStatus).every(s => ['409', '429'].includes(s)),
        fixed_count: 0,
        total_errors: fails.length,
      })
    } finally {
      setLoading(false)
    }
  }

  if (!pushSummary || pushSummary.failed === 0 || dismissed_inner) return null

  return (
    <div className="ai-monitor-card ai-monitor-card--alert">
      <div className="ai-monitor-card__header" onClick={() => setOpen(o => !o)}>
        <div className="ai-monitor-card__title">
          <span>{loading ? '🔄' : '🤖'}</span>
          <div>
            <div className="ai-monitor-card__name">AI Failure Analysis</div>
            <div className="ai-monitor-card__sub">
              {loading
                ? 'Analyzing failures…'
                : result
                ? result.summary.slice(0, 80) + (result.summary.length > 80 ? '…' : '')
                : `${failures.length} API failure(s) detected — click to analyze`}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="ai-icon-btn" onClick={e => { e.stopPropagation(); setDismissed_inner(true) }}>✕</button>
          {!loading && failures.length > 0 && !result && (
            <button className="ai-btn ai-btn--accept" style={{ padding: '4px 10px', fontSize: '0.72rem' }}
              onClick={e => { e.stopPropagation(); handleAnalyze(failures) }}>
              Analyze
            </button>
          )}
          <span className="ai-icon-btn">{open ? '▴' : '▾'}</span>
        </div>
      </div>

      {open && (
        <div className="ai-monitor-card__body">
          {loading && (
            <div className="ai-bot-loading">
              <span className="ai-typing"><span /><span /><span /></span>
              <span>Analyzing API failures…</span>
            </div>
          )}

          {!loading && result && (
            <>
              {/* Stats row */}
              <div className="ai-monitor-stats">
                {Object.entries(
                  failures.reduce((acc, f) => { acc[f.httpStatus] = (acc[f.httpStatus]||0)+1; return acc }, {})
                ).map(([status, count]) => (
                  <div key={status} className="ai-monitor-stat">
                    <span style={{ fontSize: '1.1rem' }}>{HTTP_ICONS[Number(status)] || '❗'}</span>
                    <span className="ai-monitor-stat__status" style={{ color: HTTP_COLORS[Number(status)] }}>
                      {status}
                    </span>
                    <span className="ai-monitor-stat__count">{count}×</span>
                  </div>
                ))}
              </div>

              <div className="ai-section">
                <div className="ai-section__label">🔍 Root Cause</div>
                <p className="ai-text">{result.root_cause}</p>
              </div>

              <div className="ai-section">
                <div className="ai-section__label">⚡ Impact</div>
                <p className="ai-text ai-text--warn">{result.impact}</p>
              </div>

              <div className={`ai-proceed-badge ${result.can_proceed ? 'ai-proceed-badge--ok' : 'ai-proceed-badge--warn'}`}>
                {result.can_proceed
                  ? '♻️ These failures are retryable — fix and push again.'
                  : '🛑 Manual data correction required before retry.'}
              </div>

              {result.suggestions?.length > 0 && (
                <div className="ai-section">
                  <div className="ai-section__label">💡 Fix Actions</div>
                  <div className="ai-suggestions-list">
                    {result.suggestions.map((sug, i) => {
                      const isAcc = accepted.has(i)
                      const isDen = denied.has(i)
                      return (
                        <div key={i} className={`ai-sug-card ai-sug--fix ${isAcc ? 'ai-sug-card--accepted' : ''} ${isDen ? 'ai-sug-card--denied' : ''}`}>
                          <div className="ai-sug-card__top">
                            <span className="ai-sug-card__icon">⚡</span>
                            <div className="ai-sug-card__content">
                              {sug.field && <div className="ai-sug-card__field"><code>{sug.field}</code></div>}
                              <div className="ai-sug-card__reason">{sug.reason}</div>
                            </div>
                          </div>
                          {!isAcc && !isDen && (
                            <div className="ai-sug-card__actions">
                              <button className="ai-btn ai-btn--accept"
                                onClick={() => setAccepted(p => new Set([...p, i]))}>
                                ✓ Acknowledge
                              </button>
                              <button className="ai-btn ai-btn--deny"
                                onClick={() => setDenied(p => new Set([...p, i]))}>
                                ✗ Skip
                              </button>
                            </div>
                          )}
                          {isAcc && <div className="ai-sug-card__outcome ai-sug-card__outcome--accepted">✅ Acknowledged</div>}
                          {isDen && <div className="ai-sug-card__outcome ai-sug-card__outcome--denied">⏭ Skipped</div>}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Monitoring tips */}
              <div className="ai-section">
                <div className="ai-section__label">📡 Monitoring Checklist</div>
                <div className="ai-monitor-checklist">
                  {[
                    'Watch the Live API Rate meter — stay under 29 calls/min',
                    'Check DrChrono dashboard for duplicate record alerts',
                    'OAuth tokens expire every 48h — re-auth before large batch pushes',
                    'Use dry_run=true in /push/run to preview before live push',
                    'Export failed records CSV → fix → re-upload → re-push',
                  ].map((tip, i) => (
                    <div key={i} className="ai-check-row">
                      <span className="ai-check-icon">◻</span>
                      <span>{tip}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ai-bot-footer">
                <span className="ai-bot-footer__note">
                  Optional — review suggestions and retry push as needed.
                </span>
                <button className="ai-btn ai-btn--proceed" onClick={() => setDismissed_inner(true)}>
                  Dismiss →
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Exported wrapper ──────────────────────────────────────────────────────────
export function ApiPrePushBot({ validationDetails, selected, resources }) {
  return (
    <PrePushAnalysis
      validationDetails={validationDetails}
      selected={selected}
      resources={resources}
    />
  )
}

export function ApiPostPushBot({ pushLog, pushSummary }) {
  return <PostPushAnalysis pushLog={pushLog} pushSummary={pushSummary} />
}
