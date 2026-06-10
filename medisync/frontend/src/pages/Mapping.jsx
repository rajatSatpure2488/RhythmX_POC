import { useState, useEffect, useRef } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import axios from 'axios'

const BACKEND = 'http://localhost:8000'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications',
  conditions:'Conditions', condition:'Conditions',
  problems:'Conditions', problem:'Conditions', problem_list:'Conditions',
  encounters:'Encounters', encounter:'Encounters',
  appointments:'Appointments', appointment:'Appointments',
  observations:'Observations', observation:'Observations',
  allergies:'Allergies', allergy:'Allergies',
  immunizations:'Immunizations', immunization:'Immunizations',
  procedures:'Procedures', procedure:'Procedures',
  patient:'Patient', patients:'Patient',
  documents:'Documents', document:'Documents',
  document_reference:'Documents', document_references:'Documents',
  clinical_notes:'Clinical Notes', clinical_note:'Clinical Notes',
  vitals:'Vitals',
  coverages:'Coverages', coverage:'Coverages',
}

// DrChrono FHIR target schema per resource
const FHIR_SCHEMA = {
  medications:   { required:['name','dosage','status'], optional:['route','frequency','authored_on','prescriber','patient_id'] },
  conditions:    { required:['code','clinical_status','patient_id'], optional:['onset_date','severity','note'] },
  problems:      { required:['code','clinical_status','patient_id'], optional:['onset_date','severity','note'] },
  // DrChrono has no encounters endpoint — encounters are pushed as appointments,
  // so validate them with the appointment shape (date = scheduled_time).
  encounters:    { required:['date'], optional:['duration','status','reason','type','exam_room','office','patient_id','period','provider','participant'] },
  appointments:  { required:['date'], optional:['duration','status','reason','type','exam_room','office'] },
  appointment:   { required:['date'], optional:['duration','status','reason','type','exam_room','office'] },
  // Transformed observations come as lab results (value/test_name/date_collected)
  // or pivoted vitals (bp_s, pulse, ...). Both share the patient link.
  observations:  { required:['patient_id'], optional:['value','test_name','units','date_collected','abnormal_status','bp_s','bp_d','pulse','respiratory_rate','temperature','weight','height','oxygen_saturation','bmi','encounter_id','doctor','code','effective_date'] },
  allergies:     { required:['substance','status','patient_id'], optional:['severity','reaction','onset'] },
  immunizations: { required:['vaccine_code','date','patient_id'], optional:['dose','manufacturer','status'] },
  procedures:    { required:['code','performed','patient_id'], optional:['performer','outcome','status'] },
  patient:       { required:['name','birth_date','gender'], optional:['id','address','phone','email'] },
  documents:     { required:['patient','description','document'], optional:['doctor','date','metatags','archived','filename','mime_type'] },
  document_reference: { required:['patient','description','document'], optional:['doctor','date','metatags','archived','filename','mime_type'] },
  // Transformed clinical notes are split into a base file (join keys + doctor +
  // appointment) and a melted sections file (section_name + value). Both share the
  // note linkage, so note_id is the real requirement; everything else is optional.
  clinical_notes:{ required:['note_id'], optional:['patient_id','encounter_id','section_name','value','appointment','doctor','notes','clinical_note_date'] },
  // Transformed coverages drop status; key fields are the insurer + patient link.
  coverages:     { required:['insurance_company','patient_id'], optional:['payer_id','insurance_group_number','insurance_id_number','insurance_plan_type','insurance_plan_name','doctor','plan','group','member_id'] },
}

