"""Tests for paper trading engine."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.execution.paper_engine import PaperEngine
from src.execution.position_tracker import Position
from src.strategy.spike_fade import SpikeFadeSignal
from src.strategy.confidence import ConfidenceScore


def _make_config():
    cfg = MagicMock()
    cfg.get = lambda *keys, **kw: {
        ("execution",): {
            "slippage_bps": 100,
            "take_profit_delta": 0.06,
            "stop_loss_delta": 0.04,
            "time_stop_seconds": 2400,
            "max_open_positions": 5,
        },
        ("risk", "notional_per_trade_usd"): 100,
    }.get(keys, kw.get("default", {}))
    return cfg


def _make_signal(direction="fade_yes") -> SpikeFadeSignal:
    return SpikeFadeSignal(
        market_id="mkt1",
        token_id="tok1",
        direction=direction,
        entry_price=0.70,
        spike_magnitude=0.07,
        spike_magnitude_pct=0.10,
        volume_spike_ratio=3.0,
        days_to_expiry=60,
    )


def _make_confidence(total=0.70) -> ConfidenceScore:
    return ConfidenceScore(
        total=total,
        spike_magnitude_score=0.7,
        volume_confirmation_score=0.7,
        liquidity_score=0.7,
        time_of_day_score=0.7,
        meets_threshold=total >= 0.55,
    )


@pytest.mark.asyncio
async def test_try_open_returns_none_below_threshold():
    cfg = _make_config()
    db = AsyncMock()
    engine = PaperEngine.__new__(PaperEngine)
    engine._slippage_bps = 100
    engine._tp_delta = 0.06
    engine._sl_delta = 0.04
    engine._time_stop_sec = 2400
    engine._notional_usd = 100
    engine._max_open = 5
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    engine._tracker = tracker
    engine._db = db

    signal = _make_signal()
    conf = _make_confidence(total=0.40)  # below threshold

    result = await engine.try_open(signal, conf)
    assert result is None


@pytest.mark.asyncio
async def test_try_open_respects_max_positions():
    cfg = _make_config()
    engine = PaperEngine.__new__(PaperEngine)
    engine._slippage_bps = 100
    engine._tp_delta = 0.06
    engine._sl_delta = 0.04
    engine._time_stop_sec = 2400
    engine._notional_usd = 100
    engine._max_open = 5
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=5)  # at max
    engine._tracker = tracker

    signal = _make_signal()
    conf = _make_confidence(total=0.80)
    result = await engine.try_open(signal, conf)
    assert result is None


@pytest.mark.asyncio
async def test_slippage_applied_fade_yes():
    """fade_yes → sell YES → entry should be slightly below signal price."""
    engine = PaperEngine.__new__(PaperEngine)
    engine._slippage_bps = 100  # 1%
    engine._tp_delta = 0.06
    engine._sl_delta = 0.04
    engine._time_stop_sec = 2400
    engine._notional_usd = 100
    engine._max_open = 5
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    mock_pos = Position(
        id=1, market_id="mkt1", direction="fade_yes",
        entry_price=0.693, size_usd=350, tp_price=0.633, sl_price=0.733,
        time_stop_at=None, status="open",
    )
    tracker.open_position = AsyncMock(return_value=mock_pos)
    engine._tracker = tracker
    engine._db = AsyncMock()

    signal = _make_signal("fade_yes")
    conf = _make_confidence(0.70)
    pos = await engine.try_open(signal, conf)
    # Entry should be 0.70 * (1 - 0.01) = 0.693
    assert pos is not None
    assert pos.entry_price == pytest.approx(0.693, rel=1e-3)
