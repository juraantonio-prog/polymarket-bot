"""Tests for PriceTracker."""
import pytest
import time
from unittest.mock import MagicMock

from src.data.price_tracker import PriceTracker, PriceTick


def _make_tracker() -> PriceTracker:
    tracker = PriceTracker.__new__(PriceTracker)
    tracker._window_sec = 3600.0
    tracker._max_ticks = 360
    tracker._baseline_window = 600.0
    tracker._ticks = {}
    return tracker


def test_add_tick_and_snapshot():
    tracker = _make_tracker()
    now = time.time()
    for i in range(10):
        tick = PriceTick(token_id="tok1", price=0.50 + i * 0.01, volume_usd=1000.0, timestamp=now - 500 + i * 10)
    # Add spike tick
    tracker.add_tick(PriceTick("tok1", 0.50, 1000.0, now - 500))
    tracker.add_tick(PriceTick("tok1", 0.51, 1000.0, now - 400))
    tracker.add_tick(PriceTick("tok1", 0.65, 3000.0, now - 10))
    snap = tracker.get_snapshot("mkt1", "tok1")
    assert snap is not None
    assert snap.current_price == pytest.approx(0.65)
    assert snap.price_change_pct > 0


def test_snapshot_returns_none_with_one_tick():
    tracker = _make_tracker()
    tracker.add_tick(PriceTick("tok1", 0.50, 1000.0))
    snap = tracker.get_snapshot("mkt1", "tok1")
    assert snap is None


def test_token_ids():
    tracker = _make_tracker()
    tracker.add_tick(PriceTick("tokA", 0.5, 1000.0))
    tracker.add_tick(PriceTick("tokB", 0.5, 1000.0))
    assert set(tracker.token_ids()) == {"tokA", "tokB"}
