import { useState } from 'react'
import { useDataset } from '../context/DatasetContext'
import { useApiRate } from '../context/ApiRateContext'
import axios from 'axios'
import AiAssistantBot from '../components/AiAssistantBot'

const BACKEND = 'http://localhost:8000'

const TAB_LABELS = {
  medications:'Medications', medication:'Medications',
  conditions:'Conditions', condition:'Conditions',
  problems:'Conditions', problem:'Conditions', problem_list:'Conditions',
  encounters:'Encounters', encounter:'Encounters',
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
  appointments:'Appointments',
  diagnostic_reports:'Diagnostic Reports',
  observation_notes:'Observation Notes',
  service_requests:'Service Requests',
}

const DRCHRONO_ENDPOINTS = {
  patient:              { method:'POST',  path:'/api/patients',                     note:'Creates patient in DrChrono' },
  patients:             { method:'POST',  path:'/api/patients',                     note:'Creates patient in DrChrono' },
  medications:          { method:'POST',  path:'/api/medications',                  note:'Attached to patient by ID' },
  conditions:           { method:'POST',  path:'/api/problems',                     note:'Requires patient_id' },
  problems:             { method:'POST',  path:'/api/problems',                     note:'Requires patient_id' },
  encounters:           { method:'POST',  path:'/api/appointments',                 note:'Requires doctor_id + patient_id' },
  observations:         { method:'POST',  path:'/api/patient_lab_results',          note:'Structured lab result per observation (joined with notes)' },
  allergies:            { method:'POST',  path:'/api/allergies',                    note:'Requires patient_id' },
  allergy:              { method:'POST',  path:'/api/allergies',                    note:'Requires patient_id' },
  immunizations:        { method:'POST',  path:'/api/patient_vaccine_records',      note:'Requires patient_id' },
  procedures:           { method:'POST',  path:'/api/procedures',                  note:'Requires patient_id' },
  documents:            { method:'POST',  path:'/api/documents',                   note:'Multipart file upload (PDF, JPG, etc.)' },
  document_reference:   { method:'POST',  path:'/api/documents',                   note:'Multipart file upload from FHIR DocumentReference' },
  document_references:  { method:'POST',  path:'/api/documents',                   note:'Multipart file upload from FHIR DocumentReference' },
  clinical_notes:       { method:'POST',  path:'/api/clinical_note_field_values',   note:'Vitals -> PATCH /api/appointments, then note sections -> clinical_note_field_values' },
  coverages:            { method:'POST',  path:'/api/insurances',                    note:'Insurance type primary/secondary' },
  appointments:         { method:'POST',  path:'/api/appointments',                 note:'Requires doctor_id' },
  diagnostic_reports:   { method:'POST',  path:'/api/documents',                   note:'Binary upload supported' },
  observation_notes:    { method:'POST',  path:'/api/patient_lab_results',          note:'Merged into observations (or standalone lab result if pushed alone)' },
}

const REQUIRED = {
  medications:          ['name','dosage','status'],
  conditions:           ['code','status','patient_id'],
  problems:             ['code','status','patient_id'],
  encounters:           ['date'],   // pushed as appointments; date = scheduled_time
  observations:         ['patient_id'],   // labs (value) or pivoted vitals; share patient link
  allergies:            ['description','status'],
  allergy:              ['description','status'],
  immunizations:        ['vaccine_code','date','patient_id'],
  procedures:           ['code','performed_date','patient_id'],
  patient:              ['name','birth_date','gender'],
  patients:             ['name','birth_date','gender'],
  documents:            ['patient','description','document'],
  document_reference:   ['patient','description','document'],
  document_references:  ['patient','description','document'],
  clinical_notes:       ['note_id'],   // base + sections files share the note link
  coverages:            ['insurance_company','patient_id'],   // status is dropped in transform
  appointments:         ['date'],
  observation_notes:    ['patient_id'],   // pushed as a per-encounter PDF document
}

