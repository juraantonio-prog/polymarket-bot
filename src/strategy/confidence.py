"""
Confidence scoring with normalization.
All sub-scores are normalized to [0.0, 1.0].
Weights come from config/strategy.yaml.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.config import Config
from src.strategy.spike_fade import SpikeFadeSignal
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class ConfidenceScore:
    total: float                    # [0.0, 1.0]
    spike_magnitude_score: float    # [0.0, 1.0]
    volume_confirmation_score: float
    liquidity_score: float
    time_of_day_score: float
    meets_threshold: bool


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class ConfidenceScorer:
    """Computes normalized confidence score for a spike-fade signal."""

    def __init__(self, config: Config) -> None:
        cf = config.get("confidence", default={})
        w = cf.get("weights", {})
        raw_weights = {
            "spike_magnitude": float(w.get("spike_magnitude", 0.35)),
            "volume_confirmation": float(w.get("volume_confirmation", 0.30)),
            "liquidity_score": float(w.get("liquidity_score", 0.20)),
            "time_of_day": float(w.get("time_of_day", 0.15)),
        }
        total_w = sum(raw_weights.values())
        # Normalize weights to sum exactly to 1.0
        self._weights = {k: v / total_w for k, v in raw_weights.items()}
        self._threshold = float(cf.get("min_threshold", 0.55))

        # Calibration parameters
        self._spike_cap = 0.20      # 20% spike → score 1.0
        self._vol_cap = 10.0        # 10x volume → score 1.0
        self._depth_cap = 50000.0   # $50k depth → score 1.0

    def score(
        self,
        signal: SpikeFadeSignal,
        orderbook_depth_usd: float = 0.0,
        hour_utc: int | None = None,
    ) -> ConfidenceScore:
        """
        Score a signal. All sub-scores in [0.0, 1.0].
        """
        # 1. Spike magnitude: sigmoid-like normalization
        spike_score = _clamp(signal.spike_magnitude_pct / self._spike_cap)

        # 2. Volume confirmation: log-normalized ratio
        if signal.volume_spike_ratio > 1:
            vol_score = _clamp(math.log(signal.volume_spike_ratio) / math.log(self._vol_cap))
        else:
            vol_score = 0.0

        # 3. Liquidity score: depth normalized
        liq_score = _clamp(orderbook_depth_usd / self._depth_cap)

        # 4. Time-of-day score: higher during US market hours (13:30–20:00 UTC)
        if hour_utc is None:
            import datetime
            hour_utc = datetime.datetime.now(tz=datetime.timezone.utc).hour
        if 13 <= hour_utc < 20:
            tod_score = 1.0
        elif 9 <= hour_utc < 13 or 20 <= hour_utc < 22:
            tod_score = 0.7
        else:
            tod_score = 0.4

        total = (
            self._weights["spike_magnitude"] * spike_score
            + self._weights["volume_confirmation"] * vol_score
            + self._weights["liquidity_score"] * liq_score
            + self._weights["time_of_day"] * tod_score
        )
        total = _clamp(total)

        result = ConfidenceScore(
            total=total,
            spike_magnitude_score=spike_score,
            volume_confirmation_score=vol_score,
            liquidity_score=liq_score,
            time_of_day_score=tod_score,
            meets_threshold=total >= self._threshold,
        )
        log.debug(
            "confidence.scored",
            total=round(total, 4),
            spike=round(spike_score, 4),
            vol=round(vol_score, 4),
            liq=round(liq_score, 4),
            tod=round(tod_score, 4),
            meets=result.meets_threshold,
        )
        return result
