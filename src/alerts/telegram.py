"""
Telegram alert integration.
All message templates come from config/telegram.yaml.
"""
from __future__ import annotations

import os
import time
from collections import deque
from typing import Optional

import httpx

from src.config import Config
from src.logger import get_logger

log = get_logger(__name__)


class TelegramAlerter:
    """Sends formatted alerts to a Telegram chat via Bot API."""

    def __init__(self, config: Config) -> None:
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        alert_cfg = config.get("alerts", default={})
        self._enabled = alert_cfg.get("enabled", True)
        self._min_confidence = float(alert_cfg.get("min_confidence_for_alert", 0.60))
        self._max_per_hour = int(alert_cfg.get("max_alerts_per_hour", 20))
        self._templates = alert_cfg.get("templates", {})
        self._sent_timestamps: deque[float] = deque()

    def _check_rate_limit(self) -> bool:
        now = time.time()
        cutoff = now - 3600
        while self._sent_timestamps and self._sent_timestamps[0] < cutoff:
            self._sent_timestamps.popleft()
        if len(self._sent_timestamps) >= self._max_per_hour:
            log.warning("telegram.rate_limited", sent_last_hour=len(self._sent_timestamps))
            return False
        return True

    def _is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    async def send_raw(self, text: str) -> bool:
        """Send raw text to Telegram. Returns True on success."""
        if not self._enabled:
            log.debug("telegram.disabled")
            return False
        if not self._is_configured():
            log.warning("telegram.not_configured", msg="TELEGRAM_BOT_TOKEN/CHAT_ID not set")
            return False
        if not self._check_rate_limit():
            return False

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                resp.raise_for_status()
                self._sent_timestamps.append(time.time())
                log.info("telegram.sent", chars=len(text))
                return True
        except Exception as exc:
            log.error("telegram.send_failed", error=str(exc))
            return False

    def _render(self, template_key: str, **kwargs) -> str:
        tmpl = self._templates.get(template_key, f"[{template_key}]\n" + str(kwargs))
        try:
            return tmpl.format(**kwargs)
        except KeyError as e:
            log.warning("telegram.template_key_missing", key=str(e))
            return str(kwargs)

    async def send_signal(
        self,
        market_name: str,
        direction: str,
        entry_price: float,
        confidence: float,
        days_to_expiry: float,
        volume_spike: float,
        mode: str = "paper",
    ) -> bool:
        if confidence < self._min_confidence:
            return False
        text = self._render(
            "signal",
            market_name=market_name,
            direction=direction,
            entry_price=entry_price,
            confidence=confidence,
            days_to_expiry=int(days_to_expiry),
            volume_spike=volume_spike,
            mode=mode.upper(),
        )
        return await self.send_raw(text)

    async def send_position_open(
        self, market_name: str, size_usd: float, entry_price: float,
        tp_price: float, sl_price: float,
    ) -> bool:
        text = self._render(
            "position_open",
            market_name=market_name,
            size_usd=size_usd,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        return await self.send_raw(text)

    async def send_position_closed(
        self, market_name: str, pnl_usd: float, pnl_pct: float, reason: str,
    ) -> bool:
        text = self._render(
            "position_closed",
            market_name=market_name,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            reason=reason,
        )
        return await self.send_raw(text)

    async def send_daily_report(
        self, date: str, total_trades: int, win_rate: float,
        total_pnl: float, avg_latency_ms: float,
    ) -> bool:
        text = self._render(
            "daily_report",
            date=date,
            total_trades=total_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_latency_ms=avg_latency_ms,
        )
        return await self.send_raw(text)
