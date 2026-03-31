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


def _make_detector(min_spike=0.05, vol_mult=2.0, min_vol=1000, min_days=30,
                   max_spread=0.10, cooldown=0.0) -> SpikeFadeDetector:
    """Build a SpikeFadeDetector without Config, with cooldown=0 by default (no cooldown in tests)."""
    d = SpikeFadeDetector.__new__(SpikeFadeDetector)
    d._min_spike = min_spike
    d._baseline_window = 600
    d._vol_spike_mult = vol_mult
    d._min_volume_usd = min_vol
    d._cooldown_sec = cooldown
    d._min_days = min_days
    d._max_spread = max_spread
    d._last_signal_ts = {}
    return d


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
    detector = _make_detector()
    snap = _make_snapshot(price_change_pct=0.10, avg_vol=1000.0)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000, spread=0.02)
    assert signal is not None
    assert signal.direction == "fade_yes"
    assert signal.market_id == "mkt1"


def test_detect_rejects_low_expiry():
    detector = _make_detector()
    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=10, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is None


def test_detect_rejects_small_spike():
    detector = _make_detector()
    snap = _make_snapshot(price_change_pct=0.02)  # below 5%
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is None


def test_detect_rejects_wide_spread():
    detector = _make_detector()
    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000, spread=0.15)
    assert signal is None


def test_detect_rejects_low_market_volume():
    detector = _make_detector(min_vol=500_000)
    snap = _make_snapshot(price_change_pct=0.10)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=14.0)
    assert signal is None


def test_fade_no_direction():
    detector = _make_detector()
    snap = _make_snapshot(price_change_pct=-0.10, current_price=0.30)
    signal = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert signal is not None
    assert signal.direction == "fade_no"


def test_cooldown_blocks_repeat_signal():
    detector = _make_detector(cooldown=300.0)
    snap = _make_snapshot(price_change_pct=0.10, avg_vol=1000.0)

    # First signal should pass
    sig1 = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert sig1 is not None

    # Immediate second call on same market — blocked by cooldown
    sig2 = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert sig2 is None


def test_cooldown_allows_after_expiry():
    import time
    detector = _make_detector(cooldown=1.0)  # 1 second cooldown
    snap = _make_snapshot(price_change_pct=0.10, avg_vol=1000.0)

    sig1 = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert sig1 is not None

    # Manually backdate the timestamp so cooldown has expired
    detector._last_signal_ts["mkt1"] -= 2.0

    sig2 = detector.detect(snap, days_to_expiry=60, current_volume_usd=5000.0, market_volume_usd=10_000_000)
    assert sig2 is not None
