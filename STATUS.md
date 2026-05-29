# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 29.05.2026.

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
| Telegram token | u `.env` kao `TELEGRAM_BOT_TOKEN` (token zamijenjen 02.04. i 29.05.) |
| Telegram chat_id | u `.env` kao `TELEGRAM_CHAT_ID` (bez minusa — private chat) |
| Telegram bot | @pm_alfa_bot (PolymarketAlpha) |

---

## Trenutni status

| | Stavka |
|-|--------|
| ✅ | Bot radi 24/7 na VPS-u |
| ✅ | systemd servis aktivan i enabled |
| ✅ | Telegram alertovi rade (token osvježen 29.05.) |
| ✅ | WebSocket prima live price updateove |
| ✅ | Signal detection radi |
| ✅ | Paper engine otvara pozicije |
| ✅ | Exit logika implementirana (TP/SL/timeout svakih 30s) |
| ✅ | Cooldown 300s per market |
| ✅ | Sports/crypto/entertainment blokirani po keyword filteru |
| ✅ | pnl_usd kalkulacija ispravljena (29.05.) |
| ✅ | Telegram command handler implementiran (/status, /positions, /help) |
| ✅ | Automatski dnevni report u 20:00 UTC |
| ✅ | **239 zatvorenih tradova, P&L: +$39.45** |

---

## Faza projekta

**Faza 1 — Paper trading** (aktivna od 29.03.2026.)

- Paper bankroll: $10,000
- Nominalni iznos po tradu: $100
- Max otvorenih pozicija: 5
- Cooldown per market: 300s (5 min)
- Live trading: **ONEMOGUĆEN**
- **239 tradova zatvoreno do 29.05.2026.**

---

## Strategija (spike-fade)

| Parametar | Vrijednost |
|-----------|-----------|
| Min. pomak cijene | 8pp |
| Rolling window | 600s (10 min) |
| Volume filter | market_volume_usd iz Gamma API |
| Min. market volume | $500,000 |
| Take profit | ±0.08 od entry _(promijenjeno 29.05.)_ |
| Stop loss | ∓0.03 od entry _(promijenjeno 29.05.)_ |
| Max hold | 2400s (40 min) |
| Min. confidence | 0.55 _(promijenjeno 29.05.)_ |
| Exit check interval | 30s |

---

## Telegram komande

| Komanda | Opis |
|---------|------|
| `/status` | Status bota, broj otvorenih/zatvorenih pozicija, ukupni P&L |
| `/positions` | Lista otvorenih pozicija s entry cijenom i smjerom |
| `/help` | Lista dostupnih komandi |
| _automatski_ | Dnevni report svaki dan u 20:00 UTC |

---

## Statistika (29.05.2026.)

| Razlog | Tradovi | Ukupni P&L | Avg P&L |
|--------|---------|------------|---------|
| stop_loss | 110 | -$2,958 | -$26.9 |
| take_profit | 87 | +$2,908 | +$33.4 |
| time_stop | 41 | +$90 | +$2.2 |
| **UKUPNO** | **238** | **+$39** | — |

_Napomena: rani tradovi imaju nepouzdane iznose zbog pnl_usd buga koji je ispravljen 29.05. Pouzdana statistika kreće od tog datuma._

---

## Dozvoljene/blokirane kategorije

**Dozvoljeno:** geopolitics, macro, politics, elections

**Blokirano (tagovi):** sports, nba, nfl, fifa, mma, boxing, crypto, cryptocurrency, entertainment, culture, celebrity

**Blokirano (keyword u imenu/slugu):** nba, nfl, fifa, nhl, mlb, world cup, champions league, 76ers, lakers, celtics, warriors, knicks, finals, playoff, super bowl, ufc, boxing, mma, wrestling

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
Telegram chat_id minus uklonjen (-8731364432 → 8731364432).

### Fix 12 — 31.03. ✅
Cooldown 300s per market implementiran.

### Fix 13 — 31.03. ✅
Crypto/entertainment/sports keyword filter dodan.

### Fix 14 — 01.04. ✅
**Exit logika nije radila** — `exit_loop` gradio prices keyed by token_id, ali `check_exits` tražio market_id (conditionId). Nikad matchalo → pozicije ostajale zauvijek open → max 5 popunjeno → 0 novih tradova.
Fix: `token_to_market` mapping, prices dict keyed by market_id.

### Fix 15 — 01.04. ✅
Telegram token revoked i zamijenjen novim (stari davao 401 Unauthorized).

### Fix 16 — 29.05. ✅
Telegram token opet revoked — zamijenjen novim token za @pm_alfa_bot.

### Fix 17 — 29.05. ✅
**pnl_usd kalkulacija bila kriva** — dijelila s entry cijenom što je amplificiralo P&L za niske cijene (0.03 entry → 200x amplifikacija). Fix: pnl_pct = apsolutna razlika cijena (entry - exit_price), pnl_usd = size * pnl_pct. TP sada daje ~+$8, SL ~-$3.

### Fix 18 — 29.05. ✅
**Parametri podešeni** za bolju kvalitetu signala: confidence 0.40→0.55, TP 0.06→0.08, SL 0.04→0.03.

### Fix 19 — 29.05. ✅
**Telegram command handler** dodan (`src/alerts/command_handler.py`). Komande: /status, /positions, /help. Automatski dnevni report u 20:00 UTC.

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

# Telegram test:
curl -s "https://api.telegram.org/bot8581641008:AAFgqnexOa8nagl99ZE5zCvBh5VVtXJxbvE/getMe"

# Zašto nema signala:
journalctl -u polymarket-bot --since "1 hour ago" --no-pager | grep -E "no_signal|confidence|magnitude" | tail -20
```

---

## Sljedeći koraci

- [ ] Pratiti novi P&L s ispravnom kalkulacijom (od 29.05.)
- [ ] Čekati 2-4 tjedna čistih podataka za validnu statistiku
- [ ] Cilj: win rate > 52%, EV > 0
- [ ] Nakon dovoljno čistih tradova → Kelly Criterion, Bayesian scoring (@LunarResearcher)
- [ ] Faza 2: Random Forest model (@noisyb0y1)

---

## Kriterij za live micro-pilot

- [ ] Min. 50 paper tradova s pozitivnom expectancy (EV > 0) — s čistim podacima od 29.05.
- [ ] Win rate > 52%
- [ ] Max drawdown < 15% paper bankrolla
- [ ] Bot radi bez nadzora min. 14 dana bez kritičnih grešaka
- [ ] Telegram alertovi stižu pouzdano
- [ ] Dedicated Polygon wallet kreiran i testiran
