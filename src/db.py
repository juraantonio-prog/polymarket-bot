"""SQLite schema + async helpers via aiosqlite."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite

from src.logger import get_logger

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    question TEXT,
    category TEXT,
    end_date_iso TEXT,
    days_to_expiry REAL,
    active INTEGER DEFAULT 1,
    discovered_at TEXT DEFAULT (datetime('now')),
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS price_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,           -- 'yes' | 'no'
    price REAL NOT NULL,
    volume_usd REAL,
    recorded_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    direction TEXT NOT NULL,      -- 'fade_yes' | 'fade_no'
    entry_price REAL NOT NULL,
    confidence REAL NOT NULL,
    spike_magnitude REAL,
    volume_spike REAL,
    days_to_expiry REAL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    market_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    size_usd REAL NOT NULL,
    tp_price REAL NOT NULL,
    sl_price REAL NOT NULL,
    time_stop_at TEXT NOT NULL,
    status TEXT DEFAULT 'open',   -- 'open' | 'closed'
    exit_price REAL,
    pnl_usd REAL,
    pnl_pct REAL,
    close_reason TEXT,
    opened_at TEXT DEFAULT (datetime('now')),
    closed_at TEXT,
    mode TEXT DEFAULT 'paper',
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE IF NOT EXISTS latency_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    status_code INTEGER,
    recorded_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_price_ticks_market ON price_ticks(market_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_id, status);
CREATE INDEX IF NOT EXISTS idx_signals_market ON signals(market_id, created_at);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        log.info("db.connected", path=self.path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        assert self._conn, "Database not connected"
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        assert self._conn, "Database not connected"
        cur = await self._conn.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        assert self._conn, "Database not connected"
        cur = await self._conn.execute(sql, params)
        row = await cur.fetchone()
        return dict(row) if row else None

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
