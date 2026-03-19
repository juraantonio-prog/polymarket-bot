"""Tests for confidence scorer."""
import pytest
from src.strategy.confidence import ConfidenceScorer, ConfidenceScore, _clamp
from src.strategy.spike_fade import SpikeFadeSignal


def _make_scorer() -> ConfidenceScorer:
    scorer = ConfidenceScorer.__new__(ConfidenceScorer)
    scorer._weights = {
        "spike_magnitude": 0.35,
        "volume_confirmation": 0.30,
        "liquidity_score": 0.20,
        "time_of_day": 0.15,
    }
    scorer._threshold = 0.55
    scorer._spike_cap = 0.20
    scorer._vol_cap = 10.0
    scorer._depth_cap = 50000.0
    return scorer


def _make_signal(spike_pct=0.10, vol_ratio=3.0) -> SpikeFadeSignal:
    return SpikeFadeSignal(
        market_id="mkt",
        token_id="tok",
        direction="fade_yes",
        entry_price=0.70,
        spike_magnitude=0.07,
        spike_magnitude_pct=spike_pct,
        volume_spike_ratio=vol_ratio,
        days_to_expiry=60,
    )


def test_score_all_sub_scores_in_range():
    scorer = _make_scorer()
    signal = _make_signal()
    result = scorer.score(signal, orderbook_depth_usd=10000, hour_utc=15)
    assert 0.0 <= result.total <= 1.0
    assert 0.0 <= result.spike_magnitude_score <= 1.0
    assert 0.0 <= result.volume_confirmation_score <= 1.0
    assert 0.0 <= result.liquidity_score <= 1.0
    assert 0.0 <= result.time_of_day_score <= 1.0


def test_score_meets_threshold():
    scorer = _make_scorer()
    signal = _make_signal(spike_pct=0.15, vol_ratio=5.0)
    result = scorer.score(signal, orderbook_depth_usd=30000, hour_utc=15)
    assert result.meets_threshold == (result.total >= 0.55)


def test_score_zero_for_no_volume():
    scorer = _make_scorer()
    signal = _make_signal(vol_ratio=0.5)
    result = scorer.score(signal, hour_utc=15)
    assert result.volume_confirmation_score == 0.0


def test_clamp_utility():
    assert _clamp(-1.0) == 0.0
    assert _clamp(2.0) == 1.0
    assert _clamp(0.5) == 0.5


def test_time_of_day_score_us_hours():
    scorer = _make_scorer()
    signal = _make_signal()
    r_us = scorer.score(signal, hour_utc=15)
    r_off = scorer.score(signal, hour_utc=3)
    assert r_us.time_of_day_score > r_off.time_of_day_score
