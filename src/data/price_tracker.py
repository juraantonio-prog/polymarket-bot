"""
Rolling price + volume tracker with in-memory ring buffer.
Thread-safe for asyncio usage.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from src.config import Config
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class PriceTick:
    token_id: str
    price: float
    volume_usd: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class MarketSnapshot:
    market_id: str
    token_id: str
    current_price: float
    baseline_price: float           # avg over baseline_window
    price_change: float             # current - baseline
    price_change_pct: float         # (current - baseline) / baseline
    rolling_volume: float           # sum over window
    avg_volume_per_tick: float
    tick_count: int
    window_seconds: float


class PriceTracker:
    """Maintains rolling price/volume windows per token."""

    def __init__(self, config: Config) -> None:
        pt = config.get("price_tracker", default={})
        self._window_sec = float(pt.get("window_seconds", 3600))
        self._baseline_window = float(
            config.get("spike_fade", "baseline_window_seconds", default=600)
        )
        # Downsample: only keep one tick per interval to avoid deque overflow
        # swamping the baseline window with same-price rapid messages.
        self._min_tick_interval = float(pt.get("min_tick_interval_seconds", 10))
        # token_id -> deque[PriceTick] (unbounded; time-based pruning handles memory)
        self._ticks: dict[str, deque[PriceTick]] = {}
        # token_id -> last accepted tick timestamp
        self._last_tick_ts: dict[str, float] = {}

    def add_tick(self, tick: PriceTick) -> None:
        now = tick.timestamp
        last = self._last_tick_ts.get(tick.token_id, 0.0)
        # Downsample: skip tick if it arrived too soon after the previous one
        if now - last < self._min_tick_interval:
            return
        self._last_tick_ts[tick.token_id] = now

        q = self._ticks.setdefault(tick.token_id, deque())
        q.append(tick)
        # Prune ticks older than the rolling window
        cutoff = now - self._window_sec
        while q and q[0].timestamp < cutoff:
            q.popleft()

    def get_snapshot(self, market_id: str, token_id: str) -> Optional[MarketSnapshot]:
        q = self._ticks.get(token_id)
        if not q or len(q) < 2:
            return None

        now = time.time()
        # All ticks within window
        window_ticks = [t for t in q if t.timestamp >= now - self._window_sec]
        if not window_ticks:
            return None

        current_price = window_ticks[-1].price

        # Baseline: ticks older than recent 30s but within baseline window
        baseline_cutoff = now - self._baseline_window
        recent_cutoff = now - 30
        baseline_ticks = [t for t in window_ticks if baseline_cutoff <= t.timestamp <= recent_cutoff]
        if not baseline_ticks:
            # Fall back to full window avg
            baseline_ticks = window_ticks[:-1]

        if not baseline_ticks:
            return None

        baseline_price = sum(t.price for t in baseline_ticks) / len(baseline_ticks)
        price_change = current_price - baseline_price
        price_change_pct = price_change / baseline_price if baseline_price else 0.0
        rolling_volume = sum(t.volume_usd for t in window_ticks)
        avg_vol = rolling_volume / len(window_ticks)

        return MarketSnapshot(
            market_id=market_id,
            token_id=token_id,
            current_price=current_price,
            baseline_price=baseline_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            rolling_volume=rolling_volume,
            avg_volume_per_tick=avg_vol,
            tick_count=len(window_ticks),
            window_seconds=self._window_sec,
        )

    def has_token(self, token_id: str) -> bool:
        return token_id in self._ticks and bool(self._ticks[token_id])

    def token_ids(self) -> list[str]:
        return list(self._ticks.keys())
