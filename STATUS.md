# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 11.06.2026.

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
| ✅ | Entry price filter: [0.05, 0.95] |
| ✅ | EV filtar: ulaz samo ako EV > 0 |
| ✅ | News shock filter: ne fadeati pomak > 15pp |
| ✅ | Telegram command handler: /status, /positions, /help |
| ✅ | /status: P&L split, win rate, avg hold time, risk status, kategorije, signali |
| ✅ | Dnevni report: expectancy/trade, profit factor, avg winner/loser |
| ✅ | Category parser ispravljen: sve tagove + category polje + keyword-map (11.06.) |
| ⏳ | Čekamo nove tradove s ispravnim kategorijama |

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
| Min. pomak cijene | 0.08 (8pp) |
| Rolling window | 300s (5 min) |
| Min. volume multiple | 1.5x |
| Min. market volume | $500,000 |
| Take profit | ±0.08 od entry |
| Stop loss | ∓0.03 od entry |
| Max hold | 2400s (40 min) |
| Min. confidence | 0.55 |
| EV filtar | EV > 0 obavezan |
| News shock filter | Ne fadeati pomak > 15pp |
| Entry price filter | [0.05, 0.95] |
| Cooldown per market | 900s (15 min) |
| Min. days to expiry | 30 dana |

---

## Telegram komande

| Komanda | Opis |
|---------|------|
| `/status` | P&L od 29.05. + ukupni + win rate + avg hold time + kategorije + risk status + signali + countdown |
| `/positions` | Lista otvorenih pozicija |
| `/help` | Lista komandi |
| _automatski_ | Dnevni report 20:00 UTC: expectancy/trade, profit factor, avg winner/loser |

---

## Statistika (od 29.05.2026.)

| Razlog | Tradovi | P&L |
|--------|---------|-----|
| take_profit | 3 | +$2.20 |
| stop_loss | 2 | -$1.36 |
| time_stop | 7 | -$0.93 |
| **UKUPNO** | **12** | **-$0.09** |

Win rate: 25% — ispod cilja 52%. Kategorije bile sve "other" zbog parser buga (fixed 11.06.).

---

## Povijest fixeva

### Fix 1-19 — 26.03–29.05. ✅
WS fix, exit logika, cooldown, keyword filter, Telegram token (×2), pnl_usd, parametri, command handler.

### Fix 20-23 — 29.05. ✅
6-faktorski confidence scoring, RiskGuard, time-to-expiry filter, slippage 100bps.

### Fix 24 — 01.06. ✅
/status proširen: P&L split, win rate, risk status, signal info, countdown.

### Fix 25-26 — 10.06. ✅
Entry price filter [0.05, 0.95]. Parametri olabavljeni: move 0.08, volume 1.5x.

### Fix 27 — 10.06. ✅
Kategorije u /status, expectancy report u dnevnom reportu, EV filtar, news shock filter (15pp).

### Fix 28 — 11.06. ✅
Category parser ispravljen — sve padalo na "other" jer je čitao samo prvi tag.
Nova funkcija `resolve_market_category()` u `gamma_client.py`: parsira `category` polje + sve tagove, exact-match na `_CANONICAL` set → keyword-map (40+ ključnih riječi) → fallback "other". Dodan `crypto` i `sports` u `category_weights`/`category_priorities` u `strategy.yaml`.

---

## Resetiranje pozicija

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "UPDATE positions SET status='closed' WHERE status='open';"
```

---

## Brza provjera P&L

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT 'Open: ' || COUNT(*) FROM positions WHERE status='open'; SELECT 'Closed: ' || COUNT(*) || ' | PnL: $' || ROUND(SUM(CASE WHEN direction='fade_yes' THEN (entry_price - exit_price) * 100 ELSE (exit_price - entry_price) * 100 END), 2) FROM positions WHERE status='closed' AND exit_price IS NOT NULL AND opened_at >= '2026-05-29';"
```

---

## Deploy workflow

```bash
# Lokalno:
cd C:\ClaudeProjects\polymarket-bot
claude
git add -A && git commit -m "opis" && git push origin master

# VPS:
cd /root/polymarket-bot && git pull && systemctl restart polymarket-bot
```

---

## Dijagnostičke komande

```bash
systemctl status polymarket-bot
journalctl -u polymarket-bot --since "1 hour ago" --no-pager | grep -E "signal|skip|category" | tail -30
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT COUNT(*) FROM positions WHERE status='open';"
```

---

## Sljedeći koraci

- [ ] Pratiti kategorije u /status — gdje je edge?
- [ ] Skupiti 50+ čistih tradova za validnu statistiku
- [ ] Ako win rate ostane < 52% do kraja lipnja → razmotriti pivot strategije
- [ ] Kelly Criterion + Bayesian scoring (Faza 2)
- [ ] Random Forest model (Faza 2)

---

## Kriterij za live micro-pilot

- [ ] Min. 50 tradova s EV > 0 od 29.05.
- [ ] Win rate > 52%
- [ ] Max drawdown < 15%
- [ ] Bot stabilan 14+ dana
- [ ] Polygon wallet kreiran
