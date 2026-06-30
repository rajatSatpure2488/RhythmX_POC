# import json
# import logging
# import mimetypes
# import os
# import random
# import time
# from pathlib import Path
# from typing import Any, List, Optional

# import requests
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel

# from app.core import config
# from app.routes.upload import _SESSION
# from app.services.token_store import token_store

# log = logging.getLogger("medisync.push")

# router = APIRouter()

# ENDPOINT_MAP = {
#     "patient": "patients",
#     "patients": "patients",
#     "encounter": "appointments",
#     "encounters": "appointments",
#     "condition": "problems",
#     "conditions": "problems",
#     "problem": "problems",
#     "problems": "problems",
#     "problem_list": "problems",
#     "medication": "medications",
#     "medications": "medications",
#     "allergy": "allergies",
#     "allergies": "allergies",
#     "immunization": "vaccines",
#     "immunizations": "vaccines",
#     "observation": "lab_results",
#     "observations": "lab_results",
#     "procedure": "procedures",
#     "procedures": "procedures",
#     "coverage": "patient_insurances",
#     "coverages": "patient_insurances",
#     "document": "documents",
#     "documents": "documents",
#     "document_reference": "documents",
#     "document_references": "documents",
#     "clinical_note": "clinical_notes",
#     "clinical_notes": "clinical_notes",
# }

# _GENDER_MAP = {
#     "male": "Male", "m": "Male",
#     "female": "Female", "f": "Female",
#     "other": "Other", "o": "Other",
#     "unknown": "Unknown", "u": "Unknown",
#     "UNK": "Unknown",
# }


# def _strip_empty(payload: dict) -> dict:
#     return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


# def _normalize_date(val: Any) -> str:
#     if not val:
#         return ""
#     return str(val)[:10]


# def _map_gender(val: Any) -> str:
#     if not val:
#         return ""
#     return _GENDER_MAP.get(str(val).strip(), str(val).strip())


# def _extract_name(name_field: Any):
#     if not name_field:
#         return "", ""

#     if isinstance(name_field, str):
#         parts = name_field.strip().split(" ", 1)
#         return parts[0], parts[1] if len(parts) > 1 else ""

#     if isinstance(name_field, list) and name_field:
#         n = name_field[0]
#         if isinstance(n, dict):
#             given = n.get("given") or []
#             first = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
#             last = str(n.get("family") or "")
#             return first.strip(), last.strip()

#     return "", ""


# def _codeable_text(value: Any) -> str:
#     if not value:
#         return ""

#     if isinstance(value, str):
#         return value.strip()

#     if isinstance(value, dict):
#         if value.get("text"):
#             return str(value["text"]).strip()

#         coding = value.get("coding") or []
#         if isinstance(coding, list) and coding:
#             first = coding[0]
#             if isinstance(first, dict):
#                 return str(first.get("display") or first.get("code") or "").strip()

#     return ""


# def _codeable_code(value: Any) -> str:
#     if isinstance(value, dict):
#         coding = value.get("coding") or []
#         if isinstance(coding, list) and coding:
#             first = coding[0]
#             if isinstance(first, dict):
#                 return str(first.get("code") or "").strip()
#     return ""


# def _active_status(value: Any, default: str = "active") -> str:
#     raw = str(value or default).lower()
#     if raw in ("active", "completed", "intended", "confirmed", "final"):
#         return "active"
#     return "inactive"


# def _condition_status(record: dict) -> str:
#     clinical = record.get("clinicalStatus")
#     if isinstance(clinical, dict):
#         text = _codeable_text(clinical).lower()
#         if "resolved" in text or "inactive" in text:
#             return "resolved"

#     raw = str(record.get("status") or record.get("verificationStatus") or "active").lower()
#     if raw in ("resolved", "inactive", "entered-in-error"):
#         return "resolved"
#     return "active"


# def _json_headers(token: str) -> dict:
#     return {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json",
#         "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
#     }


# def _multipart_headers(token: str) -> dict:
#     return {
#         "Authorization": f"Bearer {token}",
#         "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
#     }


# def _map_patient(record: dict, doctor_id: Optional[int] = None) -> dict:
#     name_raw = record.get("name")

#     if isinstance(name_raw, list):
#         first, last = _extract_name(name_raw)
#     else:
#         first = record.get("first_name") or record.get("given") or ""
#         last = record.get("last_name") or record.get("family") or ""
#         if not first and not last:
#             first, last = _extract_name(name_raw)

#     addr_raw = record.get("address")
#     address = city = state = zip_code = ""

#     if isinstance(addr_raw, list) and addr_raw:
#         a = addr_raw[0]
#         if isinstance(a, dict):
#             lines = a.get("line") or []
#             address = " ".join(lines) if isinstance(lines, list) else str(lines)
#             city = a.get("city", "")
#             state = a.get("state", "")
#             zip_code = a.get("postalCode", "")
#     elif isinstance(addr_raw, str):
#         address = addr_raw

#     phone = email = ""
#     for t in record.get("telecom") or []:
#         if isinstance(t, dict):
#             system = t.get("system", "")
#             value = t.get("value", "")
#             if system == "phone" and not phone:
#                 phone = value
#             elif system == "email" and not email:
#                 email = value

#     payload = {
#         "first_name": first or "Unknown",
#         "last_name": last or "Patient",
#         "date_of_birth": _normalize_date(
#             record.get("birthDate")
#             or record.get("date_of_birth")
#             or record.get("birth_date")
#             or record.get("dob")
#         ),
#         "gender": _map_gender(record.get("gender") or record.get("sex")) or "Unknown",
#         "email": email or record.get("email", ""),
#         "home_phone": phone or record.get("phone") or record.get("home_phone", ""),
#         "address": address or record.get("address") or record.get("street", ""),
#         "city": city or record.get("city", ""),
#         "state": state or record.get("state", ""),
#         "zip_code": zip_code or record.get("zip_code") or record.get("zip", ""),
#     }

#     if doctor_id:
#         payload["doctor"] = int(doctor_id)

#     return _strip_empty(payload)


# def _map_medication(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     med_name = (
#         record.get("name")
#         or record.get("name_full")
#         or record.get("display")
#         or _codeable_text(record.get("medicationCodeableConcept"))
#         or _codeable_text(record.get("medication"))
#         or ""
#     )

#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "name": med_name,
#         "status": _active_status(record.get("status"), default="active"),
#     }

#     rxnorm = (
#         record.get("rxnorm")
#         or record.get("rxnorm_code")
#         or _codeable_code(record.get("medicationCodeableConcept"))
#     )
#     if rxnorm:
#         payload["rxnorm"] = str(rxnorm)

#     dosage = record.get("dosageInstruction") or []
#     if isinstance(dosage, list) and dosage:
#         d0 = dosage[0]
#         if isinstance(d0, dict) and d0.get("text"):
#             payload["frequency"] = d0["text"]

#     if record.get("dosage_quantity"):
#         payload["dosage_quantity"] = str(record["dosage_quantity"])
#     if record.get("dosage_unit"):
#         payload["dosage_unit"] = record["dosage_unit"]
#     if record.get("route"):
#         payload["route"] = record["route"]
#     if record.get("frequency") or record.get("frequencyText"):
#         payload["frequency"] = record.get("frequencyText") or record.get("frequency")
#     if record.get("reason") or record.get("indication"):
#         payload["indication"] = record.get("reason") or record.get("indication")

#     start_date = record.get("start_dt") or record.get("start_date") or record.get("authoredOn") or record.get("date")
#     if start_date:
#         payload["start_date"] = _normalize_date(start_date)

#     return _strip_empty(payload)


# def _map_condition(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     name = (
#         record.get("description")
#         or record.get("name")
#         or record.get("name_full")
#         or _codeable_text(record.get("code"))
#         or ""
#     )

#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "description": name,
#         "status": _condition_status(record),
#     }

#     icd_code = (
#         record.get("icd_code")
#         or record.get("code_value")
#         or record.get("code")
#         if isinstance(record.get("code"), str)
#         else _codeable_code(record.get("code"))
#     )
#     if icd_code:
#         payload["icd_code"] = str(icd_code)

#     onset = record.get("date_onset") or record.get("onsetDateTime") or record.get("start_dt")
#     if onset:
#         payload["date_onset"] = _normalize_date(onset)

#     return _strip_empty(payload)


# def _map_allergy(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     name = (
#         record.get("description")
#         or record.get("name")
#         or record.get("name_full")
#         or _codeable_text(record.get("code"))
#         or ""
#     )

#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "description": name,
#         "status": _active_status(record.get("clinicalStatus") or record.get("status"), default="active"),
#     }

#     reaction = record.get("reaction") or record.get("reaction_manifestation")
#     if isinstance(reaction, list) and reaction:
#         reaction = _codeable_text((reaction[0] or {}).get("manifestation"))

#     if reaction:
#         payload["reaction"] = str(reaction)

#     return _strip_empty(payload)


# def _map_immunization(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "name": record.get("name") or record.get("name_full") or _codeable_text(record.get("vaccineCode")),
#         "administered_at": _normalize_date(
#             record.get("administered_at")
#             or record.get("occurrenceDateTime")
#             or record.get("occurrence_dt")
#             or record.get("date")
#         ),
#         "lot_number": record.get("lot_number"),
#         "manufacturer": record.get("manufacturer"),
#     }

#     return _strip_empty(payload)


# def _map_observation(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     name = (
#         record.get("description")
#         or record.get("name")
#         or record.get("name_full")
#         or _codeable_text(record.get("code"))
#         or "Observation"
#     )

#     value = record.get("value")
#     if value is None and isinstance(record.get("valueQuantity"), dict):
#         value = record["valueQuantity"].get("value")

#     notes = record.get("notes") or record.get("conclusion") or ""
#     if value not in (None, ""):
#         unit = record.get("value_unit") or record.get("unit") or ""
#         notes = f"{name}: {value} {unit}".strip()

#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "description": name,
#         "document_date": _normalize_date(record.get("effectiveDateTime") or record.get("effective_dt") or record.get("date")),
#         "notes": notes,
#     }

#     return _strip_empty(payload)


# def _map_clinical_note(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     payload = {
#         "patient": int(patient_id) if patient_id else None,
#         "doctor": int(doctor_id) if doctor_id else None,
#         "clinical_note_date": _normalize_date(
#             record.get("clinical_note_date")
#             or record.get("date")
#             or record.get("effective_dt")
#         ),
#         "notes": (
#             record.get("notes")
#             or record.get("note_text")
#             or record.get("text")
#             or record.get("content")
#             or record.get("summary_text")
#             or ""
#         ),
#     }

#     return _strip_empty(payload)


# def _map_record(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
#     key = resource_key.lower()

#     if key in ("patient", "patients"):
#         return _map_patient(record, doctor_id=doctor_id)
#     if key in ("medication", "medications"):
#         return _map_medication(record, doctor_id, patient_id)
#     if key in ("condition", "conditions", "problem", "problems", "problem_list"):
#         return _map_condition(record, doctor_id, patient_id)
#     if key in ("allergy", "allergies"):
#         return _map_allergy(record, doctor_id, patient_id)
#     if key in ("immunization", "immunizations"):
#         return _map_immunization(record, doctor_id, patient_id)
#     if key in ("observation", "observations"):
#         return _map_observation(record, doctor_id, patient_id)
#     if key in ("clinical_note", "clinical_notes"):
#         return _map_clinical_note(record, doctor_id, patient_id)

#     mapped = dict(record)
#     if patient_id:
#         mapped.setdefault("patient", int(patient_id))
#     if doctor_id:
#         mapped.setdefault("doctor", int(doctor_id))
#     return _strip_empty(mapped)


# def _resolve_file_path(raw_path: str) -> Optional[str]:
#     if not raw_path:
#         return None

#     p = Path(str(raw_path)).expanduser()

#     candidates = []
#     if p.is_absolute():
#         candidates.append(p)
#     else:
#         candidates.append(Path.cwd() / p)

#         base_dir = getattr(config, "BASE_DIR", None)
#         if base_dir:
#             candidates.append(Path(base_dir) / p)

#         upload_dir = getattr(config, "UPLOAD_DIR", None)
#         if upload_dir:
#             candidates.append(Path(upload_dir) / p)

#         project_root = Path(__file__).resolve().parents[2]
#         candidates.append(project_root / p)

#     for candidate in candidates:
#         try:
#             resolved = candidate.resolve()
#             if resolved.exists() and resolved.is_file():
#                 return str(resolved)
#         except Exception:
#             continue

#     return None


# def _upload_document(record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
#     if not patient_id:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "Cannot upload document: DrChrono patient_id is missing",
#             "already_exists": False,
#         }

#     raw_path = (
#         record.get("file_path")
#         or record.get("path")
#         or record.get("filename")
#         or record.get("local_path")
#         or record.get("document_path")
#     )

#     file_path = _resolve_file_path(raw_path)

#     if not file_path:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": f"Document file not found: {raw_path}",
#             "already_exists": False,
#         }

#     url = f"{config.DRCHRONO_API_BASE}documents"

#     data = {
#         "patient": str(patient_id),
#         "doctor": str(doctor_id) if doctor_id else "",
#         "description": (
#             record.get("description")
#             or record.get("name")
#             or record.get("name_full")
#             or Path(file_path).name
#         ),
#         "date": _normalize_date(
#             record.get("document_date")
#             or record.get("date")
#             or record.get("created_dt")
#             or record.get("effective_dt")
#         ),
#     }

#     tags = record.get("metatags") or record.get("tags")
#     if tags:
#         if isinstance(tags, str):
#             tags = [t.strip() for t in tags.replace(",", "|").split("|") if t.strip()]
#         data["metatags"] = json.dumps(tags)

#     data = _strip_empty(data)
#     mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

#     log.info("POST %s multipart_data=%s file=%s mime=%s", url, data, file_path, mime_type)

#     try:
#         with open(file_path, "rb") as f:
#             files = {
#                 "document": (Path(file_path).name, f, mime_type)
#             }
#             resp = requests.post(
#                 url,
#                 headers=_multipart_headers(token),
#                 data=data,
#                 files=files,
#                 timeout=60,
#             )

#         log.info("Document upload response: %d — %s", resp.status_code, resp.text[:800])

#         if resp.status_code in (200, 201):
#             body = resp.json()
#             return {
#                 "success": True,
#                 "status_code": resp.status_code,
#                 "drchrono_id": body.get("id"),
#                 "error": "",
#                 "already_exists": False,
#             }

#         return {
#             "success": False,
#             "status_code": resp.status_code,
#             "drchrono_id": None,
#             "error": resp.text[:1000],
#             "already_exists": False,
#         }

#     except Exception as e:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": str(e),
#             "already_exists": False,
#         }


# def _simulate_push(records: list, resource: str) -> dict:
#     if not records:
#         return {"total": 0, "successful": 0, "failed": 0}

#     total = len(records)
#     successful = round(total * random.uniform(0.90, 1.0))
#     return {"total": total, "successful": successful, "failed": total - successful}


# def _find_existing_patient(payload: dict, token: str) -> Optional[int]:
#     params = {}
#     if payload.get("first_name"):
#         params["first_name"] = payload["first_name"]
#     if payload.get("last_name"):
#         params["last_name"] = payload["last_name"]
#     if payload.get("date_of_birth"):
#         params["date_of_birth"] = payload["date_of_birth"]

#     if not params:
#         return None

#     url = f"{config.DRCHRONO_API_BASE}patients"

#     try:
#         resp = requests.get(url, params=params, headers=_json_headers(token), timeout=15)
#         log.info("Patient search GET %s params=%s status=%d", url, params, resp.status_code)

#         if resp.status_code == 200:
#             results = resp.json().get("results", [])
#             if results:
#                 return results[0].get("id")

#     except Exception as e:
#         log.warning("Patient search failed: %s", e)

#     return None


# def _live_push_record(
#     record: dict,
#     resource: str,
#     token: str,
#     doctor_id: Optional[int] = None,
#     patient_id: Optional[int] = None,
# ) -> dict:
#     key = resource.lower()
#     path = ENDPOINT_MAP.get(key)

#     if not path:
#         log.warning("No DrChrono endpoint for resource: %s — skipping", resource)
#         return {
#             "success": True,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "skipped (no endpoint)",
#             "already_exists": False,
#         }

#     is_patient = key.rstrip("s") == "patient"

#     if key in ("document", "documents", "document_reference", "document_references"):
#         return _upload_document(record, token, doctor_id=doctor_id, patient_id=patient_id)

#     if not is_patient and not patient_id:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": f"Cannot push {resource}: DrChrono patient_id is missing",
#             "already_exists": False,
#         }

#     url = f"{config.DRCHRONO_API_BASE}{path}"

#     try:
#         payload = _map_record(resource, record, doctor_id=doctor_id, patient_id=patient_id)
#     except Exception as e:
#         log.error("Mapping failed for %s: %s", resource, e)
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": f"Mapping error: {e}",
#             "already_exists": False,
#         }

#     if key in ("condition", "conditions", "problem", "problems", "problem_list") and not payload.get("description"):
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "Problem/condition description is missing. Map name_full/code.text to description.",
#             "already_exists": False,
#         }

#     if key in ("medication", "medications") and not payload.get("name"):
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "Medication name is missing. Map name_full/medicationCodeableConcept.text to name.",
#             "already_exists": False,
#         }

#     if is_patient:
#         existing_id = _find_existing_patient(payload, token)
#         if existing_id:
#             return {
#                 "success": True,
#                 "status_code": 200,
#                 "drchrono_id": existing_id,
#                 "error": "",
#                 "already_exists": True,
#                 "message": f"Patient already exists in DrChrono ID={existing_id}",
#             }

#     log.info("POST %s payload=%s", url, payload)

#     try:
#         resp = requests.post(url, json=payload, headers=_json_headers(token), timeout=20)
#         log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:800])

#         if resp.status_code in (200, 201):
#             body = resp.json()
#             return {
#                 "success": True,
#                 "status_code": resp.status_code,
#                 "drchrono_id": body.get("id"),
#                 "error": "",
#                 "already_exists": False,
#             }

#         error_detail = resp.text[:1000]
#         try:
#             err_json = resp.json()
#             messages = []
#             for field, val in err_json.items():
#                 if isinstance(val, list):
#                     messages.extend(f"{field}: {m}" for m in val)
#                 else:
#                     messages.append(f"{field}: {val}")
#             if messages:
#                 error_detail = " | ".join(messages)
#         except Exception:
#             pass

#         return {
#             "success": False,
#             "status_code": resp.status_code,
#             "drchrono_id": None,
#             "error": error_detail,
#             "already_exists": False,
#         }

#     except requests.exceptions.Timeout:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "Request timed out",
#             "already_exists": False,
#         }

#     except requests.exceptions.ConnectionError:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": "Connection error",
#             "already_exists": False,
#         }

#     except Exception as e:
#         return {
#             "success": False,
#             "status_code": 0,
#             "drchrono_id": None,
#             "error": str(e),
#             "already_exists": False,
#         }


# @router.get("/preflight")
# def push_preflight():
#     session_resources = _SESSION.get("resources", {})
#     resource_types = [k for k, v in session_resources.items() if v]
#     record_count = sum(len(v) for v in session_resources.values() if v)

#     tok = token_store.get_token()
#     token_valid = token_store.is_valid()
#     doctor_id = tok.doctor_id if tok else None
#     doctor_name = tok.doctor_name if tok else None
#     expires_in = token_store.seconds_until_expiry()

#     issues = []
#     if record_count == 0:
#         issues.append("No data in backend session. Re-upload your file.")
#     if not token_valid:
#         issues.append("No valid DrChrono token. Authenticate first.")
#     if token_valid and not doctor_id:
#         issues.append("Doctor ID missing from token.")

#     return {
#         "ready": len(issues) == 0,
#         "issues": issues,
#         "session": {
#             "loaded": record_count > 0,
#             "record_count": record_count,
#             "resource_types": resource_types,
#         },
#         "auth": {
#             "token_valid": token_valid,
#             "doctor_id": doctor_id,
#             "doctor_name": doctor_name,
#             "expires_in": expires_in,
#         },
#     }


# class PushRequest(BaseModel):
#     resources: List[str] = []
#     dry_run: bool = False
#     doctor_id: Optional[int] = None
#     patient_id: Optional[int] = None


# @router.post("/run")
# async def push_run(req: PushRequest):
#     source = _SESSION.get("resources") or _SESSION.get("mapped")

#     if not source:
#         raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")

#     target_keys = req.resources if req.resources else list(source.keys())

#     token: Optional[str] = None
#     doctor_id = req.doctor_id

#     if not req.dry_run:
#         tok_obj = token_store.get_token()

#         if not tok_obj or not tok_obj.access_token:
#             raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")

#         token = tok_obj.access_token

#         if not doctor_id and tok_obj.doctor_id:
#             try:
#                 doctor_id = int(tok_obj.doctor_id)
#             except (TypeError, ValueError):
#                 pass

#     push_order = [
#         "patient",
#         "patients",
#         "encounter",
#         "encounters",
#         "condition",
#         "conditions",
#         "problem",
#         "problems",
#         "problem_list",
#         "medication",
#         "medications",
#         "allergy",
#         "allergies",
#         "immunization",
#         "immunizations",
#         "observation",
#         "observations",
#         "procedure",
#         "procedures",
#         "coverage",
#         "coverages",
#         "document",
#         "documents",
#         "document_reference",
#         "document_references",
#         "clinical_note",
#         "clinical_notes",
#     ]

