"""Tests for config loader."""
import pytest
from pathlib import Path
import tempfile, yaml, os

from src.config import Config


def _write_yaml(d: Path, name: str, content: dict):
    (d / name).write_text(yaml.dump(content))


def test_config_loads_from_dir(tmp_path):
    _write_yaml(tmp_path, "settings.yaml", {
        "api": {"gamma_base_url": "https://example.com", "clob_base_url": "https://clob.example.com", "ws_url": "wss://ws.example.com"},
        "db": {"path": "/tmp/test.db"},
    })
    _write_yaml(tmp_path, "strategy.yaml", {
        "spike_fade": {"min_spike_magnitude": 0.05},
        "confidence": {"min_threshold": 0.55},
        "expiry": {"min_days_to_expiry": 30},
        "execution": {"slippage_bps": 100},
    })
    _write_yaml(tmp_path, "telegram.yaml", {"alerts": {"enabled": False}})
    cfg = Config(config_dir=tmp_path)
    assert cfg.gamma_base_url == "https://example.com"
    assert cfg.get("spike_fade", "min_spike_magnitude") == 0.05


def test_config_get_default():
    cfg = Config.__new__(Config)
    cfg._data = {"a": {"b": 42}}
    assert cfg.get("a", "b") == 42
    assert cfg.get("a", "c", default=99) == 99
    assert cfg.get("x", default="missing") == "missing"


def test_config_require_raises():
    cfg = Config.__new__(Config)
    cfg._data = {}
    with pytest.raises(KeyError):
        cfg.require("nonexistent", "key")
