"""
CLOB REST client with token-bucket rate limiter and exponential backoff on 429.
All URLs from config.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.config import Config
from src.logger import get_logger

log = get_logger(__name__)


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate_per_minute: int) -> None:
        self._rate = rate_per_minute / 60.0  # tokens/sec
        self._capacity = float(rate_per_minute)
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            wait = (tokens - self._tokens) / self._rate
        await asyncio.sleep(wait)
        async with self._lock:
            self._tokens = max(0.0, self._tokens - tokens)


class CLOBClient:
    """Async HTTP client for the Polymarket CLOB REST API."""

    def __init__(self, config: Config) -> None:
        self._base = config.clob_base_url
        rl = config.get("rate_limiter", default={})
        self._bucket = TokenBucket(rl.get("orders_per_minute", 60))
        self._backoff_base = float(rl.get("backoff_base_seconds", 1.0))
        self._backoff_max = float(rl.get("backoff_max_seconds", 60.0))
        self._backoff_mult = float(rl.get("backoff_multiplier", 2.0))
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "CLOBClient":
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
        auth_headers: dict | None = None,
        _attempt: int = 0,
    ) -> Any:
        assert self._client, "Client not started"
        await self._bucket.acquire()
        headers = dict(auth_headers or {})
        t0 = time.monotonic()
        try:
            resp = await self._client.request(method, path, params=params, json=json, headers=headers)
            latency_ms = (time.monotonic() - t0) * 1000
            log.debug("clob.request", method=method, path=path, status=resp.status_code, latency_ms=round(latency_ms, 1))

            if resp.status_code == 429:
                delay = min(self._backoff_base * (self._backoff_mult ** _attempt), self._backoff_max)
                log.warning("clob.rate_limited", attempt=_attempt, retry_in=delay)
                await asyncio.sleep(delay)
                return await self._request(method, path, params, json, auth_headers, _attempt + 1)

            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            log.error("clob.http_error", path=path, status=exc.response.status_code)
            raise

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """Fetch the orderbook for a token."""
        return await self.get("/book", params={"token_id": token_id})

    async def get_last_trade_price(self, token_id: str) -> float | None:
        """Get last traded price for a token."""
        try:
            data = await self.get("/last-trade-price", params={"token_id": token_id})
            price = data.get("price") if isinstance(data, dict) else None
            return float(price) if price is not None else None
        except Exception:
            return None

    async def get_midpoint(self, token_id: str) -> float | None:
        """Get midpoint price."""
        try:
            data = await self.get("/midpoint", params={"token_id": token_id})
            mid = data.get("mid") if isinstance(data, dict) else None
            return float(mid) if mid is not None else None
        except Exception:
            return None

    async def get_spread(self, token_id: str) -> dict[str, float] | None:
        """Get bid-ask spread."""
        try:
            data = await self.get("/spread", params={"token_id": token_id})
            return {
                "bid": float(data.get("bid", 0)),
                "ask": float(data.get("ask", 0)),
                "spread": float(data.get("spread", 0)),
            }
        except Exception:
            return None
