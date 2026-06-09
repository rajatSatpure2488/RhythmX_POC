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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core import config
from app.routes.upload import _SESSION
from app.services.token_store import token_store
from app.services.drchrono_proxy import drchrono_post_document
log = logging.getLogger("medisync.push")

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
    "observation": "documents",
    "observations": "documents",
    "observation_note": "documents",
    "observation_notes": "documents",
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
    raw = str(value or default).lower()
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
        "gender": _map_gender(
            record.get("gender")
            or record.get("sex")
            or record.get("gender_administrative")
            or record.get("administrative_gender")
        ) or "Other",
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
    """
    Map to DrChrono /problems.
    Verified field names (from live DrChrono 400 responses):
      Required: patient, doctor, description
      Optional: icd_code, date_onset, status ('active' / 'resolved' — lowercase only)
    """
    description = (
        record.get("description")
        or record.get("name")
        or record.get("name_full")
        or _codeable_text(record.get("code"))
        or record.get("condition_name")
        or ""
    )

    payload = {
        "patient": int(patient_id) if patient_id else None,
        "doctor": int(doctor_id) if doctor_id else None,
        "description": description,
        "status": _condition_status(record),
    }

    icd_code = (
        record.get("icd_code")
        or record.get("code_value")
        or record.get("icd")
        or (record.get("code") if isinstance(record.get("code"), str) else None)
        or _codeable_code(record.get("code"))
    )
    if icd_code:
        payload["icd_code"] = str(icd_code).strip()

    onset = (
        record.get("date_onset")
        or record.get("onsetDateTime")
        or record.get("start_dt")
        or record.get("onset_date")
        or record.get("diagnosis_date")
        or record.get("date_diagnosis")
    )
    if onset:
        payload["date_onset"] = _normalize_date(onset)

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

    duration = 30
    try:
        duration = int(_first_present(record, "duration", "minutesDuration", "length_minutes", default=30) or 30)
    except (ValueError, TypeError):
        pass

    # DrChrono caps "reason" at 100 chars — anything longer 400s. Truncate safely.
    reason = _first_present(record, "reason", "encounter_type", "description", "chief_complaint")
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

    reaction = record.get("reaction") or record.get("reaction_manifestation")
    if isinstance(reaction, list) and reaction:
        reaction = _codeable_text((reaction[0] or {}).get("manifestation"))
    if reaction:
        payload["reaction"] = str(reaction)

    notes = _first_present(record, "notes", "note", "allergy_note")
    if notes:
        payload["notes"] = str(notes)

    snomed_reaction = record.get("snomed_reaction")
    if snomed_reaction:
        payload["snomed_reaction"] = str(snomed_reaction)

    raw_code = record.get("code")
    if isinstance(raw_code, dict):
        raw_code = _codeable_code(raw_code)
    raw_code = str(raw_code or "").strip()
    code_vocab = str(record.get("code_vocab") or "").upper()
    if raw_code:
        if "SNOMED" in code_vocab:
            payload["snomed_code"] = raw_code
        elif "RXNORM" in code_vocab or code_vocab.startswith("RX"):
            payload["rxnorm"] = raw_code

    rxnorm = record.get("rxnorm")
    if rxnorm:
        payload["rxnorm"] = str(rxnorm)

    vs_raw = _first_present(record, "verification_status", "verificationStatus", default="confirmed")
    if isinstance(vs_raw, dict):
        vs_raw = _codeable_text(vs_raw) or "confirmed"
    payload["verification_status"] = str(vs_raw).strip().lower() or "confirmed"

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
        "description": _first_present(record, "description", "service_name", "name_full", default=_codeable_text(record.get("code"))),
        "status": _first_present(record, "status", default="active"),
        "order_date": _normalize_date(_first_present(record, "order_date", "order_dt", "authored_dt", "authoredOn")),
    }

    return _strip_empty(payload)