// Troubleshooting guide per error type + resource
const TROUBLESHOOT = {
  null_value: {
    patient:    `1. Check your patients CSV has 'name', 'birth_date', 'gender' columns.\n2. Ensure no rows are blank for these fields.\n3. Re-upload after filling missing values.`,
    medications:`1. Check 'name', 'dosage', 'status' columns exist in medications CSV.\n2. Null values will be rejected by DrChrono API.\n3. Add default values (e.g. status='active') before re-ingesting.`,
    conditions: `1. Ensure 'code', 'status', 'patient_id' are populated per row.\n2. DrChrono rejects conditions without a valid patient_id.\n3. Run Patient stage first to generate patient IDs.`,
    allergies:  `1. Ensure allergy rows map to 'description' and 'status'.\n2. The allergen code belongs inside notes, not snomed_code unless explicitly provided.\n3. Run Patient stage first so patient_id is available before push.`,
    encounters: `1. 'type', 'date', 'patient_id' are required.\n2. Dates must be in YYYY-MM-DD format.\n3. patient_id must match a created patient in DrChrono.`,
    documents:  `1. Each document row must have 'patient' (patient_id), 'description', and 'document' (base64 or file path).\n2. DrChrono /api/documents uses multipart upload — the file content is required.\n3. Supported file types: PDF, JPEG, PNG, TIFF.\n4. If using FHIR DocumentReference, ensure content[0].attachment.data has the base64 content.`,
    document_reference: `1. FHIR DocumentReference must have content[0].attachment.data (base64 encoded).\n2. Also needs subject.reference or _drchrono_patient_id.\n3. The attachment.contentType determines the upload MIME type.`,
    default:    `1. Fill all required fields in the source CSV.\n2. Check column names match expected FHIR field names.\n3. Re-upload the corrected file in Stage 2 (Ingestion).`,
  },
  date_format: {
    default: `1. All date fields must use ISO-8601 format: YYYY-MM-DD.\n2. Common issue: MM/DD/YYYY or DD-MM-YY formats.\n3. Use Excel "Format Cells → Text" then manually correct dates.\n4. Or use a script: pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')`,
  },
  terminology: {
    default: `1. Code fields (ICD, SNOMED, LOINC) must be short codes, not descriptions.\n2. Example: use '250.00' not 'Type 2 Diabetes Mellitus'.\n3. Look up correct codes at: https://browser.ihtsdotools.org\n4. Update the CSV and re-ingest.`,
  },
}

