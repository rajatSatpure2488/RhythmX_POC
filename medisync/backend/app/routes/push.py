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
import time
from pathlib import Path
from typing import Any, List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import config
from app.routes.upload import _SESSION
from app.services.token_store import token_store

log = logging.getLogger("medisync.push")

router = APIRouter()

ENDPOINT_MAP = {
    "patient": "patients",
    "patients": "patients",
    "encounter": "appointments",
    "encounters": "appointments",
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
    "observation": "lab_results",
    "observations": "lab_results",
    "procedure": "procedures",
    "procedures": "procedures",
    "coverage": "patient_insurances",
    "coverages": "patient_insurances",
    "document": "documents",
    "documents": "documents",
    "document_reference": "documents",
    "document_references": "documents",
    "clinical_note": "clinical_notes",
    "clinical_notes": "clinical_notes",
}

_GENDER_MAP = {
    "male": "Male", "m": "Male",
    "female": "Female", "f": "Female",
    "other": "Other", "o": "Other",
    "unknown": "Unknown", "u": "Unknown",
    "UNK": "Unknown",
}


def _strip_empty(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def _normalize_date(val: Any) -> str:
    if not val:
        return ""
    return str(val)[:10]


def _map_gender(val: Any) -> str:
    if not val:
        return ""
    return _GENDER_MAP.get(str(val).strip(), str(val).strip())


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
    raw = str(value or default).lower()
    if raw in ("active", "completed", "intended", "confirmed", "final"):
        return "active"
    return "inactive"


def _condition_status(record: dict) -> str:
    clinical = record.get("clinicalStatus")
    if isinstance(clinical, dict):
        text = _codeable_text(clinical).lower()
        if "resolved" in text or "inactive" in text:
            return "resolved"

    raw = str(record.get("status") or record.get("verificationStatus") or "active").lower()
    if raw in ("resolved", "inactive", "entered-in-error"):
        return "resolved"
    return "active"


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


def _map_patient(record: dict, doctor_id: Optional[int] = None) -> dict:
    name_raw = record.get("name")

    if isinstance(name_raw, list):
        first, last = _extract_name(name_raw)
    else:
        first = record.get("first_name") or record.get("given") or ""
        last = record.get("last_name") or record.get("family") or ""
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

    phone = email = ""
    for t in record.get("telecom") or []:
        if isinstance(t, dict):
            system = t.get("system", "")
            value = t.get("value", "")
            if system == "phone" and not phone:
                phone = value
            elif system == "email" and not email:
                email = value

    payload = {
        "first_name": first or "Unknown",
        "last_name": last or "Patient",
        "date_of_birth": _normalize_date(
            record.get("birthDate")
            or record.get("date_of_birth")
            or record.get("birth_date")
            or record.get("dob")
        ),
        "gender": _map_gender(record.get("gender") or record.get("sex")) or "Unknown",
        "email": email or record.get("email", ""),
        "home_phone": phone or record.get("phone") or record.get("home_phone", ""),
        "address": address or record.get("address") or record.get("street", ""),
        "city": city or record.get("city", ""),
        "state": state or record.get("state", ""),
        "zip_code": zip_code or record.get("zip_code") or record.get("zip", ""),
    }

    if doctor_id:
        payload["doctor"] = int(doctor_id)

    return _strip_empty(payload)


def _map_medication(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    med_name = (
        record.get("name")
        or record.get("name_full")
        or record.get("display")
        or _codeable_text(record.get("medicationCodeableConcept"))
        or _codeable_text(record.get("medication"))
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "name": med_name,
        "status": _active_status(record.get("status"), default="active"),
    }

    rxnorm = (
        record.get("rxnorm")
        or record.get("rxnorm_code")
        or _codeable_code(record.get("medicationCodeableConcept"))
    )
    if rxnorm:
        payload["rxnorm"] = str(rxnorm)

    dosage = record.get("dosageInstruction") or []
    if isinstance(dosage, list) and dosage:
        d0 = dosage[0]
        if isinstance(d0, dict) and d0.get("text"):
            payload["frequency"] = d0["text"]

    if record.get("dosage_quantity"):
        payload["dosage_quantity"] = str(record["dosage_quantity"])
    if record.get("dosage_unit"):
        payload["dosage_unit"] = record["dosage_unit"]
    if record.get("route"):
        payload["route"] = record["route"]
    if record.get("frequency") or record.get("frequencyText"):
        payload["frequency"] = record.get("frequencyText") or record.get("frequency")
    if record.get("reason") or record.get("indication"):
        payload["indication"] = record.get("reason") or record.get("indication")

    start_date = record.get("start_dt") or record.get("start_date") or record.get("authoredOn") or record.get("date")
    if start_date:
        payload["start_date"] = _normalize_date(start_date)

    return _strip_empty(payload)


def _map_condition(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    name = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or _codeable_text(record.get("code"))
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": name,
        "status": _condition_status(record),
    }

    icd_code = (
        record.get("icd_code")
        or record.get("code_value")
        or record.get("code")
        if isinstance(record.get("code"), str)
        else _codeable_code(record.get("code"))
    )
    if icd_code:
        payload["icd_code"] = str(icd_code)

    onset = record.get("date_onset") or record.get("onsetDateTime") or record.get("start_dt")
    if onset:
        payload["date_onset"] = _normalize_date(onset)

    return _strip_empty(payload)


def _map_allergy(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    name = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or _codeable_text(record.get("code"))
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": name,
        "status": _active_status(record.get("clinicalStatus") or record.get("status"), default="active"),
    }

    reaction = record.get("reaction") or record.get("reaction_manifestation")
    if isinstance(reaction, list) and reaction:
        reaction = _codeable_text((reaction[0] or {}).get("manifestation"))

    if reaction:
        payload["reaction"] = str(reaction)

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
    name = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or _codeable_text(record.get("code"))
        or "Observation"
    )

    value = record.get("value")
    if value is None and isinstance(record.get("valueQuantity"), dict):
        value = record["valueQuantity"].get("value")

    notes = record.get("notes") or record.get("conclusion") or ""
    if value not in (None, ""):
        unit = record.get("value_unit") or record.get("unit") or ""
        notes = f"{name}: {value} {unit}".strip()

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": name,
        "document_date": _normalize_date(record.get("effectiveDateTime") or record.get("effective_dt") or record.get("date")),
        "notes": notes,
    }

    return _strip_empty(payload)


