"""
Gamma API client for Polymarket market discovery.
All URLs come from config — never hardcoded here.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.config import Config
from src.logger import get_logger

log = get_logger(__name__)


class GammaClient:
    """Async HTTP client for the Polymarket Gamma API."""

    def __init__(self, config: Config) -> None:
        self._base = config.gamma_base_url
        self._min_volume = config.get("discovery", "min_volume_usd", default=500_000)
        self._max_markets = config.get("discovery", "max_markets_per_poll", default=100)
        self._allowed_categories: set[str] = {
            c.lower() for c in config.get("filters", "allowed_categories", default=[])
        }
        self._blocked_categories: set[str] = {
            c.lower() for c in config.get("filters", "blocked_categories", default=[])
        }
        overrides = config.get("market_overrides", default={})
        self._whitelist: set[str] = set(overrides.get("whitelist") or [])
        self._blacklist: set[str] = set(overrides.get("blacklist") or [])
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GammaClient":
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        assert self._client, "Client not started"
        t0 = time.monotonic()
        try:
            resp = await self._client.get(path, params=params)
            latency_ms = (time.monotonic() - t0) * 1000
            log.debug("gamma.request", path=path, status=resp.status_code, latency_ms=round(latency_ms, 1))
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            log.error("gamma.http_error", path=path, status=exc.response.status_code, error=str(exc))
            raise
        except Exception as exc:
            log.error("gamma.request_failed", path=path, error=str(exc))
            raise

    async def get_markets(
        self,
        active: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch active markets from Gamma API."""
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": "false",
            "limit": limit or self._max_markets,
            "offset": offset,
        }
        data = await self._get("/markets", params=params)
        markets = data if isinstance(data, list) else data.get("data", data.get("markets", []))
        log.info("gamma.markets_fetched", count=len(markets))
        return markets

    async def get_market(self, market_id: str) -> dict[str, Any]:
        """Fetch a single market by ID."""
        return await self._get(f"/markets/{market_id}")

    async def discover_markets(self, min_volume: float | None = None) -> list[dict[str, Any]]:
        """
        Full discovery pass: fetch markets and filter by volume, binary type, and category.
        Logs the exact rejection reason for every market to aid debugging.
        """
        raw = await self.get_markets()
        threshold = min_volume if min_volume is not None else self._min_volume
        allowed = self._allowed_categories
        blocked = self._blocked_categories
        whitelist = self._whitelist
        blacklist = self._blacklist

        filtered = []
        rejection_counts: dict[str, int] = {}

        for m in raw:
            name = m.get("question", m.get("title", m.get("id", "?")))

            # Whitelist bypasses all filters
            mid = m.get("conditionId", m.get("id", ""))
            if whitelist and mid in whitelist:
                filtered.append(m)
                continue

            # Blacklist always rejects
            if blacklist and mid in blacklist:
                reason = "blacklisted"
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                continue

            # Skip closed markets
            if m.get("closed", False):
                reason = "closed"
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                continue

            # Accept only binary (YES/NO) markets — clobTokenIds is a JSON string
            clob_ids = m.get("clobTokenIds", m.get("clob_token_ids", m.get("tokens", [])))
            if isinstance(clob_ids, str):
                import json as _json
                try:
                    clob_ids = _json.loads(clob_ids)
                except Exception:
                    clob_ids = []
            if len(clob_ids) != 2:
                reason = f"not_binary(tokens={len(clob_ids)})"
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                continue

            vol = float(m.get("volumeNum", m.get("volume", 0)) or 0)
            if vol < threshold:
                reason = f"low_volume(${vol:,.0f}<${threshold:,.0f})"
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                continue

            # Collect market tags for category checks
            tags = m.get("tags", [])
            tag_labels = {
                (t.get("label", t) if isinstance(t, dict) else t).lower()
                for t in tags
            }
            top_category = (m.get("category") or "").lower()
            if top_category:
                tag_labels.add(top_category)

            if not tag_labels:
                # Market has no tags — check name/slug for blocked sports keywords.
                _BLOCKED_NAME_KEYWORDS = {
                    "nba", "nfl", "fifa", "nhl", "mlb", "world cup",
                    "champions league", "76ers", "lakers", "celtics",
                    "warriors", "knicks", "finals", "playoff", "super bowl",
                    "ufc", "boxing", "mma", "wrestling",
                }
                slug = (m.get("slug", "") or "").lower()
                name_lower = name.lower()
                hit = next(
                    (kw for kw in _BLOCKED_NAME_KEYWORDS if kw in name_lower or kw in slug),
                    None,
                )
                if hit:
                    reason = f"blocked_keyword({hit})"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                    continue
                log.debug("gamma.market_untagged", market=name[:60])
            else:
                # Reject if category is explicitly blocked
                if blocked and tag_labels.intersection(blocked):
                    bad = tag_labels.intersection(blocked)
                    reason = f"blocked_category({','.join(bad)})"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                    continue

                # Reject if not in the allowed category list (only when list is non-empty)
                if allowed and not tag_labels.intersection(allowed):
                    reason = f"no_allowed_category(tags={sorted(tag_labels)})"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    log.debug("gamma.market_rejected", reason=reason, market=name[:60])
                    continue

            filtered.append(m)

        log.info(
            "gamma.discovery_complete",
            total=len(raw),
            filtered=len(filtered),
            rejection_summary=rejection_counts,
        )
        return filtered