function getTroubleshootText(errorType, resourceKey) {
  const group = TROUBLESHOOT[errorType] || TROUBLESHOOT.null_value
  return group[resourceKey] || group.default
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/
const SHORT_DATE = /^\d{2}[\/\-]\d{2}[\/\-]\d{2,4}$/

// Alias map: required field tokens that map to multiple source key tokens
const FIELD_ALIASES = {
  'birthdate':    ['birthdate', 'dateofbirth', 'dob', 'birthdt'],
  'vaccinecode':  ['vaccinecode', 'cvxcode', 'cvx', 'vaccinename'],
  'patientid':    ['patientid', 'patient', 'memberid'],
  'patient':      ['patient', 'patientid', 'memberid'],
  'document':     ['document', 'filepath', 'filename', 'localpath', 'documentpath', 'filecontent', 'data', 'attachmentdata'],
  'description':  [
    'description', 'name', 'namefull', 'nameshort', 'namerx', 'title', 'label',
    'substance', 'substancedisplay', 'allergen', 'allergenname', 'allergendisplay',
    'code', 'codetext', 'codedisplay',
  ],
  'date':         ['date', 'scheduledtime', 'datereport', 'documentdate', 'effectivedt', 'appointmentdate'],
  'noteid':       ['noteid', 'sourcenoteid'],
  // Insurer name arrives as insurance_company (transformed) or payor_name (raw).
  'insurancecompany': ['insurancecompany', 'payorname', 'payername', 'insurer', 'payer'],
}

// Normalize a field key: lowercase, remove underscores/spaces/hyphens AND camelCase humps
function normalizeKey(s) {
  return s
    .replace(/([a-z])([A-Z])/g, '$1$2')
    .toLowerCase()
    .replace(/[_\s\-]/g, '')
}

// Unwrap FHIR complex types (HumanName arrays, CodeableConcept, etc.) to a display string
function resolveValue(val) {
  if (val === null || val === undefined) return undefined
  if (Array.isArray(val)) {
    if (val.length === 0) return undefined
    const first = val[0]
    if (typeof first === 'object' && first !== null) {
      if (first.family || first.text) {
        const given = Array.isArray(first.given) ? first.given.join(' ') : ''
        return `${given} ${first.family || first.text || ''}`.trim()
      }
      if (first.text)    return first.text
      if (first.display) return first.display
    }
    return String(first)
  }
  if (typeof val === 'object') {
    if (val.text) return val.text
    if (val.display) return val.display
    if (Array.isArray(val.coding) && val.coding[0]) {
      return val.coding[0].display || val.coding[0].code || undefined
    }
    if (typeof val.reference === 'string') {
      const parts = val.reference.split('/')
      return parts[parts.length - 1]
    }
  }
  return val
}


// Required-field defaults that mirror backend pusher behavior (e.g.
// _condition_status defaults to "Active"). Without these, the dry-run flags
// rows that DrChrono would happily accept.
const REQUIRED_DEFAULTS = {
  conditions: { status: 'active' },
  problems:   { status: 'active' },
  allergies:  { status: 'active' },
  allergy:    { status: 'active' },
  medications:{ status: 'active' },
}

function canonicalResourceKey(resourceKey) {
  return resourceKey === 'allergy' ? 'allergies' : resourceKey
}

function getRequiredFieldValue(rec, requiredField) {
  const allFields = Object.keys(rec)
  const rfNorm = normalizeKey(requiredField)
  const aliases = FIELD_ALIASES[rfNorm] || [rfNorm]
  const candidates = []

  for (const f of allFields) {
    const fNorm = normalizeKey(f)
    if (fNorm === rfNorm || aliases.includes(fNorm)) candidates.push(f)
  }
  for (const f of allFields) {
    const fNorm = normalizeKey(f)
    if (!candidates.includes(f) && (rfNorm.includes(fNorm) || fNorm.includes(rfNorm))) {
      candidates.push(f)
    }
  }

  let firstMatchedKey = null
  for (const key of candidates) {
    if (firstMatchedKey === null) firstMatchedKey = key
    const val = resolveValue(rec[key])
    if (val !== null && val !== undefined && val !== '') {
      return { key, val }
    }
  }

  return { key: firstMatchedKey || requiredField, val: undefined }
}

function auditRecord(rec, resourceKey) {
  const errors = []
  const canonicalKey = canonicalResourceKey(resourceKey)
  const reqFields = REQUIRED[resourceKey] || REQUIRED[canonicalKey] || []
  const defaults = REQUIRED_DEFAULTS[resourceKey] || REQUIRED_DEFAULTS[canonicalKey] || {}

  for (const rf of reqFields) {
    const { key: matchKey, val } = getRequiredFieldValue(rec, rf)
    if (val === null || val === undefined || val === '') {
      if (defaults[rf] !== undefined) continue  // backend will fill this in
      errors.push({ field: matchKey || rf, type:'null_value', tag:'Null value', cls:'err-tag--null',
        detail:`Required field '${rf}' is null or missing.` })
    }
  }

  const allFields = Object.keys(rec)
  for (const f of allFields) {
    const lower = f.toLowerCase()
    if (lower.includes('date') || lower.endsWith('_on') || lower.endsWith('_at') || lower.endsWith('date')) {
      const val = String(rec[f] || '')
      if (val.length > 3) {
        // ISO datetime (with T) is VALID — truncate mentally, do NOT flag
        const isIsoDatetime = /^\d{4}-\d{2}-\d{2}T/.test(val)
        const isIsoDate     = /^\d{4}-\d{2}-\d{2}$/.test(val)
        const isShortDate   = SHORT_DATE.test(val)
        // DD-MM-YYYY / MM-DD-YYYY short dates are auto-normalized to YYYY-MM-DD on
        // push, so only flag them if the numbers can't form a real calendar date.
        if (!isIsoDatetime && !isIsoDate && isShortDate) {
          const [a, b] = val.split(/[/.\-]/).map(Number)
          const day = a > 12 ? a : (b > 12 ? b : a)
          const month = a > 12 ? b : (b > 12 ? a : b)
          const validCal = month >= 1 && month <= 12 && day >= 1 && day <= 31
          if (!validCal) {
            errors.push({ field: f, type:'date_format', tag:'Bad date', cls:'err-tag--date',
              detail:`'${f}' is not a valid date. Got: '${val.slice(0,20)}'` })
          }
        }
      }
    }
  }

  for (const f of allFields) {
    const lower = f.toLowerCase()
    const skipTerminologyCheck = canonicalKey === 'allergies'
    if (!skipTerminologyCheck && (lower.includes('code') || lower.includes('icd'))) {
      const val = String(rec[f] || '')
      if (val.length > 10 && /\s/.test(val)) {
        errors.push({ field: f, type:'terminology', tag:'Terminology', cls:'err-tag--term',
          detail:`'${f}' looks like a description, not a code.` })
      }
    }
  }
  return errors
}

function auditResource(key, records) {
  let passed = 0, failed = 0
  const errorsByType = { null_value:0, date_format:0, terminology:0 }
  const failedRecords = []
  for (let i = 0; i < records.length; i++) {
    const errs = auditRecord(records[i], key)
    if (!errs.length) { passed++ } else {
      failed++
      errs.forEach(e => { if (errorsByType[e.type]!==undefined) errorsByType[e.type]++ })
      if (failedRecords.length < 100) failedRecords.push({
        idx:i+1, id:records[i].id||records[i].patient_id||`${key.toUpperCase()}-${i+1}`, errors:errs
      })
    }
  }
  const rate = records.length ? Math.round(passed/records.length*100) : 100
  return { count:records.length, passed, failed, rate, errorsByType, failedRecords }
}

// ── Patient Check Banner ─────────────────────────────────────────
function PatientCheckBanner({ resources }) {
  const patientData = resources.patient || resources.patients || []
  const hasPatient = patientData.length > 0
  const samplePatient = patientData[0] || {}
  const name = samplePatient.name || samplePatient.patient_name || samplePatient.first_name || '—'
  // Support both FHIR camelCase (birthDate) and snake_case (birth_date); truncate to YYYY-MM-DD
  const dobRaw = samplePatient.birthDate || samplePatient.birth_date || samplePatient.dob || ''
  const dob = dobRaw ? dobRaw.slice(0, 10) : '—'
  const gender = samplePatient.gender || '—'

  return (
    <div className={`vld-patient-banner ${hasPatient ? 'vld-patient-banner--found' : 'vld-patient-banner--missing'}`}>
      <div className="vld-patient-banner__icon">{hasPatient ? '👤' : '⚠️'}</div>
      <div className="vld-patient-banner__body">
        <div className="vld-patient-banner__title">
          {hasPatient
            ? `Patient Record Found — ${patientData.length} patient(s) to create in DrChrono`
            : 'No Patient Record Detected'}
        </div>
        {hasPatient ? (
          <div className="vld-patient-banner__meta">
            <span>Name: <strong>{name}</strong></span>
            <span>DOB: <strong>{dob}</strong></span>
            <span>Gender: <strong>{gender}</strong></span>
            <span className="vld-patient-action">→ Will call <code>POST /api/patients</code></span>
          </div>
        ) : (
          <div className="vld-patient-banner__meta">
            <span>All other resources require a patient_id. Upload a patients.csv or ensure patient records exist in DrChrono before pushing.</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── API Push Plan ────────────────────────────────────────────────
function ApiPushPlan({ availableKeys }) {
  // Split into pushable (has endpoint) vs skipped (no endpoint)
  const pushable = []
  const skipped = []
  const ordered = ['patient', ...availableKeys.filter(k => k !== 'patient' && k !== 'patients')]
  for (const k of ordered) {
    if (DRCHRONO_ENDPOINTS[k]) pushable.push(k)
    else skipped.push(k)
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
      {/* Pushable resources */}
      <div className="vld-push-plan">
        <div className="vld-push-plan__title">📡 API Push Plan — DrChrono Endpoints ({pushable.length} resource{pushable.length !== 1 ? 's' : ''})</div>
        <div className="vld-push-plan__list">
          {pushable.map((k, i) => {
            const ep = DRCHRONO_ENDPOINTS[k]
            return (
              <div key={k} className="vld-push-plan__row">
                <span className="vld-push-plan__step">{i + 1}</span>
                <span className="vld-push-plan__label">{TAB_LABELS[k] || k}</span>
                <span className={`vld-push-plan__method vld-push-plan__method--${ep.method.toLowerCase()}`}>{ep.method}</span>
                <code className="vld-push-plan__path">{ep.path}</code>
                <span className="vld-push-plan__note">{ep.note}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Skipped resources — no valid API endpoint */}
      {skipped.length > 0 && (
        <div className="vld-push-plan" style={{ borderColor:'#FDE68A' }}>
          <div className="vld-push-plan__title" style={{ background:'#FFFBEB', color:'#92400E' }}>
            ⚠️ Skipped Resources — No DrChrono API Endpoint ({skipped.length})
          </div>
          <div className="vld-push-plan__list">
            {skipped.map(k => (
              <div key={k} className="vld-push-plan__row" style={{ opacity: 0.7 }}>
                <span className="vld-push-plan__step" style={{ background:'#D1D5DB', fontSize:'0.55rem' }}>–</span>
                <span className="vld-push-plan__label">{TAB_LABELS[k] || k}</span>
                <span style={{ fontSize:'0.68rem', color:'#92400E', background:'#FEF3C7', padding:'2px 8px', borderRadius:4 }}>
                  No endpoint
                </span>
                <span className="vld-push-plan__note" style={{ color:'#92400E' }}>
                  This resource type will be skipped during push.
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Right-side Troubleshoot Panel ────────────────────────────────
function TroubleshootPanel({ selectedKey, details }) {
  if (!selectedKey || !details[selectedKey]) return (
    <div className="vld-troubleshoot vld-troubleshoot--empty">
      <div className="vld-troubleshoot__placeholder">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/>
        </svg>
        <p>Select a resource row to see troubleshooting steps</p>
      </div>
    </div>
  )

  const d = details[selectedKey]
  const ep = DRCHRONO_ENDPOINTS[selectedKey]
  const errorTypes = Object.entries(d.errorsByType).filter(([,v]) => v > 0)

  return (
    <div className="vld-troubleshoot">
      <div className="vld-troubleshoot__header">
        <div className="vld-troubleshoot__title">
          🔧 Troubleshoot: <strong>{TAB_LABELS[selectedKey] || selectedKey}</strong>
        </div>
        <div className="vld-troubleshoot__stats">
          <span className="vld-ts-stat vld-ts-stat--pass">✓ {d.passed} passed</span>
          <span className="vld-ts-stat vld-ts-stat--fail">✗ {d.failed} failed</span>
        </div>
      </div>

      <div className="vld-troubleshoot__scroll">
        {/* Push status */}
        <div className="vld-ts-section">
          <div className="vld-ts-section__label">DrChrono API Target</div>
          {ep ? (
            <div className="vld-ts-endpoint">
              <span className={`vld-push-plan__method vld-push-plan__method--${ep.method.toLowerCase()}`}>{ep.method}</span>
              <code>{ep.path}</code>
              <span className="vld-ts-ep-note">{ep.note}</span>
            </div>
          ) : <span style={{fontSize:'0.75rem',color:'var(--text-muted)'}}>No endpoint mapped</span>}
        </div>

        {/* Error summary */}
        {errorTypes.length > 0 && (
          <div className="vld-ts-section">
            <div className="vld-ts-section__label">Errors Found</div>
            <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              {d.errorsByType.null_value > 0 && <span className="err-tag err-tag--null">Null values: {d.errorsByType.null_value}</span>}
              {d.errorsByType.date_format > 0 && <span className="err-tag err-tag--date">Bad dates: {d.errorsByType.date_format}</span>}
              {d.errorsByType.terminology > 0 && <span className="err-tag err-tag--term">Terminology: {d.errorsByType.terminology}</span>}
            </div>
          </div>
        )}

        {/* Troubleshoot steps per error type */}
        {errorTypes.map(([type]) => (
          <div key={type} className="vld-ts-section">
            <div className="vld-ts-section__label">
              {type === 'null_value' ? '🔴 Fix: Null / Missing Fields'
               : type === 'date_format' ? '🟡 Fix: Date Format Issues'
               : '🟠 Fix: Terminology Code Issues'}
            </div>
            <pre className="vld-ts-steps">{getTroubleshootText(type, selectedKey)}</pre>
          </div>
        ))}

        {/* Top failing fields */}
        {d.failedRecords.length > 0 && (
          <div className="vld-ts-section">
            <div className="vld-ts-section__label">Top Failing Fields</div>
            <div style={{display:'flex',flexDirection:'column',gap:4}}>
              {[...new Set(d.failedRecords.flatMap(fr => fr.errors.map(e => e.field)))].slice(0,5).map(f => (
                <div key={f} className="vld-ts-field-row">
                  <code className="vld-ts-field-name">{f}</code>
                  <span className="vld-ts-field-note">→ Check this column in your CSV</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {d.failed === 0 && (
          <div className="vld-ts-section">
            <div className="vld-ts-all-clear">✅ All {d.count} records are valid and ready to push!</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Resource Row ─────────────────────────────────────────────────
function ResourceRow({ rkey, data, expanded, onToggle, isSelected, onSelect }) {
  const rate  = data.rate
  const color = rate>=90?'#16a34a':rate>=60?'#d97706':'#dc2626'
  return (
    <div
      className={`vld-resource-row ${isSelected ? 'vld-resource-row--selected' : ''}`}
      onClick={() => onSelect(rkey)}>
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
        {data.failed>0 && <span
          style={{fontSize:'0.68rem',color:'var(--primary)',cursor:'pointer'}}
          onClick={e=>{e.stopPropagation();onToggle(rkey)}}>{expanded?'▴':'▾'} Errors</span>}
      </div>
      {data.failed>0 && (
        <div style={{display:'flex',gap:6,padding:'0 20px 8px',flexWrap:'wrap'}}>
          {data.errorsByType.null_value>0 && <span className="err-tag err-tag--null">Null: {data.errorsByType.null_value}</span>}
          {data.errorsByType.date_format>0 && <span className="err-tag err-tag--date">Bad dates: {data.errorsByType.date_format}</span>}
          {data.errorsByType.terminology>0 && <span className="err-tag err-tag--term">Terminology: {data.errorsByType.terminology}</span>}
        </div>
      )}
      {expanded && data.failedRecords.length>0 && (
        <div className="vld-resource-errors">
          <table className="vld-debug-table">
            <thead><tr><th>#</th><th>RECORD ID</th><th>FIELD</th><th>ERROR</th><th>DETAIL</th></tr></thead>
            <tbody>
              {data.failedRecords.map((fr,i)=>fr.errors.map((e,j)=>(
                <tr key={`${i}-${j}`}>
                  {j===0 && <td rowSpan={fr.errors.length} style={{verticalAlign:'top',color:'var(--text-muted)',fontSize:'0.7rem'}}>{fr.idx}</td>}
                  {j===0 && <td rowSpan={fr.errors.length} className="vld-record-id" style={{verticalAlign:'top'}}>{fr.id}</td>}
                  <td><code style={{fontSize:'0.7rem',background:'#F1F5F9',padding:'1px 5px',borderRadius:3}}>{e.field}</code></td>
                  <td><span className={`err-tag ${e.cls}`}>{e.tag}</span></td>
                  <td className="vld-debug-detail">{e.detail}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────
export default function Validation({ onComplete }) {
  const { dataset, setValidationResults } = useDataset()
  const [acceptedFixes, setAcceptedFixes] = useState({})

  const handleFixAccepted = (resourceKey, suggestion) => {
    setAcceptedFixes(prev => ({
      ...prev,
      [resourceKey]: [...(prev[resourceKey] || []), suggestion],
    }))
  }
  const [running, setRunning]   = useState(false)
  const [done, setDone]         = useState(false)
  const [details, setDetails]   = useState({})
  const [expanded, setExpanded] = useState({})
  const [selectedKey, setSelectedKey] = useState(null)
  const [progress, setProgress] = useState(0)
  const [currentKey, setCurrentKey] = useState(null)
  const { recordCall } = useApiRate()

  const resources     = dataset.resources || {}
  const availableKeys = Object.entries(resources).filter(([,v])=>Array.isArray(v)&&v.length>0).map(([k])=>k)
  const totalRecords  = availableKeys.reduce((s,k)=>s+(resources[k]?.length||0),0)

  const handleRun = async () => {
    setRunning(true); setDone(false); setDetails({}); setProgress(0)
    const newDetails = {}; let processed = 0
    for (const key of availableKeys) {
      setCurrentKey(key)
      const recs = resources[key] || []
      await new Promise(r => setTimeout(r, 80 + Math.random()*150))
      recordCall()
      newDetails[key] = auditResource(key, recs)
      processed += recs.length
      setProgress(Math.round(processed/totalRecords*100))
      setDetails({...newDetails})
    }
    axios.post(`${BACKEND}/dryrun/run`,{},{timeout:15000}).catch(()=>{})
    setValidationResults({ details: newDetails, totalRecords })
    setCurrentKey(null); setRunning(false); setDone(true)
    // Auto-select first failing resource
    const firstFail = availableKeys.find(k => newDetails[k]?.failed > 0)
    if (firstFail) setSelectedKey(firstFail)
  }

  const toggle = k => setExpanded(p => ({...p, [k]:!p[k]}))
  const totalPassed = Object.values(details).reduce((s,d)=>s+d.passed,0)
  const totalFailed = Object.values(details).reduce((s,d)=>s+d.failed,0)
  const overallPct  = totalRecords ? Math.round(totalPassed/totalRecords*100) : 0
  const needsKeys   = Object.entries(details).filter(([,d])=>d.rate<80)

  const handleExport = () => {
    const rows = ['RESOURCE,RECORD_ID,FIELD,ERROR_TYPE,DETAIL']
    Object.entries(details).forEach(([k,d])=>
      d.failedRecords.forEach(fr=>fr.errors.forEach(e=>
        rows.push(`${k},${fr.id},${e.field},"${e.tag}","${e.detail}"`)
      ))
    )
    const a = Object.assign(document.createElement('a'),{
      href: URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'})),
      download:'validation_errors.csv'
    }); a.click()
  }

  if (!availableKeys.length) return (
    <div className="validation-v2">
      <div className="validation-idle-card">
        <div style={{fontSize:'2rem',marginBottom:12}}>📭</div>
        <p style={{color:'var(--text-muted)'}}>No dataset loaded. Upload files in Ingestion first.</p>
      </div>
    </div>
  )

  return (
    <div className="validation-v2">
      {/* Header */}
      <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:16}}>
        <div>
          <div className="stage-header__badge">Stage 5</div>
          <h1 className="stage-header__title">Validation & Dry Run</h1>
          <p className="stage-header__desc">
            Validates all records for FHIR compliance, checks patient existence, and previews the DrChrono API push plan.
          </p>
        </div>
        <div style={{display:'flex',gap:8}}>
          {done && <button className="btn btn--secondary" onClick={handleExport}>↓ Export Errors</button>}
          {done && <button className="btn btn--ghost" onClick={()=>{setDone(false);setDetails({})}}>↺ Re-run</button>}
        </div>
      </div>

      {/* Patient Check Banner */}
      <PatientCheckBanner resources={resources} />

      {/* API Push Plan */}
      {!done && !running && <ApiPushPlan availableKeys={availableKeys} />}

      {/* Pre-run card */}
      {!done && !running && (
        <div className="validation-idle-card" style={{marginTop:16}}>
          <div style={{fontSize:'2rem',marginBottom:10}}>🔍</div>
          <h2 style={{marginBottom:6}}>Ready to Validate</h2>
          <p style={{color:'var(--text-secondary)',fontSize:'0.84rem',marginBottom:4}}>
            {availableKeys.length} resource types · {totalRecords.toLocaleString()} total records
          </p>
          <p style={{color:'var(--text-muted)',fontSize:'0.74rem',marginBottom:20}}>
            Checks: null values · date formats · required fields · terminology codes
          </p>
          <button className="btn btn--primary" onClick={handleRun}>▶ Start Validation</button>
        </div>
      )}

      {/* Progress */}
      {running && (
        <div className="mapping-run-progress" style={{margin:'12px 0'}}>
          <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize:'0.78rem'}}>
            <span>Validating {currentKey ? (TAB_LABELS[currentKey]||currentKey) : ''}…</span>
            <span style={{color:'var(--primary)',fontWeight:600}}>{progress}%</span>
          </div>
          <div style={{height:6,background:'#E5E7EB',borderRadius:3,overflow:'hidden'}}>
            <div style={{height:'100%',background:'var(--primary)',width:`${progress}%`,transition:'width 0.3s',borderRadius:3}}/>
          </div>
        </div>
      )}

      {/* Results: split layout */}
      {Object.keys(details).length > 0 && (
        <div className="vld-split">
          {/* LEFT: results */}
          <div className="vld-split__left">
            {/* Summary stats */}
            <div className="vld-stat-row" style={{marginBottom:14}}>
              <div className="vld-stat-card">
                <div className="vld-stat-card__big">{totalRecords.toLocaleString()}</div>
                <div className="vld-stat-card__label">Records Scanned</div>
              </div>
              <div className="vld-stat-card">
                <div className="vld-stat-card__big" style={{color:'#16a34a'}}>{totalPassed.toLocaleString()}</div>
                <div className="vld-stat-card__label">Records Passed</div>
              </div>
              <div className="vld-stat-card">
                <div className="vld-stat-card__big" style={{color:'#dc2626'}}>{totalFailed.toLocaleString()}</div>
                <div className="vld-stat-card__label">With Errors</div>
              </div>
              <div className="vld-stat-card">
                <div className="vld-stat-card__big" style={{color:'var(--primary)'}}>{overallPct}%</div>
                <div className="vld-stat-card__label">Overall Pass Rate</div>
              </div>
            </div>

            <div style={{fontSize:'0.7rem',color:'var(--text-muted)',marginBottom:8}}>
              Click a row to see troubleshooting steps →
            </div>

            {/* Per-resource rows */}
            {Object.entries(details).map(([k,d]) => (
              <ResourceRow key={k} rkey={k} data={d}
                expanded={!!expanded[k]} onToggle={toggle}
                isSelected={selectedKey===k} onSelect={setSelectedKey}
              />
            ))}

            {/* API Push Plan (after run) */}
            {done && <ApiPushPlan availableKeys={availableKeys} />}
          </div>

          {/* RIGHT: troubleshoot panel + AI Bot */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, flex: '0 0 340px', minWidth: 0 }}>
            <TroubleshootPanel selectedKey={selectedKey} details={details} />
            <AiAssistantBot
              selectedKey={selectedKey}
              details={details}
              onFixesAccepted={handleFixAccepted}
            />
          </div>
        </div>
      )}

      {/* Actions */}
      {done && (
        <div className="stage-actions" style={{marginTop:16}}>
          <span style={{fontSize:'0.78rem',color:needsKeys.length>0?'#d97706':'#16a34a',fontWeight:500}}>
            {needsKeys.length>0 ? `⚠️ ${needsKeys.length} resource type(s) have errors` : '✅ All types ready to push'}
          </span>
          <button className="btn btn--primary" onClick={()=>onComplete?.()}>
            Select Resources & Push →
          </button>
        </div>
      )}
    </div>
  )
}
