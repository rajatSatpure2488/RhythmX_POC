import { useState, useCallback } from 'react'
import { useDataset } from '../context/DatasetContext'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications', conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters', observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies', immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures', patient:'Patient', patients:'Patient',
  vitals:'Vitals', coverages:'Coverages', coverage:'Coverages', documents:'Documents',
}

function StatusBadge({ value }) {
  const v = String(value || '').toLowerCase()
  if (v.includes('active')||v.includes('complete')||v.includes('resolved'))
    return <span className="badge badge--success">{value}</span>
  if (v.includes('discon')||v.includes('inactive')||v.includes('error'))
    return <span className="badge badge--error">{value}</span>
  if (v.includes('pend')||v.includes('sched'))
    return <span className="badge badge--warning">{value}</span>
  return <span style={{ color:'var(--text-secondary)', fontSize:'0.78rem' }}>{value}</span>
}

const DATE_COLS = ['date','dt','on','at','time','created','updated','onset','performed']
const STATUS_COLS = ['status','state']

function isStatusCol(col) { return STATUS_COLS.some(s => col.toLowerCase().includes(s)) }
function isDateCol(col)   { return DATE_COLS.some(s => col.toLowerCase().endsWith(s) || col.toLowerCase().startsWith(s)) }

function formatCell(col, val) {
  if (val === null || val === undefined || val === '') return <span style={{ color:'var(--text-muted)' }}>—</span>
  const s = String(val)
  if (isStatusCol(col)) return <StatusBadge value={s} />
  if (isDateCol(col) && s.length > 10) return <code style={{ fontSize:'0.7rem', color:'#334155' }}>{s.slice(0,19).replace('T',' ')}</code>
  if (s.length > 60) return <span title={s}>{s.slice(0,58)}…</span>
  return s
}

const TIMELINE_STEPS = ['Resources Extracted','FHIR Mapping','Validation','Ready to Push']

