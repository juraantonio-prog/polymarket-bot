"""Configuration loader — reads YAML files, merges with env vars."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_logger = logging.getLogger(__name__)

# Required files — bot will not start if any are missing.
_REQUIRED_FILES = ("settings.yaml", "strategy.yaml", "telegram.yaml", "risk.yaml")
# Optional files — missing file logs a warning but does not block startup.
_OPTIONAL_FILES = ("markets.yaml",)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    """Immutable config object built from YAML files + env vars."""

    def __init__(self, config_dir: Path | None = None):
        base = config_dir or _CONFIG_DIR
        self._data: dict[str, Any] = {}
        for fname in _REQUIRED_FILES:
            fpath = base / fname
            if fpath.exists():
                self._data = _deep_merge(self._data, _load_yaml(fpath))
        for fname in _OPTIONAL_FILES:
            fpath = base / fname
            if fpath.exists():
                self._data = _deep_merge(self._data, _load_yaml(fpath))
            else:
                _logger.warning(
                    "Optional config file not found — using defaults: %s "
                    "(create config/%s to customise market filters)",
                    fpath,
                    fname,
                )

        # Env overrides
        if level := os.getenv("LOG_LEVEL"):
            self._data.setdefault("logging", {})["level"] = level
        if db_path := os.getenv("DB_PATH"):
            self._data.setdefault("db", {})["path"] = db_path

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    def require(self, *keys: str) -> Any:
        val = self.get(*keys)
        if val is None:
            raise KeyError(f"Required config key missing: {'.'.join(keys)}")
        return val

    # Convenience properties
    @property
    def gamma_base_url(self) -> str:
        return self.require("api", "gamma_base_url")

    @property
    def clob_base_url(self) -> str:
        return self.require("api", "clob_base_url")

    @property
    def ws_url(self) -> str:
        return self.require("api", "ws_url")

    @property
    def db_path(self) -> str:
        return self.get("db", "path", default="data/polymarket.db")

    @property
    def log_level(self) -> str:
        return self.get("logging", "level", default="INFO")

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
