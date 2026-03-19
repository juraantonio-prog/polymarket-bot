"""
Spike-fade detector.
Detects sudden price spikes and generates fade signals.
All thresholds come from config/strategy.yaml.
"""
from __future__ import annotations

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
        self._min_days = float(config.get("expiry", "min_days_to_expiry", default=30))
        self._max_spread = float(config.get("filters", "max_spread", default=0.10))

    def detect(
        self,
        snapshot: MarketSnapshot,
        days_to_expiry: float,
        current_volume_usd: float,
        spread: float = 0.0,
    ) -> Optional[SpikeFadeSignal]:
        """
        Evaluate a market snapshot for spike-fade signal.
        Returns signal or None.
        """
        # Time-to-expiry filter
        if days_to_expiry < self._min_days:
            log.debug("spike_fade.reject_expiry", market=snapshot.market_id, days=days_to_expiry)
            return None

        # Spread filter
        if spread > self._max_spread:
            log.debug("spike_fade.reject_spread", market=snapshot.market_id, spread=spread)
            return None

        # Minimum volume filter
        if current_volume_usd < self._min_volume_usd:
            log.debug("spike_fade.reject_volume", market=snapshot.market_id, vol=current_volume_usd)
            return None

        # Magnitude filter
        magnitude_pct = abs(snapshot.price_change_pct)
        if magnitude_pct < self._min_spike:
            return None

        # Volume spike filter
        vol_ratio = (current_volume_usd / snapshot.avg_volume_per_tick) if snapshot.avg_volume_per_tick > 0 else 0.0
        if vol_ratio < self._vol_spike_mult:
            log.debug("spike_fade.reject_vol_spike", market=snapshot.market_id, ratio=vol_ratio)
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
        log.info(
            "spike_fade.signal",
            market=snapshot.market_id,
            direction=direction,
            magnitude_pct=round(magnitude_pct, 4),
            vol_ratio=round(vol_ratio, 2),
        )
        return signal
