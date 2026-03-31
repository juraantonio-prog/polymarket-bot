"""
Paper trading engine.
Simulates order fills with configurable slippage. No live execution.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.config import Config
from src.db import Database
from src.execution.position_tracker import PositionTracker, Position
from src.strategy.spike_fade import SpikeFadeSignal
from src.strategy.confidence import ConfidenceScore
from src.logger import get_logger

log = get_logger(__name__)


class PaperEngine:
    """
    Simulates trade execution for paper trading.
    Applies slippage, tracks positions, checks TP/SL/time-stop.
    """

    MODE = "paper"

    def __init__(self, config: Config, db: Database) -> None:
        ex = config.get("execution", default={})
        self._slippage_bps = int(ex.get("slippage_bps", 100))
        self._tp_delta = float(ex.get("take_profit_delta", 0.06))
        self._sl_delta = float(ex.get("stop_loss_delta", 0.04))
        self._time_stop_sec = int(ex.get("time_stop_seconds", 2400))
        self._max_open = int(ex.get("max_open_positions", 5))
        self._notional_usd = float(config.get("risk", "notional_per_trade_usd", default=100))
        self._threshold = float(config.get("confidence", "min_threshold", default=0.55))
        self._tracker = PositionTracker(db)
        self._db = db

    async def try_open(
        self,
        signal: SpikeFadeSignal,
        confidence: ConfidenceScore,
        market_name: str = "",
    ) -> Optional[Position]:
        """Attempt to open a paper position for a signal."""
        log.info(
            "paper.try_open",
            market=signal.market_id,
            direction=signal.direction,
            confidence=round(confidence.total, 4),
            meets_threshold=confidence.meets_threshold,
            threshold=self._threshold,
        )
        if not confidence.meets_threshold:
            log.info("paper.below_threshold", market=signal.market_id, conf=round(confidence.total, 4))
            return None

        open_count = await self._tracker.count_open()
        if open_count >= self._max_open:
            log.info("paper.max_positions", open=open_count, max=self._max_open)
            return None

        # Apply slippage to entry
        slippage = self._slippage_bps / 10000.0
        if signal.direction == "fade_yes":
            # We're fading (shorting) YES → selling at slightly lower price
            entry = signal.entry_price * (1 - slippage)
            tp = entry - self._tp_delta
            sl = entry + self._sl_delta
        else:
            # Fading NO → buying YES at slightly higher price
            entry = signal.entry_price * (1 + slippage)
            tp = entry + self._tp_delta
            sl = entry - self._sl_delta

        # Clamp prices to [0.01, 0.99]
        entry = max(0.01, min(0.99, entry))
        tp = max(0.01, min(0.99, tp))
        sl = max(0.01, min(0.99, sl))

        size_usd = self._notional_usd
        time_stop_at = datetime.now(tz=timezone.utc) + timedelta(seconds=self._time_stop_sec)

        position = await self._tracker.open_position(
            market_id=signal.market_id,
            direction=signal.direction,
            entry_price=entry,
            size_usd=size_usd,
            tp_price=tp,
            sl_price=sl,
            time_stop_at=time_stop_at,
            confidence=confidence.total,
            mode=self.MODE,
        )
        log.info(
            "paper.position_opened",
            position_id=position.id,
            market=signal.market_id,
            direction=signal.direction,
            entry=round(entry, 4),
            tp=round(tp, 4),
            sl=round(sl, 4),
            size_usd=round(size_usd, 2),
        )
        return position

    async def check_exits(self, current_prices: dict[str, float]) -> list[Position]:
        """Check all open positions against current prices for exit conditions."""
        closed = []
        open_positions = await self._tracker.get_open_positions()
        now = datetime.now(tz=timezone.utc)

        for pos in open_positions:
            price = current_prices.get(pos.market_id)
            if price is None:
                continue

            reason: Optional[str] = None

            # Time stop
            if pos.time_stop_at and now >= pos.time_stop_at:
                reason = "time_stop"
            # Take profit / stop loss
            elif pos.direction == "fade_yes":
                if price <= pos.tp_price:
                    reason = "take_profit"
                elif price >= pos.sl_price:
                    reason = "stop_loss"
            else:
                if price >= pos.tp_price:
                    reason = "take_profit"
                elif price <= pos.sl_price:
                    reason = "stop_loss"

            if reason:
                closed_pos = await self._tracker.close_position(pos.id, price, reason)
                if closed_pos:
                    closed.append(closed_pos)
                    log.info(
                        "paper.position_closed",
                        position_id=pos.id,
                        reason=reason,
                        pnl_usd=round(closed_pos.pnl_usd or 0, 2),
                        pnl_pct=round((closed_pos.pnl_pct or 0) * 100, 2),
                    )
        return closed