const DRCHRONO_ENDPOINTS = {
  medications:          'POST /api/medications',
  conditions:           'POST /api/problems',
  problems:             'POST /api/problems',
  encounters:           'POST /api/appointments',
  appointments:         'POST /api/appointments',
  appointment:          'POST /api/appointments',
  observations:         'POST /api/patient_lab_results',
  observation:          'POST /api/patient_lab_results',
  observation_notes:    'POST /api/patient_lab_results',
  observation_note:     'POST /api/patient_lab_results',
  diagnostic_report:    'POST /api/documents (PDF)',
  diagnostic_reports:   'POST /api/documents (PDF)',
  report:               'POST /api/documents (PDF)',
  reports:              'POST /api/documents (PDF)',
  service_request:      'POST /api/lab_orders',
  service_requests:     'POST /api/lab_orders',
  servicerequests:      'POST /api/lab_orders',
  allergies:            'POST /api/allergies',
  immunizations:        'POST /api/patient_vaccine_records',
  procedures:           'POST /api/procedures',
  patient:              'POST /api/patients',
  patients:             'POST /api/patients',
  documents:            'POST /api/documents (multipart)',
  document_reference:   'POST /api/documents (multipart)',
  document_references:  'POST /api/documents (multipart)',
  clinical_notes:       'PATCH /api/appointments + POST /api/yellow_notepad',
  clinical_note:        'PATCH /api/appointments + POST /api/yellow_notepad',
  coverages:            'POST /api/insurances',
}

// ── Field name normalizer (camelCase-aware) ──────────────────────
// Converts any field name to a flat lowercase token for fuzzy matching.
// Examples: 'birthDate' → 'birthdate',  'birth_date' → 'birthdate'
//           'dateOfBirth' → 'dateofbirth',  'date_of_birth' → 'dateofbirth'
function normalizeKey(s) {
  return s
    .replace(/([a-z])([A-Z])/g, '$1$2')  // collapse camelCase humps before lowercasing
    .toLowerCase()
    .replace(/[_\s\-]/g, '')             // strip all separators
}

// Alias map: schema field names → all acceptable source key tokens
// This handles CSV (birth_date), FHIR JSON (birthDate), and legacy (dob)
const FIELD_ALIASES = {
  'birth_date': ['birthdate', 'dateofbirth', 'dob', 'birthdt'],
  'birthdate':  ['birthdate', 'dateofbirth', 'dob', 'birthdt'],
  'name':       ['name', 'patientname', 'fullname', 'displayname'],
  'vaccine_code': ['vaccinecode', 'cvxcode', 'cvx', 'vaccinename'],
  'patient_id': ['patientid', 'patient', 'memberid'],
  'patient':    ['patient', 'patientid', 'memberid'],
  'document':   ['document', 'filepath', 'filename', 'localpath', 'documentpath', 'filecontent', 'data', 'attachmentdata'],
  'description':['description', 'name', 'namefull', 'title', 'label'],
  // Appointment date can arrive as scheduled_time (DrChrono) or other date fields.
  'date':       ['date', 'scheduledtime', 'datereport', 'documentdate', 'effectivedt', 'appointmentdate'],
  'note_id':    ['noteid', 'sourcenoteid'],
  // Insurer name arrives as insurance_company (transformed) or payor_name (raw).
  'insurance_company': ['insurancecompany', 'payorname', 'payername', 'insurer', 'payer'],
}

// Try to match a schema field name to a source key in the record
function matchField(schemaField, srcKeys) {
  const sNorm = normalizeKey(schemaField)
  // Check exact token match (most reliable)
  for (const sf of srcKeys) {
    const tNorm = normalizeKey(sf)
    if (sNorm === tNorm) return sf
  }
  // Check alias map
  const aliases = FIELD_ALIASES[schemaField] || FIELD_ALIASES[sNorm] || []
  for (const sf of srcKeys) {
    const tNorm = normalizeKey(sf)
    if (aliases.includes(tNorm)) return sf
  }
  // Check substring inclusion (fallback)
  for (const sf of srcKeys) {
    const tNorm = normalizeKey(sf)
    if (sNorm.includes(tNorm) || tNorm.includes(sNorm)) return sf
  }
  return null
}

