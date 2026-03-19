"""
WebSocket client for Polymarket CLOB subscriptions.
Handles reconnect with exponential backoff.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed

from src.config import Config
from src.logger import get_logger

log = get_logger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class WSClient:
    """Resilient WebSocket client with auto-reconnect."""

    def __init__(self, config: Config) -> None:
        self._url = config.ws_url
        ws_cfg = config.get("websocket", default={})
        self._ping_interval = ws_cfg.get("ping_interval_seconds", 30)
        self._reconnect_delay = ws_cfg.get("reconnect_delay_seconds", 5)
        self._max_attempts = ws_cfg.get("max_reconnect_attempts", 10)
        self._asset_ids: list[str] = []
        self._handlers: list[MessageHandler] = []
        self._running = False
        self._ws: Any = None

    def add_handler(self, handler: MessageHandler) -> None:
        self._handlers.append(handler)

    def subscribe_market(self, market_id: str) -> None:
        self._asset_ids.append(market_id)

    def subscribe_asset(self, asset_id: str) -> None:
        self._asset_ids.append(asset_id)

    async def start(self) -> None:
        self._running = True
        attempt = 0
        while self._running and attempt < self._max_attempts:
            try:
                log.info("ws.connecting", url=self._url, attempt=attempt)
                async with websockets.connect(
                    self._url,
                    ping_interval=self._ping_interval,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    attempt = 0
                    await self._send_subscriptions(ws)
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            # Server sends list of events or empty list on subscribe ack
                            if isinstance(msg, list):
                                for item in msg:
                                    if isinstance(item, dict):
                                        await self._dispatch(item)
                            elif isinstance(msg, dict):
                                await self._dispatch(msg)
                        except json.JSONDecodeError:
                            log.warning("ws.bad_json", raw=raw[:200])
            except ConnectionClosed as exc:
                log.warning("ws.disconnected", code=exc.code, reason=exc.reason)
            except Exception as exc:
                log.error("ws.error", error=str(exc))

            if self._running:
                delay = min(self._reconnect_delay * (2 ** attempt), 60)
                log.info("ws.reconnecting", delay=delay, attempt=attempt)
                await asyncio.sleep(delay)
                attempt += 1

        log.info("ws.stopped")

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _send_subscriptions(self, ws: Any) -> None:
        if not self._asset_ids:
            log.warning("ws.no_assets", msg="No assets to subscribe to")
            return
        # Polymarket WS protocol: one message with all asset IDs
        sub = {
            "assets_ids": self._asset_ids,
            "type": "market",
        }
        await ws.send(json.dumps(sub))
        log.info("ws.subscribed", assets=len(self._asset_ids))

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        for handler in self._handlers:
            try:
                await handler(msg)
            except Exception as exc:
                log.error("ws.handler_error", error=str(exc))
