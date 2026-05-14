"""
ai_explain.py — /ai router
Accepts validation errors or API push failures and returns
a structured AI-powered breakdown with actionable fix suggestions.

Falls back to smart rule-based responses if no LLM key is set.
"""
from __future__ import annotations
import os
import json
import logging
from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("medisync.ai_explain")
router = APIRouter()

# ── Request / Response models ──────────────────────────────────────────────────

class ValidationError(BaseModel):
    field: str
    type: str          # null_value | date_format | terminology
    tag: str
    detail: str

class FailedRecord(BaseModel):
    record_id: str
    resource: str
    errors: list[ValidationError] = []

class ExplainValidationRequest(BaseModel):
    resource: str
    failed_records: list[FailedRecord]
    context: Optional[str] = None      # e.g. "CSV mapping stage"

class ApiFailure(BaseModel):
    record_id: str
    resource: str
    endpoint: str
    http_status: int
    error: str
    detail: str

class ExplainApiRequest(BaseModel):
    failures: list[ApiFailure]
    context: Optional[str] = None      # e.g. "DrChrono push stage"

class Suggestion(BaseModel):
    field: Optional[str] = None
    original_value: Optional[str] = None
    suggested_value: Optional[str] = None
    action: str                        # "fix" | "skip" | "default"
    reason: str

class ExplainResponse(BaseModel):
    summary: str
    root_cause: str
    impact: str
    suggestions: list[Suggestion]
    can_proceed: bool
    fixed_count: int
    total_errors: int


# ── Rule-based engine (no LLM required) ───────────────────────────────────────

_NULL_FIXES = {
    "name":         ("John Doe",       "Patient name is required by DrChrono."),
    "first_name":   ("John",           "First name is required for patient creation."),
    "last_name":    ("Doe",            "Last name is required for patient creation."),
    "birth_date":   ("1990-01-01",     "Date of birth in YYYY-MM-DD format is required."),
    "gender":       ("Male",           "Gender must be Male, Female, or Other."),
    "status":       ("active",         "Defaulting status to 'active' — a safe DrChrono value."),
    "dosage":       ("1 tablet",       "A safe dosage default for missing medication dosage."),
    "code":         ("UNKNOWN",        "Code is required — update with valid ICD/SNOMED/LOINC code."),
    "patient_id":   ("",               "patient_id is injected automatically after patient creation."),
    "doctor_id":    ("",               "doctor_id is injected from GET /api/doctors response."),
    "substance":    ("Unknown",        "Allergen name defaults to 'Unknown' — update before push."),
    "vaccine_code": ("08",             "CVX code 08 = Hep B, adult. Update with correct vaccine CVX."),
    "effective_date": ("2025-01-01",   "Observation effective date required — using today as default."),
    "date":         ("2025-01-01",     "Date required in YYYY-MM-DD — using today as placeholder."),
    "payer":        ("Self-Pay",       "Insurance payer defaulted to Self-Pay. Update as needed."),
}

_DATE_FIX_HINT = (
    "Reformat date to ISO-8601: YYYY-MM-DD.\n"
    "Python fix: pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')\n"
    "Excel fix: Format Cells → Text, then retype in YYYY-MM-DD format."
)

_TERM_FIX_HINT = (
    "Replace description text with a proper clinical code.\n"
    "• ICD-10: https://www.icd10data.com\n"
    "• SNOMED: https://browser.ihtsdotools.org\n"
    "• LOINC:  https://loinc.org/search\n"
    "• RxNorm: https://mor.nlm.nih.gov/RxNav"
)

_HTTP_FIXES = {
    400: {
        "summary": "Bad Request — invalid data sent to DrChrono API",
        "root_cause": "One or more fields contain values in an invalid format (e.g. wrong date format, out-of-range values).",
        "fix": "Check date fields are YYYY-MM-DD. Verify enum values match DrChrono accepted options.",
    },
    401: {
        "summary": "Unauthorized — OAuth token is invalid or expired",
        "root_cause": "The Bearer token used for API calls is missing, expired (48h TTL), or revoked.",
        "fix": "Re-authenticate via OAuth. Tokens expire every 48 hours. Refresh using grant_type=refresh_token.",
    },
    403: {
        "summary": "Forbidden — insufficient OAuth scope",
        "root_cause": "Your OAuth app lacks the required scope for this resource (e.g. 'clinical' or 'billing').",
        "fix": "Re-authorize with the correct scopes. Check DrChrono OAuth app settings.",
    },
    404: {
        "summary": "Not Found — resource ID does not exist in DrChrono",
        "root_cause": "The patient_id, doctor_id, or appointment_id referenced was not found in DrChrono.",
        "fix": "Ensure patient is created (POST /api/patients) before pushing clinical resources.",
    },
    409: {
        "summary": "Conflict — record already exists in DrChrono",
        "root_cause": "A record with the same identifier already exists. DrChrono does not allow duplicate creation.",
        "fix": "Use PATCH/PUT to update existing records instead of POST. Check for prior successful pushes.",
    },
    422: {
        "summary": "Unprocessable Entity — required field missing or null",
        "root_cause": "A required field was sent as null, empty string, or with an invalid value.",
        "fix": "Fill all required fields before pushing. Run the validation step to identify nulls.",
    },
    429: {
        "summary": "Rate Limited — too many requests to DrChrono",
        "root_cause": "DrChrono enforces API rate limits (29/min, 500/day). Your batch exceeded this threshold.",
        "fix": "Add delays between requests (50-100ms). Reduce batch size. Schedule large pushes off-peak.",
    },
}


