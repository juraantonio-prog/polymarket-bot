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
| Telegram token | u `.env` kao `TELEGRAM_BOT_TOKEN` (token osvježen 29.05.) |
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
Telegram token istekao/revoked — zamijenjen novim tokenom u `.env` na VPS-u.

### Fix 17 — 29.05. ✅
pnl_usd kalkulacija koristila relativnu razliku umjesto apsolutne. `pnl_usd = size * (exit - entry)` — ispravno.

### Fix 18 — 29.05. ✅
Parametri zaošteni: confidence threshold 0.40→0.55, TP delta 0.06→0.08, SL delta 0.04→0.03.

### Fix 19 — 29.05. ✅
Telegram command handler dodan (`/status`, `/positions`, `/help`). Automatski dnevni report u 20:00 UTC. Handler radi kao background coroutine uz WS/exit/report loop.

---

## Resetiranje pozicija (kad je max dostignut)

```bash
/usr/bin/sqlite3 /root/polymarket-bot/data/polymarket.db "UPDATE positions SET status='closed' WHERE status='open';"
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
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage?chat_id=${TELEGRAM_CHAT_ID}&text=Test"
```

---

## Sljedeći koraci

- [ ] Potvrditi zatvaranje pozicija s P&L na Telegramu
- [ ] Pratiti daily report s nenultim tradovima
- [ ] Nakon 30 dana → Kelly Criterion, Bayesian scoring (@LunarResearcher)
- [ ] Faza 2: Random Forest model (@noisyb0y1)

---

## Kriterij za live micro-pilot

- [ ] Min. 50 paper tradova s pozitivnom expectancy (EV > 0)
- [ ] Win rate > 52%
- [ ] Max drawdown < 15% paper bankrolla
- [ ] Bot radi bez nadzora min. 14 dana bez kritičnih grešaka
- [ ] Telegram alertovi stižu pouzdano
- [ ] Dedicated Polygon wallet kreiran i testiran
