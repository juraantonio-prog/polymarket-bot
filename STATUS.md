# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 10.06.2026.

---

## Infrastruktura

| Stavka | Vrijednost |
|--------|-----------|
| VPS IP | 204.168.167.229 |
| SSH | `ssh root@204.168.167.229` |
| Putanja na VPS-u | `/root/polymarket-bot` |
| Python venv | `/root/polymarket-bot/venv` |
| Servis | `systemd` — `polymarket-bot.service` |
| Lokalni projekt | `C:\ClaudeProjects\polymarket-bot` |
| GitHub | https://github.com/juraantonio-prog/polymarket-bot |
| Branch | `master` (ne main!) |
| Claude Code | radi lokalno na laptopu, ne na VPS-u |
| CLI komanda | `python /root/polymarket-bot/cli/main.py <cmd>` |
| Prava DB | `/root/polymarket-bot/data/polymarket.db` |
| sqlite3 putanja | `/usr/bin/sqlite3` (ne samo `sqlite3`!) |
| Telegram token | u `.env` kao `TELEGRAM_BOT_TOKEN` |
| Telegram chat_id | u `.env` kao `TELEGRAM_CHAT_ID` (bez minusa — private chat) |
| Telegram bot | @pm_alfa_bot (PolymarketAlpha) |

---

## Trenutni status

| | Stavka |
|-|--------|
| ✅ | Bot radi 24/7 na VPS-u |
| ✅ | systemd servis aktivan i enabled |
| ✅ | Telegram alertovi rade |
| ✅ | WebSocket prima live price updateove |
| ✅ | Signal detection radi |
| ✅ | Paper engine otvara pozicije |
| ✅ | Exit logika implementirana (TP/SL/timeout svakih 30s) |
| ✅ | Cooldown 900s per market |
| ✅ | Sports/crypto/entertainment blokirani po keyword filteru |
| ✅ | pnl_usd kalkulacija ispravljena (29.05.) |
| ✅ | 6-faktorski confidence scoring normaliziran [0.0, 1.0] |
| ✅ | RiskGuard: max $250 dnevni gubitak, 4 uzastopna gubitka → 2h cooldown |
| ✅ | Time-to-expiry filter: min 30 dana do isteka |
| ✅ | Telegram command handler: /status, /positions, /help |
| ✅ | Automatski dnevni report u 20:00 UTC |
| ✅ | Entry price filter: odbij tržišta izvan [0.05, 0.95] (10.06.) |
| ✅ | /status: prosječni holding time od 29.05. (10.06.) |
| ✅ | Dnevni report: broj signala odbijenih zbog entry price (10.06.) |
| ⏳ | Čekamo signale s novim parametrima |

---

## Faza projekta

**Faza 1 — Paper trading** (aktivna od 29.03.2026.)

- Paper bankroll: $10,000
- Nominalni iznos po tradu: $100
- Max otvorenih pozicija: 5
- Cooldown per market: 900s (15 min)
- Live trading: **ONEMOGUĆEN**
- Pouzdana statistika kreće od: **29.05.2026.**
- Tradovi od 29.05.: **12** | Win rate: **25%** | P&L: **-$0.09**

---

## Strategija (spike-fade)

| Parametar | Vrijednost |
|-----------|-----------|
| Min. pomak cijene | 0.08 (sniženo 10.06.) |
| Rolling window | 300s (5 min) |
| Min. volume multiple | 1.5x (sniženo 10.06.) |
| Min. market volume | $500,000 |
| Take profit | ±0.08 od entry |
| Stop loss | ∓0.03 od entry |
| Max hold | 2400s (40 min) |
| Min. confidence | 0.55 (sniženo 10.06.) |
| Cooldown per market | 900s (15 min) |
| Min. days to expiry | 30 dana |
| Entry price filter | [0.05, 0.95] — odbij izvan raspona (10.06.) |
| Exit check interval | 30s |

---

## Confidence scoring (6 faktora, sve [0.0, 1.0])

| Faktor | Formula | Weight |
|--------|---------|--------|
| price_move_strength | clamp((move - 0.08) / 0.08, 0, 1) | 0.30 |
| volume_spike_strength | clamp((vol_mult - 1.5) / 3.0, 0, 1) | 0.20 |
| spread_quality | clamp(1 - spread_bps/max_spread, 0, 1) | 0.15 |
| liquidity_quality | clamp(log10(vol/min_vol) / 2, 0, 1) | 0.15 |
| market_priority | priority / 10.0 | 0.10 |
| category_weight | iz category_weights u strategy.yaml | 0.10 |

---

## Risk kontrole (RiskGuard)

| Pravilo | Vrijednost |
|---------|-----------|
| Max dnevni gubitak | $250 — tvrdi stop |
| Max uzastopnih gubitaka | 4 → 2h cooldown |
| Max otvorenih pozicija | 5 |
| Slippage | 100 bps |

---

## Telegram komande

