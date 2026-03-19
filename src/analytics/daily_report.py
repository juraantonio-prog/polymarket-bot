"""Daily performance report generation."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.analytics.metrics import MetricsCalculator
from src.alerts.telegram import TelegramAlerter
from src.db import Database
from src.logger import get_logger

log = get_logger(__name__)


class DailyReporter:
    def __init__(self, db: Database, alerter: TelegramAlerter) -> None:
        self._calculator = MetricsCalculator(db)
        self._alerter = alerter

    async def run(self, report_date: date | None = None) -> dict:
        if report_date is None:
            report_date = date.today()
        date_str = report_date.isoformat()
        date_from = f"{date_str} 00:00:00"
        date_to = f"{date_str} 23:59:59"

        metrics = await self._calculator.compute(date_from=date_from, date_to=date_to)
        report = {
            "date": date_str,
            "total_trades": metrics.total_trades,
            "winning_trades": metrics.winning_trades,
            "losing_trades": metrics.losing_trades,
            "win_rate": metrics.win_rate,
            "total_pnl_usd": metrics.total_pnl_usd,
            "avg_pnl_usd": metrics.avg_pnl_usd,
            "max_win_usd": metrics.max_win_usd,
            "max_loss_usd": metrics.max_loss_usd,
            "avg_latency_ms": metrics.avg_latency_ms,
            "sharpe_ratio": metrics.sharpe_ratio,
        }

        log.info("daily_report", **report)

        await self._alerter.send_daily_report(
            date=date_str,
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            total_pnl=metrics.total_pnl_usd,
            avg_latency_ms=metrics.avg_latency_ms,
        )
        return report