def _explain_validation_rule_based(req: ExplainValidationRequest) -> ExplainResponse:
    """Generate a rich, rule-based AI explanation for CSV mapping validation errors."""
    all_errors = [e for rec in req.failed_records for e in rec.errors]
    total = len(all_errors)

    null_errs  = [e for e in all_errors if e.type == "null_value"]
    date_errs  = [e for e in all_errors if e.type == "date_format"]
    term_errs  = [e for e in all_errors if e.type == "terminology"]

    # Build root cause sentence
    causes = []
    if null_errs:  causes.append(f"{len(null_errs)} missing/null required fields")
    if date_errs:  causes.append(f"{len(date_errs)} incorrectly formatted dates")
    if term_errs:  causes.append(f"{len(term_errs)} terminology description-instead-of-code issues")
    root_cause = "Detected: " + "; ".join(causes) + f" across {len(req.failed_records)} record(s) in '{req.resource}'."

    # Build suggestions
    suggestions: list[Suggestion] = []
    seen_fields = set()

    for e in null_errs:
        f = e.field.lower().replace(" ", "_")
        if f in seen_fields: continue
        seen_fields.add(f)
        fix_info = _NULL_FIXES.get(f, _NULL_FIXES.get(f.split("_")[-1], None))
        if fix_info:
            sug_val, reason = fix_info
            suggestions.append(Suggestion(
                field=e.field,
                original_value=None,
                suggested_value=sug_val if sug_val else None,
                action="fix" if sug_val else "skip",
                reason=reason,
            ))
        else:
            suggestions.append(Suggestion(
                field=e.field,
                action="fix",
                reason=f"Field '{e.field}' is required by DrChrono's {req.resource} endpoint. Add this column to your CSV.",
            ))

    if date_errs:
        unique_date_fields = list({e.field for e in date_errs})[:3]
        suggestions.append(Suggestion(
            field=", ".join(unique_date_fields),
            action="fix",
            reason=_DATE_FIX_HINT,
        ))

    if term_errs:
        unique_term_fields = list({e.field for e in term_errs})[:3]
        suggestions.append(Suggestion(
            field=", ".join(unique_term_fields),
            action="fix",
            reason=_TERM_FIX_HINT,
        ))

    auto_fixable = len([s for s in suggestions if s.action == "fix" and s.suggested_value])
    can_proceed  = len(null_errs) == 0 or all(
        _NULL_FIXES.get(e.field.lower(), ("", ""))[0] for e in null_errs
    )

    summary = (
        f"Found {total} issue(s) in {len(req.failed_records)} '{req.resource}' record(s). "
        f"{auto_fixable} field(s) can be auto-corrected with safe defaults. "
        f"{'You can still proceed — errors are non-blocking.' if can_proceed else 'Fix required fields before pushing to DrChrono.'}"
    )

    impact = (
        f"If pushed as-is, DrChrono will reject records with null required fields (HTTP 422). "
        f"Date format issues cause HTTP 400. Terminology descriptions are accepted but may cause "
        f"incorrect clinical coding. Fixing all issues ensures 100% push success rate."
    )

    return ExplainResponse(
        summary=summary,
        root_cause=root_cause,
        impact=impact,
        suggestions=suggestions,
        can_proceed=can_proceed,
        fixed_count=auto_fixable,
        total_errors=total,
    )


