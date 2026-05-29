"""Tests for paper trading engine."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.execution.paper_engine import PaperEngine, RiskGuard
from src.execution.position_tracker import Position
from src.strategy.spike_fade import SpikeFadeSignal
from src.strategy.confidence import ConfidenceScore


def _make_config():
    cfg = MagicMock()
    cfg.get = lambda *keys, **kw: {
        ("execution",): {
            "slippage_bps": 100,
            "take_profit_delta": 0.08,
            "stop_loss_delta": 0.03,
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
        spike_magnitude_pct=0.16,
        volume_spike_ratio=4.0,
        days_to_expiry=60,
    )


def _make_confidence(total=0.70) -> ConfidenceScore:
    return ConfidenceScore(
        total=total,
        price_move_score=0.7,
        volume_spike_score=0.7,
        spread_quality_score=0.7,
        liquidity_quality_score=0.7,
        market_priority_score=0.7,
        category_weight_score=0.7,
        meets_threshold=total >= 0.65,
    )


def _make_engine(threshold=0.65) -> PaperEngine:
    """Build PaperEngine bypassing __init__ for unit testing."""
    engine = PaperEngine.__new__(PaperEngine)
    engine._slippage_bps = 100
    engine._tp_delta = 0.08
    engine._sl_delta = 0.03
    engine._time_stop_sec = 2400
    engine._notional_usd = 100
    engine._max_open = 5
    engine._threshold = threshold
    engine._db = AsyncMock()
    # Risk guard: always allow by default
    engine._risk_guard = MagicMock()
    engine._risk_guard.is_allowed = MagicMock(return_value=(True, ""))
    engine._risk_guard.record_close = MagicMock()
    return engine


@pytest.mark.asyncio
async def test_try_open_returns_none_below_threshold():
    engine = _make_engine()
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    engine._tracker = tracker

    signal = _make_signal()
    conf = _make_confidence(total=0.40)   # below threshold 0.65

    result = await engine.try_open(signal, conf)
    assert result is None


@pytest.mark.asyncio
async def test_try_open_respects_max_positions():
    engine = _make_engine()
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=5)  # at max
    engine._tracker = tracker

    signal = _make_signal()
    conf = _make_confidence(total=0.80)
    result = await engine.try_open(signal, conf)
    assert result is None


@pytest.mark.asyncio
async def test_try_open_blocked_by_risk_guard():
    engine = _make_engine()
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    engine._tracker = tracker
    engine._risk_guard.is_allowed = MagicMock(return_value=(False, "daily_loss_limit"))

    signal = _make_signal()
    conf = _make_confidence(total=0.80)
    result = await engine.try_open(signal, conf)
    assert result is None


@pytest.mark.asyncio
async def test_slippage_applied_fade_yes():
    """fade_yes → sell YES → entry should be slightly below signal price."""
    engine = _make_engine()
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    mock_pos = Position(
        id=1, market_id="mkt1", direction="fade_yes",
        entry_price=0.693, size_usd=100, tp_price=0.613, sl_price=0.723,
        time_stop_at=None, status="open",
    )
    tracker.open_position = AsyncMock(return_value=mock_pos)
    engine._tracker = tracker

    signal = _make_signal("fade_yes")
    conf = _make_confidence(0.80)
    pos = await engine.try_open(signal, conf)
    # Entry should be 0.70 * (1 - 0.01) = 0.693
    assert pos is not None
    assert pos.entry_price == pytest.approx(0.693, rel=1e-3)


@pytest.mark.asyncio
async def test_slippage_applied_fade_no():
    """fade_no → buy YES → entry should be slightly above signal price."""
    engine = _make_engine()
    tracker = AsyncMock()
    tracker.count_open = AsyncMock(return_value=0)
    mock_pos = Position(
        id=2, market_id="mkt1", direction="fade_no",
        entry_price=0.707, size_usd=100, tp_price=0.787, sl_price=0.677,
        time_stop_at=None, status="open",
    )
    tracker.open_position = AsyncMock(return_value=mock_pos)
    engine._tracker = tracker

    signal = _make_signal("fade_no")
    conf = _make_confidence(0.80)
    pos = await engine.try_open(signal, conf)
    # Entry should be 0.70 * (1 + 0.01) = 0.707
    assert pos is not None
    assert pos.entry_price == pytest.approx(0.707, rel=1e-3)


def test_risk_guard_daily_loss_blocks():
    cfg = MagicMock()
    cfg.get = lambda *keys, **kw: {
        ("risk",): {"max_daily_loss_usd": 250, "max_consecutive_losses": 4,
                    "consecutive_loss_cooldown_seconds": 7200},
    }.get(keys, kw.get("default", {}))
    guard = RiskGuard.__new__(RiskGuard)
    guard._max_daily_loss = 250
    guard._max_consecutive = 4
    guard._cooldown_sec = 7200
    guard._daily_pnl = -250.01
    guard._consecutive_losses = 0
    guard._cooldown_until = 0.0
    import datetime as dt
    guard._last_reset_date = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")

    allowed, reason = guard.is_allowed()
    assert not allowed
    assert "daily_loss_limit" in reason


def test_risk_guard_consecutive_loss_cooldown():
    import time
    guard = RiskGuard.__new__(RiskGuard)
    guard._max_daily_loss = 250
    guard._max_consecutive = 4
    guard._cooldown_sec = 7200
    guard._daily_pnl = 0.0
    guard._consecutive_losses = 0
    guard._cooldown_until = time.time() + 3600  # 1 hour from now
    import datetime as dt
    guard._last_reset_date = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")

    allowed, reason = guard.is_allowed()
    assert not allowed
    assert "cooldown" in reason


def test_risk_guard_resets_consecutive_on_win():
    guard = RiskGuard.__new__(RiskGuard)
    guard._max_daily_loss = 250
    guard._max_consecutive = 4
    guard._cooldown_sec = 7200
    guard._daily_pnl = -50.0
    guard._consecutive_losses = 3
    guard._cooldown_until = 0.0
    import datetime as dt
    guard._last_reset_date = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%d")

    guard.record_close(pnl_usd=8.0)  # win
    assert guard._consecutive_losses == 0