def _map_coverage(record: dict, doctor_id: Optional[int], patient_id: Optional[int]) -> dict:
    payload = {
        "patient": int(patient_id) if patient_id else None,
        "insurance_company": _first_present(record, "insurance_company", "payer_name", "payor_name"),
        "insurance_plan_name": _first_present(record, "insurance_plan_name", "plan_name"),
        "insurance_id_number": _first_present(record, "insurance_id_number", "member_id", "subscriber_id"),
        "insurance_group_number": _first_present(record, "insurance_group_number", "group_id", "group_number"),
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


def _map_record(resource_key: str, record: dict, doctor_id: Optional[int] = None, patient_id: Optional[int] = None) -> dict:
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
        s = (s or "").encode("latin-1", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Build (font, size, text) lines, wrapping each by an approximate char width.
    raw: list[tuple[str, int, str]] = []
    raw.append(("F2", 16, title or "Diagnostic Report"))
    raw.append(("F1", 6, ""))                 # spacer
    for label, val in (("Date", report_date), *meta.items()):
        if val:
            raw.append(("F1", 10, f"{label}: {val}"))
    raw.append(("F1", 6, ""))                 # spacer
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
    body_text = _first_present(
        record, "test_notes", "conclusion_text", "notes", "conclusion",
        "clinical_information", "text",
    )
    meta = {
        "Report ID": _first_present(record, "source_report_id", "diagnostic_report_id", "id"),
        "ICD-10": _first_present(record, "icd10_codes", "conclusion_code"),
        "Status": _first_present(record, "order_status", "status"),
    }

    try:
        pdf_bytes = _render_report_pdf(description, report_date, body_text, meta)
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
# Clinical notes → DrChrono yellow_notepad
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


def _format_vitals(text: str) -> str:
    """Regex-parse a free-text vital_signs string into the fixed 9-field line.
    Missing vitals render as 'Not provided' so the layout is always consistent
    and the push never breaks on incomplete data."""
    parts = []
    for label, pattern, unit in _VITAL_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            if label == "BP":
                val = re.sub(r"\s*", "", m.group(1))
            elif label == "Temperature":
                val = _temp_to_fahrenheit(m.group(1).strip())
            else:
                val = m.group(1).strip()
            parts.append(f"{label}: {val}{unit}")
        else:
            parts.append(f"{label}: Not provided")
    return " | ".join(parts)


def _build_note_content(note: dict) -> str:
    """Assemble the yellow_notepad content string: clinical narrative only.

    Vitals are pushed to the appointment's vitals section (PATCH), so they are NOT
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
        log.warning("yellow_notepad token refresh failed: %s", e)
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

    return {"vitals": vitals, "status": "Checked In"}


def _patch_appointment_vitals(appt_id, payload: dict, token: str) -> dict:
    """PATCH structured vitals onto the appointment. Success = 204 No Content.
    Refreshes the token once on 401 and retries up to 3x on 429/5xx (2s backoff)."""
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
        if resp.status_code == 204:
            # Verify DrChrono actually persisted the vitals: a 204 is returned even
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
            return {"ok": True, "status_code": 204, "error": ""}
        return {"ok": False, "status_code": resp.status_code, "error": resp.text[:500]}
    return {"ok": False, "status_code": 0, "error": "retries exhausted"}


def _push_clinical_note_yellow_notepad(
    note: dict, token: str, doctor_id: Optional[int], patient_id: Optional[int]
) -> dict:
    """Dual push for one clinical note:
      STEP 1 — PATCH vitals to /api/appointments/{appointment_id}  (success = 204)
      STEP 2 — POST the note to /api/yellow_notepad (appointment_id + template_id as
               query params; body holds only `content`).
    Vitals are best-effort (a vitals failure is logged but does not drop the note).
    On 401 the token is refreshed and the request retried.
    """
    appt_id = _resolve_appointment_id(note)
    if not appt_id:
        # Fallback: look the appointment up live from DrChrono by patient + date.
        appt_id = _lookup_appointment_id(token, patient_id, note.get("note_date"))
    if not appt_id:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": "No DrChrono appointment found for this note. Push the patient's "
                         "encounter/appointment first (any run), or ensure the appointment "
                         "exists in DrChrono for that date.",
                "already_exists": False, "retryable": True}

    content = _build_note_content(note)

    # ── STEP 1: PATCH structured vitals onto the appointment ──
    vitals_payload = _build_vitals_payload(note)
    vitals_result = _patch_appointment_vitals(appt_id, vitals_payload, token)
    if vitals_result["ok"]:
        log.info("Vitals PATCH appt=%s -> 204 (%d vitals)", appt_id, len(vitals_payload["vitals"]))
    else:
        log.warning("Vitals PATCH appt=%s -> %s %s", appt_id,
                    vitals_result["status_code"], vitals_result["error"][:200])
    url = f"{config.DRCHRONO_API_BASE}yellow_notepad"
    params = {"appointment_id": str(appt_id), "template_id": TEMPLATE_ID}
    body = {"content": content}

    def _post(tok: str):
        return requests.post(url, params=params, json=body, headers=_json_headers(tok), timeout=30)

    try:
        log.info("POST %s?appointment_id=%s&template_id=%s (note %s)",
                 url, appt_id, TEMPLATE_ID, note.get("source_note_id"))
        resp = _post(token)
        if resp.status_code == 401:
            new_tok = _refresh_access_token()
            if new_tok:
                resp = _post(new_tok)
        log.info("DrChrono response: %d — %s", resp.status_code, resp.text[:400])

        vitals_code = vitals_result["status_code"]
        vitals_tag = "Vitals 204 ✓" if vitals_result["ok"] else f"Vitals failed ({vitals_code}) ✗"
        vitals_note = "" if vitals_result["ok"] else f" | {vitals_tag}"

        if resp.status_code in (200, 201):
            try:
                nid = resp.json().get("id")
            except Exception:
                nid = None
            # Dual status: note pushed; vitals reported alongside (best-effort).
            return {"success": True, "status_code": resp.status_code,
                    "drchrono_id": nid, "error": "", "already_exists": False,
                    "vitals_status": vitals_code,
                    "detail": f"{vitals_tag} · Note {resp.status_code} ✓"}

        # 400 = bad appointment_id / template mismatch — surface the full body.
        return {"success": False, "status_code": resp.status_code, "drchrono_id": None,
                "error": resp.text[:1000] + vitals_note, "already_exists": False,
                "vitals_status": vitals_code, "retryable": resp.status_code >= 500}
    except Exception as e:
        return {"success": False, "status_code": 0, "drchrono_id": None,
                "error": str(e), "already_exists": False}
    finally:
        time.sleep(0.3)  # 300 ms between yellow_notepad requests


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

# DrChrono lab_order_status valid choices do NOT include "Resulted"/"Cancelled".
# "In Progress" is confirmed valid; completed results map to "Reviewed".
_LAB_STATUS_MAP = {
    "final": "Reviewed", "preliminary": "In Progress", "amended": "Reviewed",
    "cancelled": "In Progress", "unknown": "In Progress",
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


def _lab_order_status(status) -> str:
    return _LAB_STATUS_MAP.get(str(status or "").strip().lower(), "In Progress")


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
        "title": _first_present(obs, "name_full", "name_short", "name_rx", "test_name", "code",
                                default="Lab Result"),
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
        "lab_order_status": _lab_order_status(_first_present(obs, "status")),
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

    # Clinical notes are pushed to DrChrono /api/yellow_notepad (template 7520906),
    # with vitals + CC/HPI/Assessment/Plan as the note content. The records arriving
    # here are note-level (aggregated in generate()), and the appointment_id is
    # resolved from appointments pushed earlier in the same run.
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
    # _APPT_ID_MAP persists across runs in this process so notes can resolve
    # appointments pushed in an earlier run; a live DrChrono lookup is the fallback.
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

    _prepare_obs_lab_index(source, ordered)  # index notes; decide merge vs standalone

    def generate():
        stats: dict[str, dict] = {}
        current_patient_id = req.patient_id
        already_exists_total = 0
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

                latency_ms = int((time.time() - t0) * 1000)

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

        summary = {
            "type": "summary",
            "total": sum(s["total"] for s in stats.values()),
            "successful": sum(s["successful"] for s in stats.values()),
            "failed": sum(s["failed"] for s in stats.values()),
            "already_exists": already_exists_total,
            "patient_id": current_patient_id,
            "stats": stats,
        }
        yield json.dumps(summary) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
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
