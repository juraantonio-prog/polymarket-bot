"""
Paper trading engine.
Simulates order fills with configurable slippage. No live execution.
"""
from __future__ import annotations

import asyncio
import time
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


class RiskGuard:
    """
    Enforces hard risk limits:
    - Daily loss cap: stop opening positions once daily PnL drops below threshold.
    - Consecutive-loss cooldown: after N consecutive losses, pause for a configurable period.

    State is initialized from the DB at startup and maintained in memory thereafter.
    """

    def __init__(self, config: Config) -> None:
        r = config.get("risk", default={})
        self._max_daily_loss = float(r.get("max_daily_loss_usd", 250))
        self._max_consecutive = int(r.get("max_consecutive_losses", 4))
        self._cooldown_sec = float(r.get("consecutive_loss_cooldown_seconds", 7200))

        self._daily_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._cooldown_until: float = 0.0   # Unix timestamp
        self._last_reset_date: str = ""     # YYYY-MM-DD of last daily reset

    async def init_from_db(self, db: Database) -> None:
        """Load today's PnL and consecutive-loss state from the positions table."""
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        self._last_reset_date = today

        # Sum today's closed-position PnL
        rows = await db.fetchall(
            "SELECT pnl_usd FROM positions "
            "WHERE status = 'closed' AND closed_at >= ? ORDER BY closed_at ASC",
            (f"{today} 00:00:00",),
        )
        self._daily_pnl = sum(float(r["pnl_usd"]) for r in rows if r["pnl_usd"] is not None)

        # Count consecutive losses from most recent closed positions
        recent = await db.fetchall(
            "SELECT pnl_usd FROM positions WHERE status = 'closed' "
            "ORDER BY closed_at DESC LIMIT 20"
        )
        count = 0
        for r in recent:
            if float(r.get("pnl_usd") or 0) <= 0:
                count += 1
            else:
                break
        self._consecutive_losses = count

        log.info(
            "risk_guard.initialized",
            daily_pnl=round(self._daily_pnl, 2),
            consecutive_losses=self._consecutive_losses,
        )

    def is_allowed(self) -> tuple[bool, str]:
        """Returns (trading_allowed, reason_if_blocked)."""
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        # Reset daily PnL at UTC midnight
        if today != self._last_reset_date:
            self._daily_pnl = 0.0
            self._last_reset_date = today

        # Consecutive-loss cooldown check
        if self._cooldown_until > time.time():
            remaining = int(self._cooldown_until - time.time())
            return False, f"consecutive_loss_cooldown ({remaining}s remaining)"

        # Daily loss hard stop
        if self._daily_pnl <= -self._max_daily_loss:
            return False, (
                f"daily_loss_limit (pnl={self._daily_pnl:.2f}, "
                f"limit=-{self._max_daily_loss})"
            )

        return True, ""

    def record_close(self, pnl_usd: float) -> None:
        """Update risk state after a position closes."""
        self._daily_pnl += pnl_usd

        if pnl_usd <= 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self._max_consecutive:
                self._cooldown_until = time.time() + self._cooldown_sec
                log.warning(
                    "risk.consecutive_loss_cooldown_triggered",
                    consecutive=self._consecutive_losses,
                    cooldown_sec=self._cooldown_sec,
                    resume_at=datetime.fromtimestamp(
                        self._cooldown_until, tz=timezone.utc
                    ).isoformat(),
                )
        else:
            self._consecutive_losses = 0

        log.info(
            "risk.state_updated",
            pnl_usd=round(pnl_usd, 2),
            daily_pnl=round(self._daily_pnl, 2),
            consecutive_losses=self._consecutive_losses,
        )


class PaperEngine:
    """
    Simulates trade execution for paper trading.
    Applies slippage, tracks positions, checks TP/SL/time-stop,
    and enforces risk limits via RiskGuard.
    """

    MODE = "paper"

    def __init__(self, config: Config, db: Database) -> None:
        ex = config.get("execution", default={})
        self._slippage_bps = int(ex.get("slippage_bps", 100))
        self._tp_delta = float(ex.get("take_profit_delta", 0.08))
        self._sl_delta = float(ex.get("stop_loss_delta", 0.03))
        self._time_stop_sec = int(ex.get("time_stop_seconds", 2400))
        self._max_open = int(ex.get("max_open_positions", 5))
        self._notional_usd = float(config.get("risk", "notional_per_trade_usd", default=100))
        self._threshold = float(config.get("confidence", "min_threshold", default=0.65))
        self._tracker = PositionTracker(db)
        self._risk_guard = RiskGuard(config)
        self._db = db

    async def init(self) -> None:
        """Initialize risk state from DB. Call once after connecting to DB."""
        await self._risk_guard.init_from_db(self._db)

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

        # Confidence gate — cheapest check first
        if not confidence.meets_threshold:
            log.info("paper.below_threshold", market=signal.market_id, conf=round(confidence.total, 4))
            return None

        # Position count gate
        open_count = await self._tracker.count_open()
        if open_count >= self._max_open:
            log.info("paper.max_positions", open=open_count, max=self._max_open)
            return None

        # Risk guard — daily loss and consecutive-loss cooldown
        allowed, reason = self._risk_guard.is_allowed()
        if not allowed:
            log.warning("paper.risk_blocked", market=signal.market_id, reason=reason)
            return None

        # Apply slippage to entry (100 bps = 1%)
        slippage = self._slippage_bps / 10000.0
        if signal.direction == "fade_yes":
            # Fading (shorting) YES → effective sell at slightly lower price
            entry = signal.entry_price * (1 - slippage)
            tp = entry - self._tp_delta
            sl = entry + self._sl_delta
        else:
            # Fading NO → buying YES at slightly higher price
            entry = signal.entry_price * (1 + slippage)
            tp = entry + self._tp_delta
            sl = entry - self._sl_delta

        # Clamp prices to valid probability range
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
                    self._risk_guard.record_close(closed_pos.pnl_usd or 0)
                    closed.append(closed_pos)
                    log.info(
                        "paper.position_closed",
                        position_id=pos.id,
                        reason=reason,
                        pnl_usd=round(closed_pos.pnl_usd or 0, 2),
                        pnl_pct=round((closed_pos.pnl_pct or 0) * 100, 2),
                    )
        return closed
