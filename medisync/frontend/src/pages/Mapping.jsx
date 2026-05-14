import { useState, useEffect, useRef } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications', conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters', observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies', immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures', patient:'Patient', patients:'Patient',
  vitals:'Vitals', coverages:'Coverages', coverage:'Coverages',
}

// DrChrono FHIR target schema per resource
const FHIR_SCHEMA = {
  medications:   { required:['name','dosage','status'], optional:['route','frequency','authored_on','prescriber','patient_id'] },
  conditions:    { required:['code','clinical_status','patient_id'], optional:['onset_date','severity','note'] },
  encounters:    { required:['type','period','patient_id'], optional:['participant','reason','provider'] },
  observations:  { required:['code','value','effective_date','patient_id'], optional:['unit','status','category'] },
  allergies:     { required:['substance','status','patient_id'], optional:['severity','reaction','onset'] },
  immunizations: { required:['vaccine_code','date','patient_id'], optional:['dose','manufacturer','status'] },
  procedures:    { required:['code','performed','patient_id'], optional:['performer','outcome','status'] },
  patient:       { required:['name','birth_date','gender'], optional:['id','address','phone','email'] },
  coverages:     { required:['payer','status','patient_id'], optional:['plan','group','member_id'] },
}

const DRCHRONO_ENDPOINTS = {
  medications:'POST /api/medications', conditions:'POST /api/conditions',
  encounters:'POST /api/appointments', observations:'POST /api/clinical_note_field_values',
  allergies:'POST /api/allergies', immunizations:'POST /api/immunizations',
  procedures:'POST /api/procedures', patient:'POST /api/patients', coverages:'POST /api/coverages',
}

// Try to match a source field name to a schema field
function matchField(srcKey, schemaFields) {
  const s = srcKey.toLowerCase().replace(/[_\s-]/g,'')
  for (const sf of schemaFields) {
    const t = sf.toLowerCase().replace(/[_\s-]/g,'')
    if (s === t || s.includes(t) || t.includes(s)) return sf
  }
  return null
}

// Map a single record → returns { mapped: bool, unmappedRequired: [], mappedFields: {} }
function mapRecord(record, resourceKey) {
  const schema = FHIR_SCHEMA[resourceKey] || { required:[], optional:[] }
  const srcKeys = Object.keys(record)
  const mappedFields = {}
  const unmappedRequired = []

  // Map required fields
  for (const req of schema.required) {
    const match = matchField(req, srcKeys) || srcKeys.find(k => k === req)
    const val = match !== undefined && match !== null ? record[match] : record[req]
    if (val !== null && val !== undefined && val !== '') {
      mappedFields[req] = val
    } else {
      unmappedRequired.push({ field: req, reason: 'null_value', src: match || req })
    }
  }

  // Map optional fields
  for (const opt of schema.optional) {
    const match = matchField(opt, srcKeys) || srcKeys.find(k => k === opt)
    const val = match !== undefined && match !== null ? record[match] : record[opt]
    if (val !== null && val !== undefined && val !== '') {
      mappedFields[opt] = val
    }
  }

  return {
    mapped: unmappedRequired.length === 0,
    unmappedRequired,
    mappedFields,
    mappedCount: schema.required.length - unmappedRequired.length,
    totalRequired: schema.required.length,
  }
}

// Process all records for a resource
function processResource(key, records) {
  let passed = 0, failed = 0
  const failedRecords = []

  records.forEach((rec, idx) => {
    const result = mapRecord(rec, key)
    if (result.mapped) {
      passed++
    } else {
      failed++
      if (failedRecords.length < 50) { // cap for UI
        failedRecords.push({
          idx: idx + 1,
          id: rec.id || rec.patient_id || `REC-${idx+1}`,
          errors: result.unmappedRequired,
        })
      }
    }
  })

  return { total: records.length, passed, failed, failedRecords, endpoint: DRCHRONO_ENDPOINTS[key] || 'POST /api/unknown' }
}

