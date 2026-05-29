"""
Confidence scoring with normalization.
All sub-scores are normalized to [0.0, 1.0] before weighting.
Weights and calibration thresholds come from config/strategy.yaml.
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
    price_move_score: float         # clamp((move - min_move) / move_range, 0, 1)
    volume_spike_score: float       # clamp((vol_mult - min_mult) / mult_range, 0, 1)
    spread_quality_score: float     # clamp(1 - spread / max_spread, 0, 1)
    liquidity_quality_score: float  # clamp(log10(vol / min_vol) / 2, 0, 1)
    market_priority_score: float    # priority / 10.0
    category_weight_score: float    # from category_weights config
    meets_threshold: bool


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class ConfidenceScorer:
    """Computes normalized confidence score for a spike-fade signal."""

    def __init__(self, config: Config) -> None:
        cf = config.get("confidence", default={})
        w = cf.get("weights", {})
        raw_weights = {
            "price_move_strength": float(w.get("price_move_strength", 0.30)),
            "volume_spike_strength": float(w.get("volume_spike_strength", 0.20)),
            "spread_quality": float(w.get("spread_quality", 0.15)),
            "liquidity_quality": float(w.get("liquidity_quality", 0.15)),
            "market_priority": float(w.get("market_priority", 0.10)),
            "category_weight": float(w.get("category_weight", 0.10)),
        }
        total_w = sum(raw_weights.values())
        # Normalize weights to sum exactly to 1.0
        self._weights = {k: v / total_w for k, v in raw_weights.items()}
        self._threshold = float(cf.get("min_threshold", 0.65))

        # Calibration: price move normalization
        # clamp((move - min_move) / move_range, 0, 1)
        sf = config.get("spike_fade", default={})
        self._min_move = float(
            sf.get("min_price_move_abs", sf.get("min_spike_magnitude", 0.12))
        )
        self._move_range = 0.08  # min_move + move_range = saturation point (20pp)

        # Calibration: volume spike normalization
        # clamp((vol_mult - min_mult) / mult_range, 0, 1)
        self._min_vol_mult = float(
            sf.get("min_volume_multiple", sf.get("volume_spike_multiplier", 2.0))
        )
        self._vol_mult_range = 3.0  # min_mult + range = saturation point (5x)

        # Liquidity calibration: clamp(log10(vol / min_vol) / 2, 0, 1)
        self._liquidity_min_vol = float(cf.get("liquidity_min_vol_usd", 500_000))

        # Spread: clamp(1 - spread / max_spread, 0, 1)
        self._max_spread = float(config.get("filters", "max_spread", default=0.10))

        # Category tables
        self._category_weights: dict[str, float] = config.get("category_weights", default={})
        self._category_priorities: dict[str, int] = config.get("category_priorities", default={})

    def score(
        self,
        signal: SpikeFadeSignal,
        spread: float = 0.0,
        market_volume_usd: float = 0.0,
        category: str = "",
    ) -> ConfidenceScore:
        """Score a signal. All sub-scores are in [0.0, 1.0]."""
        cat = category.lower()

        # 1. Price move strength: clamp((move - min_move) / move_range, 0, 1)
        move_score = _clamp(
            (signal.spike_magnitude_pct - self._min_move) / self._move_range
        )

        # 2. Volume spike strength: clamp((vol_mult - min_mult) / mult_range, 0, 1)
        vol_score = _clamp(
            (signal.volume_spike_ratio - self._min_vol_mult) / self._vol_mult_range
        )

        # 3. Spread quality: clamp(1 - spread / max_spread, 0, 1)
        if self._max_spread > 0:
            spread_score = _clamp(1.0 - spread / self._max_spread)
        else:
            spread_score = 1.0

        # 4. Liquidity quality: clamp(log10(vol / min_vol) / 2, 0, 1)
        if market_volume_usd > 0 and self._liquidity_min_vol > 0:
            ratio = market_volume_usd / self._liquidity_min_vol
            liq_score = _clamp(math.log10(max(ratio, 1e-9)) / 2.0)
        else:
            liq_score = 0.0

        # 5. Market priority: priority / 10.0
        priority = self._category_priorities.get(cat, 5)
        priority_score = _clamp(float(priority) / 10.0)

        # 6. Category weight: value from config (already normalized [0..1])
        cat_score = _clamp(float(self._category_weights.get(cat, 0.5)))

        total = (
            self._weights["price_move_strength"] * move_score
            + self._weights["volume_spike_strength"] * vol_score
            + self._weights["spread_quality"] * spread_score
            + self._weights["liquidity_quality"] * liq_score
            + self._weights["market_priority"] * priority_score
            + self._weights["category_weight"] * cat_score
        )
        total = _clamp(total)

        result = ConfidenceScore(
            total=total,
            price_move_score=move_score,
            volume_spike_score=vol_score,
            spread_quality_score=spread_score,
            liquidity_quality_score=liq_score,
            market_priority_score=priority_score,
            category_weight_score=cat_score,
            meets_threshold=total >= self._threshold,
        )
        log.debug(
            "confidence.scored",
            total=round(total, 4),
            move=round(move_score, 4),
            vol=round(vol_score, 4),
            spread=round(spread_score, 4),
            liq=round(liq_score, 4),
            priority=round(priority_score, 4),
            cat=round(cat_score, 4),
            meets=result.meets_threshold,
        )
        return result
