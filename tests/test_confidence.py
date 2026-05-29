"""Tests for confidence scorer."""
import pytest
from src.strategy.confidence import ConfidenceScorer, ConfidenceScore, _clamp
from src.strategy.spike_fade import SpikeFadeSignal


def _make_scorer() -> ConfidenceScorer:
    scorer = ConfidenceScorer.__new__(ConfidenceScorer)
    scorer._weights = {
        "price_move_strength": 0.30,
        "volume_spike_strength": 0.20,
        "spread_quality": 0.15,
        "liquidity_quality": 0.15,
        "market_priority": 0.10,
        "category_weight": 0.10,
    }
    scorer._threshold = 0.65
    scorer._min_move = 0.12
    scorer._move_range = 0.08
    scorer._min_vol_mult = 2.0
    scorer._vol_mult_range = 3.0
    scorer._liquidity_min_vol = 500_000
    scorer._max_spread = 0.10
    scorer._category_weights = {"politics": 1.0, "other": 0.5}
    scorer._category_priorities = {"politics": 10, "other": 4}
    return scorer


def _make_signal(spike_pct=0.16, vol_ratio=4.0) -> SpikeFadeSignal:
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
    result = scorer.score(signal, spread=0.02, market_volume_usd=2_000_000, category="politics")
    assert 0.0 <= result.total <= 1.0
    assert 0.0 <= result.price_move_score <= 1.0
    assert 0.0 <= result.volume_spike_score <= 1.0
    assert 0.0 <= result.spread_quality_score <= 1.0
    assert 0.0 <= result.liquidity_quality_score <= 1.0
    assert 0.0 <= result.market_priority_score <= 1.0
    assert 0.0 <= result.category_weight_score <= 1.0


def test_score_meets_threshold():
    scorer = _make_scorer()
    signal = _make_signal(spike_pct=0.20, vol_ratio=5.0)
    result = scorer.score(signal, market_volume_usd=5_000_000, category="politics")
    assert result.meets_threshold == (result.total >= 0.65)


def test_score_zero_price_move_at_threshold():
    """A spike exactly at min_price_move_abs should yield price_move_score = 0."""
    scorer = _make_scorer()
    signal = _make_signal(spike_pct=0.12)
    result = scorer.score(signal)
    assert result.price_move_score == pytest.approx(0.0)


def test_score_zero_for_vol_at_min_mult():
    """Volume ratio exactly at min_volume_multiple should yield volume_spike_score = 0."""
    scorer = _make_scorer()
    signal = _make_signal(vol_ratio=2.0)
    result = scorer.score(signal)
    assert result.volume_spike_score == pytest.approx(0.0)


def test_spread_quality_zero_at_max():
    """Spread at max_spread should yield spread_quality_score = 0."""
    scorer = _make_scorer()
    signal = _make_signal()
    result = scorer.score(signal, spread=0.10)
    assert result.spread_quality_score == pytest.approx(0.0)


def test_spread_quality_one_at_zero_spread():
    scorer = _make_scorer()
    signal = _make_signal()
    result = scorer.score(signal, spread=0.0)
    assert result.spread_quality_score == pytest.approx(1.0)


def test_liquidity_zero_at_min_vol():
    """market_volume_usd exactly at min_vol should yield liquidity_quality_score = 0."""
    scorer = _make_scorer()
    signal = _make_signal()
    result = scorer.score(signal, market_volume_usd=500_000)
    assert result.liquidity_quality_score == pytest.approx(0.0, abs=1e-6)


def test_category_weight_uses_config():
    scorer = _make_scorer()
    signal = _make_signal()
    r_politics = scorer.score(signal, category="politics")
    r_other = scorer.score(signal, category="other")
    assert r_politics.category_weight_score > r_other.category_weight_score


def test_unknown_category_defaults():
    """Unknown category should fall back to 0.5 weight and priority 5."""
    scorer = _make_scorer()
    signal = _make_signal()
    result = scorer.score(signal, category="xyzunknown")
    assert result.category_weight_score == pytest.approx(0.5)
    assert result.market_priority_score == pytest.approx(0.5)


def test_clamp_utility():
    assert _clamp(-1.0) == 0.0
    assert _clamp(2.0) == 1.0
    assert _clamp(0.5) == 0.5