function ProgressRing({ pct, size=44 }) {
  const r = (size-6)/2, circ = 2*Math.PI*r
  const color = pct>=90?'#16a34a':pct>=60?'#d97706':'#dc2626'
  return (
    <svg width={size} height={size} style={{ flexShrink:0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#E5E7EB" strokeWidth="5"/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={circ} strokeDashoffset={circ*(1-pct/100)}
        strokeLinecap="round" transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2+4} textAnchor="middle" fill={color} fontSize="9" fontWeight="700">{pct}%</text>
    </svg>
  )
}

function TransformationShowcase({ resourceKey, record, results }) {
  const [viewType, setViewType] = useState('success') // 'success' | 'error'

  if (!resourceKey || !record) return (
    <div className="transformation-showcase transformation-showcase--empty">
      <div className="transformation-showcase__placeholder">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4 17l6-6-6-6M12 19h8"/>
        </svg>
        <p>Select a resource category to view live FHIR R4 transformation logic</p>
      </div>
    </div>
  )

  // Determine which record to show
  let displayRecord = record
  if (viewType === 'error' && results?.failedRecords?.length > 0) {
    // Find a record that actually failed (from dataset)
    const failedIdx = results.failedRecords[0].idx - 1
    // Note: this assumes dataset.resources[resourceKey] index matches
    // In a real app we'd fetch by ID, but for POC this works
  }

  const { mappedFields, unmappedRequired } = mapRecord(displayRecord, resourceKey)
  
  // Format as FHIR R4 Structure
  const fhirStructure = {
    resourceType: resourceKey.charAt(0).toUpperCase() + resourceKey.slice(1).replace(/s$/, ''),
    ...mappedFields,
    meta: {
      profile: [`http://hl7.org/fhir/us/core/StructureDefinition/us-core-${resourceKey.replace(/s$/, '')}`],
      lastUpdated: new Date().toISOString()
    }
  }

  const passedCount = results?.passed || 0
  const failedCount = results?.failed || 0
  const totalCount = results?.total || 0
  const passRate = totalCount ? Math.round((passedCount/totalCount)*100) : 0

  return (
    <div className="transformation-showcase">
      <div className="transformation-showcase__header">
        <div className="transformation-showcase__title">
          <span>Transformation Preview:</span>
          <strong>{TAB_LABELS[resourceKey] || resourceKey}</strong>
        </div>

        {/* Resource Mapping Health */}
        <div className="showcase-health">
          <div className="showcase-health__labels">
            <span className="health-label health-label--success">✓ {passedCount} Mapped</span>
            <span className="health-label health-label--failed">✗ {failedCount} Failed</span>
          </div>
          <div className="showcase-health__bar">
            <div className="showcase-health__fill" style={{ width: `${passRate}%` }} />
          </div>
        </div>

        <div className="transformation-showcase__endpoint">
          Target: <code>{DRCHRONO_ENDPOINTS[resourceKey]}</code>
        </div>
      </div>

      {/* Toggle between success and error samples if failures exist */}
      {failedCount > 0 && (
        <div className="showcase-toggle">
          <button className={`showcase-toggle__btn ${viewType === 'success' ? 'active' : ''}`}
            onClick={() => setViewType('success')}>Success Sample</button>
          <button className={`showcase-toggle__btn ${viewType === 'error' ? 'active' : ''}`}
            onClick={() => setViewType('error')}>Error Sample</button>
        </div>
      )}

      <div className="transformation-showcase__scroll">
        {/* Source Row */}
        <div className="showcase-section">
          <div className="showcase-section__label">Input (CSV Row)</div>
          <div className="showcase-csv">
            {Object.entries(displayRecord).map(([k,v]) => (
              <div key={k} className="showcase-csv__cell">
                <span className="showcase-csv__k">{k}</span>
                <span className="showcase-csv__v">{v || 'null'}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Mapping Logic */}
        <div className="showcase-section">
          <div className="showcase-section__label">Mapping Logic (Applied Rules)</div>
          <div className="showcase-rules">
            {Object.entries(mappedFields).map(([k,v]) => (
              <div key={k} className="showcase-rule">
                <span className="showcase-rule__target">{k}</span>
                <span className="showcase-rule__arrow">→</span>
                <span className="showcase-rule__src">{v}</span>
              </div>
            ))}
            {unmappedRequired.map(e => (
              <div key={e.field} className="showcase-rule showcase-rule--err">
                <span className="showcase-rule__target">{e.field}</span>
                <span className="showcase-rule__arrow">✗</span>
                <span className="showcase-rule__src">Required field missing</span>
              </div>
            ))}
          </div>
        </div>

        {/* FHIR Output */}
        <div className="showcase-section">
          <div className="showcase-section__label">Output (FHIR R4 JSON)</div>
          <div className="showcase-json">
            <pre>{JSON.stringify(fhirStructure, null, 2)}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Mapping({ onComplete }) {
  const { dataset, setMappingResults } = useDataset()
  const [results, setResults]     = useState({})   // { key: { total, passed, failed, failedRecords } }
  const [running, setRunning]     = useState(false)
  const [done, setDone]           = useState(false)
  const [expanded, setExpanded]   = useState({})
  const [approved, setApproved]   = useState(false)
  const [currentKey, setCurrentKey] = useState(null)
  const [progress, setProgress]   = useState(0)    // 0-100
  const { recordCall }            = useApiRate()

  const availableKeys = Object.entries(dataset.resources || {})
    .filter(([,v]) => Array.isArray(v) && v.length > 0)
    .map(([k]) => k)

  const totalRecords = availableKeys.reduce((s,k) => s+(dataset.resources[k]?.length||0), 0)

  const handleRunMapping = async () => {
    setRunning(true); setDone(false); setResults({}); setProgress(0)

    const newResults = {}
    let processed = 0

    for (const key of availableKeys) {
      setCurrentKey(key)
      const recs = dataset.resources[key] || []
      // Small artificial delay so UI updates are visible
      await new Promise(r => setTimeout(r, 120 + Math.random()*200))
      recordCall()  // count as one batch API call per resource
      newResults[key] = processResource(key, recs)
      processed += recs.length
      setProgress(Math.round((processed / totalRecords) * 100))
      setResults({ ...newResults })
    }

    // Also attempt backend call (graceful fail)
    axios.post(`${BACKEND}/mapping/run`, {}, { timeout: 15000 }).catch(() => {})

    setCurrentKey(null); setRunning(false); setDone(true)
    setMappingResults({ resources: newResults, totalRecords })
  }

  const handleApprove = () => {
    setApproved(true)
    setTimeout(() => onComplete?.(), 400)
  }

  const handleExport = () => {
    const rows = ['RESOURCE,ENDPOINT,TOTAL,PASSED,FAILED,PASS_RATE']
    Object.entries(results).forEach(([k,r]) => {
      rows.push(`${k},${r.endpoint},${r.total},${r.passed},${r.failed},${Math.round(r.passed/r.total*100)}%`)
    })
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([rows.join('\n')], {type:'text/csv'})),
      download:'mapping_report.csv'
    }); a.click()
  }

  const toggle = k => setExpanded(p => ({...p, [k]: !p[k]}))

  const totalPassed = Object.values(results).reduce((s,r)=>s+r.passed, 0)
  const totalFailed = Object.values(results).reduce((s,r)=>s+r.failed, 0)

  if (!availableKeys.length) {
    return (
      <div className="mapping-v2">
        <div className="validation-idle-card">
          <div style={{fontSize:'2rem',marginBottom:12}}>📭</div>
          <p style={{color:'var(--text-muted)'}}>No dataset loaded. Upload files in Ingestion first.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="mapping-v2">
      {/* Header */}
      <div className="mapping-v2__header">
        <div>
          <h1 className="stage-header__title" style={{marginBottom:4}}>Field Mapping</h1>
          <p className="mapping-v2__desc">
            Maps all {totalRecords.toLocaleString()} records across {availableKeys.length} resource types
            to DrChrono FHIR endpoints. Required fields are validated per record.
          </p>
        </div>
        <div style={{display:'flex',gap:10,flexShrink:0}}>
          {done && (
            <button className="btn btn--secondary" onClick={handleExport}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Export Report
            </button>
          )}
          {!done ? (
            <button className="btn btn--primary" onClick={handleRunMapping} disabled={running}>
              {running
                ? <><span className="btn-spinner"/> Mapping {currentKey ? `${TAB_LABELS[currentKey]||currentKey}…` : '…'}</>
                : <>▶ Run Mapping ({totalRecords.toLocaleString()} records)</>}
            </button>
          ) : (
            <button className="btn btn--primary" onClick={handleApprove} disabled={approved}>
              {approved
                ? <>✓ Mapping Approved</>
                : <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg> Approve &amp; Continue</>}
            </button>
          )}
        </div>
      </div>

      {/* Progress bar while running */}
      {running && (
        <div className="mapping-run-progress">
          <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize:'0.78rem'}}>
            <span>Mapping {currentKey ? `${TAB_LABELS[currentKey]||currentKey}` : 'records'}…</span>
            <span style={{color:'var(--primary)',fontWeight:600}}>{progress}%</span>
          </div>
          <div style={{height:6,background:'#E5E7EB',borderRadius:3,overflow:'hidden'}}>
            <div style={{height:'100%',background:'var(--primary)',width:`${progress}%`,transition:'width 0.3s',borderRadius:3}}/>
          </div>
        </div>
      )}

      {/* Pre-run resource list */}
      {!running && !done && (
        <div className="mapping-prereview">
          <div className="mapping-prereview__header">Resources to Map</div>
          {availableKeys.map(k => (
            <div key={k} className="mapping-prereview__row">
              <span className="mapping-prereview__key">{TAB_LABELS[k]||k}</span>
              <span className="mapping-prereview__count">{(dataset.resources[k]||[]).length.toLocaleString()} records</span>
              <span className="mapping-prereview__endpoint"><code>{DRCHRONO_ENDPOINTS[k]||'POST /api/unknown'}</code></span>
              <span className="mapping-prereview__schema">{(FHIR_SCHEMA[k]?.required||[]).length} required fields</span>
            </div>
          ))}
        </div>
      )}

      {/* Results / Showcase split */}
      {Object.entries(results).length > 0 && (
        <div className="mapping-split">
          <div className="mapping-results">
            {/* Summary bar */}
            {done && (
              <div className="mapping-summary-bar">
                <div className="mapping-summary-bar__item">
                  <span className="mapping-summary-bar__num" style={{color:'#16a34a'}}>{totalPassed.toLocaleString()}</span>
                  <span className="mapping-summary-bar__label">Records Mapped</span>
                </div>
                <div className="mapping-summary-bar__divider"/>
                <div className="mapping-summary-bar__item">
                  <span className="mapping-summary-bar__num" style={{color:'#dc2626'}}>{totalFailed.toLocaleString()}</span>
                  <span className="mapping-summary-bar__label">Need Attention</span>
                </div>
                <div className="mapping-summary-bar__divider"/>
                <div className="mapping-summary-bar__item">
                  <span className="mapping-summary-bar__num" style={{color:'var(--primary)'}}>
                    {totalRecords ? Math.round(totalPassed/totalRecords*100) : 0}%
                  </span>
                  <span className="mapping-summary-bar__label">Overall Rate</span>
                </div>
              </div>
            )}
  
            {/* Per-resource cards */}
            <div className="mapping-resource-list">
              {Object.entries(results).map(([key, r]) => {
                const rate = r.total ? Math.round(r.passed/r.total*100) : 0
                const isExp = expanded[key]
                const isActive = currentKey === key
                const barColor = rate>=90?'#16a34a':rate>=60?'#d97706':'#dc2626'
                return (
                  <div key={key} 
                    className={`mapping-resource-card ${isActive ? 'mapping-resource-card--active' : ''}`}
                    onClick={() => setCurrentKey(key)}>
                    <div className="mapping-resource-card__header">
                      <ProgressRing pct={rate}/>
                      <div className="mapping-resource-card__info">
                        <div className="mapping-resource-card__name">{TAB_LABELS[key]||key}</div>
                        <code className="mapping-resource-card__endpoint">{r.endpoint}</code>
                      </div>
                      <div className="mapping-resource-card__stats">
                        <span style={{color:'#16a34a',fontSize:'0.78rem',fontWeight:600}}>✓ {r.passed.toLocaleString()} mapped</span>
                        {r.failed > 0 && <span style={{color:'#dc2626',fontSize:'0.78rem',fontWeight:600,marginLeft:10}}>✗ {r.failed.toLocaleString()} failed</span>}
                        <div style={{height:4,background:'#E5E7EB',borderRadius:2,overflow:'hidden',marginTop:4,width:120}}>
                          <div style={{height:'100%',background:barColor,width:`${rate}%`}}/>
                        </div>
                      </div>
                      <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:8}}>
                        {r.failed > 0 && <span style={{fontSize:'0.72rem',color:'var(--primary)',cursor:'pointer'}} 
                          onClick={(e) => { e.stopPropagation(); toggle(key); }}>{isExp?'▴':'▾'} {r.failed} errors</span>}
                      </div>
                    </div>
  
                    {/* Expandable error details */}
                    {isExp && r.failedRecords.length > 0 && (
                      <div className="mapping-resource-card__errors">
                        <table className="vld-debug-table" style={{marginTop:0}}>
                          <thead>
                            <tr><th>#</th><th>RECORD ID</th><th>MISSING FIELD</th><th>REASON</th></tr>
                          </thead>
                          <tbody>
                            {r.failedRecords.map((fr, i) =>
                              fr.errors.map((e, j) => (
                                <tr key={`${i}-${j}`}>
                                  {j===0 && <td rowSpan={fr.errors.length} style={{verticalAlign:'top'}}>{fr.idx}</td>}
                                  {j===0 && <td rowSpan={fr.errors.length} className="vld-record-id" style={{verticalAlign:'top'}}>{fr.id}</td>}
                                  <td><code style={{fontSize:'0.7rem',background:'#F1F5F9',padding:'1px 5px',borderRadius:3}}>{e.field}</code></td>
                                  <td><span className={`err-tag ${e.reason==='null_value'?'err-tag--null':'err-tag--date'}`}>
                                    {e.reason==='null_value'?'Null value':'Field missing'}
                                  </span></td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* RIGHT SIDE: Transformation Showcase */}
          <TransformationShowcase 
            resourceKey={currentKey} 
            record={currentKey ? (dataset.resources[currentKey]?.[0] || {}) : null} 
            results={results[currentKey]}
          />
        </div>
      )}
    </div>
  )
}
