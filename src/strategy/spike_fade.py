"""
Spike-fade detector.
Detects sudden price spikes and generates fade signals.
All thresholds come from config/strategy.yaml.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.data.price_tracker import MarketSnapshot
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class SpikeFadeSignal:
    market_id: str
    token_id: str
    direction: str              # 'fade_yes' | 'fade_no'
    entry_price: float
    spike_magnitude: float      # absolute price change
    spike_magnitude_pct: float  # fractional price change
    volume_spike_ratio: float   # current vol / avg vol
    days_to_expiry: float
    detected_at: datetime = None

    def __post_init__(self) -> None:
        if self.detected_at is None:
            self.detected_at = datetime.now(tz=timezone.utc)


class SpikeFadeDetector:
    """Detects spike-fade opportunities from price snapshots."""

    def __init__(self, config: Config) -> None:
        sf = config.get("spike_fade", default={})
        self._min_spike = float(sf.get("min_spike_magnitude", 0.05))
        self._baseline_window = float(sf.get("baseline_window_seconds", 600))
        self._vol_spike_mult = float(sf.get("volume_spike_multiplier", 2.0))
        self._min_volume_usd = float(sf.get("min_volume_usd", 5000))
        self._cooldown_sec = float(sf.get("cooldown_seconds_per_market", 300))
        self._min_days = float(config.get("expiry", "min_days_to_expiry", default=30))
        self._max_spread = float(config.get("filters", "max_spread", default=0.10))
        # market_id -> timestamp of last emitted signal
        self._last_signal_ts: dict[str, float] = {}

    def detect(
        self,
        snapshot: MarketSnapshot,
        days_to_expiry: float,
        current_volume_usd: float,
        market_volume_usd: float = 0.0,
        spread: float = 0.0,
    ) -> Optional[SpikeFadeSignal]:
        """
        Evaluate a market snapshot for spike-fade signal.
        Returns signal or None.
        """
        magnitude_pct = abs(snapshot.price_change_pct)
        magnitude_pp = round(magnitude_pct * 100, 2)
        gap_pp = round((self._min_spike - magnitude_pct) * 100, 2)

        # Cooldown filter — prevent multiple signals on the same market within cooldown window
        now = time.time()
        last_ts = self._last_signal_ts.get(snapshot.market_id, 0.0)
        elapsed = now - last_ts
        if elapsed < self._cooldown_sec:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="cooldown",
                elapsed_sec=round(elapsed, 0),
                cooldown_sec=self._cooldown_sec,
            )
            return None

        # Time-to-expiry filter
        if days_to_expiry < self._min_days:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="expiry",
                days=round(days_to_expiry, 1),
                min_days=self._min_days,
                price=round(snapshot.current_price, 4),
                move_pp=magnitude_pp,
                gap_to_threshold_pp=gap_pp,
            )
            return None

        # Spread filter
        if spread > self._max_spread:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="spread",
                spread=round(spread, 4),
                max_spread=self._max_spread,
                price=round(snapshot.current_price, 4),
                move_pp=magnitude_pp,
                gap_to_threshold_pp=gap_pp,
            )
            return None

        # Minimum volume filter — use Gamma API market volume, not WS tick sizes
        if market_volume_usd < self._min_volume_usd:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="market_volume",
                market_vol_usd=round(market_volume_usd, 0),
                min_vol_usd=self._min_volume_usd,
                price=round(snapshot.current_price, 4),
                move_pp=magnitude_pp,
                gap_to_threshold_pp=gap_pp,
            )
            return None

        # Magnitude filter
        if magnitude_pct < self._min_spike:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="magnitude",
                price=round(snapshot.current_price, 4),
                baseline=round(snapshot.baseline_price, 4),
                move_pp=magnitude_pp,
                threshold_pp=round(self._min_spike * 100, 2),
                gap_to_threshold_pp=gap_pp,
                ticks=snapshot.tick_count,
            )
            return None

        # Volume spike filter — compare current tick vs rolling avg per tick
        vol_ratio = (current_volume_usd / snapshot.avg_volume_per_tick) if snapshot.avg_volume_per_tick > 0 else 0.0
        if vol_ratio < self._vol_spike_mult:
            log.info(
                "spike_fade.no_signal",
                market=snapshot.market_id,
                reason="vol_spike",
                vol_ratio=round(vol_ratio, 2),
                required_ratio=self._vol_spike_mult,
                tick_vol_usd=round(current_volume_usd, 2),
                avg_tick_vol_usd=round(snapshot.avg_volume_per_tick, 2),
                price=round(snapshot.current_price, 4),
                move_pp=magnitude_pp,
            )
            return None

        # Determine direction: if price spiked UP → fade = sell YES (fade_yes)
        direction = "fade_yes" if snapshot.price_change_pct > 0 else "fade_no"

        signal = SpikeFadeSignal(
            market_id=snapshot.market_id,
            token_id=snapshot.token_id,
            direction=direction,
            entry_price=snapshot.current_price,
            spike_magnitude=abs(snapshot.price_change),
            spike_magnitude_pct=magnitude_pct,
            volume_spike_ratio=vol_ratio,
            days_to_expiry=days_to_expiry,
        )
        self._last_signal_ts[snapshot.market_id] = time.time()
        log.info(
            "spike_fade.signal",
            market=snapshot.market_id,
            direction=direction,
            magnitude_pct=round(magnitude_pct, 4),
            vol_ratio=round(vol_ratio, 2),
            cooldown_until=round(self._cooldown_sec, 0),
        )
        return signal