def _map_clinical_note(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "clinical_note_date": _normalize_date(
            record.get("clinical_note_date")
            or record.get("date")
            or record.get("effective_dt")
        ),
        "notes": (
            record.get("notes")
            or record.get("note_text")
            or record.get("text")
            or record.get("content")
            or record.get("summary_text")
            or ""
        ),
    }

    return _strip_empty(payload)


def _map_record(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
    key = resource_key.lower()

    if key in ("patient", "patients"):
        return _map_patient(record, doctor_id=doctor_id)
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
    if key in ("clinical_note", "clinical_notes"):
        return _map_clinical_note(record, doctor_id, patient_id)

    mapped = dict(record)
    if patient_id:
        mapped.setdefault("patient", int(patient_id))
    if doctor_id:
        mapped.setdefault("doctor", int(doctor_id))
    return _strip_empty(mapped)


def _resolve_file_path(raw_path: str) -> Optional[str]:
    if not raw_path:
        return None

    p = Path(str(raw_path)).expanduser()

    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(Path.cwd() / p)

        base_dir = getattr(config, "BASE_DIR", None)
        if base_dir:
            candidates.append(Path(base_dir) / p)

        upload_dir = getattr(config, "UPLOAD_DIR", None)
        if upload_dir:
            candidates.append(Path(upload_dir) / p)

        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / p)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.exists() and resolved.is_file():
                return str(resolved)
        except Exception:
            continue

    return None


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

    data = {
        "patient": str(patient_id),
        "doctor": str(doctor_id) if doctor_id else "",
        "description": (
            record.get("description")
            or record.get("name")
            or record.get("name_full")
            or Path(file_path).name
        ),
        "date": _normalize_date(
            record.get("document_date")
            or record.get("date")
            or record.get("created_dt")
            or record.get("effective_dt")
        ),
    }

    tags = record.get("metatags") or record.get("tags")
    if tags:
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace(",", "|").split("|") if t.strip()]
        data["metatags"] = json.dumps(tags)

    data = _strip_empty(data)
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    log.info("POST %s multipart_data=%s file=%s mime=%s", url, data, file_path, mime_type)

    try:
        with open(file_path, "rb") as f:
            files = {
                "document": (Path(file_path).name, f, mime_type)
            }
            resp = requests.post(
                url,
                headers=_multipart_headers(token),
                data=data,
                files=files,
                timeout=60,
            )

        log.info("Document upload response: %d — %s", resp.status_code, resp.text[:800])

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

    if not is_patient and not patient_id:
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

    if is_patient:
        existing_id = _find_existing_patient(payload, token)
        if existing_id:
            return {
                "success": True,
                "status_code": 200,
                "drchrono_id": existing_id,
                "error": "",
                "already_exists": True,
                "message": f"Patient already exists in DrChrono ID={existing_id}",
            }

    log.info("POST %s payload=%s", url, payload)

    try:
        resp = requests.post(url, json=payload, headers=_json_headers(token), timeout=20)
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:800])

        if resp.status_code in (200, 201):
            body = resp.json()
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

        if not tok_obj or not tok_obj.access_token:
            raise HTTPException(status_code=401, detail="No DrChrono token. Please authenticate first.")

        token = tok_obj.access_token

        if not doctor_id and tok_obj.doctor_id:
            try:
                doctor_id = int(tok_obj.doctor_id)
            except (TypeError, ValueError):
                pass

    push_order = [
        "patient",
        "patients",
        "encounter",
        "encounters",
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
        "observation",
        "observations",
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

    for key in ordered:
        records = source.get(key, [])

        if not records:
            continue

        if req.dry_run:
            stats[key] = _simulate_push(records, key)
            continue

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