// Extract a display value from a FHIR field (handles arrays like HumanName,
// CodeableConcept dicts, and Reference dicts).
function resolveValue(val) {
  if (val === null || val === undefined) return undefined
  if (Array.isArray(val)) {
    if (val.length === 0) return undefined
    const first = val[0]
    if (typeof first === 'object' && first !== null) {
      // FHIR HumanName: { family, given[] }
      if (first.family || first.text) {
        const given = Array.isArray(first.given) ? first.given.join(' ') : ''
        return `${given} ${first.family || first.text || ''}`.trim()
      }
      // FHIR CodeableConcept inside an array: { coding[], text }
      if (first.text) return first.text
      if (first.display) return first.display
      if (Array.isArray(first.coding) && first.coding[0]) {
        return first.coding[0].code || first.coding[0].display || undefined
      }
    }
    return String(first)
  }
  // FHIR CodeableConcept as a single dict: { coding: [{code, display}], text }
  if (typeof val === 'object') {
    if (val.text) return val.text
    if (Array.isArray(val.coding) && val.coding[0]) {
      return val.coding[0].code || val.coding[0].display || undefined
    }
    // FHIR Reference: { reference: "Patient/123" } → "123"
    if (typeof val.reference === 'string') {
      const parts = val.reference.split('/')
      return parts[parts.length - 1]
    }
  }
  return val
}

// Per-resource defaults applied when a required field is missing.
// Mirrors what the backend pushers already do, so the FE stops gating rows
// that DrChrono would happily accept.
const REQUIRED_DEFAULTS = {
  conditions: { clinical_status: 'active' },
  problems:   { clinical_status: 'active' },
  allergies:  { status: 'active' },
  medications:{ status: 'active' },
}

// Determine 3-state mapping status from missing count
function getMappingStatus(missingCount) {
  if (missingCount === 0) return 'Fully Mapped'
  if (missingCount === 1) return 'Partial Mapping'
  return 'No Mapping'
}

const STATUS_COLORS = {
  'Fully Mapped':    { bg: '#dcfce7', color: '#16a34a', dot: '#16a34a' },
  'Partial Mapping': { bg: '#fef9c3', color: '#b45309', dot: '#d97706' },
  'No Mapping':      { bg: '#fee2e2', color: '#dc2626', dot: '#dc2626' },
}

function StatusBadge({ status, small = false }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS['No Mapping']
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: c.bg, color: c.color,
      fontSize: small ? '0.68rem' : '0.75rem',
      fontWeight: 700, padding: small ? '2px 7px' : '3px 10px',
      borderRadius: 99, whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: c.dot, flexShrink: 0 }} />
      {status}
    </span>
  )
}

// Map a single record → returns { mapped, mappingStatus, unmappedRequired, mappedFields }
function mapRecord(record, resourceKey) {
  const schema = FHIR_SCHEMA[resourceKey] || { required:[], optional:[] }
  const srcKeys = Object.keys(record)
  const mappedFields = {}
  const unmappedRequired = []

  // Map required fields
  const defaults = REQUIRED_DEFAULTS[resourceKey] || {}
  for (const req of schema.required) {
    const matchKey = matchField(req, srcKeys)
    const rawVal = matchKey !== undefined && matchKey !== null ? record[matchKey] : record[req]
    const val = resolveValue(rawVal)  // unwrap FHIR arrays, extract display text
    if (val !== null && val !== undefined && val !== '') {
      mappedFields[req] = val
    } else if (defaults[req] !== undefined) {
      mappedFields[req] = defaults[req]
    } else {
      unmappedRequired.push({ field: req, reason: 'null_value', src: matchKey || req })
    }
  }

  // Map optional fields
  for (const opt of schema.optional) {
    const matchKey = matchField(opt, srcKeys)
    const rawVal = matchKey !== undefined && matchKey !== null ? record[matchKey] : record[opt]
    const val = resolveValue(rawVal)
    if (val !== null && val !== undefined && val !== '') {
      mappedFields[opt] = val
    }
  }

  const status = getMappingStatus(unmappedRequired.length)
  return {
    mapped: unmappedRequired.length === 0,
    mappingStatus: status,
    unmappedRequired,
    mappedFields,
    mappedCount: schema.required.length - unmappedRequired.length,
    totalRequired: schema.required.length,
  }
}

