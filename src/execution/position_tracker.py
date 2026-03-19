"""Position state management backed by SQLite."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.db import Database
from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class Position:
    id: int
    market_id: str
    direction: str
    entry_price: float
    size_usd: float
    tp_price: float
    sl_price: float
    time_stop_at: Optional[datetime]
    status: str
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    close_reason: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    mode: str = "paper"


class PositionTracker:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def open_position(
        self,
        market_id: str,
        direction: str,
        entry_price: float,
        size_usd: float,
        tp_price: float,
        sl_price: float,
        time_stop_at: datetime,
        confidence: float,
        mode: str = "paper",
    ) -> Position:
        cur = await self._db.execute(
            """INSERT INTO positions
               (market_id, direction, entry_price, size_usd, tp_price, sl_price,
                time_stop_at, status, mode, opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, datetime('now'))""",
            (market_id, direction, entry_price, size_usd, tp_price, sl_price,
             time_stop_at.isoformat(), mode),
        )
        row_id = cur.lastrowid
        return Position(
            id=row_id,
            market_id=market_id,
            direction=direction,
            entry_price=entry_price,
            size_usd=size_usd,
            tp_price=tp_price,
            sl_price=sl_price,
            time_stop_at=time_stop_at,
            status="open",
            mode=mode,
        )

    async def close_position(
        self, position_id: int, exit_price: float, reason: str
    ) -> Optional[Position]:
        pos_row = await self._db.fetchone(
            "SELECT * FROM positions WHERE id = ?", (position_id,)
        )
        if not pos_row:
            return None

        entry = float(pos_row["entry_price"])
        size = float(pos_row["size_usd"])
        direction = pos_row["direction"]

        if direction == "fade_yes":
            pnl_pct = (entry - exit_price) / entry
        else:
            pnl_pct = (exit_price - entry) / entry

        pnl_usd = size * pnl_pct

        await self._db.execute(
            """UPDATE positions SET
               status = 'closed', exit_price = ?, pnl_usd = ?, pnl_pct = ?,
               close_reason = ?, closed_at = datetime('now')
               WHERE id = ?""",
            (exit_price, pnl_usd, pnl_pct, reason, position_id),
        )

        return Position(
            id=position_id,
            market_id=pos_row["market_id"],
            direction=direction,
            entry_price=entry,
            size_usd=size,
            tp_price=float(pos_row["tp_price"]),
            sl_price=float(pos_row["sl_price"]),
            time_stop_at=None,
            status="closed",
            exit_price=exit_price,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            close_reason=reason,
            mode=pos_row.get("mode", "paper"),
        )

    async def get_open_positions(self) -> list[Position]:
        rows = await self._db.fetchall(
            "SELECT * FROM positions WHERE status = 'open'"
        )
        result = []
        for r in rows:
            ts_at = None
            if r.get("time_stop_at"):
                try:
                    ts_at = datetime.fromisoformat(r["time_stop_at"])
                except Exception:
                    pass
            result.append(Position(
                id=r["id"],
                market_id=r["market_id"],
                direction=r["direction"],
                entry_price=float(r["entry_price"]),
                size_usd=float(r["size_usd"]),
                tp_price=float(r["tp_price"]),
                sl_price=float(r["sl_price"]),
                time_stop_at=ts_at,
                status=r["status"],
                mode=r.get("mode", "paper"),
            ))
        return result

    async def count_open(self) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM positions WHERE status = 'open'"
        )
        return int(row["cnt"]) if row else 0
