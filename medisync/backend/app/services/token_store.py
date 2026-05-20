# """
# MediSync — In-Memory Token Store
# Thread-safe singleton for storing DrChrono OAuth tokens during a session.
# Extend to encrypted DB persistence for multi-user support.
# """

# import time
# from typing import Optional
# from app.models.schemas import TokenData


# class _TokenStore:
#     def __init__(self):
#         self._data: Optional[TokenData] = None

#     def set_token(
#         self,
#         access_token: str,
#         expires_in: int,
#         refresh_token: Optional[str] = None,
#         doctor_id: Optional[str] = None,
#         doctor_name: Optional[str] = None,
#     ) -> None:
#         self._data = TokenData(
#             access_token=access_token,
#             refresh_token=refresh_token,
#             expires_at=time.time() + expires_in,
#             doctor_id=doctor_id,
#             doctor_name=doctor_name,
#         )

#     def get_token(self) -> Optional[TokenData]:
#         return self._data

#     def is_valid(self) -> bool:
#         if self._data is None:
#             return False
#         # Consider expired if < 60s remain
#         return time.time() < (self._data.expires_at - 60)

#     def seconds_until_expiry(self) -> Optional[int]:
#         if self._data is None:
#             return None
#         remaining = int(self._data.expires_at - time.time())
#         return max(0, remaining)

#     def clear(self) -> None:
#         self._data = None


# # Singleton instance — imported by all routes
# token_store = _TokenStore()




"""
MediSync — In-Memory Token Store
Thread-safe singleton for storing DrChrono OAuth tokens during a session.
Extend to encrypted DB persistence for multi-user support.
"""
import time
from typing import Optional
from app.models.schemas import TokenData


class _TokenStore:
    def __init__(self):
        self._data: Optional[TokenData] = None

    def set_token(
        self,
        access_token: str,
        expires_in: int,
        refresh_token: Optional[str] = None,
        doctor_id: Optional[str] = None,
        doctor_name: Optional[str] = None,
    ) -> None:
        self._data = TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            doctor_id=doctor_id,
            doctor_name=doctor_name,
        )

    def get_token(self) -> Optional[TokenData]:
        return self._data

    def is_valid(self) -> bool:
        if self._data is None:
            return False
        # Consider expired if < 60s remain
        return time.time() < (self._data.expires_at - 60)

    def seconds_until_expiry(self) -> Optional[int]:
        if self._data is None:
            return None
        remaining = int(self._data.expires_at - time.time())
        return max(0, remaining)

    def clear(self) -> None:
        self._data = None


# Singleton instance — import this directly in all routes:
# from app.services.token_store import token_store
token_store = _TokenStore()