export default function ReviewDataset({ onComplete }) {
  const { dataset, addNote } = useDataset()
  const { resources, patientInfo, resourceCount, notes } = dataset

  const availableKeys = Object.entries(resources || {})
    .filter(([, v]) => Array.isArray(v) && v.length > 0)
    .map(([k]) => k)

  const [activeTab, setActiveTab]     = useState(availableKeys[0] || '')
  const [noteText, setNoteText]       = useState('')
  const [showNote, setShowNote]       = useState(false)
  const [filterText, setFilterText]   = useState('')

  const records   = (resources?.[activeTab] || [])
  const tabNotes  = notes?.[activeTab] || []

  // Derive columns from real fields (max 8, show scrollable)
  const allCols = records.length > 0 ? Object.keys(records[0]).filter(k => k !== 'resourceType') : []
  const columns = allCols // show ALL columns, table is scrollable

  // Filter rows by text
  const filteredRows = filterText.trim()
    ? records.filter(row => Object.values(row).some(v => String(v||'').toLowerCase().includes(filterText.toLowerCase())))
    : records

  const patient  = patientInfo || {}
  const initials = (patient.name || 'U').split(' ').map(n => n[0]).join('').slice(0,2).toUpperCase()

  const handleAddNote = () => {
    if (!noteText.trim()) return
    addNote(activeTab, noteText.trim())
    setNoteText(''); setShowNote(false)
  }

  const now = new Date().toLocaleTimeString('en-US',{ hour:'2-digit', minute:'2-digit' })

  return (
    <div className="review-v2">
      {/* Breadcrumb */}
      <div className="review-breadcrumb">
        <span className="review-breadcrumb__item">Review</span>
        <span className="review-breadcrumb__sep">›</span>
        <span className="review-breadcrumb__item review-breadcrumb__item--active">Patient Details</span>
      </div>

      <div className="review-layout">
        {/* ── Main Column ─────────────────────────────────── */}
        <div className="review-main">

          {/* Patient Header */}
          <div className="patient-header-card">
            <div className="patient-header-card__left">
              <div className="patient-avatar">{initials}</div>
              <div>
                <div className="patient-info__name">
                  {patient.name || 'Unknown Patient'}
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="#1565C0" style={{flexShrink:0}}>
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  </svg>
                </div>
                <div className="patient-info__mrn">MRN <span className="patient-info__mrn-code">{patient.id || '—'}</span></div>
              </div>
            </div>
            <div className="patient-header-card__divider" />
            <div className="patient-meta-chips">
              {patient.dob    && <div className="patient-meta-chip">📅 {patient.dob}</div>}
              {patient.gender && <div className="patient-meta-chip">👤 {patient.gender}</div>}
              <div className="patient-meta-chip patient-meta-chip--code">ID: {patient.id || '—'}</div>
            </div>
          </div>

          {/* ── Tabs — horizontal scroll ─────────────────── */}
          <div className="review-tabs-wrap">
            <div className="review-tabs">
              {availableKeys.map(key => (
                <button key={key}
                  className={`review-tab${activeTab===key?' review-tab--active':''}`}
                  onClick={() => { setActiveTab(key); setShowNote(false); setFilterText('') }}>
                  {TAB_LABELS[key]||key} ({(resources?.[key]||[]).length})
                </button>
              ))}
            </div>
          </div>

          {/* ── Table Card ────────────────────────────────── */}
          <div className="review-table-card">
            <div className="review-table-card__header">
              <span className="review-table-card__title">
                {TAB_LABELS[activeTab]||activeTab} — {filteredRows.length} of {records.length} record{records.length!==1?'s':''}
              </span>
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                <input
                  className="review-filter-input"
                  placeholder="Search records…"
                  value={filterText}
                  onChange={e => setFilterText(e.target.value)}
                />
                <button className="btn btn--ghost btn--sm">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                  Filter
                </button>
                <button className="btn btn--primary btn--sm" onClick={() => setShowNote(s=>!s)}>
                  + Add Note
                </button>
              </div>
            </div>

            {/* Add Note Panel */}
            {showNote && (
              <div className="note-panel">
                <textarea className="note-panel__input" rows={2}
                  placeholder={`Add a clinical note for ${TAB_LABELS[activeTab]||activeTab}…`}
                  value={noteText} onChange={e => setNoteText(e.target.value)} />
                <div className="note-panel__actions">
                  <button className="btn btn--ghost btn--sm" onClick={()=>{setShowNote(false);setNoteText('')}}>Cancel</button>
                  <button className="btn btn--primary btn--sm" onClick={handleAddNote} disabled={!noteText.trim()}>Save Note</button>
                </div>
              </div>
            )}

            {/* Saved Notes */}
            {tabNotes.length > 0 && (
              <div className="note-list">
                {tabNotes.map(n => (
                  <div key={n.id} className="note-item">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span className="note-item__text">{n.text}</span>
                    <span className="note-item__ts">{n.ts}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Scrollable Table */}
            {records.length > 0 ? (
              <div className="review-table-scroll">
                <table className="review-data-table review-data-table--wide">
                  <thead>
                    <tr>
                      <th style={{width:36}}>#</th>
                      {columns.map(c => <th key={c}>{c.replace(/_/g,' ').toUpperCase()}</th>)}
                      <th style={{width:48}}>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.slice(0, 500).map((row, i) => (
                      <tr key={i}>
                        <td style={{ color:'var(--text-muted)', fontSize:'0.7rem' }}>{i+1}</td>
                        {columns.map(c => <td key={c}>{formatCell(c, row[c])}</td>)}
                        <td><button className="review-action-menu">⋮</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredRows.length > 500 && (
                  <div style={{ padding:'8px 14px', fontSize:'0.72rem', color:'var(--text-muted)', borderTop:'1px solid var(--border)' }}>
                    Showing 500 of {filteredRows.length} records
                  </div>
                )}
              </div>
            ) : (
              <div style={{ padding:40, textAlign:'center', color:'var(--text-muted)', fontSize:'0.82rem' }}>
                No records for this resource type
              </div>
            )}
          </div>
        </div>

        {/* ── Right Panel ─────────────────────────────────── */}
        <div className="review-right-panel">

          {/* Dataset Status */}
          <div className="review-panel-card">
            <div className="review-panel-card__header">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              Dataset Status
            </div>
            <div className="dataset-status-count">{resourceCount||0}</div>
            <div className="dataset-status-label">Resource types detected<br/>in current payload</div>
            <div className="dataset-status-rows">
              {availableKeys.slice(0,8).map(k => (
                <div key={k} className="dataset-status-row">
                  <span className="dataset-status-dot dataset-status-dot--green"/>
                  {TAB_LABELS[k]||k}
                  <span className="dataset-status-num">{(resources?.[k]||[]).length}</span>
                </div>
              ))}
              {availableKeys.length > 8 && (
                <div className="dataset-status-row" style={{ color:'var(--text-muted)', fontStyle:'italic' }}>
                  +{availableKeys.length - 8} more…
                </div>
              )}
            </div>
            <button className="btn btn--ghost btn--sm" style={{ width:'100%', marginTop:12 }}
              onClick={() => onComplete?.()}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
              Run Validation Rules →
            </button>
          </div>

          {/* Integration Timeline */}
          <div className="review-panel-card" style={{ marginTop:16 }}>
            <div className="review-panel-card__header">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              Integration Timeline
            </div>
            <div className="timeline-list">
              {TIMELINE_STEPS.map((label, i) => (
                <div key={i} className="timeline-item">
                  <div className={`timeline-dot ${i === 0 ? 'timeline-dot--done' : 'timeline-dot--pending'}`} />
                  <div className="timeline-content">
                    <div className={`timeline-label ${i>0?'timeline-label--muted':''}`}>{label}</div>
                    <div className="timeline-time">{i===0 ? `Today, ${now}` : 'Waiting for action'}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="stage-actions" style={{ marginTop:24 }}>
        <span style={{ fontSize:'0.78rem', color:'var(--text-secondary)' }}>
          {availableKeys.length} resource types · {Object.values(resources||{}).reduce((s,v)=>s+(v?.length||0),0).toLocaleString()} total records
        </span>
        <button className="btn btn--primary" onClick={() => onComplete?.()}>
          Proceed to Mapping →
        </button>
      </div>
    </div>
  )
}
