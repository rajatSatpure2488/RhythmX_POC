# MediSync — Master Build Plan

## Project Context
MediSync is a clinical data integration platform that:
- Ingests synthetic FHIR-based patient datasets (ZIP/folder/files)
- Maps 13 FHIR resources using rule-based mappers
- Validates via dry-run mechanism
- Pushes to DrChrono EHR via OAuth 2.0

**Stack:** React + Vite (frontend) | FastAPI + Uvicorn (backend)
**Target EHR:** DrChrono REST API (https://app.drchrono.com/api)

---

## STAGE 1 — OAuth 2.0 Authentication + Ingestion UI ✅ (Current)

### Goal
Build the authentication layer (OAuth 2.0 Authorization Code Flow) and the
Upload/Ingestion screen matching the provided UI mockup.

### UI Specification (from reference image)
**Layout:** 3-column — Left Sidebar | Main Content | Right Panel

#### Left Sidebar
- Logo: "MediSync" (blue text, top-left)
- User block: Avatar + "MediSync Platform / Clinical Integration Stage"
- Navigation items:
  - ⚙ Pipeline Setup
  - ⊞ Ingestion  ← ACTIVE (blue highlight + left border indicator)
  - ⊞ Mapping
  - ⚲ Review
  - ⛨ Validation
  - ⟳ Sync
- Bottom sticky items:
  - ⛨ EHR Authentication
  - ⊞ Dataset Status
  - ⟳ API Rate Monitor

#### Top Navbar (inside main area)
- Right: Cloud icon + "Connected" text | Avatar "SM" + "Dr. Sarah Mitchell"

#### Main Content (Upload Dataset panel)
- Title: "Upload Dataset"
- Subtitle: "Securely transfer patient records and clinical notes for ingestion."
- Drag-drop zone (dashed border, cloud-upload icon):
  - "Drop your ZIP file, folder, or files here"
  - "Supports standard HL7, FHIR JSON, and unstructured clinical notes (PDF, TXT). Max 5GB per batch."
- Three action buttons: [📁 Upload ZIP] [📁 Upload Folder] [📄 Upload Files]
- Staged Files section showing filename + size + delete icon
- [▶ LOAD & PROCESS DATASET] — dark teal CTA button

#### Right Panel (EHR Authentication)
- "EHR Authentication" header with grid icon
- CONNECTED badge (green pill)
- Stats: Target System | Last Handshake | Token Expiry
- "Manage Connection Config →" link
- Info box: "Ingestion Guidelines" with blue info icon

### Backend Endpoints (Stage 1)
```
POST /auth/oauth/initiate       → Returns DrChrono authorization URL
GET  /auth/oauth/callback       → Exchanges code → access_token + refresh_token
POST /auth/manual               → Accept token + doctor_id directly
GET  /auth/status               → Current token validity + doctor info
POST /auth/refresh              → Refresh expired access token
GET  /auth/user                 → Get doctor profile (name, ID)
```

### OAuth 2.0 Flow (RFC 6749 — Authorization Code)
1. User clicks "Login with DrChrono" → GET /auth/oauth/initiate
2. Backend generates: https://drchrono.com/o/authorize/?client_id=&redirect_uri=&response_type=code&scope=...
3. User logs in on DrChrono, grants permission
4. DrChrono redirects to: http://localhost:8000/auth/oauth/callback?code=AUTH_CODE
5. Backend POSTs to https://drchrono.com/o/token/ → receives access_token + refresh_token
6. Token stored in-memory (token_store.py) with expiry timestamp
7. Frontend polls /auth/status → shows CONNECTED state

### Token Lifecycle
- access_token: 48h lifespan (172,800 seconds)
- refresh_token: long-lived
- Auto-refresh triggered when token expires (401 response)

### DrChrono OAuth Scopes Required
- user:read
- patients:read
- patients:write
- clinical:read
- clinical:write
- calendar:read
- calendar:write

### Security Rules
- CLIENT_SECRET only in .env, never logged or sent to frontend
- Tokens never stored plaintext — encrypted at rest
- All production calls over HTTPS
- Error messages sanitized (no credential leakage)

### Files Impacted (Stage 1)
**Frontend:**
- frontend/src/App.jsx                         (root + router)
- frontend/src/index.css                       (design system)
- frontend/src/pages/Dashboard.jsx            (3-col layout)
- frontend/src/components/Sidebar/            (nav + auth button)
- frontend/src/components/Upload/             (drag-drop + staged files)
- frontend/src/components/Push/              (EHR Auth right panel)
- frontend/src/context/AuthContext.jsx        (token state)
- frontend/src/services/ehrService.js         (API calls)

**Backend:**
- backend/app/main.py                         (FastAPI app + CORS)
- backend/app/routes/auth.py                  (all OAuth endpoints)
- backend/app/services/token_store.py         (in-memory token storage)
- backend/app/services/drchrono_client.py     (HTTP client)
- backend/app/models/schemas.py               (Pydantic models)
- .env                                        (credentials)

### Verification Checklist (Stage 1)
- [ ] OAuth URL generated correctly
- [ ] Code → token exchange works
- [ ] /auth/status returns CONNECTED with doctor name
- [ ] Frontend shows CONNECTED badge + token expiry countdown
- [ ] Drag-drop zone accepts ZIP/folder/files
- [ ] Staged files list shows filename + size
- [ ] LOAD & PROCESS DATASET button enabled only when file staged
- [ ] Manual token fallback works

---

## STAGE 2 — Data Ingestion & Patient Display (Planned)

### Goal
Pre-processing engine: unzip, detect FHIR types, identify patient ID,
link foreign keys, validate mandatory fields. Display patient card + 13 resource tabs.

### Files Impacted (Stage 2)
- backend/app/routes/upload.py
- backend/app/utils/file_parser.py
- backend/app/utils/foreign_key_linker.py
- backend/app/mappers/ (all 13)
- frontend/src/components/Patient/PatientCard.jsx
- frontend/src/components/Patient/ResourceTabs.jsx

---

## STAGE 3 — Mapping Engine (Planned)

### Goal
Rule-based field mapper for all 13 FHIR resources.
UI: mapping table with Source → Target → Status columns.

---

## STAGE 4 — Resource Selection (Planned)

### Goal
Checkbox-based resource selector (Select All or custom).
Shows "Selected: X of 13 Resources".

---

## STAGE 5 — Dry Run Validation (Planned)

### Goal
Validate selected resources without pushing.
Shows: patient uniqueness check, API count estimate, per-resource pass/fail, edge cases.

---

## STAGE 6 — Push to EHR (Planned)

### Goal
Rate-limited push (29/min) with patient CREATE/UPDATE logic.
Shows: pass/fail per API call, failed row detail table (Resource | Row | Column | Error).

---

## STAGE 7 — Polish & Testing (Planned)

### Goal
UI refinement, error handling, edge case coverage, E2E test with real synthetic data.

---

## DrChrono API Reference (Quick)
- Base URL: https://app.drchrono.com/api
- Auth URL: https://drchrono.com/o/authorize/
- Token URL: https://drchrono.com/o/token/
- Rate limits: 500/day | 29/min
- Token type: Bearer

## Color Palette (from UI reference)
- Primary Blue: #1565C0 / #1976D2
- Sidebar bg: #FFFFFF
- Sidebar active: #E3F2FD border-left #1976D2
- Connected green: #00897B / badge bg #E0F2F1
- CTA button: #0D3B6E (dark navy)
- Background: #F5F7FA
- Card bg: #FFFFFF
- Text primary: #1A1A2E
- Text secondary: #6B7280
