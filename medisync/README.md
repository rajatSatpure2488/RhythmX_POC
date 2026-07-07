# MediSync - DrChrono CSV Integration Platform

## Overview
MediSync is a FastAPI + React proof of concept for ingesting clinical CSV datasets,
reviewing mapped resources, validating rows, and pushing the selected data into the
DrChrono EHR through OAuth-authenticated REST APIs.

The active workflow is CSV-first. The app currently focuses on the DrChrono push path
used by this project, including patients, appointments, problems, medications,
allergies, immunizations, lab results, lab orders, documents, clinical notes,
procedures, coverage, and care-team support. Older FHIR helper modules remain in the
repository for reference, but they are not required for the current sync workflow.

## Quick Start

### Backend (FastAPI)
```bash
cd medisync/backend
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (React + Vite)
```bash
cd medisync/frontend
npm install
npm run dev
```

### Docker (Full Stack)
```bash
cd medisync
docker-compose up --build
```

## Current Workflow
1. Auth - connect to DrChrono with OAuth or a manual access token.
2. Upload - load CSV files or ZIP/folder datasets.
3. Review - inspect detected resources and source rows.
4. Mapping - preview CSV fields mapped to DrChrono payloads.
5. Validation - dry-run selected resources and catch missing required fields.
6. Push - send selected resources to DrChrono with row-level status tracking.

## Important Routing Notes
- Encounters are pushed as DrChrono appointments.
- Observations and observation notes are pushed as `patient_lab_results`.
- Diagnostic reports are rendered as generated PDFs and uploaded to `documents`
  because the lab partner APIs are gated.
- Generated local datasets under `Dataset/`, `data/`, `docs/`, and `graphify-out/`
  are ignored by Git and are not pushed with the application code.

## Project Layout
- `backend/app/routes` - API routes for upload, mapping, validation, auth, and push.
- `backend/app/services` - DrChrono client/proxy, token, logging, and prerequisite helpers.
- `backend/tests` - focused tests for push mapping and workflow behavior.
- `frontend/src/pages` - upload, mapping, validation, review, and EHR push screens.
- `scripts` - local dataset transformation helpers.
