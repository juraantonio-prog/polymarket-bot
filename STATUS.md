# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 01.06.2026.

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
| ✅ | Cooldown 300s per market |
| ✅ | Sports/crypto/entertainment blokirani po keyword filteru |
| ✅ | pnl_usd kalkulacija ispravljena (29.05.) |
| ✅ | 6-faktorski confidence scoring normaliziran [0.0, 1.0] (29.05.) |
| ✅ | RiskGuard: max $250 dnevni gubitak, 4 uzastopna gubitka → 2h cooldown (29.05.) |
| ✅ | Time-to-expiry filter: min 30 dana do isteka (29.05.) |
| ✅ | Telegram command handler: /status, /positions, /help (29.05.) |
| ✅ | Automatski dnevni report u 20:00 UTC |
| ✅ | /status prikazuje P&L od 29.05. + ukupni P&L + win rate + risk status + signal info (01.06.) |

---

## Faza projekta

**Faza 1 — Paper trading** (aktivna od 29.03.2026.)

- Paper bankroll: $10,000
- Nominalni iznos po tradu: $100
- Max otvorenih pozicija: 5
- Cooldown per market: 300s (5 min)
- Live trading: **ONEMOGUĆEN**
- Pouzdana statistika kreće od: **29.05.2026.**

---

## Strategija (spike-fade)

| Parametar | Vrijednost |
|-----------|-----------|
| Min. pomak cijene | 12pp (spec v2.0) |
| Rolling window | 300s (5 min) |
| Volume filter | min_volume_multiple: 2.0x |
| Min. market volume | $500,000 |
| Take profit | ±0.08 od entry |
| Stop loss | ∓0.03 od entry |
| Max hold | 2400s (40 min) |
| Min. confidence | 0.65 (6-faktorski model) |
| Cooldown per market | 900s (15 min) |
| Min. days to expiry | 30 dana |
| Exit check interval | 30s |

---

## Confidence scoring (6 faktora, sve [0.0, 1.0])

| Faktor | Formula | Weight |
|--------|---------|--------|
| price_move_strength | clamp((move - 0.12) / 0.08, 0, 1) | 0.30 |
| volume_spike_strength | clamp((vol_mult - 2.0) / 3.0, 0, 1) | 0.20 |
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
| `/status` | P&L od 29.05. + ukupni P&L + win rate + tradovi danas + risk status + signali + countdown do reporta |
| `/positions` | Lista otvorenih pozicija s entry cijenom i smjerom |
| `/help` | Lista dostupnih komandi |
| _automatski_ | Dnevni report svaki dan u 20:00 UTC |

---

## Statistika (podaci do 29.05. — djelomično nepouzdani)

| Razlog | Tradovi | Ukupni P&L | Avg P&L |
|--------|---------|------------|---------|
| stop_loss | 110 | -$2,958 | -$26.9 |
| take_profit | 87 | +$2,908 | +$33.4 |
| time_stop | 41 | +$90 | +$2.2 |
| **UKUPNO** | **238** | **+$39** | — |

_Pouzdana statistika kreće od 29.05.2026. — koristiti /status za čiste podatke._

---

## Dozvoljene/blokirane kategorije

**Dozvoljeno:** geopolitics, macro, politics, elections

**Blokirano (tagovi):** sports, nba, nfl, fifa, mma, boxing, crypto, cryptocurrency, entertainment, culture, celebrity

**Blokirano (keyword):** nba, nfl, fifa, nhl, mlb, world cup, champions league, 76ers, lakers, celtics, warriors, knicks, finals, playoff, super bowl, ufc, boxing, mma, wrestling

---

## Povijest fixeva

### Fix 1-4 — 26-29.03. ✅
markets.yaml kreiran, WS subscription tip ispravljen, price updateovi potvrđeni.

### Fix 5-7 — 30.03. ✅
Deque overflow, volume filter bug, spike threshold 12pp→8pp.

### Fix 8-9 — 31.03. ✅
Vol_spike filter, confidence threshold lanac (paper_engine→telegram).

### Fix 10 — 31.03. ✅
spike_fade.signal nije pozivao paper_engine — ispravan await lanac.

### Fix 11 — 31.03. ✅
Telegram chat_id minus uklonjen.

### Fix 12 — 31.03. ✅
Cooldown 300s per market implementiran.

### Fix 13 — 31.03. ✅
Crypto/entertainment/sports keyword filter dodan.

### Fix 14 — 01.04. ✅
Exit logika nije radila — token_to_market mapping fix.

### Fix 15 — 01.04. ✅
Telegram token revoked i zamijenjen novim.

### Fix 16 — 29.05. ✅
Telegram token opet zamijenjen.

### Fix 17 — 29.05. ✅
pnl_usd kalkulacija ispravljena — apsolutna razlika cijena × 100.

### Fix 18 — 29.05. ✅
Parametri podešeni: confidence 0.55, TP 0.08, SL 0.03.

### Fix 19 — 29.05. ✅
Telegram command handler dodan: /status, /positions, /help + dnevni report 20:00 UTC.

### Fix 20 — 29.05. ✅
6-faktorski confidence scoring normaliziran na [0.0, 1.0] prema specu v2.0.

### Fix 21 — 29.05. ✅
RiskGuard implementiran: max $250 dnevni gubitak, 4 uzastopna gubitka → 2h cooldown.

### Fix 22 — 29.05. ✅
Time-to-expiry filter: odbij tržišta s <30 dana do isteka. Caution zone: 14 dana.

### Fix 23 — 29.05. ✅
Slippage 100 bps potvrđen u paper_engine.

### Fix 24 — 01.06. ✅
/status proširen: P&L od 29.05. + ukupni P&L + win rate + tradovi danas + risk status (dnevni gubitak, uzastopni gubici, cooldown) + signal info + countdown do dnevnog reporta.

---

## Resetiranje pozicija (kad je max dostignut)

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "UPDATE positions SET status='closed' WHERE status='open';"
```

---

## Brza provjera P&L (VPS)

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT 'Open: ' || COUNT(*) FROM positions WHERE status='open'; SELECT 'Closed: ' || COUNT(*) || ' | PnL: $' || ROUND(SUM(CASE WHEN direction='fade_yes' THEN (entry_price - exit_price) * 100 ELSE (exit_price - entry_price) * 100 END), 2) FROM positions WHERE status='closed' AND exit_price IS NOT NULL;"
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

# Signali i pozicije:
journalctl -u polymarket-bot --since "30 min ago" --no-pager | grep -E "SIGNAL|paper\.|exit|closed" | tail -20

# Otvorene pozicije:
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "SELECT COUNT(*) FROM positions WHERE status='open';"

# Zašto nema signala:
journalctl -u polymarket-bot --since "1 hour ago" --no-pager | grep -E "no_signal|confidence|magnitude" | tail -20
```

---

## Sljedeći koraci

- [ ] Pratiti P&L od 29.05. putem /status na Telegramu
- [ ] Čekati 2-4 tjedna čistih podataka (cilj: 50+ tradova)
- [ ] Cilj: win rate > 52%, EV > 0
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
