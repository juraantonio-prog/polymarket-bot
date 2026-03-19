"""
HMAC-SHA256 request signing for authenticated Polymarket CLOB endpoints.
Skeleton — disabled in v1.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional


class HMACSigner:
    """Signs HTTP requests for authenticated CLOB endpoints."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> None:
        self._api_key = api_key
        self._api_secret = api_secret

    @classmethod
    def from_env(cls) -> "HMACSigner":
        import os
        return cls(
            api_key=os.getenv("POLYMARKET_API_KEY"),
            api_secret=os.getenv("POLYMARKET_API_SECRET"),
        )

    def sign(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Return auth headers for a CLOB request."""
        if not self._api_key or not self._api_secret:
            raise RuntimeError("HMAC credentials not loaded — live mode only")
        ts = str(int(time.time() * 1000))
        message = ts + method.upper() + path + body
        sig = hmac.new(
            self._api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "POLY-API-KEY": self._api_key,
            "POLY-TIMESTAMP": ts,
            "POLY-SIGNATURE": sig,
        }
