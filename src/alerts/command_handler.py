"""
Telegram command handler.
Long-polls getUpdates and responds to /status, /positions, /help.
"""
from __future__ import annotations

import os
import time

import httpx

from src.db import Database
from src.logger import get_logger

log = get_logger(__name__)

_HELP = (
    "*Polymarket Bot — dostupne komande:*\n\n"
    "/status — status bota, pozicije i P&L\n"
    "/positions — lista otvorenih pozicija\n"
    "/help — ova poruka"
)


def _safe(text: str) -> str:
    """Strip Markdown special chars from untrusted strings (market names)."""
    return text.replace("*", "").replace("_", " ").replace("`", "").replace("[", "")


class TelegramCommandHandler:
    """Polls Telegram for bot commands and replies with live bot state."""

    def __init__(self, db: Database, bot_start_time: float) -> None:
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._db = db
        self._start_time = bot_start_time
        self._offset: int = 0

    def _is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    async def _send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
        except Exception as exc:
            log.error("cmd_handler.send_failed", error=str(exc))

    async def _fetch_updates(self, timeout: int = 30) -> list[dict]:
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        try:
            async with httpx.AsyncClient(timeout=float(timeout + 5)) as client:
                resp = await client.get(url, params={
                    "offset": self._offset,
                    "timeout": timeout,
                    "allowed_updates": ["message"],
                })
                data = resp.json()
                return data.get("result", []) if data.get("ok") else []
        except Exception as exc:
            log.warning("cmd_handler.poll_failed", error=str(exc))
            return []

    async def _handle_status(self) -> None:
        open_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM positions WHERE status = 'open'"
        )
        closed_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM positions WHERE status = 'closed'"
        )
        pnl_row = await self._db.fetchone(
            "SELECT COALESCE(SUM(pnl_usd), 0) as total FROM positions WHERE status = 'closed'"
        )

        n_open = int(open_row["cnt"]) if open_row else 0
        n_closed = int(closed_row["cnt"]) if closed_row else 0
        total_pnl = float(pnl_row["total"]) if pnl_row else 0.0

        elapsed = int(time.time() - self._start_time)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        sign = "+" if total_pnl >= 0 else ""

        await self._send(
            f"*Bot status*\n\n"
            f"Status: ✅ Aktivan\n"
            f"Uptime: {h}h {m}m {s}s\n\n"
            f"Otvorene pozicije: *{n_open}*\n"
            f"Zatvoreni tradovi: *{n_closed}*\n"
            f"Ukupni P&L: *{sign}{total_pnl:.2f} USD*"
        )

    async def _handle_positions(self) -> None:
        rows = await self._db.fetchall(
            """SELECT p.id, p.market_id, p.direction, p.entry_price,
                      p.size_usd, p.tp_price, p.sl_price, p.opened_at,
                      m.name as market_name
               FROM positions p
               LEFT JOIN markets m ON p.market_id = m.id
               WHERE p.status = 'open'
               ORDER BY p.opened_at DESC"""
        )
        if not rows:
            await self._send("Nema otvorenih pozicija.")
            return

        parts = ["*Otvorene pozicije:*\n"]
        for r in rows:
            raw_name = r.get("market_name") or r["market_id"]
            name = _safe(raw_name[:50])
            direction = "SHORT (fade YES)" if r["direction"] == "fade_yes" else "LONG (fade NO)"
            parts.append(
                f"*#{r['id']}* {name}\n"
                f"  Smjer: {direction}\n"
                f"  Entry: *{float(r['entry_price']):.4f}*\n"
                f"  TP: {float(r['tp_price']):.4f}  |  SL: {float(r['sl_price']):.4f}\n"
                f"  Veličina: ${float(r['size_usd']):.0f}\n"
            )
        await self._send("\n".join(parts))

    async def _dispatch(self, text: str) -> None:
        cmd = text.strip().split()[0].lower()
        if cmd == "/status":
            await self._handle_status()
        elif cmd == "/positions":
            await self._handle_positions()
        elif cmd == "/help":
            await self._send(_HELP)
        else:
            await self._send(
                f"Nepoznata komanda: `{cmd}`\nKoristi /help za listu komandi."
            )

    async def poll_loop(self) -> None:
        """Long-poll Telegram for commands indefinitely."""
        if not self._is_configured():
            log.warning(
                "cmd_handler.disabled",
                reason="TELEGRAM_BOT_TOKEN/CHAT_ID not set",
            )
            return

        # Drain updates that arrived before bot started (no processing)
        initial = await self._fetch_updates(timeout=0)
        if initial:
            self._offset = initial[-1]["update_id"] + 1

        log.info("cmd_handler.started")
        while True:
            updates = await self._fetch_updates(timeout=30)
            for upd in updates:
                self._offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if text.startswith("/") and chat_id == self._chat_id:
                    log.info("cmd_handler.command", cmd=text.split()[0])
                    try:
                        await self._dispatch(text)
                    except Exception as exc:
                        log.error("cmd_handler.dispatch_error", error=str(exc))
