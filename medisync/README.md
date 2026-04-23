# MediSync — Clinical Notes Integration Platform

## Overview
MediSync ingests synthetic FHIR-based patient datasets, maps 13+ healthcare resources
using rule-based mappers, validates data via a dry-run mechanism, and pushes cleaned
& mapped data to the **DrChrono EHR system** via OAuth-authenticated API calls.

## Quick Start

### Backend (FastAPI)
```bash
cd backend
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

### Docker (Full Stack)
```bash
docker-compose up --build
```

## Architecture
- **Frontend**: React + Vite (port 5173)
- **Backend**: FastAPI + Uvicorn (port 8000)
- **EHR Target**: DrChrono REST API
- **Data Format**: FHIR R4 (JSON)

## 7-Phase Pipeline
1. **Auth** — OAuth or Manual Token
2. **Upload** — ZIP / folder / multi-file ingestion
3. **Patient Display** — 13-resource tabbed view
4. **Mapping** — Rule-based field mapper (FHIR → DrChrono)
5. **Resource Selection** — Choose which resources to push
6. **Dry Run** — Validate, estimate API calls, detect edge cases
7. **Push** — Rate-limited EHR push with row-level error tracking

## Folder Structure
See `/docs/BLUEPRINT.md` for full technical blueprint.

## Environment Variables
Copy `.env` and fill in your DrChrono credentials.

## Resources Supported (13)
Patient · Medication · Condition · Encounter · Observation
Allergy · Immunization · Procedure · DiagnosticReport
DocumentReference · CarePlan · Practitioner · Organization
