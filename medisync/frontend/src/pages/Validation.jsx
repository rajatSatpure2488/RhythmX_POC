import { useState } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications', conditions:'Conditions', condition:'Conditions',
  encounters:'Encounters', encounter:'Encounters', observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies', immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures', patient:'Patient', patients:'Patient',
  vitals:'Vitals', coverages:'Coverages',
}

// Required fields per resource — what FHIR/DrChrono needs
const REQUIRED = {
  medications:   ['name','dosage','status'],
  conditions:    ['code','status','patient_id'],
  encounters:    ['type','date','patient_id'],
  observations:  ['code','value','effective_date','patient_id'],
  allergies:     ['substance','status','patient_id'],
  immunizations: ['vaccine_code','date','patient_id'],
  procedures:    ['code','performed_date','patient_id'],
  patient:       ['name','birth_date','gender'],
  coverages:     ['payer','status','patient_id'],
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/
const SHORT_DATE = /^\d{2}[\/\-]\d{2}[\/\-]\d{2,4}$/

// Scan a single record for all error types
function auditRecord(rec, resourceKey, idx) {
  const errors = []
  const reqFields = REQUIRED[resourceKey] || []
  const allFields = Object.keys(rec)

  // 1. Missing / null required fields
  for (const rf of reqFields) {
    const matchKey = allFields.find(f => f.toLowerCase().replace(/[_\s]/g,'').includes(rf.replace(/[_\s]/g,'')))
    const val = matchKey ? rec[matchKey] : undefined
    if (val === null || val === undefined || val === '') {
      errors.push({ field: matchKey||rf, type:'null_value', tag:'Null value', cls:'err-tag--null',
        detail:`Required field '${rf}' is null or missing.` })
    }
  }

  // 2. Bad date format in any date-named field
  for (const f of allFields) {
    const lower = f.toLowerCase()
    if (lower.includes('date')||lower.endsWith('_on')||lower.endsWith('_at')||lower.includes('time')) {
      const val = String(rec[f]||'')
      if (val.length > 3 && !ISO_DATE.test(val) && SHORT_DATE.test(val)) {
        errors.push({ field: f, type:'date_format', tag:'Bad date', cls:'err-tag--date',
          detail:`'${f}' must be ISO-8601 (YYYY-MM-DD). Got: '${val.slice(0,20)}'` })
      }
    }
  }

  // 3. Suspiciously long strings in code fields (terminology mismatch)
  for (const f of allFields) {
    if (f.toLowerCase().includes('code')||f.toLowerCase().includes('icd')) {
      const val = String(rec[f]||'')
      if (val.length > 10 && /\s/.test(val)) {
        errors.push({ field: f, type:'terminology', tag:'Terminology', cls:'err-tag--term',
          detail:`'${f}' looks like a description, not a code: '${val.slice(0,30)}'` })
      }
    }
  }

  return errors
}

// Run full audit on a resource
function auditResource(key, records) {
  let passed = 0, failed = 0
  const errorsByType = { null_value:0, date_format:0, terminology:0 }
  const failedRecords = []

  for (let i = 0; i < records.length; i++) {
    const errs = auditRecord(records[i], key, i)
    if (errs.length === 0) {
      passed++
    } else {
      failed++
      errs.forEach(e => { if (errorsByType[e.type]!==undefined) errorsByType[e.type]++ })
      if (failedRecords.length < 100) {
        failedRecords.push({
          idx: i+1,
          id: records[i].id || records[i].patient_id || `${key.toUpperCase()}-${i+1}`,
          errors: errs,
        })
      }
    }
  }

  const rate = records.length ? Math.round(passed/records.length*100) : 100
  return { count:records.length, passed, failed, rate, errorsByType, failedRecords }
}

function ResourceRow({ rkey, data, expanded, onToggle }) {
  const rate  = data.rate
  const color = rate>=90?'#16a34a':rate>=60?'#d97706':'#dc2626'
  return (
    <div className="vld-resource-row" onClick={() => data.failed>0 && onToggle(rkey)}>
      <div className="vld-resource-row__header">
        <span className="vld-resource-row__name">{TAB_LABELS[rkey]||rkey}</span>
        <span style={{fontSize:'0.7rem',color:'var(--text-muted)',marginRight:4}}>{data.count} records</span>
        <div className="vld-resource-row__bar">
          <div className="vld-resource-row__fill" style={{width:`${rate}%`,background:color}}/>
        </div>
        <span className="vld-resource-row__pct" style={{color}}>{rate}%</span>
        <span className="vld-resource-row__counts">{data.passed}/{data.count} passed</span>
        <span style={{fontSize:'0.68rem',color:'#dc2626',fontWeight:500,minWidth:70}}>
          {data.failed>0 ? `${data.failed} errors` : ''}
        </span>
        {data.failed===0 && <span style={{fontSize:'0.7rem',color:'#16a34a'}}>✓ Ready</span>}
        {data.failed>0 && <span style={{fontSize:'0.68rem',color:'var(--primary)',cursor:'pointer'}}>{expanded?'▴':'▾'} Details</span>}
      </div>

      {/* Error type breakdown chips */}
      {data.failed>0 && (
        <div style={{display:'flex',gap:6,padding:'0 20px 8px',flexWrap:'wrap'}}>
          {data.errorsByType.null_value>0 && <span className="err-tag err-tag--null">Null: {data.errorsByType.null_value}</span>}
          {data.errorsByType.date_format>0 && <span className="err-tag err-tag--date">Bad dates: {data.errorsByType.date_format}</span>}
          {data.errorsByType.terminology>0 && <span className="err-tag err-tag--term">Terminology: {data.errorsByType.terminology}</span>}
        </div>
      )}

      {/* Expanded per-record error table */}
      {expanded && data.failedRecords.length>0 && (
        <div className="vld-resource-errors">
          <table className="vld-debug-table">
            <thead>
              <tr><th>#</th><th>RECORD ID</th><th>FIELD</th><th>ERROR</th><th>DETAIL</th></tr>
            </thead>
            <tbody>
              {data.failedRecords.map((fr,i) =>
                fr.errors.map((e,j) => (
                  <tr key={`${i}-${j}`} className={j>0?'vld-row-continuation':''}>
                    {j===0 && <td rowSpan={fr.errors.length} style={{verticalAlign:'top',color:'var(--text-muted)',fontSize:'0.7rem'}}>{fr.idx}</td>}
                    {j===0 && <td rowSpan={fr.errors.length} className="vld-record-id" style={{verticalAlign:'top'}}>{fr.id}</td>}
                    <td><code style={{fontSize:'0.7rem',background:'#F1F5F9',padding:'1px 5px',borderRadius:3}}>{e.field}</code></td>
                    <td><span className={`err-tag ${e.cls}`}>{e.tag}</span></td>
                    <td className="vld-debug-detail">{e.detail}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {data.failed>100 && (
            <div style={{padding:'6px 16px',fontSize:'0.7rem',color:'var(--text-muted)',borderTop:'1px solid var(--border)'}}>
              Showing 100 of {data.failed} failed records
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Validation({ onComplete }) {
  const { dataset, setValidationResults } = useDataset()
  const [running, setRunning]   = useState(false)
  const [done, setDone]         = useState(false)
  const [details, setDetails]   = useState({})
  const [expanded, setExpanded] = useState({})
  const [currentKey, setCurrentKey] = useState(null)
  const [progress, setProgress] = useState(0)
  const { recordCall }          = useApiRate()

  const resources    = dataset.resources || {}
  const availableKeys = Object.entries(resources).filter(([,v])=>Array.isArray(v)&&v.length>0).map(([k])=>k)
  const totalRecords = availableKeys.reduce((s,k)=>s+(resources[k]?.length||0),0)

  const handleRun = async () => {
    setRunning(true); setDone(false); setDetails({}); setProgress(0)
    const newDetails = {}
    let processed = 0

    for (const key of availableKeys) {
      setCurrentKey(key)
      const recs = resources[key] || []
      await new Promise(r => setTimeout(r, 80 + Math.random()*150))
      recordCall()  // one validation API call per resource type
      newDetails[key] = auditResource(key, recs)
      processed += recs.length
      setProgress(Math.round(processed/totalRecords*100))
      setDetails({...newDetails})
    }

    axios.post(`${BACKEND}/dryrun/run`, {}, { timeout:15000 }).catch(()=>{})
    setValidationResults({ details: newDetails, totalRecords })
    setCurrentKey(null); setRunning(false); setDone(true)
  }

  const toggle = k => setExpanded(p => ({...p, [k]:!p[k]}))

  const totalPassed = Object.values(details).reduce((s,d)=>s+d.passed,0)
  const totalFailed = Object.values(details).reduce((s,d)=>s+d.failed,0)
  const overallPct  = totalRecords ? Math.round(totalPassed/totalRecords*100) : 0
  const readyKeys   = Object.entries(details).filter(([,d])=>d.rate>=80)
  const needsKeys   = Object.entries(details).filter(([,d])=>d.rate<80)

  const handleExport = () => {
    const rows = ['RESOURCE,RECORD_ID,FIELD,ERROR_TYPE,DETAIL']
    Object.entries(details).forEach(([k,d]) =>
      d.failedRecords.forEach(fr =>
        fr.errors.forEach(e =>
          rows.push(`${k},${fr.id},${e.field},"${e.tag}","${e.detail}"`)
        )
      )
    )
    const a = Object.assign(document.createElement('a'),{
      href: URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'})),
      download:'validation_errors.csv'
    }); a.click()
  }

  if (!availableKeys.length) {
    return (
      <div className="validation-v2">
        <div className="validation-idle-card">
          <div style={{fontSize:'2rem',marginBottom:12}}>📭</div>
          <p style={{color:'var(--text-muted)'}}>No dataset loaded. Upload files in Ingestion first.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="validation-v2">
      {/* Header */}
      <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:20}}>
        <div>
          <div className="stage-header__badge">Stage 5</div>
          <h1 className="stage-header__title">Validation &amp; Dry Run</h1>
          <p className="stage-header__desc">
            Scans every record for FHIR compliance: null required fields, date format errors, terminology mismatches.
          </p>
        </div>
        <div style={{display:'flex',gap:8}}>
          {done && <button className="btn btn--secondary" onClick={handleExport}>↓ Export Errors</button>}
          {done && <button className="btn btn--ghost" onClick={()=>{setDone(false);setDetails({})}}>↺ Re-run</button>}
        </div>
      </div>

      {/* Pre-run or run button */}
      {!done && !running && (
        <div className="validation-idle-card" style={{marginBottom:20}}>
          <div style={{fontSize:'2.5rem',marginBottom:12}}>🔍</div>
          <h2 style={{marginBottom:8}}>Ready to Validate</h2>
          <p style={{color:'var(--text-secondary)',fontSize:'0.85rem',marginBottom:6}}>
            {availableKeys.length} resource types · {totalRecords.toLocaleString()} total records
          </p>
          <p style={{color:'var(--text-muted)',fontSize:'0.75rem',marginBottom:20}}>
            Checks per record: null values · date formats · required fields · terminology codes
          </p>
          <button className="btn btn--primary" onClick={handleRun}>▶ Start Validation</button>
        </div>
      )}

      {/* Progress while running */}
      {running && (
        <div className="mapping-run-progress" style={{marginBottom:16}}>
          <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize:'0.78rem'}}>
            <span>Validating {currentKey ? (TAB_LABELS[currentKey]||currentKey) : ''}…</span>
            <span style={{color:'var(--primary)',fontWeight:600}}>{progress}%</span>
          </div>
          <div style={{height:6,background:'#E5E7EB',borderRadius:3,overflow:'hidden'}}>
            <div style={{height:'100%',background:'var(--primary)',width:`${progress}%`,transition:'width 0.3s',borderRadius:3}}/>
          </div>
        </div>
      )}

      {/* Summary stats after run */}
      {(done||running) && Object.keys(details).length>0 && (
        <div className="vld-section" style={{marginBottom:16}}>
          <div className="vld-section__header">
            <span>▶</span>
            <span className="vld-section__title">Validation Results</span>
            {done && <span className="vld-simulation-badge">Scan Complete</span>}
          </div>
          <div className="vld-stat-row">
            <div className="vld-stat-card">
              <div className="vld-stat-card__big">{totalRecords.toLocaleString()}</div>
              <div className="vld-stat-card__label">Total Records Scanned</div>
              <div className="vld-stat-card__sub">{availableKeys.length} resource types</div>
            </div>
            <div className="vld-stat-card">
              <div className="vld-stat-card__big" style={{color:'#16a34a'}}>{totalPassed.toLocaleString()}</div>
              <div className="vld-stat-card__label">Records Passed</div>
              <div className="vld-stat-card__sub">{readyKeys.length} types ready to push</div>
            </div>
            <div className="vld-stat-card">
              <div className="vld-stat-card__big" style={{color:'#dc2626'}}>{totalFailed.toLocaleString()}</div>
              <div className="vld-stat-card__label">Records With Errors</div>
              <div className="vld-stat-card__sub">{needsKeys.length} types need attention</div>
            </div>
          </div>
        </div>
      )}

      {/* Per-resource rows */}
      {Object.keys(details).length>0 && (
        <div className="vld-section" style={{marginBottom:16}}>
          <div className="vld-section__header">
            <span>📊</span>
            <span className="vld-section__title">Per-Resource Breakdown</span>
            <span style={{marginLeft:'auto',fontSize:'0.7rem',color:'var(--text-muted)'}}>Click a row to see failing records</span>
          </div>
          {Object.entries(details).map(([k,d])=>(
            <ResourceRow key={k} rkey={k} data={d} expanded={!!expanded[k]} onToggle={toggle}/>
          ))}
        </div>
      )}

      {/* Push readiness summary */}
      {done && (
        <div className="vld-section" style={{marginBottom:20}}>
          <div className="vld-section__header">
            <span style={{color:'var(--primary)'}}>⬆</span>
            <span className="vld-section__title">Push Readiness</span>
          </div>
          <div className="vld-progress-area">
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize:'0.82rem'}}>
              <span style={{fontWeight:500}}>Overall record pass rate</span>
              <span style={{color:'var(--text-secondary)'}}>{overallPct}%</span>
            </div>
            <div className="vld-progress-bar">
              <div className="vld-progress-fill" style={{width:`${overallPct}%`}}/>
              <div className="vld-progress-fail" style={{width:`${100-overallPct}%`}}/>
            </div>
            <div className="vld-pass-fail">
              <span className="vld-dot vld-dot--green"/>{totalPassed.toLocaleString()} ready
              <span className="vld-dot vld-dot--red" style={{marginLeft:16}}/>{totalFailed.toLocaleString()} with errors
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      {done && (
        <div className="stage-actions">
          <span style={{fontSize:'0.78rem',color:needsKeys.length>0?'#d97706':'#16a34a',fontWeight:500}}>
            {needsKeys.length>0 ? `⚠️ ${needsKeys.length} resource type${needsKeys.length>1?'s':''} have errors` : '✅ All types ready to push'}
          </span>
          <button className="btn btn--primary" onClick={()=>onComplete?.()}>
            Select Resources &amp; Push →
          </button>
        </div>
      )}
    </div>
  )
}