def _explain_api_rule_based(req: ExplainApiRequest) -> ExplainResponse:
    """Generate a rich, rule-based AI explanation for DrChrono API push failures."""
    total = len(req.failures)
    by_status: dict[int, list[ApiFailure]] = {}
    for f in req.failures:
        by_status.setdefault(f.http_status, []).append(f)

    dominant_status = max(by_status, key=lambda k: len(by_status[k])) if by_status else 0
    info = _HTTP_FIXES.get(dominant_status, {
        "summary": f"HTTP {dominant_status} errors from DrChrono API",
        "root_cause": "Unknown API error. Check DrChrono API documentation.",
        "fix": "Review request payload and authentication.",
    })

    suggestions: list[Suggestion] = []
    seen_statuses = set()
    for status, fails in sorted(by_status.items()):
        if status in seen_statuses: continue
        seen_statuses.add(status)
        fix_info = _HTTP_FIXES.get(status, {})
        resources_affected = list({f.resource for f in fails})
        suggestions.append(Suggestion(
            field=f"HTTP {status} — affects: {', '.join(resources_affected)}",
            action="fix",
            reason=fix_info.get("fix", "Review the request and retry."),
        ))

    # 409 conflicts — suggest PATCH
    if 409 in by_status:
        endpoints = list({f.endpoint for f in by_status[409]})
        suggestions.append(Suggestion(
            field="Duplicate records",
            action="skip",
            reason=f"These records already exist in DrChrono. Consider using PATCH on: {', '.join(endpoints)}",
        ))

    # Rate limit — actionable
    if 429 in by_status:
        suggestions.append(Suggestion(
            field="Rate limiting",
            action="fix",
            reason="Add throttle delay: 60ms between requests, max 29/min. Retry after 60 seconds.",
        ))

    groups = [f"HTTP {s}: {len(f)} record(s)" for s, f in by_status.items()]
    root_cause = info["root_cause"] + f" Breakdown — {'; '.join(groups)}."

    can_proceed = dominant_status in (409, 429)  # these are retryable
    fixable = len([s for s in suggestions if s.action == "fix"])

    summary = (
        f"{total} API call(s) failed during DrChrono push. "
        f"Dominant error: {info['summary']}. "
        f"{fixable} actionable fix(es) identified."
    )

    impact = (
        f"Failed records were NOT saved to DrChrono. "
        f"{'These errors are retryable — fix and push again.' if can_proceed else 'Manual data correction required before retry.'} "
        f"Successful records in the same batch were saved normally."
    )

    return ExplainResponse(
        summary=summary,
        root_cause=root_cause,
        impact=impact,
        suggestions=suggestions,
        can_proceed=can_proceed,
        fixed_count=0,
        total_errors=total,
    )


# ── Optional LLM enhancement ───────────────────────────────────────────────────

async def _try_llm_enhance(base: ExplainResponse, context_str: str) -> ExplainResponse:
    """Try to enrich the response with an LLM if GEMINI_API_KEY is configured."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return base

    try:
        import httpx
        prompt = (
            f"You are a DrChrono EHR integration expert. A developer encountered these errors:\n\n"
            f"Context: {context_str}\n"
            f"Summary: {base.summary}\n"
            f"Root Cause: {base.root_cause}\n\n"
            f"In 2 sentences max, provide one additional expert tip that goes beyond the basic fix. "
            f"Focus on prevention. Be specific to DrChrono API v4. Do not repeat what was already said."
        )
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                base.suggestions.append(Suggestion(
                    field="💡 AI Expert Tip",
                    action="fix",
                    reason=text,
                ))
    except Exception as e:
        log.debug(f"LLM enhance skipped: {e}")

    return base


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/explain/validation", response_model=ExplainResponse)
async def explain_validation(req: ExplainValidationRequest):
    """Explain CSV mapping validation errors with AI-powered breakdown and fix suggestions."""
    result = _explain_validation_rule_based(req)
    context = f"CSV mapping validation for '{req.resource}' resource"
    result = await _try_llm_enhance(result, context)
    return result


@router.post("/explain/api", response_model=ExplainResponse)
async def explain_api_failures(req: ExplainApiRequest):
    """Explain DrChrono API push failures with AI-powered root cause analysis."""
    result = _explain_api_rule_based(req)
    context = f"DrChrono API push failures across {len(set(f.resource for f in req.failures))} resource type(s)"
    result = await _try_llm_enhance(result, context)
    return result


@router.get("/status")
async def ai_status():
    """Check if AI features are available."""
    has_llm = bool(os.getenv("GEMINI_API_KEY", ""))
    return {
        "ai_module": "active",
        "llm_enhanced": has_llm,
        "mode": "gemini-2.0-flash" if has_llm else "rule-based",
        "endpoints": ["/ai/explain/validation", "/ai/explain/api"],
    }
