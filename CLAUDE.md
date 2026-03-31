# CLAUDE.md — Polymarket Bot

Working notes for Claude Code. Reflects actual state as of 2026-03-31.

## Running the bot

```bash
python -m cli.main run-bot --mode paper
python -m cli.main discover-markets
python -m cli.main health-check
python -m cli.main validate-config
```

## Architecture

Single-process async bot (`cli/main.py`). No event bus — signal flow is direct function calls:

```
WS tick → on_message() → PriceTracker → SpikeFadeDetector.detect()
        → ConfidenceScorer.score() → TelegramAlerter.send_signal()
        → PaperEngine.try_open()
```

### Key source files

| File | Role |
|------|------|
| `cli/main.py` | Entry point, `on_message` handler, bot loop |
| `src/data/price_tracker.py` | Rolling price window, tick downsampling |
| `src/data/ws_client.py` | WebSocket client, reconnect logic |
| `src/data/gamma_client.py` | Gamma API market discovery |
| `src/strategy/spike_fade.py` | Signal detection, cooldown tracking |
| `src/strategy/confidence.py` | Confidence scoring |
| `src/execution/paper_engine.py` | Paper trade execution |
| `src/alerts/telegram.py` | Telegram alerts |
| `src/db.py` | SQLite async helpers |

### Config loading order

`settings.yaml` → `strategy.yaml` → `telegram.yaml` → `risk.yaml` → `markets.yaml` (optional, overrides previous)

## Current parameter values (2026-03-31)

### Signal detection (`config/strategy.yaml`)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `min_spike_magnitude` | 0.08 | 8pp minimum price move |
| `baseline_window_seconds` | 600 | 10-minute baseline |
| `volume_spike_multiplier` | 0.5 | Lowered for paper trading (live: 2.0+) |
| `cooldown_seconds_per_market` | 300 | 5 min between signals on same market |
| `min_volume_usd` | 100 | Per-tick floor (Gamma volume is the real filter) |

### Confidence & execution

| Parameter | Value | Notes |
|-----------|-------|-------|
| `confidence.min_threshold` | 0.40 | Paper trading (live: 0.55+) |
| `alerts.min_confidence_for_alert` | 0.40 | Paper trading (live: 0.60) |
| `expiry.min_days_to_expiry` | 30 | |
| `filters.max_spread` | 0.10 | |

### Discovery (`config/markets.yaml`)

| Parameter | Value |
|-----------|-------|
| `discovery.min_volume_usd` | 500,000 |
| `allowed_categories` | politics, geopolitics, macro, elections, science, technology, tech, business, finance, economics, world, news, law, legal, climate, health, ai, other |
| `blocked_categories` | sports, nfl, nba, mlb, nhl, soccer, football, basketball, baseball, tennis, golf, mma, boxing, hockey, racing, esports, **crypto, cryptocurrency, entertainment, culture** |

## Volume filter (important — was bugged before 2026-03-31)

`SpikeFadeDetector.detect()` receives `market_volume_usd` from the Gamma API (stored in `raw_json` in the `markets` DB table at discovery time). This is the real cumulative market volume.

**Do NOT use `snapshot.rolling_volume`** for the volume filter — that is a sum of WS tick `size` fields (orderbook change sizes), not market volume. A market with $1.4M real volume showed `rolling_vol_usd=$14` because of this bug.

In `on_message()`, volume is parsed from the stored `raw_json`:
```python
_m = json.loads(market_row.get("raw_json") or "{}")
market_vol_usd = float(_m.get("volumeNum", _m.get("volume", 0)) or 0)
```

## Cooldown

`SpikeFadeDetector` holds `_last_signal_ts: dict[str, float]` (market_id → Unix timestamp). Cooldown is checked first in `detect()`, before all other filters. Timestamp is updated when a signal is emitted.

## WebSocket

- Subscription type: `"Market"` (capital M — lowercase was silently rejected by server)
- Message fields used: `asset_id`, `price`, `size`
- Tick downsampling: 1 tick per 10 seconds per token (`min_tick_interval_seconds: 10` in `price_tracker` config)

## Database

- Path: `data/polymarket.db` (default in `Config.db_path`, overrideable via `DB_PATH` env var)
- Schema: `markets`, `price_ticks`, `signals`, `positions`, `latency_log`
- `markets.raw_json` stores full Gamma API response — used at runtime for volume lookup

## Telegram

- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `TELEGRAM_CHAT_ID` format for private chats: numeric only, **no minus sign** (e.g. `8731364432`)
- Minus prefix is for group chats only

## Paper trading vs live

The bot only supports `--mode paper`. Live trading is explicitly disabled in `cli/main.py`. Several thresholds are intentionally relaxed for paper trading (see table above) — restore before going live.
