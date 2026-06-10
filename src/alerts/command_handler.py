"""
Telegram command handler.
Long-polls getUpdates and responds to /status, /positions, /help.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.db import Database
from src.logger import get_logger

log = get_logger(__name__)

# P&L cutoff: data before this date contains noise from early testing
_CLEAN_DATA_FROM = "2026-05-29 00:00:00"
_CLEAN_DATA_LABEL = "29.05."

# Daily report fires at 20:00 UTC
_DAILY_REPORT_HOUR_UTC = 20

_HELP = (
    "*Polymarket Bot — dostupne komande:*\n\n"
    "/status — status bota, pozicije i P&L\n"
    "/positions — lista otvorenih pozicija\n"
    "/help — ova poruka"
)


def _safe(text: str) -> str:
    """Strip Markdown special chars from untrusted strings (market names)."""
    return text.replace("*", "").replace("_", " ").replace("`", "").replace("[", "")


def _sign(val: float) -> str:
    return "+" if val >= 0 else ""


class TelegramCommandHandler:
    """Polls Telegram for bot commands and replies with live bot state."""

    def __init__(
        self,
        db: Database,
        bot_start_time: float,
        risk_guard: Optional[Any] = None,
        min_confidence_threshold: float = 0.40,
    ) -> None:
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._db = db
        self._start_time = bot_start_time
        self._offset: int = 0
        self._risk_guard = risk_guard
        self._min_confidence_threshold = min_confidence_threshold

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
        now_utc = datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        today_from = f"{today} 00:00:00"

        # --- P&L od 29.05. (clean data) + win rate ---
        clean_row = await self._db.fetchone(
            "SELECT COALESCE(SUM(pnl_usd), 0) as pnl, COUNT(*) as cnt, "
            "COUNT(CASE WHEN pnl_usd > 0 THEN 1 END) as wins "
            "FROM positions WHERE status = 'closed' AND closed_at >= ?",
            (_CLEAN_DATA_FROM,),
        )
        clean_pnl = float(clean_row["pnl"]) if clean_row else 0.0
        clean_cnt = int(clean_row["cnt"]) if clean_row else 0
        clean_wins = int(clean_row["wins"] or 0) if clean_row else 0
        clean_wr = clean_wins / clean_cnt if clean_cnt > 0 else 0.0

        # --- Prosjecni holding time od 29.05. ---
        holding_row = await self._db.fetchone(
            "SELECT AVG((julianday(closed_at) - julianday(opened_at)) * 1440) as avg_min "
            "FROM positions WHERE status = 'closed' AND closed_at >= ?",
            (_CLEAN_DATA_FROM,),
        )
        avg_hold_min = float(holding_row["avg_min"]) if holding_row and holding_row["avg_min"] else 0.0
        if avg_hold_min >= 60:
            avg_hold_str = f"{avg_hold_min / 60:.1f}h"
        else:
            avg_hold_str = f"{avg_hold_min:.0f}min"

        # --- P&L ukupno (sve zatvorene pozicije) ---
        total_row = await self._db.fetchone(
            "SELECT COALESCE(SUM(pnl_usd), 0) as pnl FROM positions WHERE status = 'closed'"
        )
        total_pnl = float(total_row["pnl"]) if total_row else 0.0

        # --- Danas: broj tradova, max win/loss ---
        today_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt, "
            "COALESCE(MAX(pnl_usd), 0) as max_win, "
            "COALESCE(MIN(pnl_usd), 0) as max_loss "
            "FROM positions WHERE status = 'closed' AND closed_at >= ?",
            (today_from,),
        )
        today_cnt = int(today_row["cnt"]) if today_row else 0
        today_max_win = float(today_row["max_win"]) if today_row else 0.0
        today_max_loss = float(today_row["max_loss"]) if today_row else 0.0

        # --- Risk: dnevni gubitak od DB ---
        daily_pnl_row = await self._db.fetchone(
            "SELECT COALESCE(SUM(pnl_usd), 0) as pnl FROM positions "
            "WHERE status = 'closed' AND closed_at >= ?",
            (today_from,),
        )
        daily_pnl = float(daily_pnl_row["pnl"]) if daily_pnl_row else 0.0

        # --- Risk: uzastopni gubici (iz DB) ---
        recent_rows = await self._db.fetchall(
            "SELECT pnl_usd FROM positions WHERE status = 'closed' "
            "ORDER BY closed_at DESC LIMIT 20"
        )
        consecutive = 0
        for r in recent_rows:
            if float(r.get("pnl_usd") or 0) <= 0:
                consecutive += 1
            else:
                break

        # --- Risk: cooldown (iz in-memory RiskGuard stanja) ---
        in_cooldown = False
        cooldown_str = "NE"
        if self._risk_guard is not None:
            now_ts = time.time()
            if getattr(self._risk_guard, "_cooldown_until", 0.0) > now_ts:
                in_cooldown = True
                rem_h = (self._risk_guard._cooldown_until - now_ts) / 3600
                cooldown_str = f"DA ({rem_h:.1f}h preostalo)"

        # --- Signali danas ---
        sig_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM signals WHERE created_at >= ?",
            (today_from,),
        )
        signals_today = int(sig_row["cnt"]) if sig_row else 0

        pos_opened_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM positions WHERE opened_at >= ?",
            (today_from,),
        )
        positions_today = int(pos_opened_row["cnt"]) if pos_opened_row else 0
        skipped_today = max(0, signals_today - positions_today)

        # Razlog preskakanja: koliko ima confidence ispod praga
        conf_skip_row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM signals WHERE created_at >= ? AND confidence < ?",
            (today_from, self._min_confidence_threshold),
        )
        conf_skipped = int(conf_skip_row["cnt"] or 0) if conf_skip_row else 0

        if skipped_today == 0:
            skip_reason = "—"
        elif conf_skipped >= skipped_today:
            skip_reason = "confidence"
        elif conf_skipped > 0:
            skip_reason = f"confidence ({conf_skipped}), ostalo max_open/risk"
        else:
            skip_reason = "max_open / risk"

        # --- Sati do sljedeceg dnevnog reporta (20:00 UTC) ---
        next_report = now_utc.replace(
            hour=_DAILY_REPORT_HOUR_UTC, minute=0, second=0, microsecond=0
        )
        if now_utc >= next_report:
            next_report += timedelta(days=1)
        hours_until = (next_report - now_utc).total_seconds() / 3600

        # --- Uptime ---
        elapsed = int(time.time() - self._start_time)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)

        msg = (
            f"*Bot status*\n"
            f"Status: ✅ Aktivan  |  Uptime: {h}h {m}m {s}s\n\n"
            f"✅ *P&L od {_CLEAN_DATA_LABEL}*: "
            f"*{_sign(clean_pnl)}{clean_pnl:.2f} USD*  ({clean_cnt} trad.)\n"
            f"⚠️ *P&L ukupno* _(uklj. stare podatke)_: "
            f"*{_sign(total_pnl)}{total_pnl:.2f} USD*\n"
            f"\U0001f4ca *Win rate od {_CLEAN_DATA_LABEL}*: "
            f"*{clean_wr * 100:.1f}%*  ({clean_wins}/{clean_cnt})\n"
            f"⏱ *Avg holding time od {_CLEAN_DATA_LABEL}*: *{avg_hold_str}*\n\n"
            f"\U0001f4c5 *Danas*\n"
            f"  Zatvoreni tradovi: *{today_cnt}*\n"
            f"  Najveci dobitak: *{_sign(today_max_win)}{today_max_win:.2f} USD*\n"
            f"  Najveci gubitak: *{_sign(today_max_loss)}{today_max_loss:.2f} USD*\n\n"
            f"\U0001f6e1 *Risk status*\n"
            f"  Dnevni gubitak: *{daily_pnl:.2f}* / -250.00 USD\n"
            f"  Uzastopni gubici: *{consecutive}* / 4\n"
            f"  Cooldown aktivan: *{cooldown_str}*\n\n"
            f"\U0001f4e1 *Signali danas*\n"
            f"  Detektirano: *{signals_today}*\n"
            f"  Preskoceno: *{skipped_today}*  _(razlog: {skip_reason})_\n\n"
            f"⏰ *Sljedeci dnevni report*: za *{hours_until:.1f}h*  (20:00 UTC)"
        )
        await self._send(msg)

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
                f"  Velicina: ${float(r['size_usd']):.0f}\n"
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
