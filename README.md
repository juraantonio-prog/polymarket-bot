# Polymarket Alpha Bot

Production-grade private Polymarket signal detection and paper trading system.

## Features

- **Market Discovery** — Gamma API polling with volume + binary market filters
- **Real-time Data** — WebSocket price/volume feed with auto-reconnect
- **Spike-Fade Strategy** — Detects anomalous price spikes with volume confirmation
- **Confidence Scoring** — Normalized [0,1] multi-factor scoring with configurable weights
- **Paper Trading** — Full position lifecycle with TP/SL/time-stop simulation
- **Telegram Alerts** — Structured signal and trade alerts
- **Daily Reports** — Performance metrics with Sharpe ratio
- **Replay Mode** — Backtest strategy changes against stored ticks

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your Telegram credentials (optional for paper mode)
```

All trading thresholds are in `config/strategy.yaml`.
All API endpoints are in `config/settings.yaml`.

### 3. Initialize database

```bash
polybot init-db
```

### 4. Validate config

```bash
polybot validate-config
```

### 5. Run

```bash
# Paper trading (default, no credentials needed)
polybot run-bot --mode paper

# Other commands
polybot discover-markets
polybot health-check
polybot test-alert
polybot replay --limit 5000
polybot daily-report
polybot daily-report --date 2025-01-15
```

## Architecture

```
src/
├── config.py          — YAML config loader
├── db.py              — SQLite schema + async helpers
├── logger.py          — Structured JSON logging (structlog)
├── auth/              — Wallet + signing skeletons (disabled v1)
├── data/              — Gamma API, CLOB REST, WebSocket, price tracker
├── strategy/          — Spike-fade detector, confidence scorer
├── execution/         — Paper engine, position tracker
├── alerts/            — Telegram integration
└── analytics/         — Metrics, daily report, replay
```

## Configuration Reference

### strategy.yaml

| Key | Default | Description |
|-----|---------|-------------|
| `spike_fade.min_spike_magnitude` | `0.05` | Min price move to trigger signal |
| `spike_fade.volume_spike_multiplier` | `2.0` | Min volume ratio vs rolling avg |
| `confidence.min_threshold` | `0.55` | Min score to open position |
| `expiry.min_days_to_expiry` | `30` | Reject markets expiring soon |
| `execution.slippage_bps` | `100` | Simulated slippage in basis points |
| `execution.take_profit_delta` | `0.06` | TP distance from entry |
| `execution.stop_loss_delta` | `0.04` | SL distance from entry |
| `execution.time_stop_seconds` | `2400` | Max position hold time |

## Live Trading

Live trading is **disabled** in v1. Auth module skeleton is in `src/auth/`:
- `wallet.py` — Polygon wallet (EVM)
- `eip712.py` — EIP-712 order signing, chain ID 137
- `hmac_signer.py` — HMAC-SHA256 for CLOB authenticated endpoints

## Tests

```bash
pytest tests/ -v
```

## Constraints

- No live trading without explicit `--mode live` (disabled in v1)
- All thresholds from config files — no hardcoded values
- No LLM in decision loop
- All errors logged via structlog
- Rate limiter: 60 orders/min sustained, exponential backoff on HTTP 429
- Paper mode requires zero external credentials
