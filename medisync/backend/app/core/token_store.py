"""
MediSync — In-Memory Token Store
Thread-safe singleton for storing EMR OAuth tokens during a session.
Extend to encrypted DB persistence for multi-user support.
"""
from loguru import logger as loguru_logger
import time
from typing import Optional
from app.core.schemas import TokenData


class _TokenStore:
    """In-memory storage for one EMR token session.

    Parameters:
        None.

    Use case:
        Keeps the current access token, refresh token, provider ID, and expiry in
        memory so push routes can authenticate outbound EMR calls.
    """

    def __init__(self):
        """Create an empty token store.

        Parameters:
            None.

        Use case:
            Initializes backend state before a user authenticates.
        """
        try:
            self._data: Optional[TokenData] = None
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.__init__: {exc}")
            raise

    def set_token(
        self,
        access_token: str,
        expires_in: int,
        refresh_token: Optional[str] = None,
        doctor_id: Optional[str] = None,
        doctor_name: Optional[str] = None,
        target_system: str = "EMR",
    ) -> None:
        """Store token metadata for the active backend session.

        Parameters:
            access_token: EMR OAuth access token.
            expires_in: Number of seconds until the access token expires.
            refresh_token: Optional refresh token for renewing access.
            doctor_id: Provider/doctor ID associated with this token.
            doctor_name: Provider display name.
            target_system: Configured EMR display name.

        Use case:
            Called after OAuth exchange, manual token entry, or token refresh.
        """
        try:
            self._data = TokenData(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=time.time() + expires_in,
                doctor_id=doctor_id,
                doctor_name=doctor_name,
                target_system=target_system,
            )
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.set_token: {exc}")
            raise

    def get_token(self) -> Optional[TokenData]:
        """Return the currently stored token data.

        Parameters:
            None.

        Use case:
            Used by push/auth routes to retrieve access token and provider context.
        """
        try:
            return self._data
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.get_token: {exc}")
            raise

    def is_valid(self) -> bool:
        """Return whether a usable access token is stored.

        Parameters:
            None.

        Use case:
            Guards routes that require authentication and treats tokens expiring in
            less than 60 seconds as invalid.
        """
        try:
            if self._data is None:
                return False
            # Consider expired if < 60s remain
            return time.time() < (self._data.expires_at - 60)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.is_valid: {exc}")
            raise

    def seconds_until_expiry(self) -> Optional[int]:
        """Return remaining token lifetime in seconds.

        Parameters:
            None.

        Use case:
            Displayed in auth status responses and used by UI/session indicators.
        """
        try:
            if self._data is None:
                return None
            remaining = int(self._data.expires_at - time.time())
            return max(0, remaining)
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.seconds_until_expiry: {exc}")
            raise

    def clear(self) -> None:
        """Remove stored token data.

        Parameters:
            None.

        Use case:
            Used on logout/disconnect or test cleanup to reset auth state.
        """
        try:
            self._data = None
        except Exception as exc:
            loguru_logger.error(f"Exception in {__name__}.clear: {exc}")
            raise


# Singleton instance — import this directly in all routes:
# from app.services.token_store import token_store
token_store = _TokenStore()