// Process all records for a resource
function processResource(key, records) {
  let passed = 0, partial = 0, failed = 0
  const failedRecords = []

  records.forEach((rec, idx) => {
    const result = mapRecord(rec, key)
    if (result.mapped) {
      passed++
    } else if (result.unmappedRequired.length === 1) {
      partial++
      if (failedRecords.length < 50) {
        failedRecords.push({
          idx: idx + 1,
          id: rec.id || rec.patient_id || `REC-${idx+1}`,
          errors: result.unmappedRequired,
          status: 'Partial Mapping',
        })
      }
    } else {
      failed++
      if (failedRecords.length < 50) {
        failedRecords.push({
          idx: idx + 1,
          id: rec.id || rec.patient_id || `REC-${idx+1}`,
          errors: result.unmappedRequired,
          status: 'No Mapping',
        })
      }
    }
  })

  // Overall resource status: worst case wins
  const resourceStatus = failed > 0
    ? 'No Mapping'
    : partial > 0
    ? 'Partial Mapping'
    : 'Fully Mapped'

  return {
    total: records.length, passed, partial, failed,
    failedRecords, resourceStatus,
    endpoint: DRCHRONO_ENDPOINTS[key] || 'POST /api/unknown',
  }
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
          <div className="showcase-health__labels" style={{ alignItems: 'center', gap: 10 }}>
            <StatusBadge status={
              results
                ? getMappingStatus(
                    results.failedRecords?.filter(fr => fr.status === 'No Mapping').length > 0
                      ? 2
                      : results.failedRecords?.some(fr => fr.status === 'Partial Mapping')
                      ? 1
                      : 0
                  )
                : 'Fully Mapped'
            } />
            <span className="health-label health-label--success">✓ {passedCount} Fully Mapped</span>
            {(results?.partial || 0) > 0 && <span style={{ color:'#b45309', fontSize:'0.75rem', fontWeight:600 }}>◑ {results.partial} Partial</span>}
            <span className="health-label health-label--failed">✗ {failedCount} No Mapping</span>
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
                <span className="showcase-rule__src" style={{ display:'flex', alignItems:'center', gap:6 }}>
                  Required field missing
                  <StatusBadge
                    status={unmappedRequired.length === 1 ? 'Partial Mapping' : 'No Mapping'}
                    small
                  />
                </span>
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

  const totalPassed  = Object.values(results).reduce((s,r) => s + r.passed,  0)
  const totalPartial = Object.values(results).reduce((s,r) => s + (r.partial || 0), 0)
  const totalFailed  = Object.values(results).reduce((s,r) => s + r.failed,  0)

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
                  <span className="mapping-summary-bar__num" style={{color:'#b45309'}}>{totalPartial.toLocaleString()}</span>
                  <span className="mapping-summary-bar__label">Partial Mapping</span>
                </div>
                <div className="mapping-summary-bar__divider"/>
                <div className="mapping-summary-bar__item">
                  <span className="mapping-summary-bar__num" style={{color:'#dc2626'}}>{totalFailed.toLocaleString()}</span>
                  <span className="mapping-summary-bar__label">No Mapping</span>
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
                        <StatusBadge status={r.resourceStatus} small />
                        <div style={{ display:'flex', gap:8, marginTop:4, flexWrap:'wrap' }}>
                          <span style={{color:'#16a34a',fontSize:'0.75rem',fontWeight:600}}>✓ {r.passed.toLocaleString()} fully mapped</span>
                          {r.partial > 0 && <span style={{color:'#b45309',fontSize:'0.75rem',fontWeight:600}}>◑ {r.partial.toLocaleString()} partial</span>}
                          {r.failed > 0 && <span style={{color:'#dc2626',fontSize:'0.75rem',fontWeight:600}}>✗ {r.failed.toLocaleString()} no mapping</span>}
                        </div>
                        <div style={{height:4,background:'#E5E7EB',borderRadius:2,overflow:'hidden',marginTop:4,width:120}}>
                          <div style={{height:'100%',background:STATUS_COLORS[r.resourceStatus]?.dot || '#dc2626',width:`${rate}%`}}/>
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
