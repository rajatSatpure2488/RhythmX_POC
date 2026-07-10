"""Shared HTTPX client manager for outbound EMR/API calls.

The backend is mostly synchronous today, so this module provides process-wide
sync and async HTTPX clients. Reusing clients keeps TCP connections pooled
instead of opening a fresh connection for every request.
"""
from __future__ import annotations

from loguru import logger as loguru_logger
import logging
from asyncio import Lock as AsyncLock
from threading import Lock

import httpx


log = logging.getLogger("  http_client")


class HTTPClientManager:
    """Manage shared sync and async HTTPX clients.

    Parameters:
        None.

    Use case:
        Provides one place for connection pooling, timeouts, and shutdown cleanup
        for all outbound EMR/API requests.
    """

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
        """Return the shared synchronous HTTPX client.

        Parameters:
            None.

        Use case:
            Used by synchronous route and push code to reuse open EMR connections
            instead of creating a new TCP connection for every request.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_http_client: {exc}")
            raise

    @classmethod
    async def get_async_http_client(cls) -> httpx.AsyncClient:
        """Return the shared asynchronous HTTPX client.

        Parameters:
            None.

        Use case:
            Available for async routes or future background jobs that need pooled
            outbound HTTP calls.
        """
        try:
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
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_async_http_client: {exc}")
            raise

    @classmethod
    def close_http_client(cls) -> None:
        """Close the shared synchronous HTTPX client.

        Parameters:
            None.

        Use case:
            Called during backend shutdown or cleanup to release pooled EMR
            connections cleanly.
        """
        try:
            with cls._client_lock:
                if cls._client and not cls._client.is_closed:
                    cls._client.close()
                    log.info("Closed shared HTTPX client")

                cls._client = None
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.close_http_client: {exc}")
            raise

    @classmethod
    async def close_async_http_client(cls) -> None:
        """Close the shared asynchronous HTTPX client.

        Parameters:
            None.

        Use case:
            Called during backend shutdown to close async pooled connections.
        """
        try:
            async with cls._async_client_lock:
                if cls._async_client and not cls._async_client.is_closed:
                    await cls._async_client.aclose()
                    log.info("Closed shared async HTTPX client")

                cls._async_client = None
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.close_async_http_client: {exc}")
            raise

    @classmethod
    async def close_all(cls) -> None:
        """Close every shared HTTPX client.

        Parameters:
            None.

        Use case:
            Used by FastAPI shutdown so both sync and async EMR/API connection
            pools are released.
        """
        try:
            cls.close_http_client()
            await cls.close_async_http_client()
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.close_all: {exc}")
            raise
