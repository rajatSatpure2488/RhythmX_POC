"""DrChrono API client that reads endpoints from mappers.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

TokenProvider = Callable[[], str]


class DrChronoMapperClient:
    def __init__(
        self,
        access_token: Optional[str] = None,
        token_provider: Optional[TokenProvider] = None,
        mapper_config_path: Optional[Path] = None,
        api_base: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.access_token = access_token
        self.token_provider = token_provider
        self.mapper_config_path = mapper_config_path or Path(__file__).with_name("mappers.json")
        self.api_base = api_base or os.getenv("DRCHRONO_API_BASE", "https://app.drchrono.com/api/")
        self.api_version = api_version or os.getenv("DRCHRONO_API_VERSION", "v4")
        self.timeout = timeout or float(os.getenv("DRCHRONO_TIMEOUT", "30"))
        self._configs = self._load_mapper_configs()

    def get_category(self, category_name: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self.get(self.category_endpoint(category_name), params=params)

    def post_category(self, category_name: str, payload: dict[str, Any]) -> Any:
        return self.post(self.category_endpoint(category_name), payload)

    def get_resource(self, resource_type: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self.get(self.resource_endpoint(resource_type), params=params)

    def post_resource(self, resource_type: str, payload: dict[str, Any]) -> Any:
        return self.post(self.resource_endpoint(resource_type), payload)

    def category_endpoint(self, category_name: str) -> str:
        return self._normalize_endpoint(self._config_by("category_name", category_name).get("category_api", ""))

    def resource_endpoint(self, resource_type: str) -> str:
        return self._normalize_endpoint(self._config_by("fhir_resource_type", resource_type).get("category_api", ""))

    def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self._json(self.request("GET", endpoint, params=params))

    def post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        return self._json(self.request("POST", endpoint, json_body=payload))

    def request(self, method: str, endpoint: str, params: Optional[dict[str, Any]] = None, json_body: Optional[dict[str, Any]] = None) -> httpx.Response:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method,
                self._url(endpoint),
                headers=self._headers(self._access_token()),
                params={k: v for k, v in (params or {}).items() if v is not None} or None,
                json=json_body,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"DrChrono API error: {response.status_code} {response.text[:500]}")
        return response

    def _load_mapper_configs(self) -> list[dict[str, Any]]:
        with self.mapper_config_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _config_by(self, key: str, value: str) -> dict[str, Any]:
        for config in self._configs:
            if config.get(key) == value and config.get("implemented", True):
                return config
        raise KeyError(f"No implemented mapper config found for {key}={value}")

    def _access_token(self) -> str:
        token = self.access_token or (self.token_provider() if self.token_provider else "")
        if not token:
            raise RuntimeError("DrChrono OAuth access token is required.")
        return token

    def _headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-DRC-API-Version": self.api_version,
        }

    def _url(self, endpoint: str) -> str:
        return f"{self.api_base.rstrip('/')}/{self._normalize_endpoint(endpoint)}"

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        endpoint = endpoint.strip().lstrip("/")
        return endpoint.removeprefix("api/")

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        return response.json() if response.content else {}
