"""Shared HTTPX client manager for outbound EMR/API calls.

The backend is mostly synchronous today, so this module provides process-wide
sync and async HTTPX clients. Reusing clients keeps TCP connections pooled
instead of opening a fresh connection for every request.
"""

from __future__ import annotations

import logging
from asyncio import Lock as AsyncLock
from threading import Lock

import httpx

log = logging.getLogger("medisync.http_client")


class HTTPClientManager:
    """Manages shared sync and async HTTPX clients."""

    _client: httpx.Client | None = None
    _async_client: httpx.AsyncClient | None = None

    _client_lock = Lock()
    _async_client_lock = AsyncLock()

    DEFAULT_TIMEOUT = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=30.0,
        pool=10.0,
    )

    DEFAULT_LIMITS = httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30.0,
    )

    @classmethod
    def get_http_client(cls) -> httpx.Client:
        """Return the shared sync HTTPX client, creating it on first use."""
        if cls._client and not cls._client.is_closed:
            return cls._client

        with cls._client_lock:
            if cls._client is None or cls._client.is_closed:
                cls._client = httpx.Client(
                    timeout=cls.DEFAULT_TIMEOUT,
                    limits=cls.DEFAULT_LIMITS,
                    follow_redirects=True,
                )
                log.info("Initialized shared HTTPX client")

            return cls._client

    @classmethod
    async def get_async_http_client(cls) -> httpx.AsyncClient:
        """Return the shared async HTTPX client, creating it on first use."""
        if cls._async_client and not cls._async_client.is_closed:
            return cls._async_client

        async with cls._async_client_lock:
            if cls._async_client is None or cls._async_client.is_closed:
                cls._async_client = httpx.AsyncClient(
                    timeout=cls.DEFAULT_TIMEOUT,
                    limits=cls.DEFAULT_LIMITS,
                    follow_redirects=True,
                )
                log.info("Initialized shared async HTTPX client")

            return cls._async_client

    @classmethod
    def close_http_client(cls) -> None:
        """Close the shared sync HTTPX client and release pooled connections."""
        with cls._client_lock:
            if cls._client and not cls._client.is_closed:
                cls._client.close()
                log.info("Closed shared HTTPX client")

            cls._client = None

    @classmethod
    async def close_async_http_client(cls) -> None:
        """Close the shared async HTTPX client and release pooled connections."""
        async with cls._async_client_lock:
            if cls._async_client and not cls._async_client.is_closed:
                await cls._async_client.aclose()
                log.info("Closed shared async HTTPX client")

            cls._async_client = None

    @classmethod
    async def close_all(cls) -> None:
        """Close both sync and async shared HTTPX clients."""
        cls.close_http_client()
        await cls.close_async_http_client()