| Komanda | Opis |
|---------|------|
| `/status` | P&L od 29.05. + ukupni P&L + win rate + **avg holding time** + tradovi danas + risk status + signali + countdown |
| `/positions` | Lista otvorenih pozicija s entry cijenom i smjerom |
| `/help` | Lista dostupnih komandi |
| _automatski_ | Dnevni report svaki dan u 20:00 UTC (22:00 tvoje vrijeme) — uključuje **entry_price_skipped** |

---

## Statistika (od 29.05.2026. — čisti podaci)

| Razlog | Tradovi | P&L |
|--------|---------|-----|
| take_profit | 3 | +$2.20 |
| stop_loss | 2 | -$1.36 |
| time_stop | 7 | -$0.93 |
| **UKUPNO** | **12** | **-$0.09** |

Win rate: 25% (3/12) — ispod cilja 52%. Parametri olabavljeni 10.06., entry price filter proširen na [0.05, 0.95].

---

## Dozvoljene/blokirane kategorije

**Dozvoljeno:** geopolitics, macro, politics, elections

**Blokirano (tagovi):** sports, nba, nfl, fifa, mma, boxing, crypto, cryptocurrency, entertainment, culture, celebrity

**Blokirano (keyword):** nba, nfl, fifa, nhl, mlb, world cup, champions league, 76ers, lakers, celtics, warriors, knicks, finals, playoff, super bowl, ufc, boxing, mma, wrestling

---

## Povijest fixeva

### Fix 1-15 — 26.03–01.04. ✅
WS fix, exit logika, cooldown, keyword filter, Telegram token, pnl_usd.

### Fix 16-19 — 29.05. ✅
Telegram token, pnl_usd kalkulacija, parametri (confidence 0.55, TP 0.08, SL 0.03), command handler.

### Fix 20-23 — 29.05. ✅
6-faktorski confidence scoring, RiskGuard, time-to-expiry filter, slippage 100bps.

### Fix 24 — 01.06. ✅
/status proširen: P&L split, win rate, risk status, signal info, countdown.

### Fix 25 — 10.06. ✅
Parametri olabavljeni: min_price_move 0.12→0.08, min_volume_multiple 2.0→1.5, confidence threshold 0.65→0.55.

### Fix 26 — 10.06. ✅
Entry price filter dodan: odbij signal ako entry_price izvan [0.10, 0.90]. Nova DB tablica `entry_price_rejections`.

### Fix 27 — 10.06. ✅
Entry price bounds prošireni: [0.10, 0.90] → [0.05, 0.95].

### Fix 28 — 10.06. ✅
/status: dodan prosječni holding time za zatvorene tradove od 29.05.
Dnevni report: dodan `entry_price_skipped` — broj signala odbijenih zbog entry cijene izvan raspona.

---

## Resetiranje pozicija (kad je max dostignut)

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "UPDATE positions SET status='closed' WHERE status='open';"
```

---

## Brza provjera P&L (VPS)

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT 'Open: ' || COUNT(*) FROM positions WHERE status='open'; SELECT 'Closed: ' || COUNT(*) || ' | PnL: $' || ROUND(SUM(CASE WHEN direction='fade_yes' THEN (entry_price - exit_price) * 100 ELSE (exit_price - entry_price) * 100 END), 2) FROM positions WHERE status='closed' AND exit_price IS NOT NULL AND opened_at >= '2026-05-29';"
```

---

## Deploy workflow

```bash
# Lokalno (laptop):
cd C:\ClaudeProjects\polymarket-bot
claude
git add -A && git commit -m "opis" && git push origin master

# Na VPS-u (SSH):
cd /root/polymarket-bot
git pull
systemctl restart polymarket-bot
```

---

## Dijagnostičke komande (VPS)

```bash
# Status:
systemctl status polymarket-bot

# Zašto nema signala:
journalctl -u polymarket-bot --since "1 hour ago" --no-pager | grep -E "signal|skip|entry_price" | tail -30

# Otvorene pozicije:
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT COUNT(*) FROM positions WHERE status='open';"

# Entry price rejections danas:
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT COUNT(*) FROM entry_price_rejections WHERE rejected_at >= date('now');"
```

---

## Sljedeći koraci

- [ ] Pratiti signale s novim entry price filterom i olabavljenim parametrima
- [ ] Cilj: 50+ čistih tradova, win rate > 52%, EV > 0
- [ ] Kelly Criterion + Bayesian scoring (@LunarResearcher)
- [ ] Faza 2: Random Forest model (@noisyb0y1)

---

## Kriterij za live micro-pilot

- [ ] Min. 50 paper tradova s pozitivnom expectancy (EV > 0) od 29.05.
- [ ] Win rate > 52%
- [ ] Max drawdown < 15% paper bankrolla
- [ ] Bot radi bez nadzora min. 14 dana bez kritičnih grešaka
- [ ] Telegram alertovi stižu pouzdano
- [ ] Dedicated Polygon wallet kreiran i testiran
