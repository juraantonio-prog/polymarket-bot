"""Performance metrics computation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.db import Database
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_usd: float
    avg_pnl_usd: float
    max_win_usd: float
    max_loss_usd: float
    avg_latency_ms: float
    sharpe_ratio: Optional[float]


class MetricsCalculator:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def compute(self, date_from: str = "", date_to: str = "") -> PerformanceMetrics:
        where = "WHERE status = 'closed'"
        params: tuple = ()
        if date_from:
            where += " AND closed_at >= ?"
            params = params + (date_from,)
        if date_to:
            where += " AND closed_at <= ?"
            params = params + (date_to,)

        rows = await self._db.fetchall(
            f"SELECT pnl_usd, pnl_pct FROM positions {where}", params
        )
        pnls = [float(r["pnl_usd"]) for r in rows if r["pnl_usd"] is not None]

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        # Latency
        lat_row = await self._db.fetchone(
            "SELECT AVG(latency_ms) as avg_lat FROM latency_log"
        )
        avg_lat = float(lat_row["avg_lat"]) if lat_row and lat_row["avg_lat"] else 0.0

        # Sharpe (annualized, assume daily returns)
        sharpe = None
        if len(pnls) > 1:
            import statistics
            mean_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            if std_pnl > 0:
                sharpe = (mean_pnl / std_pnl) * (252 ** 0.5)

        return PerformanceMetrics(
            total_trades=len(pnls),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(pnls) if pnls else 0.0,
            total_pnl_usd=sum(pnls),
            avg_pnl_usd=sum(pnls) / len(pnls) if pnls else 0.0,
            max_win_usd=max(wins) if wins else 0.0,
            max_loss_usd=min(losses) if losses else 0.0,
            avg_latency_ms=avg_lat,
            sharpe_ratio=sharpe,
        )
