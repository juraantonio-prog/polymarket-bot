"""
Replay mode: re-process historical price ticks through strategy.
Useful for backtesting strategy parameter changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from src.config import Config
from src.data.price_tracker import PriceTracker, PriceTick
from src.db import Database
from src.strategy.confidence import ConfidenceScorer
from src.strategy.spike_fade import SpikeFadeDetector, SpikeFadeSignal
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class ReplayResult:
    total_ticks_replayed: int
    signals_generated: int
    signals_above_threshold: int


class ReplayEngine:
    """Replays stored price ticks through the strategy pipeline."""

    def __init__(self, config: Config, db: Database) -> None:
        self._db = db
        self._config = config
        self._detector = SpikeFadeDetector(config)
        self._scorer = ConfidenceScorer(config)

    async def run(self, market_id: str | None = None, limit: int = 10000) -> ReplayResult:
        where = "WHERE 1=1"
        params: tuple = ()
        if market_id:
            where += " AND market_id = ?"
            params = (market_id,)

        rows = await self._db.fetchall(
            f"""SELECT pt.market_id, pt.token_id, pt.side, pt.price, pt.volume_usd,
                       pt.recorded_at, m.end_date_iso, m.days_to_expiry
                FROM price_ticks pt
                LEFT JOIN markets m ON pt.market_id = m.id
                {where}
                ORDER BY pt.recorded_at ASC
                LIMIT ?""",
            params + (limit,),
        )

        tracker = PriceTracker(self._config)
        signals_generated = 0
        signals_above_threshold = 0

        import time as _time
        import datetime as _dt

        for row in rows:
            import calendar
            ts = _dt.datetime.fromisoformat(row["recorded_at"])
            epoch = calendar.timegm(ts.timetuple())

            tick = PriceTick(
                token_id=row["token_id"],
                price=float(row["price"]),
                volume_usd=float(row.get("volume_usd") or 0),
                timestamp=float(epoch),
            )
            tracker.add_tick(tick)
            snap = tracker.get_snapshot(row["market_id"], row["token_id"])
            if snap is None:
                continue

            days = float(row.get("days_to_expiry") or 9999)
            signal = self._detector.detect(
                snapshot=snap,
                days_to_expiry=days,
                current_volume_usd=tick.volume_usd,
            )
            if signal:
                signals_generated += 1
                score = self._scorer.score(signal)
                if score.meets_threshold:
                    signals_above_threshold += 1
                    log.info("replay.signal", market=row["market_id"], conf=round(score.total, 4))

        result = ReplayResult(
            total_ticks_replayed=len(rows),
            signals_generated=signals_generated,
            signals_above_threshold=signals_above_threshold,
        )
        log.info("replay.complete", **vars(result))
        return result
