"""
Polygon wallet management.
Private key loaded from environment ONLY — never hardcoded.
Skeleton implementation — live trading disabled in v1.
"""
from __future__ import annotations

import os
from typing import Optional

from src.logger import get_logger

log = get_logger(__name__)


class Wallet:
    """Manages a Polygon EOA wallet for Polymarket order signing."""

    def __init__(self) -> None:
        self._private_key: Optional[str] = None
        self._address: Optional[str] = None
        self._loaded = False

    def load_from_env(self) -> None:
        """Load private key from POLYMARKET_PRIVATE_KEY env var."""
        key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
        if not key:
            log.warning("wallet.no_key", msg="POLYMARKET_PRIVATE_KEY not set — auth disabled")
            return
        if not key.startswith("0x"):
            key = "0x" + key
        # Lazy import eth_account only when key is present
        try:
            from eth_account import Account  # type: ignore
            acct = Account.from_key(key)
            self._private_key = key
            self._address = acct.address
            self._loaded = True
            log.info("wallet.loaded", address=self._address)
        except Exception as exc:
            log.error("wallet.load_failed", error=str(exc))
            raise

    @property
    def address(self) -> str:
        if not self._address:
            raise RuntimeError("Wallet not loaded — call load_from_env() first")
        return self._address

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def sign_message(self, message: bytes) -> str:
        """Sign arbitrary bytes. Only available when key is loaded."""
        if not self._loaded or not self._private_key:
            raise RuntimeError("Wallet not loaded")
        from eth_account import Account  # type: ignore
        signed = Account.signHash(message, private_key=self._private_key)
        return signed.signature.hex()
