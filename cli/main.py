"""
CLI entry point. Implements exact commands from spec.
Usage: polybot <command> [options]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from src.config import Config
from src.db import Database
from src.logger import setup_logging, get_logger

log = get_logger(__name__)


def _get_config() -> Config:
    return Config()


def _run(coro):
    return asyncio.run(coro)


@click.group()
@click.option("--config-dir", default=None, help="Path to config directory")
@click.pass_context
def cli(ctx: click.Context, config_dir: str | None) -> None:
    """Polymarket alpha trading system."""
    ctx.ensure_object(dict)
    cfg_path = Path(config_dir) if config_dir else None
    config = Config(config_dir=cfg_path)
    setup_logging(
        level=config.log_level,
        log_file=config.get("logging", "file"),
    )
    ctx.obj["config"] = config


# ─── validate-config ──────────────────────────────────────────────────────────

@cli.command("validate-config")
@click.pass_context
def validate_config(ctx: click.Context) -> None:
    """Validate all configuration files."""
    config: Config = ctx.obj["config"]
    try:
        required_keys = [
            ("api", "gamma_base_url"),
            ("api", "clob_base_url"),
            ("api", "ws_url"),
            ("rate_limiter", "orders_per_minute"),
            ("spike_fade", "min_spike_magnitude"),
            ("confidence", "min_threshold"),
            ("expiry", "min_days_to_expiry"),
            ("execution", "slippage_bps"),
        ]
        errors = []
        for keys in required_keys:
            val = config.get(*keys)
            if val is None:
                errors.append(f"Missing: {'.'.join(keys)}")

        weights = config.get("confidence", "weights", default={})
        w_sum = sum(float(v) for v in weights.values()) if weights else 0.0
        if weights and abs(w_sum - 1.0) > 0.01:
            errors.append(f"confidence.weights sum = {w_sum:.4f}, expected ~1.0")

        if errors:
            click.echo("CONFIG ERRORS:", err=True)
            for e in errors:
                click.echo(f"  - {e}", err=True)
            sys.exit(1)
        else:
            click.echo("[OK] Config valid")
            click.echo(json.dumps(config.as_dict(), indent=2, default=str))
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


# ─── init-db ─────────────────────────────────────────────────────────────────

@cli.command("init-db")
@click.pass_context
def init_db(ctx: click.Context) -> None:
    """Initialize the SQLite database schema."""
    config: Config = ctx.obj["config"]

    async def _run_init() -> None:
        async with Database(config.db_path) as db:
            click.echo(f"[OK] Database initialized at: {config.db_path}")

    _run(_run_init())


# ─── test-alert ───────────────────────────────────────────────────────────────

@cli.command("test-alert")
@click.pass_context
def test_alert(ctx: click.Context) -> None:
    """Send a test Telegram alert."""
    config: Config = ctx.obj["config"]
    from src.alerts.telegram import TelegramAlerter

    async def _run_alert() -> None:
        alerter = TelegramAlerter(config)
        ok = await alerter.send_raw("🤖 Polymarket bot: test alert ✓")
        if ok:
            click.echo("[OK] Alert sent")
        else:
            click.echo("[FAIL] Alert failed (check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)", err=True)
            sys.exit(1)

    _run(_run_alert())


# ─── discover-markets ─────────────────────────────────────────────────────────

@cli.command("discover-markets")
@click.option("--min-volume", default=None, type=float, help="Override min volume filter")
@click.option("--limit", default=20, help="Max markets to display")
@click.pass_context
def discover_markets(ctx: click.Context, min_volume: float | None, limit: int) -> None:
    """Discover and display active Polymarket markets."""
    config: Config = ctx.obj["config"]
    from src.data.gamma_client import GammaClient
    import datetime

    async def _run_discovery() -> None:
        async with GammaClient(config) as gamma:
            markets = await gamma.discover_markets(min_volume=min_volume)
            markets = markets[:limit]
            click.echo(f"\nDiscovered {len(markets)} markets:\n")
            for m in markets:
                name = m.get("question", m.get("title", m.get("id", "?")))[:80]
                vol = float(m.get("volume", m.get("volumeNum", 0)) or 0)
                end = m.get("endDate", m.get("end_date_iso", "?"))
                click.echo(f"  [{m.get('id', '?')[:8]}] {name}")
                click.echo(f"    Volume: ${vol:,.0f}  |  Ends: {end}")

    _run(_run_discovery())


# ─── run-bot ─────────────────────────────────────────────────────────────────

@cli.command("run-bot")
@click.option("--mode", type=click.Choice(["paper", "live"]), default="paper", show_default=True)
@click.pass_context
def run_bot(ctx: click.Context, mode: str) -> None:
    """Run the trading bot."""
    config: Config = ctx.obj["config"]

    if mode == "live":
        click.echo("ERROR: Live trading is disabled in v1. Use --mode paper.", err=True)
        sys.exit(1)

    click.echo(f"Starting bot in {mode.upper()} mode. Press Ctrl+C to stop.")

    async def _run_paper() -> None:
        from src.data.gamma_client import GammaClient
        from src.data.clob_client import CLOBClient
        from src.data.price_tracker import PriceTracker, PriceTick
        from src.data.ws_client import WSClient
        from src.strategy.spike_fade import SpikeFadeDetector
        from src.strategy.confidence import ConfidenceScorer
        from src.execution.paper_engine import PaperEngine
        from src.alerts.telegram import TelegramAlerter
        import datetime, time

        async with Database(config.db_path) as db:
            tracker = PriceTracker(config)
            detector = SpikeFadeDetector(config)
            scorer = ConfidenceScorer(config)
            engine = PaperEngine(config, db)
            alerter = TelegramAlerter(config)
            ws = WSClient(config)

            # Market discovery
            async with GammaClient(config) as gamma:
                markets = await gamma.discover_markets()
                click.echo(f"Tracking {len(markets)} markets")
                # Store markets in DB
                for m in markets:
                    mid = m.get("conditionId", m.get("id", ""))
                    name = m.get("question", m.get("title", ""))
                    end_date = m.get("endDate", m.get("end_date_iso", ""))
                    try:
                        end_dt = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        days = (end_dt - datetime.datetime.now(tz=datetime.timezone.utc)).days
                    except Exception:
                        days = 9999
                    await db.execute(
                        """INSERT OR REPLACE INTO markets
                           (id, name, end_date_iso, days_to_expiry, raw_json)
                           VALUES (?, ?, ?, ?, ?)""",
                        (mid, name, end_date, float(days), json.dumps(m)),
                    )
                    # Subscribe WS to market — clobTokenIds is a JSON string
                    import json as _json
                    clob_ids = m.get("clobTokenIds", m.get("clob_token_ids", m.get("tokens", "[]")))
                    if isinstance(clob_ids, str):
                        try:
                            clob_ids = _json.loads(clob_ids)
                        except Exception:
                            clob_ids = []
                    for tid in clob_ids:
                        if tid:
                            ws.subscribe_asset(str(tid))

            # WS message handler
            async def on_message(msg: dict) -> None:
                asset_id = msg.get("asset_id", msg.get("market", ""))
                price = msg.get("price")
                size = msg.get("size", msg.get("volume", 0))
                if not asset_id or price is None:
                    return
                tick = PriceTick(
                    token_id=asset_id,
                    price=float(price),
                    volume_usd=float(size),
                )
                tracker.add_tick(tick)

                # Find market for this token
                market_row = await db.fetchone(
                    "SELECT id, name, days_to_expiry, raw_json FROM markets WHERE raw_json LIKE ?",
                    (f"%{asset_id}%",),
                )
                if not market_row:
                    return

                market_id = market_row["id"]
                market_name = market_row["name"]
                days = float(market_row.get("days_to_expiry") or 9999)

                # Parse Gamma API market volume from stored discovery data
                try:
                    _m = json.loads(market_row.get("raw_json") or "{}")
                except Exception:
                    _m = {}
                market_vol_usd = float(_m.get("volumeNum", _m.get("volume", 0)) or 0)

                snap = tracker.get_snapshot(market_id, asset_id)
                if snap is None:
                    return

                signal = detector.detect(
                    snapshot=snap,
                    days_to_expiry=days,
                    current_volume_usd=tick.volume_usd,
                    market_volume_usd=market_vol_usd,
                )
                if not signal:
                    return

                print(f"[SIGNAL] {signal.direction} market={market_id} mag={round(signal.spike_magnitude_pct,4)}", flush=True)

                try:
                    confidence = scorer.score(signal)
                except Exception as exc:
                    print(f"[SIGNAL ERROR] scorer.score failed: {exc}", flush=True)
                    raise

                print(f"[CONFIDENCE] total={round(confidence.total,4)} meets={confidence.meets_threshold}", flush=True)

                try:
                    await alerter.send_signal(
                        market_name=market_name,
                        direction=signal.direction,
                        entry_price=signal.entry_price,
                        confidence=confidence.total,
                        days_to_expiry=signal.days_to_expiry,
                        volume_spike=signal.volume_spike_ratio,
                        mode=mode,
                    )
                except Exception as exc:
                    print(f"[SIGNAL ERROR] alerter.send_signal failed: {exc}", flush=True)
                    raise

                print(f"[ENGINE] calling try_open market={market_id}", flush=True)
                pos = await engine.try_open(signal, confidence, market_name)
                print(f"[ENGINE] try_open returned pos={pos}", flush=True)
                if pos:
                    await alerter.send_position_open(
                        market_name=market_name,
                        size_usd=pos.size_usd,
                        entry_price=pos.entry_price,
                        tp_price=pos.tp_price,
                        sl_price=pos.sl_price,
                    )

            ws.add_handler(on_message)

            # Background: check exits every 30s
            async def exit_loop() -> None:
                while True:
                    await asyncio.sleep(30)
                    prices = {tid: tracker.get_snapshot("", tid).current_price
                              for tid in tracker.token_ids()
                              if tracker.get_snapshot("", tid)}
                    closed = await engine.check_exits(prices)
                    for cp in closed:
                        mrow = await db.fetchone("SELECT name FROM markets WHERE id = ?", (cp.market_id,))
                        mname = mrow["name"] if mrow else cp.market_id
                        await alerter.send_position_closed(
                            market_name=mname,
                            pnl_usd=cp.pnl_usd or 0,
                            pnl_pct=cp.pnl_pct or 0,
                            reason=cp.close_reason or "",
                        )

            # Background: send daily report at 13:00 UTC
            async def daily_report_loop() -> None:
                from src.analytics.daily_report import DailyReporter
                reporter = DailyReporter(db, alerter)
                last_sent: datetime.date | None = None
                while True:
                    await asyncio.sleep(60)
                    now = datetime.datetime.now(tz=datetime.timezone.utc)
                    if now.hour == 13 and now.minute == 0 and last_sent != now.date():
                        try:
                            await reporter.run()
                            last_sent = now.date()
                            log.info("daily_report_sent")
                        except Exception as exc:
                            log.error("daily_report_error", error=str(exc))

            await asyncio.gather(ws.start(), exit_loop(), daily_report_loop())

    try:
        _run(_run_paper())
    except KeyboardInterrupt:
        click.echo("\nBot stopped.")


# ─── replay ───────────────────────────────────────────────────────────────────

@cli.command("replay")
@click.option("--market-id", default=None, help="Replay specific market")
@click.option("--limit", default=10000, help="Max ticks to replay")
@click.pass_context
def replay(ctx: click.Context, market_id: str | None, limit: int) -> None:
    """Replay historical price data through strategy."""
    config: Config = ctx.obj["config"]
    from src.analytics.replay import ReplayEngine

    async def _run_replay() -> None:
        async with Database(config.db_path) as db:
            engine = ReplayEngine(config, db)
            result = await engine.run(market_id=market_id, limit=limit)
            click.echo(f"\nReplay Results:")
            click.echo(f"  Ticks replayed:        {result.total_ticks_replayed:,}")
            click.echo(f"  Signals generated:     {result.signals_generated:,}")
            click.echo(f"  Signals > threshold:   {result.signals_above_threshold:,}")

    _run(_run_replay())


# ─── daily-report ─────────────────────────────────────────────────────────────

@cli.command("daily-report")
@click.option("--date", "report_date", default=None, help="Date YYYY-MM-DD (default: today)")
@click.pass_context
def daily_report(ctx: click.Context, report_date: str | None) -> None:
    """Generate and send daily performance report."""
    config: Config = ctx.obj["config"]
    from src.alerts.telegram import TelegramAlerter
    from src.analytics.daily_report import DailyReporter
    import datetime

    async def _run_report() -> None:
        async with Database(config.db_path) as db:
            alerter = TelegramAlerter(config)
            reporter = DailyReporter(db, alerter)
            parsed_date = None
            if report_date:
                parsed_date = datetime.date.fromisoformat(report_date)
            report = await reporter.run(report_date=parsed_date)
            click.echo(json.dumps(report, indent=2, default=str))

    _run(_run_report())


# ─── health-check ─────────────────────────────────────────────────────────────

@cli.command("health-check")
@click.pass_context
def health_check(ctx: click.Context) -> None:
    """Check connectivity to Gamma and CLOB APIs."""
    config: Config = ctx.obj["config"]
    from src.data.gamma_client import GammaClient
    from src.data.clob_client import CLOBClient

    async def _run_health() -> None:
        results = {}
        # Gamma API
        try:
            async with GammaClient(config) as gamma:
                markets = await gamma.get_markets(limit=1)
                results["gamma_api"] = "ok" if markets is not None else "no_data"
        except Exception as exc:
            results["gamma_api"] = f"error: {exc}"

        # CLOB API
        try:
            async with CLOBClient(config) as clob:
                data = await clob.get("/")
                results["clob_api"] = "ok"
        except Exception as exc:
            results["clob_api"] = f"error: {exc}"

        # DB
        try:
            async with Database(config.db_path) as db:
                row = await db.fetchone("SELECT 1 as ok")
                results["database"] = "ok" if row else "error"
        except Exception as exc:
            results["database"] = f"error: {exc}"

        all_ok = all("ok" in str(v) for v in results.values())
        click.echo(json.dumps(results, indent=2))
        sys.exit(0 if all_ok else 1)

    _run(_run_health())


if __name__ == "__main__":
    cli()
