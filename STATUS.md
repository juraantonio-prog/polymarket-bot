# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 29.03.2026.

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

---

## Trenutni status

| | Stavka |
|-|--------|
| ✅ | Bot radi 24/7 na VPS-u |
| ✅ | systemd servis aktivan i enabled |
| ✅ | Telegram daily report stiže |
| ✅ | `config/markets.yaml` postoji |
| ✅ | Discovery: 85 tržišta prolazi filter |
| ✅ | WebSocket subscribed na 174 assets |
| ✅ | WS prima live price updateove (WS RAW potvrđen 29.03.) |
| ✅ | **30 dana paper trading sat kreće od 29.03.2026.** |
| ⏳ | Čekamo prvi spike-fade signal (12pp+ pomak) |
| ❌ | Sports tržišta prolaze filter (NBA Finals, FIFA World Cup) |
| ❌ | TP/SL bug za niske cijene (TP ispod entry za niske cijene) |

---

## Faza projekta

**Faza 1 — Paper trading** (aktivna od 29.03.2026.)

- Paper bankroll: $10,000
- Nominalni iznos po tradu: $100
- Max otvorenih pozicija: 4
- Live trading: **ONEMOGUĆEN**
- **Cilj: 50+ tradova do ~29.04.2026.**

---

## Povijest fixeva

### Fix 1 — 26.03.2026. ✅
`config/markets.yaml` nije postojao → kreiran, `min_volume_usd` spušten na $500k, kategorije proširene.

### Fix 2 — 26.03.2026. ✅
85 tržišta imalo prazan tag → untagged tržišta sad prolaze category filter.
Rezultat: `filtered: 85, Tracking 85 markets, assets: 170`

### Fix 3 — 29.03.2026. ✅
WS subscription tip `"market"` → `"Market"` (veliko M) — server prihvaćao ali nije slao podatke.

### Fix 4 — 29.03.2026. ✅
`ws.raw_message` prebačen s DEBUG na INFO + dodan `print()` za vidljivost.
Rezultat: live price updateovi potvrđeni u logovima.

---

## Poznati bugovi (sljedeći fix)

1. **Sports tržišta prolaze filter** — NBA Finals, FIFA World Cup prolaze jer nemaju tagove
   - Fix: keyword filter na name/slug (nba, nfl, fifa, world-cup, nhl, mlb, boxing, mma, ufc)

2. **TP/SL bug za niske cijene** — TP ispod entry cijene za tržišta s entry < 0.10
   - Fix: logika u `spike_fade.py`

---

## Deploy workflow

```bash
# Lokalno (laptop):
cd C:\ClaudeProjects\polymarket-bot
claude  # napravi izmjene
git add -A && git commit -m "opis" && git push origin master

# Na VPS-u (SSH):
cd /root/polymarket-bot
git pull
systemctl restart polymarket-bot
systemctl status polymarket-bot
```

---

## Dijagnostičke komande (VPS)

```bash
# Live logovi:
journalctl -u polymarket-bot -f | grep -E "raw_message|signal|spike|trade"

# Zadnjih 50 linija:
journalctl -u polymarket-bot -n 50 --no-pager

# Discovery test:
cd /root/polymarket-bot && source venv/bin/activate
python /root/polymarket-bot/cli/main.py discover-markets

# DB provjera:
sqlite3 /root/polymarket-bot/data/polymarket_bot.db "SELECT COUNT(*) FROM signals; SELECT COUNT(*) FROM trades;"
```

---

## Sljedeći koraci

- [ ] Fix sports keyword filter (NBA, FIFA prolaze)
- [ ] Fix TP/SL logika za niske cijene
- [ ] Pratiti prve signale na Telegramu
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