#     ordered = [k for k in push_order if k in target_keys]
#     ordered += [k for k in target_keys if k not in ordered]

#     stats = {}
#     current_patient_id = req.patient_id

#     for key in ordered:
#         records = source.get(key, [])

#         if not records:
#             continue

#         if req.dry_run:
#             stats[key] = _simulate_push(records, key)
#             continue

#         total = successful = failed = already_exists_count = 0
#         errors = []

#         for record in records:
#             total += 1

#             result = _live_push_record(
#                 record,
#                 key,
#                 token,
#                 doctor_id=doctor_id,
#                 patient_id=current_patient_id,
#             )

#             if result.get("already_exists"):
#                 already_exists_count += 1
#                 successful += 1

#                 if key in ("patient", "patients") and result.get("drchrono_id"):
#                     current_patient_id = result["drchrono_id"]

#             elif result.get("success"):
#                 successful += 1

#                 if key in ("patient", "patients") and result.get("drchrono_id"):
#                     current_patient_id = result["drchrono_id"]

#             else:
#                 failed += 1
#                 errors.append(result.get("error", "unknown error"))

#             time.sleep(0.1)

#         stats[key] = {
#             "total": total,
#             "successful": successful,
#             "failed": failed,
#             "already_exists": already_exists_count,
#             "errors": errors[:5],
#         }

#     total_all = sum(s["total"] for s in stats.values())
#     successful_all = sum(s["successful"] for s in stats.values())
#     failed_all = sum(s["failed"] for s in stats.values())

#     return {
#         "status": "complete",
#         "dry_run": req.dry_run,
#         "total": total_all,
#         "successful": successful_all,
#         "failed": failed_all,
#         "patient_id": current_patient_id,
#         "stats": stats,
#     }




import json
import logging
import mimetypes
import os
import random
import re
import time
from pathlib import Path
from typing import Any, List, Optional

import requests
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core import config
from app.routes.upload import _SESSION
from app.services.token_store import token_store
from app.services.drchrono_proxy import drchrono_post_document
from app.services.logging_service import LoggingService, get_last_run, set_last_run
log = logging.getLogger("medisync.push")


def _endpoint_for(key: str) -> str:
    """Human-readable DrChrono endpoint for a resource key, for record logs."""
    path = ENDPOINT_MAP.get(key.lower())
    return f"/api/{path}" if path else key


def _payload_for_logging(key: str, record: dict, doctor_id, patient_id) -> Any:
    """Best-effort request payload for record-level logs. Pure/no network; never raises."""
    try:
        return _map_record(key, record, doctor_id=doctor_id, patient_id=patient_id)
    except Exception:
        return None

router = APIRouter()

ENDPOINT_MAP = {
    "patient": "patients",
    "patients": "patients",
    "encounter": "appointments",
    "encounters": "appointments",
    "appointment": "appointments",
    "appointments": "appointments",
    "condition": "problems",
    "conditions": "problems",
    "problem": "problems",
    "problems": "problems",
    "problem_list": "problems",
    "medication": "medications",
    "medications": "medications",
    "allergy": "allergies",
    "allergies": "allergies",
    "immunization": "vaccines",
    "immunizations": "vaccines",
    # Diagnostic reports are pushed as generated PDFs to /api/documents
    # (the lab API is partner-gated → 403). See _upload_diagnostic_report_as_document.
    "diagnostic_report": "documents",
    "diagnostic_reports": "documents",
    "report": "documents",
    "reports": "documents",
    "observation": "patient_lab_results",
    "observations": "patient_lab_results",
    "observation_note": "patient_lab_results",
    "observation_notes": "patient_lab_results",
    "procedure": "clinical_note_section_field_values",
    "procedures": "clinical_note_section_field_values",
    "service_request": "lab_orders",
    "service_requests": "lab_orders",
    "coverage": "insurances",
    "coverages": "insurances",
    "document": "documents",
    "documents": "documents",
    "document_reference": "documents",
    "document_references": "documents",
    "clinical_note": "clinical_note_field_values",
    "clinical_notes": "clinical_note_field_values",
}

# DrChrono accepts only Male / Female / Other (NOT "Unknown" — it 400s).
_GENDER_MAP = {
    "male": "Male", "m": "Male",
    "female": "Female", "f": "Female",
    "other": "Other", "o": "Other",
    "unknown": "Other", "u": "Other", "unk": "Other",
}

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp"}
DOCUMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
DOCUMENT_MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG",
    ".gif": b"GIF8",
    ".bmp": b"BM",
}
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024

