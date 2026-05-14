/**
 * AiAssistantBot.jsx
 * Embedded AI assistant for the CSV Validation page.
 * Analyzes mapping errors, suggests fixes, and lets users Accept or Deny each suggestion.
 * Completely optional — users can dismiss it and still proceed.
 */
import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const TYPE_META = {
  null_value:  { icon: '🔴', label: 'Missing Field',   cls: 'ai-badge--red'    },
  date_format: { icon: '🟡', label: 'Date Format',      cls: 'ai-badge--yellow' },
  terminology: { icon: '🟠', label: 'Terminology Code', cls: 'ai-badge--orange' },
}

const ACTION_META = {
  fix:  { icon: '⚡', label: 'Auto-fix Available', cls: 'ai-sug--fix'  },
  skip: { icon: '⏭',  label: 'Skip Suggested',     cls: 'ai-sug--skip' },
}

// ── Typing animation ──────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <span className="ai-typing">
      <span /><span /><span />
    </span>
  )
}

// ── Individual suggestion card ────────────────────────────────────────────────
function SuggestionCard({ sug, idx, onAccept, onDeny, accepted, denied }) {
  const meta = ACTION_META[sug.action] || ACTION_META.fix
  const isAccepted = accepted.has(idx)
  const isDenied   = denied.has(idx)

  return (
    <div className={`ai-sug-card ${meta.cls} ${isAccepted ? 'ai-sug-card--accepted' : ''} ${isDenied ? 'ai-sug-card--denied' : ''}`}>
      <div className="ai-sug-card__top">
        <span className="ai-sug-card__icon">{meta.icon}</span>
        <div className="ai-sug-card__content">
          {sug.field && (
            <div className="ai-sug-card__field">
              <code>{sug.field}</code>
              {sug.suggested_value && (
                <span className="ai-sug-card__arrow">
                  → <span className="ai-sug-card__val">"{sug.suggested_value}"</span>
                </span>
              )}
            </div>
          )}
          <div className="ai-sug-card__reason">{sug.reason}</div>
        </div>
      </div>

      {!isAccepted && !isDenied && (
        <div className="ai-sug-card__actions">
          <button className="ai-btn ai-btn--accept" onClick={() => onAccept(idx, sug)}>
            ✓ Accept
          </button>
          <button className="ai-btn ai-btn--deny" onClick={() => onDeny(idx)}>
            ✗ Deny
          </button>
        </div>
      )}

      {isAccepted && (
        <div className="ai-sug-card__outcome ai-sug-card__outcome--accepted">
          ✅ Fix accepted — will be applied before push
        </div>
      )}
      {isDenied && (
        <div className="ai-sug-card__outcome ai-sug-card__outcome--denied">
          ⏭ Skipped — proceeding without this fix
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AiAssistantBot({ selectedKey, details, onFixesAccepted }) {
  const [open, setOpen]           = useState(false)
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)
  const [accepted, setAccepted]   = useState(new Set())
  const [denied, setDenied]       = useState(new Set())
  const [dismissed, setDismissed] = useState(false)
  const prevKey = useRef(null)

  // Reset when resource changes
  useEffect(() => {
    if (selectedKey !== prevKey.current) {
      prevKey.current = selectedKey
      setResult(null); setError(null)
      setAccepted(new Set()); setDenied(new Set())
      setDismissed(false)
    }
  }, [selectedKey])

  const data = details[selectedKey]
  const hasErrors = data && data.failed > 0

  const handleAnalyze = async () => {
    if (!data || !hasErrors) return
    setLoading(true); setError(null); setResult(null)
    setOpen(true)

    // Build request payload
    const failedRecords = data.failedRecords.slice(0, 20).map(fr => ({
      record_id: String(fr.id),
      resource: selectedKey,
      errors: fr.errors.map(e => ({
        field: e.field,
        type: e.type,
        tag: e.tag,
        detail: e.detail,
      })),
    }))

    try {
      const resp = await axios.post(`${BACKEND}/ai/explain/validation`, {
        resource: selectedKey,
        failed_records: failedRecords,
        context: 'CSV mapping stage',
      }, { timeout: 12000 })
      setResult(resp.data)
    } catch (err) {
      setError('AI analysis unavailable. Backend may be offline.')
      // Provide offline fallback
      setResult({
        summary: `Detected ${data.failed} record(s) with errors in '${selectedKey}'.`,
        root_cause: 'Analysis performed offline — backend unreachable.',
        impact: 'Records with missing required fields will be rejected by DrChrono (HTTP 422).',
        suggestions: data.failedRecords.slice(0,3).flatMap(fr =>
          fr.errors.slice(0,2).map(e => ({
            field: e.field,
            suggested_value: e.type === 'null_value' ? 'default_value' : null,
            action: 'fix',
            reason: e.detail,
          }))
        ),
        can_proceed: data.rate >= 60,
        fixed_count: 0,
        total_errors: data.failed,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleAccept = (idx, sug) => {
    setAccepted(prev => new Set([...prev, idx]))
    onFixesAccepted?.(selectedKey, sug)
  }

  const handleDeny = (idx) => {
    setDenied(prev => new Set([...prev, idx]))
  }

  const acceptedCount = accepted.size
  const deniedCount   = denied.size

  // Floating trigger button (only show when there are errors)
  if (!hasErrors || dismissed) return null

  return (
    <div className="ai-bot-container">
      {/* Collapsed trigger */}
      {!open && (
        <button
          id="ai-bot-trigger"
          className="ai-bot-trigger"
          onClick={handleAnalyze}
          title="Ask AI to explain and fix these errors"
        >
          <span className="ai-bot-trigger__pulse" />
          <span className="ai-bot-trigger__icon">🤖</span>
          <span className="ai-bot-trigger__label">
            AI Fix Assistant
            <span className="ai-bot-trigger__count">{data.failed} issues</span>
          </span>
        </button>
      )}

      {/* Expanded panel */}
      {open && (
        <div className="ai-bot-panel">
          {/* Header */}
          <div className="ai-bot-panel__header">
            <div className="ai-bot-panel__title">
              <span className="ai-bot-panel__icon">🤖</span>
              <div>
                <div className="ai-bot-panel__name">AI Fix Assistant</div>
                <div className="ai-bot-panel__sub">
                  Analyzing: <strong>{selectedKey}</strong> · {data.failed} error(s)
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="ai-icon-btn" onClick={handleAnalyze} title="Re-analyze">↺</button>
              <button className="ai-icon-btn" onClick={() => { setOpen(false); setDismissed(true) }} title="Dismiss">✕</button>
            </div>
          </div>

          {/* Body */}
          <div className="ai-bot-panel__body">
            {loading && (
              <div className="ai-bot-loading">
                <TypingDots />
                <span>Analyzing errors…</span>
              </div>
            )}

            {!loading && result && (
              <>
                {/* Summary */}
                <div className="ai-section ai-section--summary">
                  <div className="ai-section__label">📊 Summary</div>
                  <p className="ai-text">{result.summary}</p>
                </div>

                {/* Root cause */}
                <div className="ai-section">
                  <div className="ai-section__label">🔍 Root Cause</div>
                  <p className="ai-text">{result.root_cause}</p>
                </div>

                {/* Impact */}
                <div className="ai-section">
                  <div className="ai-section__label">⚡ Impact if Ignored</div>
                  <p className="ai-text ai-text--warn">{result.impact}</p>
                </div>

                {/* Can proceed badge */}
                <div className={`ai-proceed-badge ${result.can_proceed ? 'ai-proceed-badge--ok' : 'ai-proceed-badge--warn'}`}>
                  {result.can_proceed
                    ? '✅ You can proceed — errors are non-blocking. Fixes are optional.'
                    : '⚠️ Fix required fields before pushing to DrChrono to avoid rejections.'}
                </div>

                {/* Suggestions */}
                {result.suggestions?.length > 0 && (
                  <div className="ai-section">
                    <div className="ai-section__label">
                      💡 Suggested Fixes
                      {acceptedCount > 0 && (
                        <span className="ai-badge ai-badge--green">{acceptedCount} accepted</span>
                      )}
                      {deniedCount > 0 && (
                        <span className="ai-badge ai-badge--gray">{deniedCount} denied</span>
                      )}
                    </div>
                    <div className="ai-suggestions-list">
                      {result.suggestions.map((sug, i) => (
                        <SuggestionCard
                          key={i} idx={i} sug={sug}
                          onAccept={handleAccept} onDeny={handleDeny}
                          accepted={accepted} denied={denied}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Accept all / deny all */}
                {result.suggestions?.length > 1 && accepted.size + denied.size < result.suggestions.length && (
                  <div className="ai-bulk-actions">
                    <button className="ai-btn ai-btn--accept-all"
                      onClick={() => {
                        result.suggestions.forEach((s, i) => {
                          setAccepted(prev => new Set([...prev, i]))
                          onFixesAccepted?.(selectedKey, s)
                        })
                      }}>
                      ✓ Accept All ({result.suggestions.length})
                    </button>
                    <button className="ai-btn ai-btn--deny-all"
                      onClick={() => setDenied(new Set(result.suggestions.map((_, i) => i)))}>
                      ✗ Deny All
                    </button>
                  </div>
                )}

                {/* Proceed button */}
                <div className="ai-bot-footer">
                  <span className="ai-bot-footer__note">
                    Optional — you can proceed without accepting any fixes.
                  </span>
                  <button className="ai-btn ai-btn--proceed" onClick={() => setDismissed(true)}>
                    Continue →
                  </button>
                </div>
              </>
            )}

            {!loading && !result && (
              <div className="ai-bot-loading">
                <span>Click analyze to start →</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
