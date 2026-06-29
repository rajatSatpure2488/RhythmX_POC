"""
Simple EHR API handler for GET and POST calls.

This module builds authorization headers from TokenHandler and sends JSON
payloads to EHR APIs using settings loaded in dr_chrono/config.py.
"""

from urllib.parse import urljoin

import requests
from loguru import logger

try:
    from .core.config import settings
    from .core.get_token import TokenHandler
except ImportError:
    from  dr_chrono.backend.core.config import settings
    from  dr_chrono.backend.core.get_token import TokenHandler


class EHRApiError(Exception):
    def __init__(self, message, status_code=None, detail=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


ACCESS_TOKEN_KEY = "access_token"


class EHRApiHandler:
    def __init__(self, ehr_settings=settings, token_handler=None):
        self.settings = ehr_settings
        self.token_handler = token_handler or TokenHandler(self.settings)
        logger.debug("EHRApiHandler initialized for EHR={}", self.settings.EHR_NAME)

    def build_url(self, endpoint):
        logger.debug("Building EHR URL for endpoint={}", endpoint)
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return urljoin(self.settings.EHR_API_BASE_URL.rstrip("/") + "/", endpoint.lstrip("/"))

    def build_authorization_headers(self):
        logger.debug("Building authorization headers.")
        token = self.token_handler.get_token()
        if not token:
            logger.error("Token not available for EHR API call.")
            raise EHRApiError("Token not available for EHR API call.")

        access_token = token.get(ACCESS_TOKEN_KEY)
        if not access_token:
            logger.error("Access token missing in token file.")
            raise EHRApiError("Access token missing in token file.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        if self.settings.EHR_API_VERSION:
            headers["X-DRC-API-Version"] = self.settings.EHR_API_VERSION

        logger.debug("Authorization headers built with keys={}", list(headers.keys()))
        return headers

    def read_response(self, response):
        logger.debug("EHR response status={}", response.status_code)
        if response.status_code < 400:
            logger.success("EHR API call succeeded.")
            if not response.text:
                return None
            try:
                return response.json()
            except ValueError:
                return response.text

        try:
            detail = response.json()
        except ValueError:
            detail = response.text

        logger.error("EHR API call failed. status={} detail={}", response.status_code, detail)
        raise EHRApiError(
            message=f"EHR API call failed with status {response.status_code}",
            status_code=response.status_code,
            detail=detail,
        )

    def get(self, endpoint, params=None):
        logger.info("GET EHR endpoint={}", endpoint)
        response = requests.get(
            url=self.build_url(endpoint),
            headers=self.build_authorization_headers(),
            params={key: value for key, value in (params or {}).items() if value is not None},
            timeout=self.settings.EHR_REQUEST_TIMEOUT_SECONDS,
        )
        return self.read_response(response)

    def post(self, endpoint, payload=None, params=None):
        logger.info("POST EHR endpoint={}", endpoint)
        logger.debug(
            "POST payload keys={} params keys={}",
            list((payload or {}).keys()) if isinstance(payload, dict) else [],
            list((params or {}).keys()),
        )
        response = requests.post(
            url=self.build_url(endpoint),
            headers=self.build_authorization_headers(),
            params={key: value for key, value in (params or {}).items() if value is not None},
            json=payload or {},
            timeout=self.settings.EHR_REQUEST_TIMEOUT_SECONDS,
        )
        return self.read_response(response)