# Tiny valid PNG used only for demo placeholder files with supported extensions.
FALLBACK_DEMO_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac`\xf8"
    b"\xcfP\x0f\x00\x03\x86\x01\x80Z4}k\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _strip_empty(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def _normalize_date(val: Any) -> str:
    """Coerce a date to DrChrono's required YYYY-MM-DD.

    Handles ISO (already correct), DD-MM-YYYY / DD/MM/YYYY (the dataset's format,
    e.g. 22-07-1988 -> 1988-07-22) and MM-DD-YYYY. Ambiguous day/month defaults to
    day-first (DD-MM)."""
    if not val:
        return ""
    s = str(val).strip()
    # Already ISO (YYYY-MM-DD or full datetime) -> keep the date part.
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    # YYYY/MM/DD
    m = re.match(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD-MM-YYYY / DD/MM/YYYY / MM-DD-YYYY
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12:        # first part can only be a day -> DD-MM-YYYY
            day, month = a, b
        elif b > 12:      # second part can only be a day -> MM-DD-YYYY
            day, month = b, a
        else:             # ambiguous -> assume day-first (dataset convention)
            day, month = a, b
        return f"{year}-{month:02d}-{day:02d}"
    return s[:10]


def _map_gender(val: Any) -> str:
    if not val:
        return ""
    # Case-insensitive lookup; unrecognised values fall back to a valid choice.
    return _GENDER_MAP.get(str(val).strip().lower(), "Other")


def _extract_name(name_field: Any):
    if not name_field:
        return "", ""

    if isinstance(name_field, str):
        parts = name_field.strip().split(" ", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    if isinstance(name_field, list) and name_field:
        n = name_field[0]
        if isinstance(n, dict):
            given = n.get("given") or []
            first = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
            last = str(n.get("family") or "")
            return first.strip(), last.strip()

    return "", ""


def _codeable_text(value: Any) -> str:
    if not value:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        if value.get("text"):
            return str(value["text"]).strip()

        coding = value.get("coding") or []
        if isinstance(coding, list) and coding:
            first = coding[0]
            if isinstance(first, dict):
                return str(first.get("display") or first.get("code") or "").strip()

    return ""


def _codeable_code(value: Any) -> str:
    if isinstance(value, dict):
        coding = value.get("coding") or []
        if isinstance(coding, list) and coding:
            first = coding[0]
            if isinstance(first, dict):
                return str(first.get("code") or "").strip()
    return ""


def _active_status(value: Any, default: str = "active") -> str:
    if isinstance(value, dict):
        value = _codeable_code(value) or _codeable_text(value)
    raw = str(value or default).strip().lower()
    if raw in ("active", "completed", "intended", "confirmed", "final"):
        return "active"
    return "inactive"


def _condition_status(record: dict) -> str:
    """DrChrono /problems status enum is lowercase: 'active' or 'resolved'.
    Verified empirically — DrChrono rejects 'Active' with
    {"status":["\\"Active\\" is not a valid choice."]}."""
    clinical = record.get("clinicalStatus")
    if isinstance(clinical, dict):
        text = _codeable_text(clinical).lower()
        if "resolved" in text or "inactive" in text:
            return "resolved"

    raw = str(
        record.get("status")
        or record.get("verificationStatus")
        or record.get("clinical_status")
        or "active"
    ).lower()
    if raw in ("resolved", "inactive", "entered-in-error", "remission"):
        return "resolved"
    return "active"


def _first_present(record: dict, *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _clean_nested(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {k: _clean_nested(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        cleaned = [_clean_nested(v) for v in value]
        return [v for v in cleaned if v not in (None, "", [], {})]
    return value


def _first_related(record: dict, *keys: str) -> dict:
    for key in keys:
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item:
                    return item
        if isinstance(value, dict) and value:
            return value
    return {}


def _human_name_parts(value: Any) -> dict:
    if isinstance(value, list):
        value = next((n for n in value if isinstance(n, dict) and n.get("use") == "official"), value[0] if value else {})
    if isinstance(value, str):
        parts = value.strip().split()
        return {
            "first_name": parts[0] if parts else "",
            "last_name": parts[-1] if len(parts) > 1 else "",
            "middle_name": " ".join(parts[1:-1]) if len(parts) > 2 else "",
        }
    if not isinstance(value, dict):
        return {}
    given = value.get("given") or []
    if not isinstance(given, list):
        given = [given]
    return {
        "first_name": str(given[0]).strip() if given else "",
        "middle_name": " ".join(str(x).strip() for x in given[1:] if str(x).strip()),
        "last_name": str(value.get("family") or "").strip(),
        "suffix": " ".join(str(x).strip() for x in (value.get("suffix") or []) if str(x).strip())
        if isinstance(value.get("suffix"), list) else str(value.get("suffix") or "").strip(),
        "nick_name": str(value.get("text") or "").strip() if value.get("use") == "nickname" else "",
    }


def _contact_points(items: Any) -> dict:
    out = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        system = str(item.get("system") or "").lower()
        use = str(item.get("use") or "").lower()
        value = item.get("value")
        if not value:
            continue
        if system == "email" and not out.get("email"):
            out["email"] = value
        elif system == "phone":
            if use == "mobile" and not out.get("cell_phone"):
                out["cell_phone"] = value
            elif use in ("work", "office") and not out.get("office_phone"):
                out["office_phone"] = value
            elif not out.get("home_phone"):
                out["home_phone"] = value
    return out


def _address_parts(value: Any, prefix: str = "") -> dict:
    if isinstance(value, list):
        value = next((a for a in value if isinstance(a, dict) and a.get("use") == "home"), value[0] if value else {})
    if isinstance(value, str):
        return {f"{prefix}address": value}
    if not isinstance(value, dict):
        return {}
    lines = value.get("line") or []
    address = " ".join(str(x) for x in lines) if isinstance(lines, list) else str(lines or "")
    return {
        f"{prefix}address": address,
        f"{prefix}city": value.get("city", ""),
        f"{prefix}state": value.get("state", ""),
        f"{prefix}zip_code": value.get("postalCode") or value.get("zip_code") or value.get("zip") or "",
    }


def _coverage_payload(coverage: dict, prefix: str, subscriber: Optional[dict] = None) -> dict:
    if not coverage:
        return {}
    payor = coverage.get("payor") or coverage.get("insurer") or []
    payor0 = payor[0] if isinstance(payor, list) and payor else payor
    company = _first_present(coverage, f"{prefix}_insurance_company", "insurance_company", "payer_name", "payor_name")
    if not company and isinstance(payor0, dict):
        company = payor0.get("display") or payor0.get("name")
    payload = {
        "insurance_company": company,
        "insurance_id_number": _first_present(coverage, f"{prefix}_insurance_id", "insurance_id_number", "subscriberId", "subscriber_id", "member_id"),
        "insurance_group_name": _first_present(coverage, f"{prefix}_group_name", "insurance_group_name", "group_name"),
        "insurance_group_number": _first_present(coverage, f"{prefix}_group_number", "insurance_group_number", "group_number", "plan_id"),
        "insurance_claim_office_number": _first_present(coverage, f"{prefix}_claim_office_number", "insurance_claim_office_number"),
        "insurance_payer_id": _first_present(coverage, f"{prefix}_payer_id", "insurance_payer_id", "payer_id", "payor_id"),
        "insurance_plan_name": _first_present(coverage, f"{prefix}_plan_name", "insurance_plan_name", "plan_name", "plan_short_name"),
        "insurance_plan_type": _first_present(coverage, f"{prefix}_plan_type", "insurance_plan_type", "plan_type", "type"),
    }

    # Subscriber block. Default to "subscriber is the patient" unless the coverage says
    # otherwise; when it is the patient, copy the patient's demographics.
    relationship = str(_first_present(
        coverage, "patient_relationship_to_subscriber", "subscriber_relationship", "relationship", default="",
    )).strip()
    is_self = _bool_value(_first_present(coverage, "is_subscriber_the_patient"))
    if is_self is None:
        is_self = relationship.lower() in ("", "self", "1", "18")
    payload["is_subscriber_the_patient"] = is_self
    if relationship:
        payload["patient_relationship_to_subscriber"] = relationship

    if is_self and subscriber:
        payload.update({
            "subscriber_first_name":      subscriber.get("first_name"),
            "subscriber_middle_name":     subscriber.get("middle_name"),
            "subscriber_last_name":       subscriber.get("last_name"),
            "subscriber_suffix":          subscriber.get("suffix"),
            "subscriber_date_of_birth":   subscriber.get("date_of_birth"),
            "subscriber_social_security": subscriber.get("social_security_number"),
            "subscriber_gender":          subscriber.get("gender"),
            "subscriber_address":         subscriber.get("address"),
            "subscriber_city":            subscriber.get("city"),
            "subscriber_state":           subscriber.get("state"),
            "subscriber_zip_code":        subscriber.get("zip_code"),
            "subscriber_country":         subscriber.get("country") or "US",
        })
    else:
        # Subscriber differs from the patient — take their demographics off the coverage.
        sub_name = _human_name_parts(coverage.get("subscriber_name"))
        payload.update({
            "subscriber_first_name":      _first_present(coverage, "subscriber_first_name", default=sub_name.get("first_name")),
            "subscriber_last_name":       _first_present(coverage, "subscriber_last_name", default=sub_name.get("last_name")),
            "subscriber_date_of_birth":   _normalize_date(_first_present(coverage, "subscriber_date_of_birth", "subscriber_dob")),
            "subscriber_gender":          _map_gender(_first_present(coverage, "subscriber_gender")),
            "subscriber_address":         _first_present(coverage, "subscriber_address"),
            "subscriber_city":            _first_present(coverage, "subscriber_city"),
            "subscriber_state":           _first_present(coverage, "subscriber_state"),
            "subscriber_zip_code":        _first_present(coverage, "subscriber_zip_code"),
            "subscriber_country":         _first_present(coverage, "subscriber_country", default="US"),
        })

    return _clean_nested(payload)


def _json_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
    }


def _multipart_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-DRC-API-Version": config.DRCHRONO_API_VERSION,
    }


_RACE_MAP = {
    "white": "white", "caucasian": "white",
    "black": "black", "african american": "black", "black or african american": "black",
    "asian": "asian",
    "american indian": "indian", "alaska native": "indian", "native american": "indian",
    "american indian or alaska native": "indian",
    "native hawaiian": "hawaiian", "pacific islander": "hawaiian",
    "native hawaiian or other pacific islander": "hawaiian",
    "other": "other", "other race": "other",
    "declined": "declined", "declined to specify": "declined",
}

# language name -> (ISO 639-2/B, ISO 639-1, description)
_LANGUAGE_MAP = {
    "english": ("eng", "en", "English"), "spanish": ("spa", "es", "Spanish"),
    "french": ("fra", "fr", "French"), "german": ("deu", "de", "German"),
    "italian": ("ita", "it", "Italian"), "portuguese": ("por", "pt", "Portuguese"),
    "chinese": ("zho", "zh", "Chinese"), "hindi": ("hin", "hi", "Hindi"),
    "arabic": ("ara", "ar", "Arabic"), "russian": ("rus", "ru", "Russian"),
    "japanese": ("jpn", "ja", "Japanese"), "korean": ("kor", "ko", "Korean"),
    "vietnamese": ("vie", "vi", "Vietnamese"),
}


def _map_race(value: Any) -> str:
    """Map a race display/value to a DrChrono race code (white/black/asian/indian/hawaiian/other/declined)."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return _RACE_MAP.get(raw, "other")


def _map_ethnicity(value: Any) -> str:
    """Map an ethnicity display/value to a DrChrono code (hispanic/not_hispanic/declined)."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "declin" in raw:
        return "declined"
    if ("hispanic" in raw or "latino" in raw) and not ("not" in raw or "non" in raw):
        return "hispanic"
    return "not_hispanic"


def _language_fields(value: Any) -> tuple[str, str, str]:
    """Return (ISO 639-2, ISO 639-1, description) for a language name or code."""
    raw = str(value or "").strip()
    if not raw:
        return ("", "", "")
    low = raw.lower()
    if low in _LANGUAGE_MAP:
        return _LANGUAGE_MAP[low]
    for code3, code1, desc in _LANGUAGE_MAP.values():
        if low in (code3, code1):
            return (code3, code1, desc)
    return (raw[:3].lower(), raw[:2].lower(), raw.title())


def _pad_zip(value: Any) -> str:
    """Restore a leading zero stripped by CSV/Excel (e.g. 2906 -> 02906)."""
    s = str(value or "").strip()
    return s.zfill(5) if s.isdigit() and len(s) < 5 else s


def _map_patient(record: dict, doctor_id: Optional[int] = None) -> dict:
    name_raw = record.get("name")

    if isinstance(name_raw, list):
        name_parts = _human_name_parts(name_raw)
        first = name_parts.get("first_name") or ""
        last = name_parts.get("last_name") or ""
    else:
        first = record.get("first_name") or record.get("given") or ""
        last = record.get("last_name") or record.get("family") or ""
        name_parts = _human_name_parts(name_raw)
        if not first and not last:
            first, last = _extract_name(name_raw)

    addr_raw = record.get("address")
    address = city = state = zip_code = ""

    if isinstance(addr_raw, list) and addr_raw:
        a = addr_raw[0]
        if isinstance(a, dict):
            lines = a.get("line") or []
            address = " ".join(lines) if isinstance(lines, list) else str(lines)
            city = a.get("city", "")
            state = a.get("state", "")
            zip_code = a.get("postalCode", "")
    elif isinstance(addr_raw, str):
        address = addr_raw

    phones = _contact_points(record.get("telecom"))
    phone = email = ""
    for t in record.get("telecom") or []:
        if isinstance(t, dict):
            system = t.get("system", "")
            value = t.get("value", "")
            if system == "phone" and not phone:
                phone = value
            elif system == "email" and not email:
                email = value

    lang3, lang1, lang_desc = _language_fields(
        _first_present(record, "preferred_language", "language", "communication_language")
    )

    payload = {
        "first_name": first or "Unknown",
        "middle_name": record.get("middle_name") or name_parts.get("middle_name"),
        "last_name": last or "Patient",
        "nick_name": record.get("nick_name") or record.get("nickname") or name_parts.get("nick_name"),
        "suffix": _first_present(record, "suffix", "name_suffix", default=name_parts.get("suffix")),
        "date_of_birth": _normalize_date(
            record.get("birthDate")
            or record.get("date_of_birth")
            or record.get("birth_date")
            or record.get("dob")
        ),
        "gender": _map_gender(
            record.get("gender")
            or record.get("sex")
            or record.get("gender_administrative")
            or record.get("administrative_gender")
        ) or "Other",
        "social_security_number": _first_present(record, "social_security_number", "ssn"),
        "race": _map_race(_first_present(record, "race", "race_display", "race_code")),
        "ethnicity": _map_ethnicity(_first_present(record, "ethnicity", "ethnicity_display", "ethnicity_code")),
        "pronouns": _first_present(record, "pronouns"),
        "preferred_language": lang3,
        "preferred_language_description": _first_present(record, "preferred_language_description", "language_description", default=lang_desc),
        "preferred_language_code": _first_present(record, "preferred_language_code", "language_code", default=lang1),
        "gender_identity_description": _first_present(record, "gender_identity_description", "gender_identity"),
        "gender_identity_code": _first_present(record, "gender_identity_code"),
        "patient_payment_profile": _first_present(record, "patient_payment_profile", "payment_profile"),
        "patient_status": _first_present(record, "patient_status", "status"),
        "email": email or phones.get("email") or record.get("email", ""),
        "home_phone": phone or phones.get("home_phone") or record.get("phone") or record.get("home_phone", ""),
        "cell_phone": phones.get("cell_phone") or record.get("cell_phone") or record.get("mobile_phone"),
        "office_phone": phones.get("office_phone") or record.get("office_phone") or record.get("work_phone"),
        "address": address or _first_present(record, "address", "address_street", "street"),
        "city": city or _first_present(record, "city", "address_city"),
        "state": state or _first_present(record, "state", "address_state_code", "address_state"),
        "zip_code": _pad_zip(zip_code or _first_present(record, "zip_code", "zip", "address_postal_code")),
        "country": _first_present(record, "country", "address_country"),
        "emergency_contact_name": _first_present(record, "emergency_contact_name"),
        "emergency_contact_phone": _first_present(record, "emergency_contact_phone"),
        "emergency_contact_relation": _first_present(record, "emergency_contact_relation", "emergency_contact_relationship"),
        "employer": _first_present(record, "employer", "employer_name"),
        "employer_address": _first_present(record, "employer_address"),
        "employer_city": _first_present(record, "employer_city"),
        "employer_state": _first_present(record, "employer_state"),
        "employer_zip_code": _first_present(record, "employer_zip_code", "employer_zip"),
        "timezone": _first_present(record, "timezone"),
        "referring_source": _first_present(record, "referring_source"),
        "copay": _first_present(record, "copay"),
        "responsible_party_name": _first_present(record, "responsible_party_name"),
        "responsible_party_relation": _first_present(record, "responsible_party_relation", "responsible_party_relationship"),
        "responsible_party_phone": _first_present(record, "responsible_party_phone"),
        "responsible_party_email": _first_present(record, "responsible_party_email"),
    }

    disable_sms = _bool_value(_first_present(record, "disable_sms_messages", "disable_sms"))
    if disable_sms is not None:
        payload["disable_sms_messages"] = disable_sms

    patient_flags = record.get("patient_flags")
    if isinstance(patient_flags, list) and patient_flags:
        payload["patient_flags"] = patient_flags

    contact = _first_related(record, "contact", "contacts", "emergency_contact")
    if contact:
        contact_name = _human_name_parts(contact.get("name"))
        if not payload.get("emergency_contact_name"):
            payload["emergency_contact_name"] = " ".join(
                x for x in (contact_name.get("first_name"), contact_name.get("middle_name"), contact_name.get("last_name")) if x
            )
        telecom = _contact_points(contact.get("telecom"))
        if not payload.get("emergency_contact_phone"):
            payload["emergency_contact_phone"] = telecom.get("home_phone") or telecom.get("cell_phone")
        relation = contact.get("relationship")
        if isinstance(relation, list):
            relation = relation[0] if relation else {}
        if not payload.get("emergency_contact_relation"):
            payload["emergency_contact_relation"] = _value_to_text(relation)

    responsible = _first_related(record, "responsible_party", "guarantor", "related_person", "RelatedPerson")
    if responsible:
        resp_name = _human_name_parts(responsible.get("name"))
        if not payload.get("responsible_party_name"):
            payload["responsible_party_name"] = " ".join(
                x for x in (resp_name.get("first_name"), resp_name.get("middle_name"), resp_name.get("last_name")) if x
            )
        resp_telecom = _contact_points(responsible.get("telecom"))
        if not payload.get("responsible_party_phone"):
            payload["responsible_party_phone"] = resp_telecom.get("home_phone") or resp_telecom.get("cell_phone")
        if not payload.get("responsible_party_email"):
            payload["responsible_party_email"] = resp_telecom.get("email")
        if not payload.get("responsible_party_relation"):
            payload["responsible_party_relation"] = _value_to_text(_first_present(responsible, "relationship", "relation"))

    employer = _first_related(record, "employer_resource", "employer_organization", "Organization")
    if employer:
        if not payload.get("employer"):
            payload["employer"] = employer.get("name")
        payload.update({k: v for k, v in _address_parts(employer.get("address"), "employer_").items() if v and not payload.get(k)})

    referring = _first_related(record, "referring_doctor", "referring_provider", "practitioner", "Practitioner")
    if referring:
        ref_name = _human_name_parts(referring.get("name"))
        ref_telecom = _contact_points(referring.get("telecom"))
        ref_payload = {
            "first_name": _first_present(referring, "first_name", default=ref_name.get("first_name")),
            "middle_name": _first_present(referring, "middle_name", default=ref_name.get("middle_name")),
            "last_name": _first_present(referring, "last_name", default=ref_name.get("last_name")),
            "suffix": _first_present(referring, "suffix", default=ref_name.get("suffix")),
            "npi": _first_present(referring, "npi"),
            "provider_qualifier": _first_present(referring, "provider_qualifier"),
            "provider_number": _first_present(referring, "provider_number"),
            "address": _first_present(referring, "address"),
            "email": _first_present(referring, "email", default=ref_telecom.get("email")),
            "phone": _first_present(referring, "phone", default=ref_telecom.get("home_phone") or ref_telecom.get("cell_phone")),
            "fax": _first_present(referring, "fax"),
            "specialty": _value_to_text(_first_present(referring, "specialty", "qualification")),
        }
        if isinstance(ref_payload.get("address"), list) or isinstance(ref_payload.get("address"), dict):
            ref_payload["address"] = _address_parts(ref_payload["address"]).get("address")
        ref_payload = _clean_nested(ref_payload)
        if ref_payload:
            payload["referring_doctor"] = ref_payload

    primary_coverage = _first_related(record, "primary_insurance", "primary_coverage")
    secondary_coverage = _first_related(record, "secondary_insurance", "secondary_coverage")
    coverages = record.get("coverages") or record.get("coverage") or record.get("Coverage") or []
    coverages = coverages if isinstance(coverages, list) else [coverages]
    for coverage in coverages:
        if not isinstance(coverage, dict):
            continue
        rank = str(_first_present(coverage, "coverage_rank", "insurance_type", "rank", "order", default="")).lower()
        if not primary_coverage and rank in ("", "primary", "1"):
            primary_coverage = coverage
        elif not secondary_coverage and rank in ("secondary", "2"):
            secondary_coverage = coverage
    # The subscriber defaults to the patient, so the insurance subscriber_* fields
    # mirror the demographics built above.
    subscriber = {
        "first_name": payload.get("first_name"),
        "middle_name": payload.get("middle_name"),
        "last_name": payload.get("last_name"),
        "suffix": payload.get("suffix"),
        "date_of_birth": payload.get("date_of_birth"),
        "social_security_number": payload.get("social_security_number"),
        "gender": payload.get("gender"),
        "address": payload.get("address"),
        "city": payload.get("city"),
        "state": payload.get("state"),
        "zip_code": payload.get("zip_code"),
        "country": _first_present(record, "address_country", "country", default="US"),
    }
    primary_payload = _coverage_payload(primary_coverage, "primary", subscriber)
    secondary_payload = _coverage_payload(secondary_coverage, "secondary", subscriber)
    if primary_payload:
        payload["primary_insurance"] = primary_payload
    if secondary_payload:
        payload["secondary_insurance"] = secondary_payload

    if doctor_id:
        payload["doctor"] = int(doctor_id)

    return _clean_nested(payload)


def _reference_id(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("reference") or value.get("id") or value.get("value")
    if isinstance(value, str) and "/" in value:
        return value.rsplit("/", 1)[-1]
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _valid_rxnorm(value: Any) -> str:
    code = str(value or "").strip()
    return code if re.match(r"^\d{1,12}$", code) else ""


def _bool_value(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value in (None, "", [], {}):
        return None
    raw = str(value).strip().lower()
    if raw in ("true", "t", "yes", "y", "1"):
        return True
    if raw in ("false", "f", "no", "n", "0"):
        return False
    return None


def _first_dosage(record: dict) -> dict:
    dosage = record.get("dosageInstruction") or record.get("dosage") or []
    if isinstance(dosage, list) and dosage and isinstance(dosage[0], dict):
        return dosage[0]
    if isinstance(dosage, dict):
        return dosage
    return {}


def _dose_quantity(dosage: dict) -> tuple[str, str]:
    dose_and_rate = dosage.get("doseAndRate") or []
    if isinstance(dose_and_rate, list) and dose_and_rate:
        dose = dose_and_rate[0].get("doseQuantity") if isinstance(dose_and_rate[0], dict) else None
        if isinstance(dose, dict):
            return (str(dose.get("value") or "").strip(), str(dose.get("unit") or dose.get("code") or "").strip())
    dose_quantity = dosage.get("doseQuantity")
    if isinstance(dose_quantity, dict):
        return (
            str(dose_quantity.get("value") or "").strip(),
            str(dose_quantity.get("unit") or dose_quantity.get("code") or "").strip(),
        )
    return ("", "")


def _dosage_frequency(dosage: dict) -> str:
    if dosage.get("text"):
        return str(dosage["text"]).strip()
    timing = dosage.get("timing") or {}
    repeat = timing.get("repeat") if isinstance(timing, dict) else {}
    if isinstance(repeat, dict):
        frequency = repeat.get("frequency")
        period = repeat.get("period")
        period_unit = repeat.get("periodUnit")
        if frequency and period and period_unit:
            return f"{frequency} per {period} {period_unit}".strip()
    code = timing.get("code") if isinstance(timing, dict) else {}
    return _codeable_text(code)


def _medication_name(record: dict) -> str:
    med = record.get("medicationCodeableConcept") or record.get("medication")
    if isinstance(med, dict):
        concept = med.get("concept") if isinstance(med.get("concept"), dict) else med
        text = _codeable_text(concept)
        if text:
            return text
    if isinstance(med, str):
        return med.strip()
    nested_med = record.get("medication_resource") or record.get("Medication")
    if isinstance(nested_med, dict):
        text = _codeable_text(nested_med.get("code"))
        if text:
            return text
    return str(_first_present(record, "name", "name_full", "display", "medication_name", "drug_name", "description")).strip()


def _medication_rxnorm(record: dict) -> str:
    for value in (record.get("rxnorm"), record.get("rxnorm_code"), record.get("code")):
        code = _valid_rxnorm(value)
        if code:
            return code
    for med in (record.get("medicationCodeableConcept"), record.get("medication"), record.get("medication_resource"), record.get("Medication")):
        concept = med.get("concept") if isinstance(med, dict) and isinstance(med.get("concept"), dict) else med
        if not isinstance(concept, dict):
            continue
        for coding in concept.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            system = str(coding.get("system") or "").lower()
            if "rxnorm" in system:
                code = _valid_rxnorm(coding.get("code"))
                if code:
                    return code
    return ""


def _medication_ndc(record: dict) -> str:
    """Extract an NDC (National Drug Code) from flat fields or a FHIR coding.

    NDC in FHIR is carried on medicationCodeableConcept.coding with
    system 'http://hl7.org/fhir/sid/ndc'."""
    for value in (record.get("ndc"), record.get("ndc_code"), record.get("national_drug_code")):
        code = str(value or "").strip()
        if code:
            return code
    for med in (record.get("medicationCodeableConcept"), record.get("medication"), record.get("medication_resource"), record.get("Medication")):
        concept = med.get("concept") if isinstance(med, dict) and isinstance(med.get("concept"), dict) else med
        if not isinstance(concept, dict):
            continue
        for coding in concept.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            system = str(coding.get("system") or "").lower()
            if "ndc" in system or "/sid/ndc" in system:
                code = str(coding.get("code") or "").strip()
                if code:
                    return code
    return ""


def _medication_appointment(record: dict) -> str:
    direct = _first_present(record, "appointment", "appointment_id", "drchrono_appointment_id")
    direct_id = _reference_id(direct)
    if direct_id:
        return direct_id
    for key in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn", "source_appointment_id"):
        source_id = str(record.get(key) or "").strip()
        if source_id and source_id in _APPT_ID_MAP:
            return str(_APPT_ID_MAP[source_id])
    encounter = record.get("encounter") or record.get("context")
    encounter_id = _reference_id(encounter)
    if encounter_id and encounter_id in _APPT_ID_MAP:
        return str(_APPT_ID_MAP[encounter_id])
    return ""


def _med_value(record: dict, *keys: str) -> str:
    value = _first_present(record, *keys)
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            value = first.get("text") or _codeable_text(first)
        else:
            value = first
    elif isinstance(value, dict):
        value = value.get("text") or _codeable_text(value)
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _med_order_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "order": "Ordered",
        "ordered": "Ordered",
        "active": "Ordered",
        "draft": "Draft",
        "on-hold": "On Hold",
        "stopped": "Stopped",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
    }
    return mapping.get(raw, str(value).strip() if value not in (None, "") else "")


def _med_order_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "outpatient": "Prescription",
        "community": "Prescription",
        "prescription": "Prescription",
        "order": "Prescription",
        "medicationrequest": "Prescription",
    }
    return mapping.get(raw, str(value).strip() if value not in (None, "") else "")


def _number_value(value: Any) -> Any:
    if value in (None, "", [], {}):
        return ""
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return ""
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def _med_sentence(value: str) -> str:
    return str(value or "").strip().rstrip(". ")


def _compose_med_notes(record: dict, indication: str, signature_note: str, pharmacy_note: str) -> str:
    explicit = _med_value(record, "notes", "note")
    if explicit:
        return explicit
    patient_instruction = _med_value(record, "dosagePatientInstruction", "dosagepatientInstruction", "patient_instructions", "patient_instruction", "patientInstruction")
    additional = _med_value(record, "dosageInstructionText", "additional_instructions", "additional_instruction", "additionalInstruction")
    parts = []
    if indication:
        parts.append(f"Reason: {_med_sentence(indication)}.")
    if patient_instruction or signature_note:
        parts.append(f"Patient Instructions: {_med_sentence(patient_instruction or signature_note)}.")
    if additional or pharmacy_note:
        parts.append(f"Additional Instructions: {_med_sentence(additional or pharmacy_note)}.")
    return " ".join(parts)


def _map_medication(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    dosage = _first_dosage(record)
    dose_qty, dose_units = _dose_quantity(dosage)
    med_name = (
        _medication_name(record)
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "name": med_name,
        "status": _active_status(record.get("status"), default="active"),
    }

    appointment = _medication_appointment(record)
    if appointment:
        try:
            payload["appointment"] = int(appointment)
        except (TypeError, ValueError):
            payload["appointment"] = appointment

    rxnorm = _medication_rxnorm(record)
    if rxnorm:
        payload["rxnorm"] = rxnorm

    ndc = _medication_ndc(record)
    if ndc:
        payload["ndc"] = ndc

    date_prescribed = _first_present(record, "date_prescribed", "start_dt", "authoredOn", "authored_on", "ordered_at", "date")
    if date_prescribed:
        payload["date_prescribed"] = _normalize_date(date_prescribed)

    start_date = _first_present(record, "date_started_taking", "start_dt", "start_date", "effectiveDateTime")
    effective_period = record.get("effectivePeriod") or {}
    if not start_date and isinstance(effective_period, dict):
        start_date = effective_period.get("start")
    if start_date:
        payload["date_started_taking"] = _normalize_date(start_date)

    for target, keys in (
        ("order_status", ("order_status", "filled_status", "intent")),
        ("order_type", ("order_type", "category")),
        ("route", ("route",)),
        ("frequency", ("frequencyText", "frequency_name_full", "sig")),
        ("indication", ("indication", "reason", "reason_text", "reason_name_full", "reason_full_name", "reasonCode")),
        ("number_refills", ("number_refills", "frequency", "refills", "numberOfRepeatsAllowed")),
        ("dispense_quantity", ("dispense_quantity", "quantity")),
        ("notes", ("notes", "note")),
        ("signature_note", ("signature_note", "signature_instructions", "sig_note")),
        ("pharmacy_note", ("pharmacy_note", "dosageInstructionText", "pharmacy_instructions", "dispense_note", "additional_instructions", "additional_instruction", "additionalInstruction")),
    ):
        value = _first_present(record, *keys)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            value = value[0].get("text") or _codeable_text(value[0])
        elif isinstance(value, dict):
            value = value.get("text") or _codeable_text(value)
        if value not in (None, "", [], {}):
            payload[target] = str(value).strip()

    route = _first_present(dosage, "route")
    if route:
        payload["route"] = _codeable_text(route) if isinstance(route, dict) else str(route).strip()

    frequency = _dosage_frequency(dosage)
    if frequency:
        payload["frequency"] = frequency

    if not payload.get("dosage_quantity"):
        payload["dosage_quantity"] = _first_present(record, "dosage_quantity", "dose_quantity", default=dose_qty)
    if not payload.get("dosage_units"):
        payload["dosage_units"] = _first_present(record, "dosage_units", "dosage_unit", "dose_unit", "unit", default=dose_units)

    dispense = record.get("dispenseRequest") or {}
    if isinstance(dispense, dict):
        if not payload.get("number_refills") and dispense.get("numberOfRepeatsAllowed") not in (None, ""):
            payload["number_refills"] = _number_value(dispense["numberOfRepeatsAllowed"])
        quantity = dispense.get("quantity")
        if not payload.get("dispense_quantity"):
            if isinstance(quantity, dict):
                payload["dispense_quantity"] = _number_value(quantity.get("value"))
            elif quantity not in (None, ""):
                payload["dispense_quantity"] = _number_value(quantity)

    for field, keys in (("prn", ("prn", "as_needed", "asNeededBoolean")), ("daw", ("daw", "dispense_as_written"))):
        value = _first_present(record, *keys)
        if value in (None, "", [], {}) and field == "prn":
            value = dosage.get("asNeededBoolean")
        bool_value = _bool_value(value)
        if bool_value is not None:
            payload[field] = bool_value

    substitution = record.get("substitution") or {}
    if isinstance(substitution, dict) and "daw" not in payload:
        allowed = _bool_value(substitution.get("allowedBoolean"))
        if allowed is not None:
            payload["daw"] = not allowed

    if payload.get("order_status"):
        payload["order_status"] = _med_order_status(payload["order_status"])
    else:
        payload["order_status"] = "Ordered"
    if payload.get("order_type"):
        payload["order_type"] = _med_order_type(payload["order_type"])
    else:
        payload["order_type"] = "Prescription"

    for numeric_field in ("number_refills", "dispense_quantity"):
        if payload.get(numeric_field) not in (None, "", [], {}):
            normalized = _number_value(payload[numeric_field])
            if normalized != "":
                payload[numeric_field] = normalized

    if "prn" not in payload:
        payload["prn"] = False
    if "daw" not in payload:
        payload["daw"] = False

    signature_note = str(payload.get("signature_note") or "").strip()
    pharmacy_note = str(payload.get("pharmacy_note") or "").strip()
    indication = str(payload.get("indication") or "").strip()
    composed_notes = _compose_med_notes(record, indication, signature_note, pharmacy_note)
    if composed_notes:
        payload["notes"] = composed_notes

    return _strip_empty(payload)


def _problem_codes(record: dict) -> tuple[str, Any, str]:
    """Return (icd_code, icd_version, snomed_ct_code) from flat or coded problem fields.

    The source carries the code in `code` and the system in `code_vocab`
    (e.g. 'ICD-10-CM' -> icd_code + icd_version 10; 'SNOMED-CT' -> snomed_ct_code)."""
    raw_code = record.get("code")
    code_str = raw_code if isinstance(raw_code, str) else _codeable_code(raw_code)
    code_str = str(code_str or "").strip()
    vocab = str(record.get("code_vocab") or record.get("code_system") or "").upper()

    icd_code = str(_first_present(record, "icd_code", "code_value", "icd10_code", "icd") or "").strip()
    snomed = str(_first_present(record, "snomed_ct_code", "snomed_code", "snomed") or "").strip()

    if code_str:
        if "SNOMED" in vocab:
            snomed = snomed or code_str
        elif "ICD" in vocab or not vocab:
            icd_code = icd_code or code_str

    icd_version: Any = ""
    if "ICD-10" in vocab or "ICD10" in vocab:
        icd_version = 10
    elif "ICD-9" in vocab or "ICD9" in vocab:
        icd_version = 9
    elif icd_code:
        explicit_ver = _first_present(record, "icd_version", "icd_code_version")
        m = re.search(r"\d+", str(explicit_ver)) if explicit_ver else None
        if m:
            icd_version = int(m.group())

    return icd_code, icd_version, snomed


def _map_condition(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """
    Map to DrChrono /problems.
    Verified field names (from live DrChrono payloads):
      Required: patient, doctor, description
      Optional: name, category, icd_code, icd_version, snomed_ct_code, date_onset,
                date_diagnosis, status ('active' / 'resolved'), verification_status,
                problem_type, notes, appointment
    """
    name = (
        record.get("name")
        or record.get("name_full")
        or _codeable_text(record.get("code"))
        or record.get("condition_name")
        or ""
    )
    description = (
        record.get("description")
        or record.get("name_rx")
        or record.get("name_short")
        or name
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "name": name,
        "description": description,
        "status": _condition_status(record),
        "category": _first_present(record, "category", "problem_category", default="problem-list-item"),
    }

    icd_code, icd_version, snomed = _problem_codes(record)
    if icd_code:
        payload["icd_code"] = icd_code
    if icd_version != "":
        payload["icd_version"] = icd_version
    if snomed:
        payload["snomed_ct_code"] = snomed

    onset = _first_present(record, "date_onset", "onsetDateTime", "start_dt", "onset_date")
    if onset:
        payload["date_onset"] = _normalize_date(onset)

    diagnosis = _first_present(record, "date_diagnosis", "diagnosis_date", "recorded_dt", "recordedDate")
    if diagnosis:
        payload["date_diagnosis"] = _normalize_date(diagnosis)

    # NOTE: allergies use 'verification_status' (underscore); we use the same here.
    vs_raw = _first_present(record, "verification_status", "verificationStatus", default="confirmed")
    if isinstance(vs_raw, dict):
        vs_raw = _codeable_text(vs_raw) or "confirmed"
    payload["verification_status"] = str(vs_raw).strip().lower() or "confirmed"

    problem_type = _first_present(record, "problem_type", "problemType")
    if problem_type:
        payload["problem_type"] = str(problem_type).strip()

    # Notes: prefer an explicit note; otherwise surface the full condition name
    # (name_full carries detail the shorter 'description' drops, e.g. "Concentric ...").
    notes = _first_present(record, "notes", "note", "clinical_note", "plan", "instructions")
    if not notes:
        notes = _first_present(record, "name_full", "name_rx", "name_short")
    if notes:
        payload["notes"] = str(notes).strip()

    # Tag to the DrChrono appointment created earlier in this run (via encounter_id).
    appointment = _medication_appointment(record)
    if appointment:
        try:
            payload["appointment"] = int(appointment)
        except (TypeError, ValueError):
            payload["appointment"] = appointment

    return _strip_empty(payload)


def _normalize_datetime(val: Any) -> str:
    """Ensure ISO-8601 datetime for DrChrono scheduled_time: YYYY-MM-DDTHH:MM:SS."""
    if not val:
        return ""
    s = str(val).strip()
    # Already has time component
    if "T" in s:
        # Truncate timezone/microseconds: keep YYYY-MM-DDTHH:MM:SS
        return s[:19]
    # Date only — append midnight
    if len(s) >= 10:
        return s[:10] + "T09:00:00"
    return s


# DrChrono appointment custom-field id -> source columns (from appointment.csv).
# Ids verified against the live DrChrono custom-field form (Reason Short Name,
# Description, Comment, Service Type, Specialty, Appointment Type, Practitioner Name,
# Reason Code, Reason Code Vocabulary).
_APPOINTMENT_CUSTOM_FIELD_MAP = (
    (11463, ("reason_name_short", "reason_short_name", "reason_short")),
    (11465, ("description",)),
    (11466, ("comment", "clinical_notes", "clinical_note", "appointment_notes", "notes")),
    (11472, ("service_type", "service_category", "class_display", "type")),
    (11473, ("specialty", "provider_specialty", "practitioner_specialty")),
    (11474, ("appointment_type", "encounter_type", "visit_type", "care_setting", "setting", "class_display", "class")),
    (11475, ("practitioner_name", "provider_name", "practitioner_display", "doctor_name", "performer_name", "name")),
    (11488, ("reason_code", "reason_code_value")),
    (11489, ("reason_code_vocab", "reason_code_vocabulary", "reason_code_system")),
)


def _extract_icd10_codes(record: dict) -> list[str]:
    """Collect likely ICD-10 codes from flat CSV fields or FHIR-style codings."""
    raw_values = [
        _first_present(record, "primary_diagnosis_code", "diagnosis_code", "icd10_code", "icd_code", "icd"),
        record.get("icd10_codes"),
        record.get("diagnosis_codes"),
        record.get("condition_codes"),
    ]
    code_obj = record.get("code")
    if isinstance(code_obj, dict):
        for coding in code_obj.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            system = str(coding.get("system") or coding.get("code_vocab") or "").lower()
            code = coding.get("code")
            if code and ("icd-10" in system or "icd10" in system):
                raw_values.append(code)
    for related_key in ("condition", "conditions", "diagnosis", "diagnoses"):
        related = record.get(related_key)
        items = related if isinstance(related, list) else [related]
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_values.extend([
                _first_present(item, "primary_diagnosis_code", "diagnosis_code", "icd10_code", "icd_code", "icd"),
                item.get("icd10_codes"),
            ])
            item_code = item.get("code")
            if isinstance(item_code, dict):
                for coding in item_code.get("coding") or []:
                    if not isinstance(coding, dict):
                        continue
                    system = str(coding.get("system") or "").lower()
                    code = coding.get("code")
                    if code and ("icd-10" in system or "icd10" in system):
                        raw_values.append(code)

    codes: list[str] = []
    for raw in raw_values:
        values = raw if isinstance(raw, list) else str(raw or "").replace("|", ",").split(",")
        for value in values:
            code = str(value).strip()
            if code and re.match(r"^[A-TV-Z][0-9][0-9A-Z](?:\.?[0-9A-Z]{0,4})$", code, re.I):
                normalized = code.upper()
                if normalized not in codes:
                    codes.append(normalized)
    return codes


def _value_to_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        text = _codeable_text(value)
        if text:
            return text
        if value.get("display"):
            return str(value["display"]).strip()
        if value.get("given") or value.get("family"):
            given = value.get("given") or []
            given_text = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
            return f"{given_text} {value.get('family', '')}".strip()
        name = value.get("name")
        if isinstance(name, list) and name:
            first = name[0]
            if isinstance(first, dict):
                given = first.get("given") or []
                given_text = " ".join(str(x) for x in given) if isinstance(given, list) else str(given or "")
                return f"{given_text} {first.get('family', '')}".strip()
        if value.get("text"):
            return str(value["text"]).strip()
    if isinstance(value, list):
        for item in value:
            text = _value_to_text(item)
            if text:
                return text
        return ""
    return str(value).strip()


def _custom_field_value(record: dict, keys: tuple[str, ...]) -> Any:
    value = _first_present(record, *keys)
    if value:
        return _value_to_text(value)
    for related_key in ("appointment", "encounter", "condition", "conditions", "practitioner", "provider"):
        related = record.get(related_key)
        items = related if isinstance(related, list) else [related]
        for item in items:
            if isinstance(item, dict):
                value = _first_present(item, *keys)
                text = _value_to_text(value)
                if text:
                    return text
    return ""


def _appointment_custom_fields(record: dict) -> list[dict[str, Any]]:
    fields = []
    for field_type, keys in _APPOINTMENT_CUSTOM_FIELD_MAP:
        value = _custom_field_value(record, keys)
        if value not in (None, "", [], {}):
            fields.append({"field_type": field_type, "field_value": str(value).strip()})
    return fields


def _duration_minutes(value: Any, default: int = 30) -> int:
    if value in (None, "", [], {}):
        return default
    if isinstance(value, (int, float)):
        return max(int(value), 1)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return default
    try:
        return max(int(float(match.group(0))), 1)
    except (TypeError, ValueError):
        return default


def _duration_from_period(record: dict, default: int = 30) -> int:
    start = _first_present(record, "start_dt", "start", "scheduled_time", "date")
    end = _first_present(record, "end_dt", "end")
    if not start or not end:
        return default
    try:
        from datetime import datetime
        s = str(start).strip().rstrip("Z")[:19]
        e = str(end).strip().rstrip("Z")[:19]
        delta = datetime.fromisoformat(e) - datetime.fromisoformat(s)
        minutes = int(delta.total_seconds() // 60)
        return max(minutes, 1) if minutes > 0 else default
    except Exception:
        return default

def _map_encounter(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """
    Map to DrChrono /appointments.
    Required: patient, doctor, scheduled_time (ISO-8601), duration (minutes)
    Note: 'office' must be a DrChrono office/location ID — we omit it and let DrChrono use
          the doctor's default office rather than incorrectly setting it to doctor_id.
    """
    # DrChrono appointment "status" accepts a fixed enum — "Scheduled" is NOT one of
    # them (causes 400). Valid choices include Confirmed / Not Confirmed / Arrived /
    # Complete / Cancelled / In Session. Default unknown/blank to "Confirmed".
    status_raw = str(_first_present(record, "status", default="")).lower()
    if status_raw in ("finished", "completed", "complete", "fulfilled", "arrived"):
        status = "Complete"
    elif status_raw in ("cancelled", "canceled", "noshow", "no-show", "no_show"):
        status = "Cancelled"
    elif status_raw in ("in_session", "in session"):
        status = "In Session"
    elif status_raw in ("pending", "proposed", "not confirmed", "not_confirmed"):
        status = "Not Confirmed"
    else:  # booked / scheduled / blank / anything else
        status = "Confirmed"

    raw_time = _first_present(
        record,
        "scheduled_time", "start_dt", "start", "date",
        "appointment_date", "encounter_date", "visit_date",
    )
    scheduled_time = _normalize_datetime(raw_time)

    duration_value = _first_present(record, "duration_in_mins", "duration", "duration_minutes", "minutesDuration", "length_minutes")
    duration = _duration_minutes(duration_value, default=_duration_from_period(record))

    # DrChrono caps "reason" at 100 chars — anything longer 400s. Truncate safely.
    reason = _first_present(record, "reason_name_full", "reason_full_name", "reason", "chief_complaint", "service_type", "appointment_type", "encounter_type", "class_display", "description")
    if reason and len(str(reason)) > 100:
        reason = str(reason)[:97] + "..."

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "scheduled_time": scheduled_time,
        "duration": duration,
        "status": status,
        "reason": reason,
        "allow_overlapping": True,
    }

    notes = _first_present(record, "notes", "appointment_notes", "clinical_notes", "comment")
    if notes:
        payload["notes"] = str(notes)

    payment_profile = _first_present(record, "payment_profile")
    if payment_profile:
        payload["payment_profile"] = str(payment_profile)

    icd10_codes = _extract_icd10_codes(record)
    if icd10_codes:
        payload["icd10_codes"] = icd10_codes

    custom_fields = _appointment_custom_fields(record)
    if custom_fields:
        payload["custom_fields"] = custom_fields

    # Only set office if explicitly provided as an integer office ID (not doctor_id).
    # If absent, _live_push_record fills the doctor's real office from /api/offices
    # (DrChrono requires both 'office' and 'exam_room' on appointments).
    office_id = _first_present(record, "office", "office_id", "location_id")
    if office_id and str(office_id).isdigit():
        payload["office"] = int(office_id)

    # exam_room is a 1-based index within the office; default to 1 when not supplied.
    exam_room = _first_present(record, "exam_room", "room", default=1)
    try:
        payload["exam_room"] = int(exam_room)
    except (ValueError, TypeError):
        payload["exam_room"] = 1

    return _strip_empty(payload)


def _allergy_criticality(value: Any) -> str:
    """Map a FHIR allergy criticality to its display ('low' -> 'Low Risk')."""
    raw = _value_to_text(value).strip()
    if not raw or raw.lower() in ("uncoded", "unknown"):
        return ""
    return {
        "low": "Low Risk", "high": "High Risk",
        "unable-to-assess": "Unable to Assess", "unable to assess": "Unable to Assess",
    }.get(raw.lower(), raw)


def _code_system_display(value: Any) -> str:
    """Map a code-system token to a readable label ('SNOMED-CT' -> 'SNOMED CT')."""
    raw = str(value or "").strip()
    if not raw or raw.lower() == "uncoded":
        return ""
    if raw == "http://snomed.info/sct":
        return "SNOMED CT"
    if raw == "http://www.nlm.nih.gov/research/umls/rxnorm":
        return "RxNorm"
    key = re.sub(r"[\s\-_]", "", raw).upper()
    return {
        "SNOMEDCT": "SNOMED CT", "SNOMED": "SNOMED CT", "RXNORM": "RxNorm",
        "ICD10CM": "ICD-10-CM", "ICD10": "ICD-10", "ICD9CM": "ICD-9-CM", "LOINC": "LOINC",
    }.get(key, raw)


def _codeable_system(value: Any) -> str:
    if isinstance(value, dict):
        coding = value.get("coding") or []
        if isinstance(coding, list) and coding:
            first = coding[0]
            if isinstance(first, dict):
                return str(first.get("system") or "").strip()
    return ""


def _compose_allergy_notes(record: dict, description: str, reaction: Any) -> str:
    """Build the structured allergy note block DrChrono accepts:

        Allergy Note: <narrative>
        Severity: <severity>
        Criticality: <criticality>
        Category: <category>
        Type: <type>
        Code: <code>
        Code System: <code system>
        Source: RhythmX AI Import
    """
    lines: list[str] = []

    explicit = str(_first_present(record, "allergy_note", "notes", "note") or "").strip()
    if explicit:
        narrative = explicit
    elif description and reaction:
        narrative = (f"Patient reports allergic reaction to {description} "
                     f"resulting in {str(reaction).strip().lower()}.")
    else:
        narrative = ""
    if narrative:
        lines.append(f"Allergy Note: {narrative}")

    severity = _value_to_text(_first_present(record, "reaction_severity", "severity")).strip()
    if severity and severity.lower() not in ("uncoded", "unknown"):
        lines.append(f"Severity: {severity}")

    criticality = _allergy_criticality(_first_present(record, "allergy_criticality", "criticality"))
    if criticality:
        lines.append(f"Criticality: {criticality}")

    category = _value_to_text(_first_present(record, "category")).strip()
    if category and category.lower() != "uncoded":
        lines.append(f"Category: {category}")

    atype = _value_to_text(_first_present(record, "type", "allergy_type")).strip()
    if atype and atype.lower() != "uncoded":
        lines.append(f"Type: {atype}")

    raw_code = record.get("code")
    code = _codeable_code(raw_code) if isinstance(raw_code, dict) else str(raw_code or "").strip()
    if code and code.lower() != "uncoded":
        lines.append(f"Code: {code}")
        code_system = _code_system_display(
            _first_present(record, "code_vocab", "code_system", default=_codeable_system(raw_code))
        )
        if code_system:
            lines.append(f"Code System: {code_system}")

    lines.append("Source: RhythmX AI Import")
    return "\n".join(lines)


def _map_allergy(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    name = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or record.get("name_short")
        or record.get("substance")
        or _codeable_text(record.get("code"))
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": name,
        "status": _active_status(record.get("clinicalStatus") or record.get("status"), default="active"),
    }

    note_record = record
    reaction = record.get("reaction") or record.get("reaction_manifestation")
    if isinstance(reaction, list) and reaction:
        reaction_entry = reaction[0] or {}
        manifestation = reaction_entry.get("manifestation") if isinstance(reaction_entry, dict) else None
        if isinstance(manifestation, list) and manifestation:
            manifestation = manifestation[0]
        reaction = _codeable_text(manifestation) or _value_to_text(manifestation)
        if isinstance(reaction_entry, dict) and reaction_entry.get("severity") and not record.get("reaction_severity"):
            note_record = {**record, "reaction_severity": reaction_entry.get("severity")}
    if reaction:
        payload["reaction"] = str(reaction)

    notes = _compose_allergy_notes(note_record, name, reaction)
    if notes:
        payload["notes"] = notes

    snomed_reaction = record.get("snomed_reaction")
    if snomed_reaction:
        payload["snomed_reaction"] = str(snomed_reaction)

    # rxnorm comes from an explicit rxnorm field, or an RxNorm-coded `code`. The allergen's
    # SNOMED/other code is surfaced in the notes (Code / Code System), not snomed_code.
    raw_code = record.get("code")
    if isinstance(raw_code, dict):
        raw_code = _codeable_code(raw_code)
    raw_code = str(raw_code or "").strip()
    code_vocab = str(record.get("code_vocab") or "").upper()
    rxnorm = record.get("rxnorm") or (raw_code if ("RXNORM" in code_vocab or code_vocab.startswith("RX")) else "")
    if rxnorm:
        payload["rxnorm"] = str(rxnorm)

    # Only an explicitly-provided snomed_code is sent (target keeps it empty otherwise).
    snomed_code = record.get("snomed_code")
    if snomed_code:
        payload["snomed_code"] = str(snomed_code)

    # verification_status: send only what the source provides — don't force 'confirmed'.
    vs_raw = _first_present(record, "verification_status", "verificationStatus")
    if isinstance(vs_raw, dict):
        vs_raw = _codeable_text(vs_raw)
    vs = str(vs_raw or "").strip().lower()
    if vs:
        payload["verification_status"] = vs

    return _strip_empty(payload)


def _map_immunization(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "name": record.get("name") or record.get("name_full") or _codeable_text(record.get("vaccineCode")),
        "administered_at": _normalize_date(
            record.get("administered_at")
            or record.get("occurrenceDateTime")
            or record.get("occurrence_dt")
            or record.get("date")
        ),
        "lot_number": record.get("lot_number"),
        "manufacturer": record.get("manufacturer"),
    }

    return _strip_empty(payload)


def _map_observation(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    value = _first_present(record, "value", "result")
    if value in (None, "") and isinstance(record.get("valueQuantity"), dict):
        value = record["valueQuantity"].get("value")

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "clinical_note_field": _first_present(
            record,
            "clinical_note_field",
            "observation_type",
            "field_type",
            default=_codeable_code(record.get("code")) or record.get("code"),
        ),
        "value": str(value or ""),
        "units": _first_present(record, "value_unit", "unit", "units"),
    }

    return _strip_empty(payload)


def _map_diagnostic_report(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": _first_present(record, "description", "name", "name_full", default=_codeable_text(record.get("code"))),
        "document_date": _normalize_date(_first_present(record, "document_date", "effective_dt", "effectiveDateTime", "date")),
        "notes": _first_present(record, "notes", "conclusion", "clinical_information"),
    }

    return _strip_empty(payload)


def _map_clinical_note(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "clinical_note_field": _first_present(record, "clinical_note_field", "field_type"),
        "value": _first_present(record, "value", "note_text", "notes", "text", "content", "summary_text"),
        "appointment": _first_present(record, "appointment", "appointment_id"),
    }

    return _strip_empty(payload)


def _map_service_request(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": _first_present(record, "description", "service_name", "name_full", "name_short", default=_codeable_text(record.get("code"))),
        "status": _first_present(record, "status", default="active"),
        # servicerequests.csv uses occurrence_dt for the order date.
        "order_date": _normalize_date(_first_present(record, "order_date", "order_dt", "occurrence_dt", "occurrenceDateTime", "authored_dt", "authoredOn", "recorded_dt")),
        "priority": _first_present(record, "priority"),
        "notes": _first_present(record, "notes", "note", "comment"),
    }

    return _strip_empty(payload)


def _map_coverage(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        # coverages.csv uses payor_name / plan_name / subscriber_id / plan_id.
        "insurance_company": _first_present(record, "insurance_company", "payer_name", "payor_name"),
        "insurance_plan_name": _first_present(record, "insurance_plan_name", "plan_name", "plan_short_name"),
        "insurance_id_number": _first_present(record, "insurance_id_number", "member_id", "subscriber_id"),
        "insurance_group_number": _first_present(record, "insurance_group_number", "group_id", "group_number", "plan_id"),
        "insurance_payer_id": _first_present(record, "insurance_payer_id", "payer_id", "payor_id"),
    }

    return _strip_empty(payload)


def _map_procedure(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": _first_present(record, "description", "procedure_name", "name_full", default=_codeable_text(record.get("code"))),
        "procedure_date": _normalize_date(_first_present(record, "procedure_date", "performed_dt", "performedDateTime", "date")),
        "code": _first_present(record, "code", "procedure_code", "cpt_code"),
    }

    return _strip_empty(payload)


_NOT_PROVIDED = "Not Provided."

# Free-text (narrative) fields per DrChrono resource that should display "Not Provided."
# when the source is empty. ONLY string fields DrChrono accepts as free text — never
# ids, enums, numbers, dates, booleans, or codes (those stay omitted, or DrChrono 400s).
_TEXT_DEFAULT_FIELDS = {
    "medication":        ("notes", "indication", "frequency", "route", "signature_note", "pharmacy_note"),
    "condition":         ("notes",),
    "allergy":           ("reaction", "notes"),
    "encounter":         ("reason", "notes"),
    "diagnostic_report": ("notes",),
    "service_request":   ("notes",),
    "procedure":         ("notes",),
}

# Map every resource-key alias to its canonical entry in _TEXT_DEFAULT_FIELDS.
_RESOURCE_ALIASES = {
    "medications": "medication",
    "conditions": "condition", "problem": "condition", "problems": "condition", "problem_list": "condition",
    "allergies": "allergy",
    "encounters": "encounter", "appointment": "encounter", "appointments": "encounter",
    "diagnostic_reports": "diagnostic_report", "report": "diagnostic_report", "reports": "diagnostic_report",
    "service_requests": "service_request",
    "procedures": "procedure",
}


def _apply_text_defaults(payload: dict, resource_key: str) -> dict:
    """Fill the resource's designated free-text fields with 'Not Provided.' when empty.
    Typed fields (ids/enums/numbers/dates/booleans/codes) are never touched."""
    canonical = _RESOURCE_ALIASES.get(resource_key.lower(), resource_key.lower())
    for field in _TEXT_DEFAULT_FIELDS.get(canonical, ()):
        if payload.get(field) in (None, "", [], {}):
            payload[field] = _NOT_PROVIDED
    return payload


def _map_record(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
    payload = _map_record_dispatch(resource_key, record, doctor_id=doctor_id, patient_id=patient_id)
    return _apply_text_defaults(payload, resource_key)


def _map_record_dispatch(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
    key = resource_key.lower()

    if key in ("patient", "patients"):
        return _map_patient(record, doctor_id=doctor_id)
    if key in ("encounter", "encounters", "appointment", "appointments"):
        return _map_encounter(record, doctor_id, patient_id)
    if key in ("medication", "medications"):
        return _map_medication(record, doctor_id, patient_id)
    if key in ("condition", "conditions", "problem", "problems", "problem_list"):
        return _map_condition(record, doctor_id, patient_id)
    if key in ("allergy", "allergies"):
        return _map_allergy(record, doctor_id, patient_id)
    if key in ("immunization", "immunizations"):
        return _map_immunization(record, doctor_id, patient_id)
    if key in ("observation", "observations"):
        return _map_observation(record, doctor_id, patient_id)
    if key in ("diagnostic_report", "diagnostic_reports", "report", "reports"):
        return _map_diagnostic_report(record, doctor_id, patient_id)
    if key in ("clinical_note", "clinical_notes", "observation_note", "observation_notes"):
        return _map_clinical_note(record, doctor_id, patient_id)
    if key in ("service_request", "service_requests"):
        return _map_service_request(record, doctor_id, patient_id)
    if key in ("coverage", "coverages"):
        return _map_coverage(record, doctor_id, patient_id)
    if key in ("procedure", "procedures"):
        return _map_procedure(record, doctor_id, patient_id)

    mapped = dict(record)
    if patient_id:
        mapped.setdefault("patient", int(patient_id))
    if doctor_id:
        mapped.setdefault("doctor", int(doctor_id))
    return _strip_empty(mapped)




def _resolve_file_path(raw_path: Optional[str]) -> Optional[str]:
    """
    Resolve a document file path, searching in multiple locations.

    Mirrors the reference upload_document_to_drchrono() pattern:
      path = Path(file_path).expanduser().resolve()

    For relative paths, searches:
      1. CWD-relative  (where the uvicorn/server process was launched)
      2. Every ancestor directory up from the backend, looking for the relative path
      3. DOCUMENT_SEARCH_ROOT env var if set
    """
    if not raw_path:
        return None

    p = Path(str(raw_path)).expanduser()

    # Absolute path — test directly (same as reference code)
    if p.is_absolute():
        resolved = p.resolve()
        return str(resolved) if resolved.exists() and resolved.is_file() else None

    # Relative path — build candidate list
    candidates: list[Path] = []

    # 1. CWD-relative (this is how the reference script works)
    candidates.append(Path.cwd() / p)

    # 2. Walk up from this file's location all the way to the filesystem root
    #    This catches Dataset/ placed anywhere in the ancestor tree
    here = Path(__file__).resolve().parent
    while True:
        candidates.append(here / p)
        parent = here.parent
        if parent == here:   # reached fs root
            break
        here = parent

    # 3. Explicit override from env (set DOCUMENT_SEARCH_ROOT=/path/to/dir)
    search_root = os.environ.get("DOCUMENT_SEARCH_ROOT", "")
    if search_root:
        candidates.append(Path(search_root) / p)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.exists() and resolved.is_file():
                log.debug("_resolve_file_path: resolved '%s' → '%s'", raw_path, resolved)
                return str(resolved)
        except Exception:
            continue

    log.warning("_resolve_file_path: could not find '%s' in any candidate location", raw_path)
    return None



def _prepare_document_file(file_path: str) -> tuple[str, bytes, str]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Document path is not a file: {file_path}")

    file_size = path.stat().st_size
    if file_size > MAX_DOCUMENT_SIZE_BYTES:
        mb = file_size / 1024 / 1024
        raise ValueError(f"File too large: {mb:.2f} MB. Max allowed: 10 MB")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
        raise ValueError(f"Unsupported document type: {extension}. Supported: {supported}")

    file_bytes = path.read_bytes()
    expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
    is_valid_binary = bool(expected_magic and file_bytes.startswith(expected_magic))

    if not is_valid_binary:
        # If magic bytes don't match, log a warning but still try uploading —
        # DrChrono may accept the file if the content-type header is correct.
        # Only fall back to demo PNG for truly unreadable files.
        log.warning(
            "_prepare_document_file: magic bytes mismatch for %s (ext=%s) — "
            "uploading as-is with declared MIME type",
            path.name, extension,
        )
        # Still send the real bytes with the declared MIME type — let DrChrono decide
        mime = DOCUMENT_MIME_TYPES.get(extension, "application/octet-stream")
        return path.name, file_bytes, mime

    return path.name, file_bytes, DOCUMENT_MIME_TYPES[extension]


def _document_metatags(value: Any) -> Optional[str]:
    """
    DrChrono accepts metatags as a pipe-separated string: 'lab|cbc|uploaded'
    NOT as JSON. Fixed from json.dumps() to '|'.join().
    """
    if not value:
        return None

    if isinstance(value, str):
        tags = [t.strip() for t in value.replace(",", "|").split("|") if t.strip()]
    elif isinstance(value, list):
        tags = [str(t).strip() for t in value if str(t).strip()]
    else:
        tags = [str(value).strip()]

    return "|".join(tags) if tags else None


def _today_date() -> str:
    from datetime import date
    return date.today().isoformat()


def _build_document_form_payload(
    record: dict,
    file_path: str,
    doctor_id: Optional[int],
    patient_id: int,
) -> dict:
    """
    Build the multipart form fields for DrChrono POST /documents.
    Required fields: patient, doctor, description, date, document (file)
    """
    description = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or record.get("document_type")
        or Path(file_path).stem
    )

    # date is REQUIRED by DrChrono — always emit a valid date
    doc_date = _normalize_date(
        record.get("document_date")
        or record.get("date")
        or record.get("created_dt")
        or record.get("effective_dt")
        or record.get("report_date")
    ) or _today_date()

    data: dict = {
        "patient": str(patient_id),
        "description": description,
        "date": doc_date,
    }

    # doctor is required for documents
    if doctor_id:
        data["doctor"] = str(doctor_id)

    metatags = _document_metatags(
        record.get("metatags")
        or record.get("tags")
        or record.get("document_type")
    )
    if metatags:
        data["metatags"] = metatags

    if record.get("archived") is not None:
        data["archived"] = str(bool(record.get("archived"))).lower()

    return {k: v for k, v in data.items() if v not in (None, "")}


def _upload_document(record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    if not patient_id:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": "Cannot upload document: DrChrono patient_id is missing",
            "already_exists": False,
        }

    raw_path = (
        record.get("file_path")
        or record.get("path")
        or record.get("filename")
        or record.get("local_path")
        or record.get("document_path")
    )

    file_path = _resolve_file_path(raw_path)

    if not file_path:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": f"Document file not found: {raw_path}",
            "already_exists": False,
        }

    url = f"{config.DRCHRONO_API_BASE}documents"

    try:
        filename, document_bytes, mime_type = _prepare_document_file(file_path)
        data = _build_document_form_payload(record, file_path, doctor_id, int(patient_id))
        files = {"document": (filename, document_bytes, mime_type)}

        log.info(
            "POST %s multipart_fields=%s file=%s upload_name=%s mime=%s size=%d",
            url,
            list(data.keys()),
            file_path,
            filename,
            mime_type,
            len(document_bytes),
        )

        resp = requests.post(
            url,
            headers=_multipart_headers(token),
            data=data,
            files=files,
            timeout=60,
        )

        log.info("Document upload response: %d - %s", resp.status_code, resp.text[:800])

        if resp.status_code in (200, 201):
            body = resp.json()
            return {
                "success": True,
                "status_code": resp.status_code,
                "drchrono_id": body.get("id"),
                "error": "",
                "already_exists": False,
            }

        return {
            "success": False,
            "status_code": resp.status_code,
            "drchrono_id": None,
            "error": resp.text[:1000],
            "already_exists": False,
        }

    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": str(e),
            "already_exists": False,
        }


# Unicode punctuation the latin-1 PDF encoder can't represent (it would render them as
# '?'). Mapped to safe ASCII equivalents before encoding.
_PDF_CHAR_FIXUPS = {
    "—": "-", "–": "-",                 # em / en dash  (the "Report — Lab" bug)
    "‘": "'", "’": "'",                 # curly single quotes
    "“": '"', "”": '"',                 # curly double quotes
    "…": "...", "•": "-", "·": "-",  # ellipsis / bullets
    " ": " ", "→": "->", "≥": ">=", "≤": "<=",
}


def _pdf_safe(text: str) -> str:
    """Replace unicode punctuation the latin-1 PDF encoder would turn into '?'."""
    if not text:
        return ""
    for bad, good in _PDF_CHAR_FIXUPS.items():
        text = text.replace(bad, good)
    return text


def _structure_findings(text: str) -> str:
    """Format a findings/conclusion blob for the PDF.

    Text that already carries its own structure (headings + line breaks, e.g. an echo
    report) is left intact. A dense single paragraph is split into one bullet per
    sentence so it reads as a structured list instead of a wall of text. Decimals
    (no space after the dot) and the common 'X. Capital' abbreviations are preserved."""
    text = (text or "").strip()
    if not text:
        return ""
    if text.count("\n") >= 2:                      # already structured — keep as-is
        return text
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text) if s.strip()]
    if len(sentences) <= 1:
        return text
    return "\n".join(f"- {s}" for s in sentences)


def _render_report_pdf(title: str, report_date: str, body_text: str, meta: dict) -> bytes:
    """Render a diagnostic-report narrative into a (multi-page) PDF — stdlib only.

    Diagnostic-report rows are text, not files, but DrChrono /api/documents needs a
    real binary (PDF/JPG/PNG/TIFF). We hand-build a minimal but valid PDF using only
    the standard library so this never depends on a PDF package being installed in
    whatever environment the server runs under. Uses the built-in Helvetica fonts
    (no font embedding) and the two base-14 names F1=Helvetica, F2=Helvetica-Bold.
    """
    import textwrap

    PAGE_W, PAGE_H, M = 595, 842, 50          # A4 in points, 50pt margins
    USABLE = PAGE_W - 2 * M

    def esc(s: str) -> str:
        s = _pdf_safe(s or "").encode("latin-1", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Build (font, size, text) lines, wrapping each by an approximate char width.
    raw: list[tuple[str, int, str]] = []
    raw.append(("F2", 16, title or "Diagnostic Report"))
    raw.append(("F1", 6, ""))                 # spacer
    for label, val in (("Date", report_date), *meta.items()):
        if val:
            raw.append(("F1", 10, f"{label}: {val}"))
    raw.append(("F1", 6, ""))                 # spacer
    raw.append(("F2", 12, "Findings / Conclusion"))           # body heading
    raw.append(("F1", 11, body_text or "(no report text)"))   # report narrative

    lines: list[tuple[str, int, str]] = []
    for font, size, text in raw:
        if text == "":
            lines.append((font, size, ""))
            continue
        width_chars = max(10, int(USABLE / (size * 0.5)))   # Helvetica avg ~0.5*size
        for para in str(text).split("\n"):
            for chunk in (textwrap.wrap(para, width=width_chars) or [""]):
                lines.append((font, size, chunk))

    # Paginate into pages of laid-out (font, size, escaped_text, x, y) lines.
    pages: list[list] = []
    cur: list = []
    y = PAGE_H - M
    for font, size, text in lines:
        lh = size * 1.5
        if y - lh < M:
            pages.append(cur)
            cur = []
            y = PAGE_H - M
        cur.append((font, size, esc(text), M, y))
        y -= lh
    pages.append(cur)

    def content_stream(page) -> bytes:
        parts = [
            f"BT /{font} {size} Tf {x} {yy:.1f} Td ({text}) Tj ET"
            for (font, size, text, x, yy) in page if text != ""
        ]
        return ("\n".join(parts)).encode("latin-1", "replace")

    # Assemble objects. Numbering: 1 catalog, 2 pages, 3 F1, 4 F2,
    # then per page i: page obj = 5+2i, content obj = 6+2i.
    n_pages = len(pages)
    objs: dict[int, bytes] = {}
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
    objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objs[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    for i, page in enumerate(pages):
        page_no, content_no = 5 + 2 * i, 6 + 2 * i
        objs[page_no] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_no} 0 R >>"
        ).encode()
        cs = content_stream(page)
        objs[content_no] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cs), cs)

    # Serialize with a proper xref table.
    out = b"%PDF-1.4\n"
    offsets: dict[int, int] = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref_pos = len(out)
    max_num = max(objs)
    out += f"xref\n0 {max_num + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        out += (f"{offsets[num]:010d} 00000 n \n".encode() if num in offsets
                else b"0000000000 65535 f \n")
    out += (f"trailer\n<< /Size {max_num + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return out


def _upload_diagnostic_report_as_document(
    record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Generate a PDF from a diagnostic-report row and POST it to /api/documents.

    Avoids the lab API (/api/lab_results), which is gated behind DrChrono lab-partner
    enrollment (403). Documents use the already-granted clinical scope and show up
    under the patient's Documents in DrChrono.
    """
    if not patient_id:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "Cannot upload report: DrChrono patient_id is missing",
                "already_exists": False}

    description = _first_present(
        record, "description", "category_text", "name", "name_full",
        default=_codeable_text(record.get("code")) or "Diagnostic Report",
    )
    report_date = _normalize_date(_first_present(
        record, "date", "date_report", "document_date", "effective_dt",
        "effectiveDateTime", "report_date",
    )) or _today_date()
    body_text = _structure_findings(_first_present(
        record, "test_notes", "conclusion_text", "notes", "conclusion",
        "clinical_information", "text",
    ))

    # Test/category and its coding (e.g. 'Laboratory (LOINC 11502-2)').
    category_text = str(_first_present(record, "category_text", "category", "name_full") or "").strip()
    category_code = str(_first_present(record, "category_code", "loinc_code") or "").strip()
    category_vocab = str(record.get("category_code_vocab") or "").strip()
    if category_text and category_code:
        category_display = f"{category_text} ({(category_vocab + ' ') if category_vocab else ''}{category_code})"
    else:
        category_display = category_text or category_code

    # Conclusion/diagnosis code labeled with its actual vocabulary, not a hardcoded one.
    conclusion_code = str(_first_present(record, "conclusion_code", "icd10_codes") or "").strip()
    conclusion_vocab = str(record.get("conclusion_code_vocab") or "").strip()

    provider = _value_to_text(_first_present(
        record, "practitioner_display", "practitioner_name", "performer_display",
        "performer", "provider_name", "interpreting_physician",
    ))

    meta = {
        "Report ID": _first_present(record, "source_report_id", "diagnostic_report_id", "fhir_id", "id"),
        "Patient ID": patient_id,
        "Provider": provider,
        "Category": category_display,
        "Status": _first_present(record, "order_status", "status"),
    }
    if conclusion_code:
        meta[conclusion_vocab or "Conclusion Code"] = conclusion_code

    report_title = str(description).strip()
    if "report" not in report_title.lower():
        report_title = f"Diagnostic Report — {report_title}"

    try:
        pdf_bytes = _render_report_pdf(report_title, report_date, body_text, meta)
    except Exception as e:
        log.error("PDF generation failed for diagnostic report: %s", e)
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": f"PDF generation error: {e}", "already_exists": False}

    url = f"{config.DRCHRONO_API_BASE}documents"
    data = {
        "patient": str(patient_id),
        "description": str(description)[:100],
        "date": report_date,
    }
    if doctor_id:
        data["doctor"] = str(doctor_id)
    # DrChrono /api/documents expects metatags as a JSON array string. Build a clean
    # one rather than the source 'tags' value, which is a stringified Python list
    # like "['DemoPatient']" that fails DrChrono's JSON-array parsing.
    tags = ["diagnostic_report"]
    category = _first_present(record, "category_text", "description")
    if category and str(category).strip():
        tags.append(str(category).strip()[:50])
    data["metatags"] = json.dumps(tags)

    rid = _first_present(record, "source_report_id", "diagnostic_report_id", "id", default="report")
    filename = f"diagnostic_report_{rid}.pdf"

    try:
        log.info("POST %s multipart (generated PDF) fields=%s file=%s size=%d",
                 url, list(data.keys()), filename, len(pdf_bytes))
        resp = requests.post(
            url,
            headers=_multipart_headers(token),
            data=data,
            files={"document": (filename, pdf_bytes, "application/pdf")},
            timeout=60,
        )
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:500])

        if resp.status_code in (200, 201):
            body = resp.json()
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": body.get("id"), "error": "", "already_exists": False}

        error_detail = resp.text[:1000]
        try:
            err_json = resp.json()
            msgs = []
            for field, val in err_json.items():
                msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
            if msgs:
                error_detail = " | ".join(msgs)
        except Exception:
            pass
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": error_detail, "already_exists": False}

    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}


# Narrative columns on a raw clinical note row -> human-readable section labels.
_NOTE_SECTION_FIELDS = [
    ("chief_complaint",            "Chief Complaint"),
    ("history_of_present_illness", "History of Present Illness"),
    ("review_of_systems",          "Review of Systems"),
    ("physical_exam",              "Physical Exam"),
    ("assessment",                 "Assessment"),
    ("plan",                       "Plan"),
    ("social_history",             "Social History"),
    ("family_history",             "Family History"),
    ("current_medications",        "Current Medications"),
]



_CLINICAL_NOTE_FIELD_MAP = [
    (206682180, ("note_date", "clinical_note_date", "date", "encounter_date", "start_dt")),
    (206682181, ("provider_name", "practitioner_display", "practitioner_name", "doctor_name", "author", "performer_name")),
    (206682182, ("note_category", "note_type", "clinical_note_type", "type", "document_type", "title")),
    (206682183, ("chief_complaint", "reason", "reason_name_full", "reason_full_name", "visit_reason", "description")),
    (206682184, ("history_of_present_illness", "hpi", "subjective", "history", "narrative", "clinical_summary")),
    (206682185, ("review_of_systems", "ros")),
    (206682186, ("current_medications", "medications", "medication_summary")),
    (206682187, ("family_history",)),
    (206682188, ("social_history",)),
    (206682189, ("physical_exam", "exam", "objective", "physical_examination")),
    (206682190, ("diagnostic_reports", "diagnostic_report", "ecg", "ekg", "electrocardiogram", "ecg_report", "cardiac_report")),
    (206682191, ("assessment", "diagnosis_summary", "impression")),
    (206682192, ("plan", "treatment_plan", "care_plan")),
    (206682193, ("disposition", "condition_at_discharge", "discharge_disposition")),
    (206682194, ("status", "note_status", "clinical_note_status")),
    (206682195, ("lab_results", "labs", "diagnostic_results", "diagnostics", "laboratory_results")),
]

_CLINICAL_NOTE_PASSTHROUGH_FIELDS = {
    "appointment", "appointment_id", "source_appointment_id", "source_encounter_id", "encounter_id",
    "note_date", "clinical_note_date", "date", "start_dt", "provider_name", "practitioner_display", "practitioner_name",
    "doctor_name", "author", "performer_name", "note_category", "note_type", "clinical_note_type", "type",
    "document_type", "title", "reason", "reason_name_full", "reason_full_name", "visit_reason",
    "description", "chief_complaint", "history_of_present_illness", "hpi", "subjective", "history",
    "narrative", "clinical_summary", "review_of_systems", "ros", "current_medications",
    "medications", "medication_summary", "family_history", "social_history", "physical_exam", "exam",
    "objective", "physical_examination", "diagnostic_reports", "diagnostic_report", "ecg", "ekg", "electrocardiogram", "ecg_report",
    "cardiac_report", "assessment", "diagnosis_summary", "impression", "plan", "treatment_plan",
    "care_plan", "disposition", "condition_at_discharge", "discharge_disposition", "status", "note_status", "clinical_note_status", "lab_results",
    "labs", "diagnostic_results", "diagnostics", "laboratory_results", "vital_signs", "vitals",
    "height", "height_units", "weight", "weight_units", "temperature", "temperature_units",
    "blood_pressure_1", "blood_pressure_2", "systolic_bp", "diastolic_bp", "vital_bp", "pulse",
    "respiratory_rate", "oxygen_saturation", "spo2", "pain", "pain_scale", "head_circumference",
    "head_circumference_units", "weight_for_length_percentile",
    "head_occipital_frontal_circumference_percentile", "bmi_percentile", "oxygen_concentration",
    "inhaled_oxygen_flow_rate", "smoking_status", "status", "exam_room", "scheduled_time",
    "patient", "office", "doctor",
}
def _aggregate_clinical_notes(records: list) -> list:
    """Group clinical-note rows by note id into one record per note.

    Handles both shapes: the melted sections file (one row per section, with
    section_name + value) and a raw notes file (one row, many narrative columns).
    Produces note-level dicts carrying a `sections` list so each note becomes a
    single document instead of one document per section.
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for rec in records:
        nid = str(_first_present(rec, "source_note_id", "note_id", "id", default="")) or f"NOTE-{len(order)+1}"
        if nid not in groups:
            groups[nid] = {
                "source_note_id":      nid,
                "source_encounter_id": _first_present(rec, "source_encounter_id", "encounter_id"),
                "source_patient_id":   _first_present(rec, "source_patient_id", "rx_patient_id"),
                "appointment":         _first_present(rec, "appointment", "appointment_id"),
                "note_date":           _first_present(rec, "note_date", "date"),
                "vital_signs":         _first_present(rec, "vital_signs", "vitals"),
                "sections":            [],
            }
            order.append(nid)
        grp = groups[nid]
        for col in _CLINICAL_NOTE_PASSTHROUGH_FIELDS:
            if not grp.get(col) and rec.get(col) not in (None, "", [], {}):
                grp[col] = rec.get(col)
        # vital_signs may arrive on any row (e.g. raw note file) — keep the first seen.
        if not grp.get("vital_signs"):
            grp["vital_signs"] = _first_present(rec, "vital_signs", "vitals")
        # Melted section row (section_name + value).
        sec_name = _first_present(rec, "section_name")
        sec_val = _first_present(rec, "value", "note_text")
        if sec_name and sec_val:
            grp["sections"].append((str(sec_name), str(sec_val)))
        # Raw narrative columns.
        for col, label in _NOTE_SECTION_FIELDS:
            v = _first_present(rec, col)
            if v:
                grp["sections"].append((label, str(v)))
    return [groups[n] for n in order]


def _upload_clinical_note_as_document(
    note: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Render a clinical note's sections into a PDF and POST to /api/documents.

    DrChrono's native clinical-note API (/api/clinical_note_field_values) requires
    template-bound field IDs tied to an appointment — not available here. Uploading
    the note as a document (clinical scope) reliably lands it in the patient chart.
    """
    if not patient_id:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "Cannot upload clinical note: DrChrono patient_id is missing",
                "already_exists": False}

    sections = note.get("sections") or []
    if not sections:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "No clinical note content found — the base file holds only join keys. "
                         "Push the clinicalnotes_sections file (it carries the note text).",
                "already_exists": False, "retryable": False}

    body = "\n\n".join(f"{name}:\n{value}" for name, value in sections)
    report_date = _normalize_date(note.get("note_date")) or _today_date()
    meta = {
        "Note ID":  note.get("source_note_id"),
        "Encounter": note.get("source_encounter_id"),
    }
    try:
        pdf_bytes = _render_report_pdf("Clinical Note", report_date, body, meta)
    except Exception as e:
        log.error("PDF generation failed for clinical note: %s", e)
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": f"PDF generation error: {e}", "already_exists": False}

    url = f"{config.DRCHRONO_API_BASE}documents"
    data = {"patient": str(patient_id), "description": "Clinical Note", "date": report_date}
    if doctor_id:
        data["doctor"] = str(doctor_id)
    data["metatags"] = json.dumps(["clinical_note"])

    rid = note.get("source_note_id") or "note"
    filename = f"clinical_note_{rid}.pdf"
    try:
        log.info("POST %s multipart (clinical note PDF) file=%s size=%d sections=%d",
                 url, filename, len(pdf_bytes), len(sections))
        resp = requests.post(
            url, headers=_multipart_headers(token), data=data,
            files={"document": (filename, pdf_bytes, "application/pdf")}, timeout=60,
        )
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])
        if resp.status_code in (200, 201):
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": resp.json().get("id"), "error": "", "already_exists": False}
        error_detail = resp.text[:1000]
        try:
            err_json = resp.json()
            msgs = []
            for field, val in err_json.items():
                msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
            if msgs:
                error_detail = " | ".join(msgs)
        except Exception:
            pass
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": error_detail, "already_exists": False}
    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}


# ═══════════════════════════════════════════════════════════════════════════════
# Clinical notes -> DrChrono clinical_note_field_values + appointment vitals
# ═══════════════════════════════════════════════════════════════════════════════
# Fixed DrChrono clinical-note template for this practice (never changes).
TEMPLATE_ID = 7520906

# encounter/appointment source-id  ->  DrChrono numeric appointment_id created during
# THIS push run. Appointments are pushed before clinical notes, so a note can resolve
# its appointment here. Reset at the start of every push run.
_APPT_ID_MAP: dict = {}

# Vital label -> (regex to pull it from free text, display unit). Order is the
# fixed display order; missing vitals render as an em dash.
_VITAL_PATTERNS = [
    ("Temperature", r"\b(?:temp(?:erature)?)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", "°F"),
    ("Pulse",       r"\b(?:pulse|heart\s*rate|hr)\b[:\s]*([0-9]{2,3})", " bpm"),
    ("BP",          r"\b(?:bp|blood\s*pressure)\b[:\s]*([0-9]{2,3}\s*/\s*[0-9]{2,3})", " mmHg"),
    ("RR",          r"\b(?:rr|resp(?:iratory)?(?:\s*rate)?)\b[:\s]*([0-9]{1,2})", " rpm"),
    ("SpO2",        r"\b(?:spo2|sao2|o2\s*sat\w*|oxygen\s*saturation|sat)\b[:\s]*([0-9]{2,3})", "%"),
    ("Height",      r"\b(?:height|ht)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " in"),
    ("Weight",      r"\b(?:weight|wt)\b[:\s]*([0-9]{2,3}(?:\.[0-9])?)", " lbs"),
    ("BMI",         r"\bbmi\b[:\s]*([0-9]{2}(?:\.[0-9])?)", " kg/m²"),
    ("Pain",        r"\bpain\b[:\s]*([0-9]{1,2})\s*/\s*10", "/10"),
]


def _temp_to_fahrenheit(raw: str) -> str:
    """Source temperatures are in Celsius (e.g. 36.8); convert to °F so the fixed
    '°F' label is accurate. Values already in the Fahrenheit range pass through."""
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return raw
    return f"{round(c * 9 / 5 + 32, 1)}" if c <= 45 else f"{round(c, 1)}"


def _height_to_inches(raw: str, suffix: str = "") -> str:
    """DrChrono stores height in inches. Source heights are often metric (e.g. 175 cm).
    Convert when the source unit is cm — detected from the text following the value, or
    by magnitude (>96 in is an implausible adult height, so it must be cm)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    is_cm = bool(re.search(r"cm|centimet", suffix, re.I))
    is_in = bool(re.search(r'\bin\b|inch|"', suffix, re.I))
    if is_cm or (v > 96 and not is_in):
        return f"{round(v / 2.54, 1)}"
    return f"{round(v, 1)}"


def _weight_to_lbs(raw: str, suffix: str = "") -> str:
    """DrChrono stores weight in lbs. Source weights are often metric (e.g. 88 kg).
    Convert when the source unit is kg — detected from the text following the value
    (magnitude alone is ambiguous, so kg/lb must be explicit to convert)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    if re.search(r"kg|kilo", suffix, re.I):
        return f"{round(v * 2.20462, 1)}"
    return f"{round(v, 1)}"


def _format_vitals(text: str) -> str:
    """Regex-parse a free-text vital_signs string into the fixed 9-field line.
    Missing vitals render as 'Not provided' so the layout is always consistent
    and the push never breaks on incomplete data."""
    parts = []
    for label, pattern, unit in _VITAL_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            suffix = text[m.end():m.end() + 8]
            if label == "BP":
                val = re.sub(r"\s*", "", m.group(1))
            elif label == "Temperature":
                val = _temp_to_fahrenheit(m.group(1).strip())
            elif label == "Height":
                val = _height_to_inches(m.group(1).strip(), suffix)
            elif label == "Weight":
                val = _weight_to_lbs(m.group(1).strip(), suffix)
            else:
                val = m.group(1).strip()
            parts.append(f"{label}: {val}{unit}")
        else:
            parts.append(f"{label}: Not provided")
    return " | ".join(parts)


def _build_note_content(note: dict) -> str:
    """Assemble the yellow_notepad content string: clinical narrative only.

    Vitals are pushed to the appointment's vitals section (PUT), so they are NOT
    repeated here — the note carries just CC/HPI/Assessment/Plan."""
    sec = {label: value for (label, value) in note.get("sections", [])}

    def _sec(label):
        v = sec.get(label)
        return v.strip() if v and str(v).strip() else "Not provided"

    cc = _sec("Chief Complaint")
    hpi = _sec("History of Present Illness")
    assessment = _sec("Assessment")
    plan = _sec("Plan")
    return f"CC: {cc}  HPI: {hpi}  Assessment: {assessment}  Plan: {plan}"


def _remember_appointment_id(key: str, record: dict, result: dict) -> None:
    """After an appointment/encounter is created, store its DrChrono id keyed by every
    source id on the row, so a clinical note can later resolve its appointment_id."""
    if key not in ("encounter", "encounters", "appointment", "appointments"):
        return
    appt_id = result.get("drchrono_id")
    if not appt_id:
        return
    for k in ("source_encounter_id", "encounter_id", "source_appointment_id", "appointment_id", "id"):
        v = record.get(k)
        if v not in (None, ""):
            _APPT_ID_MAP[str(v)] = appt_id


def _resolve_appointment_id(note: dict):
    """Resolve a note's DrChrono appointment_id from the captured map (or a pre-resolved
    numeric id already on the row). Returns None if not found locally."""
    for k in ("source_encounter_id", "encounter_id", "source_appointment_id", "appointment_id", "appointment", "id"):
        v = note.get(k)
        if v not in (None, "") and str(v) in _APPT_ID_MAP:
            return _APPT_ID_MAP[str(v)]
    for k in ("appointment_id", "appointment"):
        v = note.get(k)
        if v not in (None, "") and str(v).isdigit():
            return int(v)
    return None


def _lookup_appointment_id(token: str, patient_id, date_str: str):
    """Fallback: ask DrChrono for the patient's appointment(s) and match by date.
    Lets a note resolve its appointment even if it was created in a previous run /
    before a restart (when the in-memory map is empty)."""
    if not token or not patient_id:
        return None
    params: dict = {"patient": int(patient_id)}
    day = (date_str or "")[:10]
    if day:
        params["date"] = day
    try:
        url = f"{config.DRCHRONO_API_BASE}appointments"
        resp = requests.get(url, params=params, headers=_json_headers(token), timeout=15)
        log.info("Appointment lookup GET %s params=%s status=%d", url, params, resp.status_code)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0].get("id")
    except Exception as e:
        log.warning("Appointment lookup failed: %s", e)
    return None


def _refresh_access_token() -> Optional[str]:
    """Refresh the DrChrono access token via the stored refresh token (used on 401).
    Returns the new access token, or None if refresh isn't possible."""
    try:
        from app.services.drchrono_client import drchrono_client
        tok = token_store.get_token()
        if not tok or not getattr(tok, "refresh_token", None):
            return None
        data = drchrono_client.refresh_token(tok.refresh_token)
        new_access = data.get("access_token")
        if new_access:
            token_store.set_token(
                access_token=new_access,
                expires_in=data.get("expires_in", 172800),
                refresh_token=data.get("refresh_token") or tok.refresh_token,
                doctor_id=tok.doctor_id,
                doctor_name=tok.doctor_name,
            )
            return new_access
    except Exception as e:
        log.warning("DrChrono token refresh failed: %s", e)
    return None


def _build_vitals_payload(note: dict) -> dict:
    """Build the DrChrono appointment-vitals PATCH body.

    Prefers structured numeric columns on the row (temperature, systolic_bp, ...),
    falling back to regex over the standardized vitals string parsed from the row's
    free-text vital_signs. Only vitals that are actually present are sent; units are
    fixed per DrChrono's confirmed rules (temperature='f', height/head='inches',
    weight='lbs')."""
    text = _format_vitals(str(note.get("vital_signs") or ""))

    def pick(struct_keys, pattern, cast):
        for k in struct_keys:
            v = note.get(k)
            if v not in (None, "", "Not provided"):
                m = re.search(r"-?\d+\.?\d*", str(v))
                if m:
                    try:
                        return cast(float(m.group(0)))
                    except (ValueError, TypeError):
                        pass
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                return cast(float(m.group(1)))
            except (ValueError, TypeError):
                pass
        return None

    temp   = pick(["temperature", "vital_temperature"], r"Temperature:\s*(\d+\.?\d*)", float)
    pulse  = pick(["pulse", "vital_pulse"], r"Pulse:\s*(\d+)", int)
    sysbp  = pick(["systolic_bp"], r"BP:\s*(\d+)/", int)
    diabp  = pick(["diastolic_bp"], r"BP:\s*\d+/(\d+)", int)
    if sysbp is None or diabp is None:               # combined "160/90" column
        m = re.search(r"(\d+)\s*/\s*(\d+)", str(note.get("vital_bp") or ""))
        if m:
            sysbp = sysbp if sysbp is not None else int(m.group(1))
            diabp = diabp if diabp is not None else int(m.group(2))
    rr     = pick(["respiratory_rate", "vital_rr"], r"RR:\s*(\d+)", int)
    spo2   = pick(["spo2", "vital_spo2"], r"SpO2:\s*(\d+)", int)
    height = pick(["height", "vital_height"], r"Height:\s*(\d+\.?\d*)", float)
    weight = pick(["weight", "vital_weight"], r"Weight:\s*(\d+\.?\d*)", float)
    pain   = pick(["pain_scale", "vital_pain"], r"Pain:\s*(\d+)/10", int)

    vitals: dict = {
        "head_circumference": 0,
        "head_circumference_units": "inches",
        "smoking_status": "blank",
    }
    if temp is not None:   vitals["temperature"] = temp; vitals["temperature_units"] = "f"
    if height is not None: vitals["height"] = height; vitals["height_units"] = "inches"
    if weight is not None: vitals["weight"] = weight; vitals["weight_units"] = "lbs"
    if sysbp is not None:  vitals["blood_pressure_1"] = sysbp
    if diabp is not None:  vitals["blood_pressure_2"] = diabp
    if pulse is not None:  vitals["pulse"] = pulse
    if rr is not None:     vitals["respiratory_rate"] = rr
    if spo2 is not None:   vitals["oxygen_saturation"] = spo2
    if pain is not None:   vitals["pain"] = str(pain)

    direct_vital_fields = {
        "height": float, "weight": float, "temperature": float,
        "blood_pressure_1": int, "blood_pressure_2": int, "pulse": int,
        "respiratory_rate": int, "oxygen_saturation": int, "head_circumference": float,
        "weight_for_length_percentile": float,
        "head_occipital_frontal_circumference_percentile": float,
        "bmi_percentile": float, "oxygen_concentration": float,
        "inhaled_oxygen_flow_rate": float,
    }
    for key, cast in direct_vital_fields.items():
        value = note.get(key)
        if value not in (None, "", [], {}, "Not provided"):
            try:
                vitals[key] = cast(float(value))
            except (TypeError, ValueError):
                pass
    for key in ("height_units", "weight_units", "temperature_units", "head_circumference_units", "smoking_status", "pain"):
        value = note.get(key)
        if value not in (None, "", [], {}, "Not provided"):
            vitals[key] = value

    payload = {"vitals": vitals, "status": _first_present(note, "status", default="Checked In")}
    for key in ("exam_room", "scheduled_time", "patient", "office", "doctor"):
        value = note.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


def _clinical_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value).strip().strip('"')


def _clinical_note_field_payloads(note: dict, appt_id) -> list[dict]:
    payloads: list[dict] = []
    seen: set[int] = set()
    explicit_field = _first_present(note, "clinical_note_field", "field_type")
    explicit_value = _first_present(note, "value", "note_text", "clinical_note", "text")
    if explicit_field and explicit_value not in (None, "", [], {}):
        try:
            field_id = int(explicit_field)
        except (TypeError, ValueError):
            field_id = explicit_field
        payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(explicit_value)})
        if isinstance(field_id, int):
            seen.add(field_id)

    for field_id, keys in _CLINICAL_NOTE_FIELD_MAP:
        if field_id in seen:
            continue
        value = _first_present(note, *keys)
        if value in (None, "", [], {}):
            continue
        payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(value)})
        seen.add(field_id)

    for label, value in note.get("sections", []) or []:
        normalized = str(label or "").strip().lower().replace(" ", "_")
        for field_id, keys in _CLINICAL_NOTE_FIELD_MAP:
            if field_id in seen:
                continue
            if normalized in {str(k).lower() for k in keys}:
                payloads.append({"clinical_note_field": field_id, "appointment": int(appt_id), "value": _clinical_text(value)})
                seen.add(field_id)
                break
    return payloads


def _post_clinical_note_field_values(payloads: list[dict], token: str) -> dict:
    if not payloads:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "No clinical note field values found to push.", "already_exists": False,
                "retryable": False}
    url = f"{config.DRCHRONO_API_BASE}clinical_note_field_values"
    tok = token
    pushed_ids = []
    errors = []
    last_status = 0
    for payload in payloads:
        try:
            resp = requests.post(url, json=payload, headers=_json_headers(tok), timeout=30)
            if resp.status_code == 401:
                new_tok = _refresh_access_token()
                if new_tok:
                    tok = new_tok
                    resp = requests.post(url, json=payload, headers=_json_headers(tok), timeout=30)
            last_status = resp.status_code
            log.info("POST %s field=%s appt=%s -> %s", url, payload.get("clinical_note_field"), payload.get("appointment"), resp.status_code)
            if resp.status_code in (200, 201):
                try:
                    pushed_ids.append(resp.json().get("id"))
                except Exception:
                    pushed_ids.append(payload.get("clinical_note_field"))
            else:
                errors.append(resp.text[:500])
        except Exception as e:
            errors.append(str(e))
            last_status = 0
    if errors:
        return {"success": False, "status_code": last_status, "drchrono_id": pushed_ids[-1] if pushed_ids else None,
                "error": " | ".join(errors[:3]), "already_exists": False,
                "retryable": last_status == 0 or last_status >= 500}
    return {"success": True, "status_code": last_status or 201, "drchrono_id": pushed_ids[-1] if pushed_ids else None,
            "error": "", "already_exists": False, "field_count": len(payloads)}

def _put_appointment_vitals(appt_id, payload: dict, token: str) -> dict:
    """PATCH structured vitals onto the appointment. Success = 200/204.

    Uses PATCH (partial update) — NOT PUT. A PUT replaces the whole appointment and
    requires every mandatory field (scheduled_time, duration, office, exam_room, ...),
    so a vitals-only PUT 400s and the vitals silently never persist. PATCH matches the
    DrChrono 'Patch_appointment_vitals' reference. Refreshes the token once on 401 and
    retries up to 3x on 429/5xx (2s backoff)."""
    url = f"{config.DRCHRONO_API_BASE}appointments/{appt_id}"
    tok = token
    for attempt in range(3):
        try:
            resp = requests.patch(url, json=payload, headers=_json_headers(tok), timeout=30)
        except Exception as e:
            return {"ok": False, "status_code": 0, "error": str(e)}
        if resp.status_code == 401:
            new_tok = _refresh_access_token()
            if new_tok:
                tok = new_tok
                continue
        if resp.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(2)
            continue
        if resp.status_code in (200, 204):
            # Verify DrChrono actually persisted the vitals: a 2xx is returned even
            # when an unknown field is silently ignored. GET the appointment back and
            # log what it stored, so we can confirm the vitals really landed.
            try:
                chk = requests.get(url, headers=_json_headers(tok), timeout=15)
                if chk.status_code == 200:
                    appt = chk.json()
                    log.info("Vitals verify appt=%s -> status=%s vitals=%s",
                             appt_id, appt.get("status"), str(appt.get("vitals"))[:400])
            except Exception as e:
                log.warning("Vitals verify GET failed: %s", e)
            return {"ok": True, "status_code": resp.status_code, "error": ""}
        return {"ok": False, "status_code": resp.status_code, "error": resp.text[:500]}
    return {"ok": False, "status_code": 0, "error": "retries exhausted"}


def _push_clinical_note_yellow_notepad(
    note: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Push one clinical note via DrChrono clinical note field values.

    Vitals are written to /api/appointments/{appointment_id} with PUT. Narrative
    sections are written to /api/clinical_note_field_values. Vitals are
    best-effort; a vitals failure is returned as detail but does not block note
    field creation.
    """
    appt_id = _resolve_appointment_id(note)
    if not appt_id:
        appt_id = _lookup_appointment_id(token, patient_id, note.get("note_date"))
    if not appt_id:
        log.info("Clinical note %s has no appointment - uploading as a document instead.",
                 note.get("source_note_id"))
        return _upload_clinical_note_as_document(note, token, doctor_id, patient_id)

    vitals_payload = _build_vitals_payload(note)
    vitals_result = _put_appointment_vitals(appt_id, vitals_payload, token)
    if vitals_result["ok"]:
        log.info("Vitals PUT appt=%s -> 204 (%d vitals)", appt_id, len(vitals_payload["vitals"]))
    else:
        log.warning("Vitals PUT appt=%s -> %s %s", appt_id,
                    vitals_result["status_code"], vitals_result["error"][:200])

    field_payloads = _clinical_note_field_payloads(note, appt_id)
    note_result = _post_clinical_note_field_values(field_payloads, token)
    note_result["vitals_status"] = vitals_result["status_code"]
    note_result["detail"] = (
        f"Vitals {vitals_result['status_code']}"
        if vitals_result["ok"] else f"Vitals failed ({vitals_result['status_code']})"
    )
    return note_result

def _upload_coverage(record: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Create a patient insurance via POST /api/insurances.

    (There is no /api/patient_insurances endpoint — that 404s.) Primary vs secondary
    is conveyed by the insurance_type field.
    """
    if not patient_id:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "Cannot push coverage: DrChrono patient_id is missing",
                "already_exists": False}

    plan_type = str(_first_present(record, "insurance_plan_type", "coverage_rank", default="primary")).strip().lower()
    insurance_type = "secondary" if plan_type in ("secondary", "2") else "primary"

    payload = {
        "patient":                int(patient_id),
        "insurance_type":         insurance_type,
        "insurance_company":      _first_present(record, "insurance_company", "payer_name", "payor_name"),
        "insurance_plan_name":    _first_present(record, "insurance_plan_name", "plan_name", "plan_short_name"),
        "insurance_id_number":    _first_present(record, "insurance_id_number", "subscriber_id", "member_id"),
        "insurance_group_number": _first_present(record, "insurance_group_number", "plan_id", "group_number"),
    }
    payer = _first_present(record, "payer_id", "payor_id")
    if payer:
        payload["payer_id"] = str(payer)
    payload = {k: v for k, v in payload.items() if v not in (None, "")}

    if not payload.get("insurance_company"):
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "Coverage requires insurance_company.", "already_exists": False}

    url = f"{config.DRCHRONO_API_BASE}insurances"
    try:
        log.info("POST %s payload=%s", url, payload)
        resp = requests.post(url, json=payload, headers=_json_headers(token), timeout=20)
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])
        if resp.status_code in (200, 201, 204):
            drchrono_id = None
            try:
                drchrono_id = resp.json().get("id")
            except Exception:
                drchrono_id = patient_id
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": drchrono_id, "error": "", "already_exists": False}
        error_detail = resp.text[:1000]
        try:
            err_json = resp.json()
            msgs = []
            for field, val in err_json.items():
                msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
            if msgs:
                error_detail = " | ".join(msgs)
        except Exception:
            pass
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": error_detail, "already_exists": False}
    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}


_VITAL_COLUMNS = [
    ("bp_s", "BP Systolic"), ("bp_d", "BP Diastolic"), ("pulse", "Pulse"),
    ("respiratory_rate", "Respiratory Rate"), ("temperature", "Temperature"),
    ("weight", "Weight"), ("height", "Height"),
    ("oxygen_saturation", "O2 Saturation"), ("bmi", "BMI"),
]


def _aggregate_observations(records: list) -> list:
    """Group observation rows by encounter into one record per encounter.

    Handles both transformed shapes: pivoted vitals (one row, many vital columns)
    and lab results (one row per test). So each encounter becomes a single document
    containing its vitals and/or lab panel.
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for rec in records:
        enc = str(_first_present(rec, "source_encounter_id", "encounter_id", default=""))
        gid = enc or f"OBS-{len(order)+1}"
        if gid not in groups:
            groups[gid] = {
                "source_encounter_id": enc,
                "source_patient_id":   _first_present(rec, "source_patient_id", "rx_patient_id"),
                "date":                _first_present(rec, "date_collected", "effective_dt", "date"),
                "vitals":              [],
                "labs":                [],
            }
            order.append(gid)
        grp = groups[gid]
        for col, label in _VITAL_COLUMNS:
            v = _first_present(rec, col)
            if v not in (None, ""):
                grp["vitals"].append((label, str(v)))
        test_name = _first_present(rec, "test_name", "name_full", "name_short")
        note_text = _first_present(rec, "note_text")
        if test_name:
            value = _first_present(rec, "value", "value_string")
            units = _first_present(rec, "units", "value_unit")
            ab = _first_present(rec, "abnormal_status")
            line = f"{test_name}: {value}{(' ' + str(units)) if units else ''}{(' [' + str(ab) + ']') if ab else ''}"
            if note_text:
                line += f" — {note_text}"
            grp["labs"].append(line)
        elif note_text:
            grp["labs"].append(str(note_text))
    return [groups[g] for g in order]


def _upload_observation_as_document(
    obs: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Render an encounter's observations (vitals + labs) to a PDF and POST to
    /api/documents. DrChrono's /api/clinical_note_field_values needs template-bound
    field PKs + an appointment, which raw lab/vital data can't supply."""
    if not patient_id:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "Cannot upload observations: DrChrono patient_id is missing",
                "already_exists": False}

    vitals = obs.get("vitals") or []
    labs = obs.get("labs") or []
    if not vitals and not labs:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "No observation data found for this encounter.",
                "already_exists": False, "retryable": False}

    parts = []
    if vitals:
        parts.append("VITAL SIGNS:\n" + "\n".join(f"  {n}: {v}" for n, v in vitals))
    if labs:
        parts.append("LABORATORY RESULTS:\n" + "\n".join(f"  {l}" for l in labs))
    body = "\n\n".join(parts)
    report_date = _normalize_date(obs.get("date")) or _today_date()
    meta = {"Encounter": obs.get("source_encounter_id")}

    try:
        pdf_bytes = _render_report_pdf("Clinical Observations", report_date, body, meta)
    except Exception as e:
        log.error("PDF generation failed for observations: %s", e)
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": f"PDF generation error: {e}", "already_exists": False}

    url = f"{config.DRCHRONO_API_BASE}documents"
    data = {"patient": str(patient_id), "description": "Clinical Observations", "date": report_date}
    if doctor_id:
        data["doctor"] = str(doctor_id)
    data["metatags"] = json.dumps(["observations"])
    filename = f"observations_{obs.get('source_encounter_id') or 'enc'}.pdf"
    try:
        log.info("POST %s multipart (observations PDF) file=%s size=%d vitals=%d labs=%d",
                 url, filename, len(pdf_bytes), len(vitals), len(labs))
        resp = requests.post(url, headers=_multipart_headers(token), data=data,
                             files={"document": (filename, pdf_bytes, "application/pdf")}, timeout=60)
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])
        if resp.status_code in (200, 201):
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": resp.json().get("id"), "error": "", "already_exists": False}
        error_detail = resp.text[:1000]
        try:
            err_json = resp.json()
            msgs = []
            for field, val in err_json.items():
                msgs.extend(f"{field}: {m}" for m in val) if isinstance(val, list) else msgs.append(f"{field}: {val}")
            if msgs:
                error_detail = " | ".join(msgs)
        except Exception:
            pass
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": error_detail, "already_exists": False}
    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}


# ═══════════════════════════════════════════════════════════════════════════════
# Observations + Observation Notes → DrChrono /api/patient_lab_results
# ═══════════════════════════════════════════════════════════════════════════════
# Notes indexed by observation_id (built per run) so an observation can be enriched
# with its matching note (LEFT join: observations is the base).
_OBS_NOTE_INDEX: dict = {}
_OBS_HAS_OBS = {"value": False}

# Valid DrChrono lab_order_status choices (exactly the EHR dropdown values).
_VALID_LAB_STATUSES = (
    "Order Entered", "Discontinued", "In Progress",
    "Results Received", "Results Reviewed with Patient", "Paper Order",
)
# Map a FHIR observation status -> a valid DrChrono lab_order_status.
_LAB_STATUS_MAP = {
    "final": "Results Received",
    "amended": "Results Received",
    "corrected": "Results Received",
    "preliminary": "In Progress",
    "registered": "Order Entered",
    "cancelled": "Discontinued",
    "entered-in-error": "Discontinued",
    "unknown": "In Progress",
}


def _prepare_obs_lab_index(source: dict, ordered: list) -> None:
    """Index observation_notes by observation_id, and record whether observations are
    being pushed this run. When they are, note rows are merged into the observation
    (LEFT join) and NOT pushed separately — so both files together = one set of calls."""
    _OBS_NOTE_INDEX.clear()
    for nkey in ("observation_note", "observation_notes"):
        for note in source.get(nkey, []) or []:
            oid = str(note.get("observation_id") or "").strip()
            if oid and oid not in _OBS_NOTE_INDEX:
                _OBS_NOTE_INDEX[oid] = note
    _OBS_HAS_OBS["value"] = any(k in ordered for k in ("observation", "observations"))


def _lab_order_status(obs: dict) -> str:
    """Resolve a valid DrChrono lab_order_status. A CSV column already holding a valid
    value (lab_order_status / order_status) wins; otherwise map the observation status."""
    direct = _first_present(obs, "lab_order_status", "order_status")
    if direct:
        d = str(direct).strip()
        for valid in _VALID_LAB_STATUSES:
            if d.lower() == valid.lower():
                return valid
    return _LAB_STATUS_MAP.get(str(_first_present(obs, "status") or "").strip().lower(), "In Progress")


def _lab_value_float(value):
    """Extract the first numeric token from a value string -> float, or None."""
    if value in (None, ""):
        return None
    m = re.search(r"([\d.]+)", str(value))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _lab_abnormal_flag(value, ref_min, ref_max, data_absent_reason) -> str:
    vf = _lab_value_float(value)
    try:
        if vf is not None and ref_max not in (None, "") and vf > float(ref_max):
            return "H"
    except (ValueError, TypeError):
        pass
    try:
        if vf is not None and ref_min not in (None, "") and vf < float(ref_min):
            return "L"
    except (ValueError, TypeError):
        pass
    if data_absent_reason not in (None, ""):
        return "N"
    return ""


def _lab_result_value_str(value, value_unit, value_string) -> str:
    suffix = "Imported via RhythmX AI integration pipeline."
    if value not in (None, ""):
        vs = f" {value_string}." if value_string not in (None, "") else ""
        return f"{value} {value_unit or ''}.{vs} {suffix}".strip()
    if value_string not in (None, ""):
        return f"{value_string}. {suffix}"
    return f"Result not provided. {suffix}"


def _lab_normal_range(obs: dict) -> str:
    rrd = _first_present(obs, "reference_range_display")
    if rrd:
        return str(rrd)
    rmin = _first_present(obs, "reference_min")
    rmax = _first_present(obs, "reference_max")
    if rmin or rmax:
        return f"{rmin}-{rmax}"
    rn = _first_present(obs, "reference_normal")
    return str(rn) if rn else "Not provided"


def _lab_doctor_comments(note: dict) -> str:
    suffix = "Result imported through RhythmX AI API integration workflow."
    body = []
    note_text = _first_present(note, "note_text")
    if note_text:
        body.append(str(note_text))
    for label, key in (("Reference", "note_reference"), ("Data absent reason", "data_absent_reason"),
                       ("Category", "category"), ("Tags", "tags")):
        v = _first_present(note, key)
        if v:
            body.append(f"{label}: {v}")
    if not body:
        return f"Observation Note: No additional notes available for this result. {suffix}"
    return f"Observation Note: {' '.join(body)} {suffix}"


def _build_lab_result_payload(obs: dict, note: Optional[dict],
                              doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Map an observation (+ optional joined note) to the patient_lab_results payload.
    Missing fields default to 'Not provided' — never raises on null."""
    obs = obs or {}
    note = note or {}
    payload = {
        "ordering_doctor": int(doctor_id) if doctor_id else None,
        "patient": int(patient_id) if patient_id else None,
        "title": (_first_present(obs, "name_full", "name_short", "name_rx", "test_name", "code")
                  or _first_present(note, "name_full", "name_short", "name_rx", "test_name")
                  or "Lab Result"),
        "lab_result_value": _lab_result_value_str(
            _first_present(obs, "value"),
            _first_present(obs, "value_unit", "units"),
            _first_present(note, "value_string"),
        ),
        "lab_result_value_as_float": _lab_value_float(_first_present(obs, "value")),
        "lab_result_value_units": _first_present(obs, "value_unit", "units", default="Not provided"),
        "lab_normal_range": _lab_normal_range(obs),
        "lab_normal_range_units": _first_present(obs, "value_unit", "units", default="Not provided"),
        "lab_abnormal_flag": _lab_abnormal_flag(
            _first_present(obs, "value"),
            _first_present(obs, "reference_min"),
            _first_present(obs, "reference_max"),
            _first_present(note, "data_absent_reason") or _first_present(obs, "data_absent_reason"),
        ),
        "lab_order_status": _lab_order_status(obs),
        # DrChrono requires a full ISO-8601 datetime (YYYY-MM-DDThh:mm:ss), not a date.
        "date_test_performed": _normalize_datetime(
            _first_present(obs, "effective_dt", "issued_dt", "date_collected", "note_date")
            or _first_present(note, "effective_dt", "issued_dt")
        ),
        "doctor_signoff": False,
        "doctor_comments": _lab_doctor_comments(note),
    }
    # loinc_code only when the code system is LOINC.
    code = _first_present(obs, "code")
    if code and str(_first_present(obs, "code_vocab")).strip().upper() == "LOINC":
        payload["loinc_code"] = str(code)

    # Neither observations.csv nor observationnotes.csv carries an appointment id or a
    # document id — only encounter_id. So both are resolved through the encounter: the
    # appointment via appointment_registry, the scanned diagnostic report via doc_registry.
    # Lab orders expose them as the 'appointment' field and the 'documents' array
    # ('Scanned in result' in the UI).
    appointment = _medication_appointment(obs) or _medication_appointment(note)
    if appointment:
        try:
            payload["appointment"] = int(appointment)
        except (TypeError, ValueError):
            payload["appointment"] = appointment

    document_id = _resolve_document_id(obs) or _resolve_document_id(note)
    if document_id:
        payload["documents"] = [str(document_id)]

    return payload


def _push_lab_result(payload: dict, token: str) -> dict:
    """POST one assembled lab-result payload to /api/patient_lab_results.
    401 -> refresh token & retry once; 400/422 -> log full body; 300 ms between calls."""
    url = f"{config.DRCHRONO_API_BASE}patient_lab_results"

    def _post(tok: str):
        return requests.post(url, json=payload, headers=_json_headers(tok), timeout=30)

    try:
        resp = _post(token)
        if resp.status_code == 401:
            new_tok = _refresh_access_token()
            if new_tok:
                resp = _post(new_tok)
        log.info("POST %s patient=%s title=%s -> %d",
                 url, payload.get("patient"), str(payload.get("title"))[:40], resp.status_code)
        if resp.status_code in (200, 201):
            try:
                rid = resp.json().get("id")
            except Exception:
                rid = None
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": rid, "error": "", "already_exists": False}
        if resp.status_code in (400, 422):
            log.warning("patient_lab_results %d body=%s", resp.status_code, resp.text[:800])
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": resp.text[:1000], "already_exists": False,
                "retryable": resp.status_code >= 500}
    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}
    finally:
        time.sleep(0.3)


def _push_observation_lab_result(record: dict, key: str, token: str,
                                 doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    """Route an observation / observation-note row to /api/patient_lab_results.

    Observations are the base, enriched with their matching note via the run index.
    Observation-note rows only reach here when observations are NOT being pushed (the
    push loop skips them otherwise), so here they map standalone to the same payload.
    """
    if key in ("observation", "observations"):
        note = _OBS_NOTE_INDEX.get(str(record.get("observation_id") or "").strip())
        return _push_lab_result(_build_lab_result_payload(record, note, doctor_id, patient_id), token)
    # observation_note(s) standalone (numeric value fields empty).
    return _push_lab_result(_build_lab_result_payload({}, record, doctor_id, patient_id), token)


def _simulate_push(records: list, resource: str) -> dict:
    if not records:
        return {"total": 0, "successful": 0, "failed": 0}

    total = len(records)
    successful = round(total * random.uniform(0.90, 1.0))
    return {"total": total, "successful": successful, "failed": total - successful}


def _find_existing_patient(payload: dict, token: str) -> Optional[int]:
    params = {}
    if payload.get("first_name"):
        params["first_name"] = payload["first_name"]
    if payload.get("last_name"):
        params["last_name"] = payload["last_name"]
    if payload.get("date_of_birth"):
        params["date_of_birth"] = payload["date_of_birth"]

    if not params:
        return None

    url = f"{config.DRCHRONO_API_BASE}patients"

    try:
        resp = requests.get(url, params=params, headers=_json_headers(token), timeout=15)
        log.info("Patient search GET %s params=%s status=%d", url, params, resp.status_code)

        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0].get("id")

    except Exception as e:
        log.warning("Patient search failed: %s", e)

    return None


# Cache resolved (office_id, exam_room) per (token, doctor) so we hit /api/offices
# at most once per push run instead of once per appointment record.
_OFFICE_CACHE: dict = {}


def _get_default_office(token: str, doctor_id: Optional[int]) -> tuple[Optional[int], int]:
    """Resolve a usable (office_id, exam_room) from DrChrono /api/offices.

    DrChrono requires both 'office' and 'exam_room' on appointments and rejects a
    guessed office ID. We pick the doctor's office (falling back to the first office
    on the account) and its first exam room. Result is cached per token+doctor.
    """
    cache_key = (token[-12:] if token else "", doctor_id)
    if cache_key in _OFFICE_CACHE:
        return _OFFICE_CACHE[cache_key]

    office_id: Optional[int] = None
    exam_room: int = 1
    try:
        url = f"{config.DRCHRONO_API_BASE}offices"
        resp = requests.get(url, headers=_json_headers(token), timeout=15)
        log.info("Offices GET %s status=%d", url, resp.status_code)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            chosen = None
            if doctor_id:
                chosen = next((o for o in results if o.get("doctor") == doctor_id), None)
            if not chosen and results:
                chosen = results[0]
            if chosen:
                office_id = chosen.get("id")
                rooms = chosen.get("exam_rooms") or []
                if rooms and isinstance(rooms[0], dict):
                    exam_room = rooms[0].get("index", 1) or 1
        else:
            log.warning("Offices lookup returned %d: %s", resp.status_code, resp.text[:300])
    except Exception as e:
        log.warning("Office lookup failed: %s", e)

    _OFFICE_CACHE[cache_key] = (office_id, exam_room)
    return office_id, exam_room


# ═══════════════════════════════════════════════════════════════════════════════
# Appointment / Encounter idempotency registry
# ═══════════════════════════════════════════════════════════════════════════════
# Maps a source appointment_id / encounter_id -> the DrChrono appointment_id created
# for it, persisted to disk so repeated pushes are idempotent (no duplicate records),
# even across backend restarts.
_APPT_REGISTRY: dict = {}
_APPT_REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # -> backend/
    "appointment_registry.json",
)


def _load_appt_registry() -> dict:
    try:
        with open(_APPT_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_appt_registry(reg: dict) -> None:
    try:
        with open(_APPT_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    except OSError as e:
        log.warning("Could not persist appointment registry: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostic-report document registry
# ═══════════════════════════════════════════════════════════════════════════════
# Maps a source encounter_id -> the DrChrono document id created for that encounter's
# diagnostic report. Observations sharing the encounter attach to it via the lab
# result 'document' field (the 'File' column in DrChrono). Persisted across restarts.
_DOC_ID_MAP: dict = {}
_DOC_REGISTRY: dict = {}
_DOC_REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # -> backend/
    "document_registry.json",
)


def _load_doc_registry() -> dict:
    try:
        with open(_DOC_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_doc_registry(reg: dict) -> None:
    try:
        with open(_DOC_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    except OSError as e:
        log.warning("Could not persist document registry: %s", e)


def _remember_document_id(key: str, record: dict, result: dict) -> None:
    """After a diagnostic report uploads as a document, store its DrChrono document id
    keyed by every source encounter id on the row, so observations sharing that encounter
    attach to it (the 'File' column on a DrChrono lab result)."""
    if key not in ("diagnostic_report", "diagnostic_reports", "report", "reports"):
        return
    doc_id = result.get("drchrono_id")
    if not doc_id:
        return
    for k in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn",
              "diagnostic_report_id", "fhir_id", "id"):
        v = record.get(k)
        if v not in (None, ""):
            _DOC_ID_MAP[str(v)] = doc_id
            _DOC_REGISTRY[str(v)] = doc_id
    _save_doc_registry(_DOC_REGISTRY)


def _resolve_document_id(record: dict):
    """Resolve the diagnostic-report document id for an observation via its encounter id."""
    for k in ("source_encounter_id", "encounter_id", "encounter_fhir_id", "encounter_csn"):
        v = record.get(k)
        if v not in (None, "") and str(v) in _DOC_ID_MAP:
            return _DOC_ID_MAP[str(v)]
    return None


def _load_registry_into_memory() -> None:
    """Load the persisted registry at the start of a push run, so existence checks and
    clinical-note appointment resolution survive restarts."""
    _APPT_REGISTRY.clear()
    _APPT_REGISTRY.update(_load_appt_registry())
    # Seed the resolver map too. _medication_appointment / _resolve_appointment_id read
    # _APPT_ID_MAP, so without this, appointment tagging for medication/condition/notes
    # only works when the parent encounter is (re)pushed in the SAME run. Seeding from the
    # persisted registry lets a resource tag to an appointment created in a PRIOR run.
    _APPT_ID_MAP.update(_APPT_REGISTRY)
    # Same for diagnostic-report documents, so observations can attach to a report
    # uploaded in a prior run.
    _DOC_REGISTRY.clear()
    _DOC_REGISTRY.update(_load_doc_registry())
    _DOC_ID_MAP.update(_DOC_REGISTRY)


def _appt_source_id(record: dict, key: str) -> str:
    """The external id used to determine appointment/encounter uniqueness."""
    if key in ("encounter", "encounters"):
        return str(_first_present(record, "source_encounter_id", "encounter_id", "id") or "").strip()
    return str(_first_present(record, "source_appointment_id", "appointment_id", "id") or "").strip()


def _drop_cached_appt(src: str) -> None:
    """Remove a stale source-id to appointment-id mapping from memory and disk."""
    _APPT_REGISTRY.pop(src, None)
    _APPT_ID_MAP.pop(src, None)
    _save_appt_registry(_APPT_REGISTRY)


def _cached_appt_exists(token: str, appt_id) -> bool:
    """Return True only when DrChrono confirms the cached appointment exists."""
    if not appt_id:
        return False
    url = f"{config.DRCHRONO_API_BASE}appointments/{appt_id}"
    try:
        resp = requests.get(url, headers=_json_headers(token), timeout=15)
        log.info("Verify cached appointment GET %s status=%d", url, resp.status_code)
        return resp.status_code == 200
    except Exception as e:
        log.warning("Could not verify cached appointment %s: %s", appt_id, e)
        return False


def _appt_already_exists(record: dict, key: str, token: str) -> Optional[dict]:
    """Idempotency check — if this appointment/encounter was already created, return an
    'already exists' result (no duplicate POST). Returns None if it's new."""
    src = _appt_source_id(record, key)
    if not src or src not in _APPT_REGISTRY:
        return None
    appt_id = _APPT_REGISTRY[src]
    if not _cached_appt_exists(token, appt_id):
        log.info(
            "Cached appointment is stale; will create a new one (source_id=%s -> appt %s)",
            src,
            appt_id,
        )
        _drop_cached_appt(src)
        return None
    is_enc = key in ("encounter", "encounters")
    msg = "Encounter already exists" if is_enc else "Appointment already exists"
    _APPT_ID_MAP[src] = appt_id
    log.info("Idempotent skip: %s (source_id=%s -> appt %s)", msg, src, appt_id)
    return {
        "success": True, "status_code": 200, "drchrono_id": appt_id,
        "error": "", "already_exists": True, "message": msg, "detail": msg,
    }


def _register_appt(record: dict, key: str, drchrono_id) -> None:
    """Record a newly-created appointment/encounter so future pushes are idempotent."""
    src = _appt_source_id(record, key)
    if src and drchrono_id:
        _APPT_REGISTRY[src] = drchrono_id
        _APPT_ID_MAP[src] = drchrono_id
        _save_appt_registry(_APPT_REGISTRY)


def _live_push_record(
    record: dict,
    resource: str,
    token: str,
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
) -> dict:
    key = resource.lower()
    path = ENDPOINT_MAP.get(key)

    if not path:
        log.warning("No DrChrono endpoint for resource: %s — skipping", resource)
        return {
            "success": True,
            "status_code": 0,
            "drchrono_id": None,
            "error": "skipped (no endpoint)",
            "already_exists": False,
        }

    is_patient = key.rstrip("s") == "patient"

    if key in ("document", "documents", "document_reference", "document_references"):
        return _upload_document(record, token, doctor_id=doctor_id, patient_id=patient_id)

    # Diagnostic reports are narrative text with no attached file. We render each
    # to a PDF and upload via /api/documents (clinical scope) rather than the
    # lab-partner-gated /api/lab_results (which returns 403).
    if key in ("diagnostic_report", "diagnostic_reports", "report", "reports"):
        return _upload_diagnostic_report_as_document(
            record, token, doctor_id=doctor_id, patient_id=patient_id
        )

    # Clinical notes are pushed to DrChrono field values, with structured vitals
    # written back to the appointment first. The records arriving here are
    # note-level (aggregated in generate()), and the appointment_id is resolved
    # from appointments pushed earlier in the same run.
    if key in ("clinical_note", "clinical_notes"):
        return _push_clinical_note_yellow_notepad(
            record, token, doctor_id=doctor_id, patient_id=patient_id
        )

    # Coverages attach to the patient via PATCH /api/patients/{id} — there is no
    # /api/patient_insurances endpoint (it 404s).
    if key in ("coverage", "coverages"):
        return _upload_coverage(record, token, doctor_id=doctor_id, patient_id=patient_id)

    # Observations + observation notes are pushed to /api/patient_lab_results as
    # structured lab results (one per observation, enriched with its matching note).
    if key in ("observation", "observations", "observation_note", "observation_notes"):
        return _push_observation_lab_result(
            record, key, token, doctor_id=doctor_id, patient_id=patient_id
        )

    patient_optional_keys = {"clinical_note", "clinical_notes"}
    if not is_patient and not patient_id and key not in patient_optional_keys:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": f"Cannot push {resource}: DrChrono patient_id is missing",
            "already_exists": False,
        }

    url = f"{config.DRCHRONO_API_BASE}{path}"

    try:
        payload = _map_record(resource, record, doctor_id=doctor_id, patient_id=patient_id)
    except Exception as e:
        log.error("Mapping failed for %s: %s", resource, e)
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": f"Mapping error: {e}",
            "already_exists": False,
        }

    # Idempotency: if this appointment/encounter id was already created, skip the
    # create and return an 'already exists' response (no duplicate in DrChrono).
    if key in ("encounter", "encounters", "appointment", "appointments"):
        existing = _appt_already_exists(record, key, token)
        if existing:
            return existing

    # Appointments require a real DrChrono office ID. If the source data didn't
    # carry one, resolve the doctor's default office (cached) and fill it in.
    if key in ("encounter", "encounters", "appointment", "appointments") and not payload.get("office"):
        office_id, exam_room = _get_default_office(token, doctor_id)
        if office_id:
            payload["office"] = office_id
            payload.setdefault("exam_room", exam_room)

    # DrChrono only accepts appointment times in the current century (2000-2099).
    # Pre-2000 dates ALWAYS 400 — fail fast locally with a clear, field-tagged
    # message instead of wasting a round-trip, and so the UI can show exactly
    # which field/value was rejected. This is deterministic → not retryable.
    if key in ("encounter", "encounters", "appointment", "appointments"):
        sched = str(payload.get("scheduled_time") or "")
        year = sched[:4]
        if year.isdigit() and int(year) < 2000:
            return {
                "success": False,
                "status_code": 422,
                "drchrono_id": None,
                "error": f"scheduled_time: {sched[:10]} is before year 2000 — "
                         f"DrChrono only accepts appointment dates in the range 2000-2099.",
                "already_exists": False,
                "retryable": False,
            }

    if key in ("condition", "conditions", "problem", "problems", "problem_list") and not payload.get("description"):
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": "Problem/condition description is missing. Map name_full/code.text to description.",
            "already_exists": False,
        }

    if key in ("medication", "medications") and not payload.get("name"):
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": "Medication name is missing. Map name_full/medicationCodeableConcept.text to name.",
            "already_exists": False,
        }

    if key in ("clinical_note", "clinical_notes", "observation_note", "observation_notes"):
        if not payload.get("clinical_note_field") or not payload.get("value"):
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": "Clinical note payload requires clinical_note_field and value/note_text.",
                "already_exists": False,
            }
        if key in ("clinical_note", "clinical_notes") and not payload.get("appointment"):
            return {
                "success": False,
                "status_code": 0,
                "drchrono_id": None,
                "error": "Clinical note payload requires appointment or appointment_id.",
                "already_exists": False,
            }

    if is_patient:
        existing_id = _find_existing_patient(payload, token)
        if existing_id:
            message = (
                "Patient already present in DrChrono; no need to push this patient "
                "again in DrChrono"
            )
            log.info("%s ID=%s", message, existing_id)
            return {
                "success": True,
                "status_code": 200,
                "drchrono_id": existing_id,
                "error": "",
                "already_exists": True,
                "message": f"{message} ID={existing_id}",
            }

    log.info("POST %s payload=%s", url, payload)

    try:
        resp = requests.post(url, json=payload, headers=_json_headers(token), timeout=20)
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:800])

        if resp.status_code in (200, 201):
            body = resp.json()
            # Record appointment/encounter creation so repeat pushes are idempotent.
            if key in ("encounter", "encounters", "appointment", "appointments"):
                _register_appt(record, key, body.get("id"))
            return {
                "success": True,
                "status_code": resp.status_code,
                "drchrono_id": body.get("id"),
                "error": "",
                "already_exists": False,
            }

        error_detail = resp.text[:1000]
        try:
            err_json = resp.json()
            messages = []
            for field, val in err_json.items():
                if isinstance(val, list):
                    messages.extend(f"{field}: {m}" for m in val)
                else:
                    messages.append(f"{field}: {val}")
            if messages:
                error_detail = " | ".join(messages)
        except Exception:
            pass

        return {
            "success": False,
            "status_code": resp.status_code,
            "drchrono_id": None,
            "error": error_detail,
            "already_exists": False,
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": "Request timed out",
            "already_exists": False,
        }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": "Connection error",
            "already_exists": False,
        }

    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "drchrono_id": None,
            "error": str(e),
            "already_exists": False,
        }


@router.get("/preflight")
def push_preflight():
    session_resources = _SESSION.get("resources", {})
    resource_types = [k for k, v in session_resources.items() if v]
    record_count = sum(len(v) for v in session_resources.values() if v)

    tok = token_store.get_token()
    token_valid = token_store.is_valid()
    doctor_id = tok.doctor_id if tok else None
    doctor_name = tok.doctor_name if tok else None
    expires_in = token_store.seconds_until_expiry()

    issues = []
    if record_count == 0:
        issues.append("No data in backend session. Re-upload your file.")
    if not token_valid:
        issues.append("No valid DrChrono token. Authenticate first.")
    if token_valid and not doctor_id:
        issues.append("Doctor ID missing from token.")

    return {
        "ready": len(issues) == 0,
        "issues": issues,
        "session": {
            "loaded": record_count > 0,
            "record_count": record_count,
            "resource_types": resource_types,
        },
        "auth": {
            "token_valid": token_valid,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "expires_in": expires_in,
        },
    }


class PushRequest(BaseModel):
    resources: List[str] = []
    dry_run: bool = False
    access_token: Optional[str] = None
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None


@router.post("/run")
async def push_run(req: PushRequest):
    source = _SESSION.get("resources") or _SESSION.get("mapped")

    if not source:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")

    target_keys = req.resources if req.resources else list(source.keys())

    token: Optional[str] = None
    doctor_id = req.doctor_id

    if not req.dry_run:
        tok_obj = token_store.get_token()

        if req.access_token:
            token = req.access_token
        elif tok_obj and tok_obj.access_token:
            token = tok_obj.access_token
        else:
            raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")

        if not doctor_id and tok_obj and tok_obj.doctor_id:
            try:
                doctor_id = int(tok_obj.doctor_id)
            except (TypeError, ValueError):
                pass

    push_order = [
        "patient",
        "patients",
        "encounter",
        "encounters",
        "appointment",
        "appointments",
        "condition",
        "conditions",
        "problem",
        "problems",
        "problem_list",
        "medication",
        "medications",
        "allergy",
        "allergies",
        "immunization",
        "immunizations",
        "diagnostic_report",
        "diagnostic_reports",
        "report",
        "reports",
        "observation",
        "observations",
        "observation_note",
        "observation_notes",
        "service_request",
        "service_requests",
        "procedure",
        "procedures",
        "coverage",
        "coverages",
        "document",
        "documents",
        "document_reference",
        "document_references",
        "clinical_note",
        "clinical_notes",
    ]

    ordered = [k for k in push_order if k in target_keys]
    ordered += [k for k in target_keys if k not in ordered]

    stats = {}
    current_patient_id = req.patient_id
    # Load the persisted appointment/encounter registry so existence checks (and
    # clinical-note appointment resolution) work across runs and restarts.
    _load_registry_into_memory()
    _prepare_obs_lab_index(source, ordered)  # index notes; decide merge vs standalone

    for key in ordered:
        records = source.get(key, [])

        if not records:
            continue
        # When observations are also being pushed, their notes are merged in — don't
        # push observation_notes separately (avoids the duplicate set of API calls).
        if key in ("observation_note", "observation_notes") and _OBS_HAS_OBS["value"]:
            continue
        if key in ("clinical_note", "clinical_notes"):
            records = _aggregate_clinical_notes(records)

        if req.dry_run:
            stats[key] = _simulate_push(records, key)
            continue

        assert token is not None  # narrows Optional[str] -> str past the dry_run guard

        total = successful = failed = already_exists_count = 0
        errors = []

        for record in records:
            total += 1

            result = _live_push_record(
                record,
                key,
                token,
                doctor_id=doctor_id,
                patient_id=current_patient_id,
            )
            _remember_appointment_id(key, record, result)

            if result.get("already_exists"):
                already_exists_count += 1
                successful += 1

                if key in ("patient", "patients") and result.get("drchrono_id"):
                    current_patient_id = result["drchrono_id"]

            elif result.get("success"):
                successful += 1

                if key in ("patient", "patients") and result.get("drchrono_id"):
                    current_patient_id = result["drchrono_id"]

            else:
                failed += 1
                errors.append(result.get("error", "unknown error"))

            time.sleep(0.1)

        stats[key] = {
            "total": total,
            "successful": successful,
            "failed": failed,
            "already_exists": already_exists_count,
            "errors": errors[:5],
        }

    total_all = sum(s["total"] for s in stats.values())
    successful_all = sum(s["successful"] for s in stats.values())
    failed_all = sum(s["failed"] for s in stats.values())

    return {
        "status": "complete",
        "dry_run": req.dry_run,
        "total": total_all,
        "successful": successful_all,
        "failed": failed_all,
        "patient_id": current_patient_id,
        "stats": stats,
    }


# Push order shared between /run and /run-stream
_PUSH_ORDER = [
    "patient", "patients", "encounter", "encounters", "appointment", "appointments",
    "condition", "conditions", "problem", "problems", "problem_list",
    "medication", "medications", "allergy", "allergies",
    "immunization", "immunizations", "diagnostic_report", "diagnostic_reports",
    "report", "reports", "observation", "observations",
    "observation_note", "observation_notes", "service_request", "service_requests",
    "procedure", "procedures", "coverage", "coverages",
    "document", "documents", "document_reference", "document_references",
    "clinical_note", "clinical_notes",
]


@router.post("/run-stream")
def push_run_stream(req: PushRequest):
    """Streaming push: yields NDJSON, one line per record + final summary line.

    Each record line:
      {"type":"record","resource":...,"record_id":...,"index":...,
       "status_code":...,"success":...,"already_exists":...,"error":...,
       "drchrono_id":...,"latency_ms":...}
    Final line:
      {"type":"summary","total":...,"successful":...,"failed":...,
       "already_exists":...,"patient_id":...,"stats":{...}}
    """
    source = _SESSION.get("resources") or _SESSION.get("mapped")
    if not source:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")

    target_keys = req.resources if req.resources else list(source.keys())

    token: Optional[str] = None
    doctor_id = req.doctor_id

    if not req.dry_run:
        tok_obj = token_store.get_token()
        if req.access_token:
            token = req.access_token
        elif tok_obj and tok_obj.access_token:
            token = tok_obj.access_token
        else:
            raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")
        if not doctor_id and tok_obj and tok_obj.doctor_id:
            try:
                doctor_id = int(tok_obj.doctor_id)
            except (TypeError, ValueError):
                pass

    ordered = [k for k in _PUSH_ORDER if k in target_keys]
    ordered += [k for k in target_keys if k not in ordered]

    _load_registry_into_memory()  # appointment/encounter idempotency, across restarts
    _prepare_obs_lab_index(source, ordered)  # index notes; decide merge vs standalone

    def generate():
        stats: dict[str, dict] = {}
        current_patient_id = req.patient_id
        already_exists_total = 0
        # Record-level logging + tracking for this run (integration.log / failed_records
        # .xlsx / processing_summary.json + frontend failure feed).
        svc = LoggingService()
        # _APPT_ID_MAP persists across runs (see push_run); live lookup is the fallback.

        for key in ordered:
            records = source.get(key, [])
            if not records:
                continue
            # Notes are merged into observations when both are pushed — skip the
            # separate observation_notes pass so the count isn't doubled.
            if key in ("observation_note", "observation_notes") and _OBS_HAS_OBS["value"]:
                continue
            # Collapse clinical-note section rows into one record per note so each
            # note becomes a single PDF document instead of one per section.
            if key in ("clinical_note", "clinical_notes"):
                records = _aggregate_clinical_notes(records)

            total = successful = failed = already_exists_count = 0
            errors: list[str] = []

            for idx, record in enumerate(records):
                total += 1
                t0 = time.time()

                if req.dry_run:
                    sim = _simulate_push([record], key)
                    result = {
                        "success": sim.get("would_succeed", 0) > 0,
                        "status_code": 201 if sim.get("would_succeed", 0) > 0 else 400,
                        "drchrono_id": None,
                        "error": None,
                        "already_exists": False,
                    }
                else:
                    assert token is not None
                    result = _live_push_record(
                        record, key, token,
                        doctor_id=doctor_id, patient_id=current_patient_id,
                    )
                    _remember_appointment_id(key, record, result)
                    _remember_document_id(key, record, result)

                latency_ms = int((time.time() - t0) * 1000)

                # Record-level log + failure tracking (never breaks the push).
                svc.log_record(
                    resource_type=key,
                    row=idx + 1,
                    record=record,
                    result=result,
                    endpoint=_endpoint_for(key),
                    request_payload=None if req.dry_run else _payload_for_logging(
                        key, record, doctor_id, current_patient_id),
                    drchrono_patient_id=current_patient_id,
                    latency_ms=latency_ms,
                )

                if result.get("already_exists"):
                    already_exists_count += 1
                    already_exists_total += 1
                    successful += 1
                    if key in ("patient", "patients") and result.get("drchrono_id"):
                        current_patient_id = result["drchrono_id"]
                elif result.get("success"):
                    successful += 1
                    if key in ("patient", "patients") and result.get("drchrono_id"):
                        current_patient_id = result["drchrono_id"]
                else:
                    failed += 1
                    err = result.get("error", "unknown error")
                    errors.append(err)

                rec_id = (
                    record.get("id")
                    or record.get("patient_id")
                    or f"{key.upper()}-{idx + 1}"
                )
                _status = result.get("status_code") or 0
                # Validation errors (4xx) are deterministic — retrying won't help.
                # Transient failures (timeout/connection/5xx, status 0 or >=500) may.
                _is_fail = not (result.get("success") or result.get("already_exists"))
                _retryable = result.get("retryable")
                if _retryable is None:
                    _retryable = _is_fail and (_status == 0 or _status >= 500)
                event = {
                    "type": "record",
                    "resource": key,
                    "record_id": str(rec_id),
                    "index": idx,
                    "status_code": _status,
                    "success": bool(result.get("success") or result.get("already_exists")),
                    "already_exists": bool(result.get("already_exists")),
                    "error": None if not _is_fail else result.get("error"),
                    "retryable": bool(_retryable) if _is_fail else False,
                    "drchrono_id": result.get("drchrono_id"),
                    "latency_ms": latency_ms,
                }
                yield json.dumps(event) + "\n"

                if not req.dry_run:
                    time.sleep(0.1)

            stats[key] = {
                "total": total, "successful": successful, "failed": failed,
                "already_exists": already_exists_count, "errors": errors[:5],
            }

        # Write integration artifacts and expose this run's failures to the frontend.
        record_summary = svc.finalize()
        set_last_run(svc)

        summary = {
            "type": "summary",
            "total": sum(s["total"] for s in stats.values()),
            "successful": sum(s["successful"] for s in stats.values()),
            "failed": sum(s["failed"] for s in stats.values()),
            "already_exists": already_exists_total,
            "patient_id": current_patient_id,
            "stats": stats,
            "run_id": svc.run_id,
            "record_summary": record_summary,
            "failed_records": svc.failures,
        }
        yield json.dumps(summary) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/failures")
def push_failures(limit: int = 500):
    """Records that failed to push in the most recent run — for the frontend
    'which record failed' table. Empty until a run has executed."""
    svc = get_last_run()
    if not svc:
        return {"run_id": None, "summary": None, "failures": []}
    return {"run_id": svc.run_id, "summary": svc.summary(), "failures": svc.failures[:limit]}


@router.get("/summary")
def push_summary():
    """processing_summary.json for the most recent run (per-resource pass/fail)."""
    svc = get_last_run()
    return svc.summary() if svc else {"run_id": None, "total_records": 0}


@router.get("/failed-records.xlsx")
def download_failed_records():
    """Download the failed_records.xlsx for the most recent run."""
    from app.services.logging_service import FAILED_XLSX

    if not FAILED_XLSX.exists():
        raise HTTPException(status_code=404, detail="No failed_records.xlsx yet — run a push first.")
    return FileResponse(
        str(FAILED_XLSX),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="failed_records.xlsx",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Document File Upload — direct file push (mirrors reference integration pattern)
# ═══════════════════════════════════════════════════════════════════════════════
@router.post(
    "/documents/file",
    tags=["Push"],
    summary="Direct document file upload to DrChrono",
)
async def push_document_file(
    patient_id:  int        = Form(...,  description="DrChrono patient ID"),
    doctor_id:   int        = Form(...,  description="DrChrono doctor ID"),
    description: str        = Form(...,  description="Human-readable document label"),
    date:        str        = Form(...,  description="Document date (YYYY-MM-DD)"),
    file:        UploadFile = File(...,  description="PDF or image file (max 10 MB)"),
    metatags:    str        = Form("",   description="Tags — comma or pipe separated, e.g. lab|cbc"),
    archived:    bool       = Form(False, description="Archive document immediately after upload"),
):
    """
    Upload a document file directly to DrChrono — no session required.

    Mirrors the reference `upload_document_to_drchrono()` pattern:
    - Validates file extension (.pdf / .jpg / .jpeg / .png / .gif / .bmp)
    - Checks file size (≤ 10 MB)
    - Verifies binary magic bytes match the declared extension
    - Posts multipart/form-data to DrChrono /api/documents

    Returns the DrChrono document object on success (includes `id` field).
    """
    filename  = file.filename or "document.pdf"
    extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{extension}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            400,
            f"File too large: {len(file_bytes)/1024/1024:.2f} MB. Max allowed: 10 MB.",
        )

    expected_magic = DOCUMENT_MAGIC_BYTES.get(extension)
    if expected_magic and not file_bytes.startswith(expected_magic):
        raise HTTPException(
            400,
            f"File extension is '{extension}' but binary content does not match. "
            "Upload a real file, not a renamed one.",
        )

    mime_type = DOCUMENT_MIME_TYPES.get(extension, "application/octet-stream")

    log.info(
        "push_document_file: patient=%d doctor=%d filename=%s size=%d mime=%s",
        patient_id, doctor_id, filename, len(file_bytes), mime_type,
    )

    return drchrono_post_document(
        patient=patient_id,
        doctor=doctor_id,
        description=description.strip(),
        date=date[:10],
        document_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        metatags=metatags,
        archived=archived,
    )





















