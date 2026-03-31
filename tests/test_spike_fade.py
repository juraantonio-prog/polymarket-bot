"""Tests for spike-fade detector."""
import pytest
from unittest.mock import MagicMock
from src.strategy.spike_fade import SpikeFadeDetector, SpikeFadeSignal
from src.data.price_tracker import MarketSnapshot


def _make_config(min_spike=0.05, vol_mult=2.0, min_vol=1000, min_days=30, max_spread=0.10):
    cfg = MagicMock()
    cfg.get = lambda *keys, default=None: {
        ("spike_fade",): {"min_spike_magnitude": min_spike, "volume_spike_multiplier": vol_mult, "min_volume_usd": min_vol, "baseline_window_seconds": 600},
        ("expiry", "min_days_to_expiry"): min_days,
        ("filters", "max_spread"): max_spread,
    }.get(keys, default)
    return cfg


def _make_snapshot(price_change_pct=0.10, avg_vol=1000.0, current_price=0.70):
    return MarketSnapshot(
        market_id="mkt1",
        token_id="tok1",
        current_price=current_price,
        baseline_price=current_price / (1 + price_change_pct),
        price_change=current_price - current_price / (1 + price_change_pct),
        price_change_pct=price_change_pct,
        rolling_volume=10000.0,
        avg_volume_per_tick=avg_vol,
        tick_count=100,
        window_seconds=3600,
    )


def test_detect_generates_signal():
    cfg = MagicMock()
    cfg.get = MagicMock(side_effect=lambda *keys, **kw: {
        ("spike_fade",): {"min_spike_magnitude": 0.05, "volume_spike_multiplier": 2.0, "min_volume_usd": 1000, "baseline_window_seconds": 600},
        ("expiry", "min_days_to_expiry"): 30,
        ("filters", "max_spread"): 0.10,
    }.get(keys, kw.get("default")))

    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 1000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=0.10, avg_vol=1000.0)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000, spread=0.02)
    assert signal is not None
    assert signal.direction == "fade_yes"
    assert signal.market_id == "mkt1"


def test_detect_rejects_low_expiry():
    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 1000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=10, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is None


def test_detect_rejects_small_spike():
    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 1000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=0.02)  # below 5%
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is None


def test_detect_rejects_wide_spread():
    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 1000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000, spread=0.15)
    assert signal is None


def test_detect_rejects_low_market_volume():
    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 500_000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=14.0)
    assert signal is None


def test_fade_no_direction():
    detector = SpikeFadeDetector.__new__(SpikeFadeDetector)
    detector._min_spike = 0.05
    detector._baseline_window = 600
    detector._vol_spike_mult = 2.0
    detector._min_volume_usd = 1000
    detector._min_days = 30
    detector._max_spread = 0.10

    snap = _make_snapshot(price_change_pct=-0.10, current_price=0.30)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is not None
    assert signal.direction == "fade_no"
